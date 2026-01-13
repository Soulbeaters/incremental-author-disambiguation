# -*- coding: utf-8 -*-
"""
ORCID Oracle (Upper Bound Only)
ORCID预言机 (仅作为上界) / ORCID-оракул (только верхняя граница)

This is NOT a deployable method. It clusters by ORCID which is the gold truth.
Used only as a theoretical upper bound on the labeled subset.

Usage:
    python baselines/orcid_oracle.py \
        --input data/mentions.jsonl \
        --output results/orcid_oracle_clusters.json
"""

import argparse
import json
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any


def load_mentions_jsonl(path: str) -> List[Dict[str, Any]]:
    """Load mentions from JSONL file."""
    mentions = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                mentions.append(json.loads(line))
    return mentions


def cluster_by_orcid_oracle(mentions: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """
    Cluster mentions by ORCID (perfect clustering on labeled subset).
    
    WARNING: This is the gold standard itself. Cannot be used for fair comparison.
    Only serves as upper bound reference.
    
    Args:
        mentions: List of mention dicts (WITH ORCID)
        
    Returns:
        Dictionary mapping cluster_id -> list of mention_ids
    """
    clusters = defaultdict(list)
    unlabeled_count = 0
    
    for m in mentions:
        mention_id = m.get('mention_id', '')
        if not mention_id:
            continue
        
        orcid = m.get('orcid', '').strip()
        
        if orcid:
            cluster_id = f"orcid:{orcid}"
            clusters[cluster_id].append(mention_id)
        else:
            # Unlabeled mentions become singletons
            cluster_id = f"unlabeled:{mention_id}"
            clusters[cluster_id].append(mention_id)
            unlabeled_count += 1
    
    return dict(clusters), unlabeled_count


def main():
    parser = argparse.ArgumentParser(
        description='ORCID Oracle (Upper Bound Only) / ORCID预言机上界'
    )
    parser.add_argument(
        '--input', '-i',
        type=str,
        default='data/mentions.jsonl',
        help='Input mentions JSONL (WITH ORCID - original data)'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='results/orcid_oracle_clusters.json',
        help='Output clusters JSON'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("WARNING: ORCID Oracle is NOT a deployable method!")
    print("It uses gold truth (ORCID) for clustering.")
    print("Use only as theoretical upper bound on labeled subset.")
    print("=" * 60)
    
    print(f"\nLoading mentions from: {args.input}")
    mentions = load_mentions_jsonl(args.input)
    print(f"  Loaded {len(mentions)} mentions")
    
    clusters, unlabeled = cluster_by_orcid_oracle(mentions)
    
    print(f"\nCreated {len(clusters)} clusters")
    print(f"  Unlabeled (singleton): {unlabeled}")
    
    # Save
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            'metadata': {
                'method': 'ORCID_ORACLE_UPPER_BOUND',
                'WARNING': 'NOT a deployable method - uses gold truth',
                'num_clusters': len(clusters),
                'unlabeled_singletons': unlabeled
            },
            'clusters': clusters
        }, f, ensure_ascii=False, indent=2)
    
    print(f"Saved to: {args.output}")


if __name__ == '__main__':
    main()
