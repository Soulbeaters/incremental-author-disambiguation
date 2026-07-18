"""Production-oriented ISTINA author-disambiguation pipeline.

The pipeline keeps the validated layers in one runtime path:

1. local Fellegi-Sunter three-way decision;
2. conservative structured-name/coauthor repair;
3. optional legacy-service fallback for unresolved local UNKNOWN decisions.

It is deliberately side-effect free. Callers decide whether and how to apply a
MERGE or NEW result to ISTINA after inspecting the returned audit fields.
"""

from __future__ import annotations

import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from disambiguation_engine.author_merger import AuthorMerger
from disambiguation_engine.decision_trace import DecisionTraceLogger
from disambiguation_engine.decision_types import Decision, DecisionResult
from disambiguation_engine.structured_name_repair import (
    RepairProfileIndex,
    StructuredRepairDecision,
    build_repair_profiles,
    compatible_structured_author_ids,
    decide_strict_name_repair,
    decide_structured_repair,
    decide_unique_non_cjk_initial_repair,
    structured_name_parts,
)
from disambiguation_engine.surname_risk import is_high_risk_surname
from integrations.istina_disambiguation_client import IstinaDisambiguationClient
from models.author import Author
from models.database import AuthorDatabase


def external_author_id(record: Mapping[str, Any]) -> str:
    for key in ("gold_author_id", "author_id", "id"):
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def mention_payload(mention: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "name": str(mention.get("name") or ""),
        "surname": str(mention.get("lastname") or mention.get("last_name") or ""),
        "firstname": str(mention.get("firstname") or mention.get("first_name") or ""),
        "orcid": str(mention.get("orcid") or ""),
        "coauthors": list(mention.get("coauthors") or []),
        "journals": [mention["journal"]] if mention.get("journal") else [],
        "affiliation": [mention["affiliation"]] if mention.get("affiliation") else [],
    }


def _index_alias(database: AuthorDatabase, author: Author, alias: str) -> None:
    alias = str(alias or "").strip()
    if not alias:
        return
    surname = database._extract_surname(alias)
    if surname:
        database.blocking_key_index[f"surname:{surname.lower()}"].append(author)
    surname_initial = database._extract_surname_initial(alias)
    if surname_initial:
        database.blocking_key_index[f"surname_init:{surname_initial}"].append(author)


def _index_structured_name(
    database: AuthorDatabase,
    author: Author,
    lastname: str,
    firstname: str,
) -> None:
    lastname = str(lastname or "").strip()
    firstname = str(firstname or "").strip()
    if not lastname:
        return
    database.blocking_key_index[f"surname:{lastname.lower()}"].append(author)
    if firstname:
        database.blocking_key_index[
            f"surname_init:{lastname.lower()}_{firstname[0].lower()}"
        ].append(author)


@dataclass
class IstinaHistoryState:
    database: AuthorDatabase
    external_to_database_id: Dict[str, str]
    repair_profiles: RepairProfileIndex

    @property
    def database_to_external_id(self) -> Dict[str, str]:
        return {
            database_id: external_id
            for external_id, database_id in self.external_to_database_id.items()
        }

    @property
    def quarantined_author_ids(self) -> frozenset[str]:
        return frozenset(self.repair_profiles.quarantined_author_ids)


def build_istina_history_state(
    history_mentions: Iterable[Mapping[str, Any]],
    index_aliases: bool = True,
) -> IstinaHistoryState:
    """Build the exact local state used by evaluation and production replay."""

    rows = [dict(mention) for mention in history_mentions]
    repair_profiles = build_repair_profiles(rows)
    quarantined = set(repair_profiles.quarantined_author_ids)
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for mention in rows:
        author_id = external_author_id(mention)
        if author_id and mention.get("name"):
            grouped[author_id].append(mention)

    database = AuthorDatabase()
    external_to_database_id: Dict[str, str] = {}
    for author_id, mentions in sorted(grouped.items()):
        names = [str(mention["name"]) for mention in mentions if mention.get("name")]
        canonical_name = Counter(names).most_common(1)[0][0]
        author = database.add_author({
            "name": canonical_name,
            "coauthors": sorted({
                str(coauthor)
                for mention in mentions
                for coauthor in mention.get("coauthors") or []
                if str(coauthor or "").strip()
            }),
            "journals": sorted({
                str(mention["journal"])
                for mention in mentions
                if mention.get("journal")
            }),
            "affiliation": sorted({
                str(mention["affiliation"])
                for mention in mentions
                if mention.get("affiliation")
            }),
        })
        external_to_database_id[author_id] = author.author_id

        # Conflicting historical identities remain addressable but their
        # aliases are not allowed to expand automatic blocking coverage.
        if index_aliases and author_id not in quarantined:
            for mention in mentions:
                author.add_alternate_name(str(mention["name"]))
                _index_alias(database, author, str(mention["name"]))
                _index_structured_name(
                    database,
                    author,
                    str(mention.get("lastname") or mention.get("last_name") or ""),
                    str(mention.get("firstname") or mention.get("first_name") or ""),
                )

    return IstinaHistoryState(
        database=database,
        external_to_database_id=external_to_database_id,
        repair_profiles=repair_profiles,
    )


