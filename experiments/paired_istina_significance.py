"""Paired significance test for new and legacy ISTINA decisions."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple


Identity = Tuple[str, str, str]


def identity(record: Mapping[str, Any]) -> Identity:
    return (
        str(record.get("article_id")),
        str(record.get("name")),
        str(record.get("gold_author_id")),
    )


def exact_mcnemar_two_sided(new_only: int, old_only: int) -> float:
    discordant = new_only + old_only
    if not discordant:
        return 1.0
    tail = sum(
        math.comb(discordant, index)
        for index in range(min(new_only, old_only) + 1)
    ) / (2 ** discordant)
    return min(1.0, 2.0 * tail)


def compare(old: Mapping[str, Any], new: Mapping[str, Any]) -> Dict[str, Any]:
    old_records = {
        identity(record): record
        for record in old["istina_service"]["records"]
    }
    local_records = {
        identity(record): record
        for record in new["local_framework"]["records"]
        if record.get("gold_seen_in_history")
    }
    repair_records = {
        identity(record): record
        for record in (new.get("structured_name_repair") or {}).get("records", [])
        if record.get("accepted")
    }
    fallback_records = {
        identity(record): record
        for record in (new.get("known_author_unknown_fallback") or {}).get("records", [])
        if record.get("accepted")
    }
    if set(old_records) != set(local_records):
        raise ValueError(
            "Legacy and new result files do not contain the same known-author records "
            f"(legacy={len(old_records)}, new={len(local_records)})"
        )

    table = {
        "both_correct": 0,
        "new_only_correct": 0,
        "old_only_correct": 0,
        "both_incorrect": 0,
    }
    pairs = []
    for key in sorted(old_records):
        local = local_records[key]
        new_correct = bool(
            (
                local.get("decision") == "merge"
                and str(local.get("predicted_gold_author_id")) == str(local.get("gold_author_id"))
            )
            or repair_records.get(key, {}).get("correct")
            or fallback_records.get(key, {}).get("correct")
        )
        old_correct = bool(old_records[key].get("result_matches_gold"))
        cell = (
            "both_correct" if new_correct and old_correct else
            "new_only_correct" if new_correct else
            "old_only_correct" if old_correct else
            "both_incorrect"
        )
        table[cell] += 1
        pairs.append({
            "article_id": key[0],
            "name": key[1],
            "gold_author_id": key[2],
            "new_correct": new_correct,
            "old_correct": old_correct,
            "cell": cell,
        })

    total = len(pairs)
    old_correct_count = table["both_correct"] + table["old_only_correct"]
    new_correct_count = table["both_correct"] + table["new_only_correct"]
    p_value = exact_mcnemar_two_sided(
        table["new_only_correct"],
        table["old_only_correct"],
    )
    return {
        "protocol": {
            "comparison": "paired known-author top-1 correctness on identical ISTINA export mentions",
            "old_method": "legacy ISTINA whole-paper service result_id",
            "new_method": "local FS + structured coauthor repair + validated legacy-service fallback",
            "test": "exact two-sided McNemar/binomial test on discordant pairs",
        },
        "n": total,
        "old_correct": old_correct_count,
        "new_correct": new_correct_count,
        "old_accuracy": old_correct_count / total if total else None,
        "new_accuracy": new_correct_count / total if total else None,
        "absolute_gain": (new_correct_count - old_correct_count) / total if total else None,
        "paired_table": table,
        "mcnemar_exact_two_sided_p": p_value,
        "statistically_significant_at_0_05": p_value < 0.05,
        "pairs": pairs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-result", type=Path, required=True)
    parser.add_argument("--new-result", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    old = json.loads(args.legacy_result.read_text(encoding="utf-8"))
    new = json.loads(args.new_result.read_text(encoding="utf-8"))
    result = compare(old, new)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "pairs"}, indent=2))


if __name__ == "__main__":
    main()
