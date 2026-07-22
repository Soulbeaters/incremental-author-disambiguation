"""Resume-safe Semantic Scholar enrichment for the public development data.

The CLI defaults to one deterministic batch.  Raw public API records are
cached under the caller-selected ignored directory; stdout contains only one
aggregate line and never includes a DOI, title, author, or embedding.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Iterable, Mapping, Sequence

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.audit_crossref_s2and_coverage import iter_json_records, sha256_file


ENDPOINT = "https://api.semanticscholar.org/graph/v1/paper/batch"
FIELDS = (
    "externalIds,title,abstract,year,venue,journal,publicationVenue,authors,"
    "embedding.specter_v2"
)
MAX_BATCH_SIZE = 500
DEFAULT_API_KEY_ENV = "SEMANTIC_SCHOLAR_API_KEY"


def normalize_doi(value: Any) -> str:
    doi = str(value or "").strip().casefold()
    for prefix in (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "doi:",
    ):
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
            break
    return doi.strip()


def load_distinct_dois(path: Path) -> list[str]:
    dois: set[str] = set()
    with path.open("r", encoding="utf-8-sig") as handle:
        for row in iter_json_records(handle):
            if not isinstance(row, Mapping):
                continue
            doi = normalize_doi(row.get("doi"))
            if doi:
                dois.add(doi)
    return sorted(
        dois,
        key=lambda doi: (hashlib.sha256(doi.encode("utf-8")).digest(), doi),
    )


def batches(values: Sequence[str], size: int) -> Iterable[tuple[int, list[str]]]:
    if not 1 <= size <= MAX_BATCH_SIZE:
        raise ValueError(f"batch size must be within 1..{MAX_BATCH_SIZE}")
    for start in range(0, len(values), size):
        yield start // size, list(values[start:start + size])


def _batch_digest(dois: Sequence[str]) -> str:
    return hashlib.sha256("\n".join(dois).encode("utf-8")).hexdigest()


def _cache_path(output_dir: Path, batch_index: int, digest: str) -> Path:
    return output_dir / f"batch_{batch_index:05d}_{digest[:16]}.json.gz"


def _legacy_cache_path(output_dir: Path, batch_index: int, digest: str) -> Path:
    return output_dir / f"batch_{batch_index:05d}_{digest[:16]}.json"


def _read_cache(path: Path) -> dict[str, Any]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid cache object: {path.name}")
    return payload


def _write_cache(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(temporary, "wt", encoding="utf-8", compresslevel=6) as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    os.replace(temporary, path)


def _validate_response(payload: Any, expected: int) -> list[Any]:
    if not isinstance(payload, list) or len(payload) != expected:
        raise ValueError("Semantic Scholar batch response has an unexpected shape")
    return payload


def fetch_batch(
    session: requests.Session,
    dois: Sequence[str],
    *,
    api_key: str | None,
    max_retries: int = 4,
    timeout_seconds: float = 90.0,
) -> list[Any]:
    headers = {
        "User-Agent": "Project2-Author-Disambiguation-Research/0.1",
        "Content-Type": "application/json",
    }
    if api_key:
        headers["x-api-key"] = api_key
    identifiers = ["DOI:" + doi for doi in dois]
    for attempt in range(max_retries + 1):
        response = session.post(
            ENDPOINT,
            params={"fields": FIELDS},
            json={"ids": identifiers},
            headers=headers,
            timeout=(10.0, timeout_seconds),
        )
        if response.status_code == 200:
            return _validate_response(response.json(), len(dois))
        if response.status_code not in {429, 500, 502, 503, 504} or attempt >= max_retries:
            raise RuntimeError(
                f"Semantic Scholar request failed with HTTP {response.status_code}"
            )
        retry_after = response.headers.get("Retry-After")
        delay = float(retry_after) if retry_after else min(2 ** attempt, 16)
        time.sleep(max(1.0, min(delay, 30.0)))
    raise AssertionError("unreachable retry state")


def aggregate_rows(rows: Sequence[Any]) -> dict[str, int]:
    matched = 0
    with_title = 0
    with_abstract = 0
    with_venue = 0
    with_authors = 0
    with_specter2 = 0
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        matched += 1
        with_title += int(bool(row.get("title")))
        with_abstract += int(bool(row.get("abstract")))
        with_venue += int(
            bool(row.get("venue") or row.get("journal") or row.get("publicationVenue"))
        )
        with_authors += int(bool(row.get("authors")))
        embedding = row.get("embedding")
        vector = embedding.get("vector") if isinstance(embedding, Mapping) else None
        with_specter2 += int(isinstance(vector, list) and len(vector) == 768)
    return {
        "matched": matched,
        "with_title": with_title,
        "with_abstract": with_abstract,
        "with_venue": with_venue,
        "with_authors": with_authors,
        "with_specter2": with_specter2,
    }


def _merge_counts(target: dict[str, int], source: Mapping[str, int]) -> None:
    for key, value in source.items():
        target[key] = target.get(key, 0) + int(value)


def run(
    *,
    authors_path: Path,
    output_dir: Path,
    batch_size: int,
    max_new_batches: int,
    min_interval_seconds: float,
    api_key: str | None,
    session: requests.Session,
) -> dict[str, Any]:
    if max_new_batches < 0:
        raise ValueError("max_new_batches must be non-negative")
    output_dir.mkdir(parents=True, exist_ok=True)
    dois = load_distinct_dois(authors_path)
    totals: dict[str, int] = {
        "requested": 0,
        "matched": 0,
        "with_title": 0,
        "with_abstract": 0,
        "with_venue": 0,
        "with_authors": 0,
        "with_specter2": 0,
    }
    cached_batches = 0
    new_batches = 0
    last_request_started: float | None = None
    for batch_index, batch_dois in batches(dois, batch_size):
        digest = _batch_digest(batch_dois)
        cache_path = _cache_path(output_dir, batch_index, digest)
        readable_cache = cache_path
        if not readable_cache.is_file():
            readable_cache = _legacy_cache_path(output_dir, batch_index, digest)
        if readable_cache.is_file():
            cache = _read_cache(readable_cache)
            if cache.get("doi_digest") != digest:
                raise ValueError(f"cache digest mismatch for batch {batch_index}")
            rows = _validate_response(cache.get("rows"), len(batch_dois))
            if readable_cache != cache_path and not cache_path.exists():
                _write_cache(cache_path, cache)
                readable_cache.unlink()
            cached_batches += 1
        else:
            if max_new_batches and new_batches >= max_new_batches:
                break
            if last_request_started is not None:
                remaining = min_interval_seconds - (time.monotonic() - last_request_started)
                if remaining > 0:
                    time.sleep(remaining)
            last_request_started = time.monotonic()
            rows = fetch_batch(session, batch_dois, api_key=api_key)
            cache = {
                "schema_version": "project2_semantic_scholar_batch_v1",
                "doi_digest": digest,
                "requested": len(batch_dois),
                "fields": FIELDS,
                "rows": rows,
            }
            _write_cache(cache_path, cache)
            new_batches += 1
        totals["requested"] += len(batch_dois)
        _merge_counts(totals, aggregate_rows(rows))

    manifest = {
        "schema_version": "project2_semantic_scholar_enrichment_v1",
        "source_file": authors_path.name,
        "source_sha256": sha256_file(authors_path),
        "distinct_dois": len(dois),
        "batch_size": batch_size,
        "cached_batches": cached_batches,
        "new_batches": new_batches,
        "api_key_used": bool(api_key),
        "fields": FIELDS,
        "aggregate": totals,
        "contains_record_values": False,
    }
    (output_dir / "aggregate_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authors", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=MAX_BATCH_SIZE)
    parser.add_argument(
        "--max-new-batches",
        type=int,
        default=1,
        help="0 means all remaining batches; default is one safe probe batch",
    )
    parser.add_argument("--min-interval-seconds", type=float, default=1.1)
    parser.add_argument("--api-key-env", default=DEFAULT_API_KEY_ENV)
    args = parser.parse_args()

    api_key = os.environ.get(args.api_key_env) or None
    with requests.Session() as session:
        manifest = run(
            authors_path=args.authors,
            output_dir=args.output_dir,
            batch_size=args.batch_size,
            max_new_batches=args.max_new_batches,
            min_interval_seconds=max(1.0, args.min_interval_seconds),
            api_key=api_key,
            session=session,
        )
    aggregate = manifest["aggregate"]
    print(
        "semantic_scholar_enrichment "
        f"new_batches={manifest['new_batches']} "
        f"requested={aggregate['requested']} "
        f"matched={aggregate['matched']} "
        f"specter2={aggregate['with_specter2']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