@dataclass(frozen=True)
class IstinaPipelineConfig:
    mode: str = "fs"
    accept_threshold: float = -0.5
    reject_threshold: float = -4.0
    min_accept_margin: float = 1e-9
    require_context_for_low_name_accept: bool = True
    topk: int = 5
    service_fallback_min_name_similarity: float = 0.85
    use_remote_fallback: bool = True
    enable_strict_name_repair: bool = True
    enable_unique_non_cjk_initial_repair: bool = True
    require_strong_context_for_weak_name_accept: bool = True
    dense_name_candidate_limit: int = 5
    run_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.mode not in {"baseline", "fs"}:
            raise ValueError("mode must be 'baseline' or 'fs'")
        if self.dense_name_candidate_limit < 1:
            raise ValueError("dense_name_candidate_limit must be positive")
        if self.reject_threshold >= self.accept_threshold:
            raise ValueError("reject_threshold must be below accept_threshold")
        if self.topk <= 0:
            raise ValueError("topk must be positive")
        if not 0.0 <= self.service_fallback_min_name_similarity <= 1.0:
            raise ValueError("service fallback name similarity must be within [0, 1]")


@dataclass(frozen=True)
class IstinaPipelineDecision:
    decision: Decision
    author_id: Optional[str]
    stage: str
    reason: str
    base_decision: Decision
    local_score: float
    candidate_count: int
    topk: Tuple[Dict[str, Any], ...] = field(default_factory=tuple)
    structured_relation: Optional[str] = None
    structured_coauthor_jaccard: float = 0.0
    legacy_result_id: Optional[str] = None
    legacy_candidate_count: int = 0
    legacy_agrees: Optional[bool] = None
    service_error: Optional[str] = None
    latency_ms: float = 0.0
    deterministic_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision.value,
            "author_id": self.author_id,
            "stage": self.stage,
            "reason": self.reason,
            "base_decision": self.base_decision.value,
            "local_score": self.local_score,
            "candidate_count": self.candidate_count,
            "topk": list(self.topk),
            "structured_relation": self.structured_relation,
            "structured_coauthor_jaccard": self.structured_coauthor_jaccard,
            "legacy_result_id": self.legacy_result_id,
            "legacy_candidate_count": self.legacy_candidate_count,
            "legacy_agrees": self.legacy_agrees,
            "service_error": self.service_error,
            "latency_ms": self.latency_ms,
            "deterministic_hash": self.deterministic_hash,
        }


def _exported_author_name(author: Mapping[str, Any]) -> str:
    original = str(author.get("original_name") or author.get("name") or "").strip()
    if original:
        return original
    return " ".join(
        part for part in (
            str(author.get("lastname") or author.get("last_name") or "").strip(),
            str(author.get("firstname") or author.get("first_name") or "").strip(),
            str(author.get("middlename") or author.get("middle_name") or "").strip(),
        )
        if part
    )


def article_mentions(
    article: Mapping[str, Any],
    article_index: Optional[int] = None,
) -> List[Dict[str, Any]]:
    authors = list(article.get("authors") or [])
    article_id = str(
        article.get("id")
        or article.get("article_id")
        or article.get("doi")
        or article_index
        or "unknown"
    )
    names = [_exported_author_name(author) for author in authors]
    mentions = []
    for fallback_position, (author, name) in enumerate(zip(authors, names), start=1):
        mentions.append({
            "article": dict(article),
            "author": dict(author),
            "article_index": article_index,
            "article_id": article_id,
            "position": author.get("position") or fallback_position,
            "name": name,
            "lastname": str(author.get("lastname") or author.get("last_name") or "").strip(),
            "firstname": str(author.get("firstname") or author.get("first_name") or "").strip(),
            "middlename": str(author.get("middlename") or author.get("middle_name") or "").strip(),
            "coauthors": [
                other_name
                for index, other_name in enumerate(names)
                if index != fallback_position - 1 and other_name and other_name != name
            ],
            "journal": article.get("journal") or article.get("venue") or "",
            "affiliation": author.get("affiliation") or "",
            "year": article.get("year"),
            "orcid": author.get("orcid") or "",
        })
    return mentions


