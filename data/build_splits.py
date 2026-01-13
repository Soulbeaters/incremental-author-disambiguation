# -*- coding: utf-8 -*-
"""
Build Dev/Test Splits by ORCID
按ORCID划分开发/测试集 / Разделение на dev/test по ORCID

This script splits the gold clusters into dev and test sets by ORCID,
ensuring that all mentions of a given author appear in only one split.

Usage:
    python data/build_splits.py --gold <gold_clusters.json> --output <splits.json>
"""

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Dict, List, Any, Set, Tuple


def split_by_orcid(
    gold_clusters: Dict[str, List[str]],
    dev_ratio: float = 0.3,
    seed: int = 42
) -> Tuple[Set[str], Set[str], Dict[str, str]]:
    """
    Split ORCIDs into dev and test sets.
    
    Args:
        gold_clusters: Dictionary mapping ORCID -> mention_ids
        dev_ratio: Proportion of ORCIDs for dev set (default 0.3)
        seed: Random seed for reproducibility
        
    Returns:
        Tuple of (dev_orcids, test_orcids, orcid_to_split_mapping)
    """
    random.seed(seed)
    
    orcids = list(gold_clusters.keys())
    random.shuffle(orcids)
    
    split_idx = int(len(orcids) * dev_ratio)
    
    dev_orcids = set(orcids[:split_idx])
    test_orcids = set(orcids[split_idx:])
    
    orcid_to_split = {
        orcid: 'dev' if orcid in dev_orcids else 'test'
        for orcid in orcids
    }
    
    return dev_orcids, test_orcids, orcid_to_split


def get_mention_ids_for_split(
    gold_clusters: Dict[str, List[str]],
    orcid_set: Set[str]
) -> Set[str]:
    """Get all mention IDs belonging to a set of ORCIDs."""
    mention_ids = set()
    for orcid in orcid_set:
        if orcid in gold_clusters:
            mention_ids.update(gold_clusters[orcid])
    return mention_ids


def main():
    parser = argparse.ArgumentParser(
        description='Build Dev/Test Splits by ORCID / 按ORCID划分开发/测试集'
    )
    parser.add_argument(
        '--gold', '-g',
        type=str,
        default='data/gold_clusters.json',
        help='Input gold clusters JSON file'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='data/splits.json',
        help='Output splits JSON file'
    )
    parser.add_argument(
        '--dev-ratio',
        type=float,
        default=0.3,
        help='Proportion of ORCIDs for dev set (default: 0.3)'
    )
    parser.add_argument(
        '--seed',
        type=int,
        default=42,
        help='Random seed for reproducibility (default: 42)'
    )
    
    args = parser.parse_args()
    
    # Load gold clusters
    gold_path = Path(args.gold)
    if not gold_path.exists():
        print(f"Error: Gold clusters file not found: {args.gold}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Loading gold clusters from: {args.gold}")
    with open(gold_path, 'r', encoding='utf-8') as f:
        gold_data = json.load(f)
    
    # Handle both old format (direct dict) and new format (with metadata)
    if 'clusters' in gold_data:
        gold_clusters = gold_data['clusters']
    else:
        gold_clusters = gold_data
    
    print(f"Loaded {len(gold_clusters)} ORCID clusters")
    
    # Split by ORCID
    print(f"Splitting with dev_ratio={args.dev_ratio}, seed={args.seed}")
    dev_orcids, test_orcids, orcid_to_split = split_by_orcid(
        gold_clusters,
        dev_ratio=args.dev_ratio,
        seed=args.seed
    )
    
    # Get mention IDs for each split
    dev_mentions = get_mention_ids_for_split(gold_clusters, dev_orcids)
    test_mentions = get_mention_ids_for_split(gold_clusters, test_orcids)
    
    # Compute statistics
    total_orcids = len(gold_clusters)
    total_mentions = sum(len(v) for v in gold_clusters.values())
    
    print("\n" + "=" * 60)
    print("Split Statistics:")
    print(f"  Total ORCIDs: {total_orcids}")
    print(f"  Total mentions: {total_mentions}")
    print(f"  Dev set:")
    print(f"    ORCIDs: {len(dev_orcids)} ({100*len(dev_orcids)/total_orcids:.1f}%)")
    print(f"    Mentions: {len(dev_mentions)} ({100*len(dev_mentions)/total_mentions:.1f}%)")
    print(f"  Test set:")
    print(f"    ORCIDs: {len(test_orcids)} ({100*len(test_orcids)/total_orcids:.1f}%)")
    print(f"    Mentions: {len(test_mentions)} ({100*len(test_mentions)/total_mentions:.1f}%)")
    print("=" * 60)
    
    # Build output structure
    output_data = {
        'metadata': {
            'source_gold': str(args.gold),
            'dev_ratio': args.dev_ratio,
            'seed': args.seed,
            'total_orcids': total_orcids,
            'total_mentions': total_mentions,
            'dev_orcids_count': len(dev_orcids),
            'dev_mentions_count': len(dev_mentions),
            'test_orcids_count': len(test_orcids),
            'test_mentions_count': len(test_mentions)
        },
        'splits': {
            'dev': {
                'orcids': sorted(dev_orcids),
                'mention_ids': sorted(dev_mentions)
            },
            'test': {
                'orcids': sorted(test_orcids),
                'mention_ids': sorted(test_mentions)
            }
        }
    }
    
    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"Writing splits to: {args.output}")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print("Done!")


if __name__ == '__main__':
    main()