def service_response_for_position(
    response: Mapping[str, Any],
    position_index: int,
) -> Optional[Dict[str, Any]]:
    result_ids = list(response.get("result_id") or [])
    if position_index >= len(result_ids):
        return None
    candidate_groups = list(response.get("authors") or [])
    parsed_names = list(response.get("authors_names") or [])
    return {
        "result_id": [result_ids[position_index]],
        "authors": [
            candidate_groups[position_index]
            if position_index < len(candidate_groups)
            else []
        ],
        "authors_names": [
            parsed_names[position_index]
            if position_index < len(parsed_names)
            else None
        ],
    }


class IstinaDisambiguationPipeline:
    """Side-effect-free runtime pipeline suitable for ISTINA shadow use."""

    def __init__(
        self,
        history_state: IstinaHistoryState,
        config: Optional[IstinaPipelineConfig] = None,
        service_client: Optional[IstinaDisambiguationClient] = None,
        trace_logger: Optional[DecisionTraceLogger] = None,
        surname_risk_checker: Optional[Callable[[str], bool]] = None,
    ) -> None:
        self.history_state = history_state
        self.config = config or IstinaPipelineConfig()
        self.service_client = service_client
        self.trace_logger = trace_logger
        self._database_to_external = history_state.database_to_external_id
        self._known_external_ids = set(history_state.external_to_database_id)
        self._quarantined = set(history_state.quarantined_author_ids)
        self._merger = AuthorMerger(
            database=history_state.database,
            mode=self.config.mode,
            accept_threshold=self.config.accept_threshold,
            reject_threshold=self.config.reject_threshold,
            min_accept_margin=self.config.min_accept_margin,
            require_context_for_low_name_accept=(
                self.config.require_context_for_low_name_accept
            ),
            topk=self.config.topk,
            run_id=self.config.run_id,
        )
        name_module = getattr(self._merger.scorer, "chinese_name_module", None)
        external_checker = getattr(name_module, "is_known_surname", None)
        supplied_checker = surname_risk_checker or external_checker
        if callable(supplied_checker):
            self._surname_risk_checker = lambda surname: (
                is_high_risk_surname(surname) or bool(supplied_checker(surname))
            )
        else:
            self._surname_risk_checker = is_high_risk_surname

    @classmethod
    def from_history_mentions(
        cls,
        history_mentions: Iterable[Mapping[str, Any]],
        config: Optional[IstinaPipelineConfig] = None,
        service_client: Optional[IstinaDisambiguationClient] = None,
        trace_logger: Optional[DecisionTraceLogger] = None,
        index_aliases: bool = True,
        surname_risk_checker: Optional[Callable[[str], bool]] = None,
    ) -> "IstinaDisambiguationPipeline":
        return cls(
            build_istina_history_state(history_mentions, index_aliases=index_aliases),
            config=config,
            service_client=service_client,
            trace_logger=trace_logger,
            surname_risk_checker=surname_risk_checker,
        )

    def _external_topk(self, local_result: DecisionResult) -> Tuple[Dict[str, Any], ...]:
        external = []
        for candidate in local_result.topk:
            author_id = self._database_to_external.get(str(candidate.get("author_id")))
            if not author_id or author_id in self._quarantined:
                continue
            item = dict(candidate)
            item["author_id"] = author_id
            external.append(item)
        return tuple(external)

    @staticmethod
    def _legacy_observation(
        response: Optional[Mapping[str, Any]],
    ) -> Tuple[Optional[str], int]:
        if not response:
            return None, 0
        result_ids = list(response.get("result_id") or [])
        result_id = str(result_ids[0]) if result_ids else None
        groups = list(response.get("authors") or [])
        candidate_count = len(groups[0] or []) if groups else 0
        return result_id, candidate_count

    def decide_mention(
        self,
        mention: Mapping[str, Any],
        service_response: Optional[Mapping[str, Any]] = None,
        allow_service_fallback: Optional[bool] = None,
        audit_metadata: Optional[Dict[str, Any]] = None,
        emit_audit: bool = True,
    ) -> IstinaPipelineDecision:
        started = time.perf_counter()
        payload = mention_payload(mention)
        local = self._merger.make_decision(payload, metadata=None)
        topk = self._external_topk(local)
        final_decision = local.decision
        final_author_id: Optional[str] = None
        stage = "local_fs"
        reason = local.reason
        structured = StructuredRepairDecision(False, "not_attempted")

        if local.decision == Decision.MERGE:
            weak_name = local.comparisons.get("name_bin") in {"medium", "low", "none"}
            strong_context = local.comparisons.get("coauthor_bin") in {"high", "medium"}
            compatible_ids = compatible_structured_author_ids(
                mention,
                self.history_state.repair_profiles,
            )
            family_key, _ = structured_name_parts(mention)
            high_risk_surname = self._surname_risk_checker(family_key)
            dense_or_ambiguous_name = (
                high_risk_surname
                or
                local.candidate_count >= self.config.dense_name_candidate_limit
                or len(compatible_ids) > 1
            )
            if (
                self.config.require_strong_context_for_weak_name_accept
                and weak_name
                and local.comparisons.get("orcid_bin") != "match"
                and not strong_context
            ):
                final_decision = Decision.UNKNOWN
                stage = "weak_name_context_guard"
                reason = "weak name evidence lacks strong coauthor or ORCID support"
            elif (
                dense_or_ambiguous_name
                and local.comparisons.get("orcid_bin") != "match"
                and not strong_context
            ):
                final_decision = Decision.UNKNOWN
                stage = "dense_name_block_context_guard"
                reason = (
                    "high-risk, dense, or ambiguous name block lacks strong coauthor or "
                    "ORCID support"
                )
            else:
                final_author_id = self._database_to_external.get(str(local.best_author_id))
                if not final_author_id:
                    final_decision = Decision.UNKNOWN
                    stage = "local_mapping_guard"
                    reason = "local merge candidate has no ISTINA external ID mapping"
                elif final_author_id in self._quarantined:
                    final_decision = Decision.UNKNOWN
                    final_author_id = None
                    stage = "history_quarantine"
                    reason = "local merge candidate has conflicting historical identities"

        if final_decision in {Decision.NEW, Decision.UNKNOWN}:
            structured = decide_structured_repair(mention, self.history_state.repair_profiles)
            if (
                structured.accepted
                and structured.author_id in self._known_external_ids
                and structured.author_id not in self._quarantined
            ):
                final_decision = Decision.MERGE
                final_author_id = structured.author_id
                stage = "structured_coauthor_repair"
                reason = structured.reason

        if (
            self.config.enable_strict_name_repair
            and final_decision in {Decision.NEW, Decision.UNKNOWN}
        ):
            strict_name = decide_strict_name_repair(
                mention,
                self.history_state.repair_profiles,
            )
            if (
                strict_name.accepted
                and strict_name.author_id in self._known_external_ids
                and strict_name.author_id not in self._quarantined
            ):
                structured = strict_name
                final_decision = Decision.MERGE
                final_author_id = strict_name.author_id
                stage = "strict_structured_name_repair"
                reason = strict_name.reason

        if (
            self.config.enable_unique_non_cjk_initial_repair
            and final_decision in {Decision.NEW, Decision.UNKNOWN}
        ):
            initial_name = decide_unique_non_cjk_initial_repair(
                mention,
                self.history_state.repair_profiles,
                self._surname_risk_checker,
            )
            if (
                initial_name.accepted
                and initial_name.author_id in self._known_external_ids
                and initial_name.author_id not in self._quarantined
            ):
                structured = initial_name
                final_decision = Decision.MERGE
                final_author_id = initial_name.author_id
                stage = "unique_non_cjk_initial_repair"
                reason = initial_name.reason

        legacy_result_id, legacy_candidate_count = self._legacy_observation(service_response)
        use_fallback = (
            self.config.use_remote_fallback
            if allow_service_fallback is None
            else allow_service_fallback
        )
        if (
            use_fallback
            and service_response
            and local.decision == Decision.UNKNOWN
            and final_decision == Decision.UNKNOWN
        ):
            allowed_ids = {
                str(candidate["author_id"])
                for candidate in topk
                if candidate.get("author_id")
            }
            fallback = IstinaDisambiguationClient.known_author_unknown_fallback(
                dict(service_response),
                known_author_ids=allowed_ids,
                min_name_similarity=self.config.service_fallback_min_name_similarity,
            )
            if fallback.accepted and fallback.candidate:
                final_decision = Decision.MERGE
                final_author_id = fallback.candidate.id
                stage = "legacy_service_validated_fallback"
                reason = fallback.reason
            else:
                reason = f"{reason}; legacy fallback rejected: {fallback.reason}"

        legacy_agrees = None
        if legacy_result_id not in (None, "0", "", "None"):
            legacy_agrees = bool(
                final_decision == Decision.MERGE
                and final_author_id == legacy_result_id
            )

        final_trace = DecisionResult(
            decision=final_decision,
            best_author_id=final_author_id if final_decision == Decision.MERGE else None,
            score_total=local.score_total,
            score_components=local.score_components,
            comparisons=local.comparisons,
            thresholds=local.thresholds,
            mode="istina_safe_pipeline",
            topk=list(topk),
            reason=f"{stage}: {reason}",
            run_id=self.config.run_id,
            candidate_count=local.candidate_count,
            blocking_keys=local.blocking_keys,
        )
        if emit_audit and self.trace_logger:
            metadata = dict(audit_metadata or {})
            metadata.update({
                "pipeline_stage": stage,
                "base_decision": local.decision.value,
                "legacy_result_id": legacy_result_id,
                "legacy_agrees": legacy_agrees,
            })
            self.trace_logger.append_trace(final_trace, payload, metadata)

        return IstinaPipelineDecision(
            decision=final_decision,
            author_id=final_author_id if final_decision == Decision.MERGE else None,
            stage=stage,
            reason=reason,
            base_decision=local.decision,
            local_score=local.score_total,
            candidate_count=local.candidate_count,
            topk=topk,
            structured_relation=structured.relation,
            structured_coauthor_jaccard=structured.coauthor_jaccard,
            legacy_result_id=legacy_result_id,
            legacy_candidate_count=legacy_candidate_count,
            legacy_agrees=legacy_agrees,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            deterministic_hash=final_trace.deterministic_hash,
        )

    def decide_paper(
        self,
        article: Mapping[str, Any],
        man_id: Optional[int] = None,
        article_index: Optional[int] = None,
        service_response: Optional[Mapping[str, Any]] = None,
        query_service: bool = False,
        capture_legacy_shadow: bool = False,
        allow_service_fallback: Optional[bool] = None,
    ) -> List[IstinaPipelineDecision]:
        mentions = article_mentions(article, article_index=article_index)
        first_pass = [
            self.decide_mention(mention, emit_audit=False)
            for mention in mentions
        ]
        should_query = query_service and (
            capture_legacy_shadow
            or any(
                decision.decision == Decision.UNKNOWN
                and decision.base_decision == Decision.UNKNOWN
                for decision in first_pass
            )
        )
        remote_error = None
        if service_response is None and should_query:
            if not self.service_client:
                remote_error = "service client is not configured"
            elif man_id is None:
                remote_error = "man_id is required for service queries"
            else:
                try:
                    queries = [
                        self.service_client.from_exported_author(
                            mention["author"],
                            repair_short_family=True,
                        )
                        for mention in mentions
                    ]
                    service_response = self.service_client.request_candidates(queries, man_id)
                except Exception as exc:  # fail closed and preserve local result
                    remote_error = f"{type(exc).__name__}: {exc}"

        if service_response is None:
            decisions = first_pass
        else:
            decisions = []
            for position_index, mention in enumerate(mentions):
                response_slice = service_response_for_position(service_response, position_index)
                decisions.append(self.decide_mention(
                    mention,
                    service_response=response_slice,
                    allow_service_fallback=allow_service_fallback,
                    audit_metadata={
                        "article_id": mention.get("article_id"),
                        "position": mention.get("position"),
                        "shadow": capture_legacy_shadow,
                    },
                ))

        if remote_error:
            decisions = [replace(decision, service_error=remote_error) for decision in decisions]

        if service_response is None and self.trace_logger:
            for mention, decision in zip(mentions, decisions):
                # Re-run only audit emission; the deterministic decision is
                # checked by tests and avoids writing a pre-final trace.
                self.decide_mention(
                    mention,
                    allow_service_fallback=False,
                    audit_metadata={
                        "article_id": mention.get("article_id"),
                        "position": mention.get("position"),
                        "shadow": capture_legacy_shadow,
                        "service_error": remote_error,
                    },
                    emit_audit=True,
                )
        return decisions


__all__ = [
    "IstinaDisambiguationPipeline",
    "IstinaHistoryState",
    "IstinaPipelineConfig",
    "IstinaPipelineDecision",
    "article_mentions",
    "build_istina_history_state",
    "external_author_id",
    "mention_payload",
    "service_response_for_position",
]
