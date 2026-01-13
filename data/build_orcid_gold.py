# -*- coding: utf-8 -*-
"""
Build Gold Clusters from ORCID Annotations
从ORCID注释构建金标准聚类 / Создание золотых кластеров на основе ORCID

This script reads a mentions JSONL file and creates gold standard clusters
where all mentions sharing the same ORCID are grouped together.

Usage:
    python data/build_orcid_gold.py --input <mentions.jsonl> --output <gold_clusters.json>
"""

import argparse
import json
import sys
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Any, Set


def load_mentions(path: str) -> List[Dict[str, Any]]:
    """Load mentions from JSONL file."""
    mentions = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                mentions.append(json.loads(line))
    return mentions


def build_gold_clusters(
    mentions: List[Dict[str, Any]],
    min_mentions: int = 2
) -> Dict[str, List[str]]:
    """
    Build gold standard clusters from ORCID annotations.
    
    Args:
        mentions: List of mention dictionaries with 'mention_id' and 'orcid' fields
        min_mentions: Minimum number of mentions per ORCID to include (default 2)
    
    Returns:
        Dictionary mapping ORCID -> list of mention_ids
    """
    # Group mentions by ORCID
    orcid_to_mentions: Dict[str, List[str]] = defaultdict(list)
    
    for mention in mentions:
        orcid = mention.get('orcid', '').strip()
        mention_id = mention.get('mention_id', '')
        
        if orcid and mention_id:
            orcid_to_mentions[orcid].append(mention_id)
    
    # Filter by minimum mentions
    if min_mentions > 1:
        orcid_to_mentions = {
            k: v for k, v in orcid_to_mentions.items()
            if len(v) >= min_mentions
        }
    
    return dict(orcid_to_mentions)


def compute_statistics(gold_clusters: Dict[str, List[str]]) -> Dict[str, Any]:
    """Compute statistics about the gold clusters."""
    sizes = [len(v) for v in gold_clusters.values()]
    
    if not sizes:
        return {
            'total_clusters': 0,
            'total_mentions': 0,
            'avg_cluster_size': 0,
            'min_cluster_size': 0,
            'max_cluster_size': 0,
            'size_distribution': {}
        }
    
    # Size distribution buckets
    size_dist = defaultdict(int)
    for s in sizes:
        if s <= 5:
            size_dist[f'{s}'] += 1
        elif s <= 10:
            size_dist['6-10'] += 1
        elif s <= 20:
            size_dist['11-20'] += 1
        else:
            size_dist['21+'] += 1
    
    return {
        'total_clusters': len(gold_clusters),
        'total_mentions': sum(sizes),
        'avg_cluster_size': sum(sizes) / len(sizes),
        'min_cluster_size': min(sizes),
        'max_cluster_size': max(sizes),
        'size_distribution': dict(size_dist)
    }


def main():
    parser = argparse.ArgumentParser(
        description='Build Gold Clusters from ORCID / 从ORCID构建金标准聚类'
    )
    parser.add_argument(
        '--input', '-i',
        type=str,
        default='data/mentions.jsonl',
        help='Input mentions JSONL file'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='data/gold_clusters.json',
        help='Output gold clusters JSON file'
    )
    parser.add_argument(
        '--min-mentions',
        type=int,
        default=2,
        help='Minimum mentions per ORCID to include (default: 2)'
    )
    parser.add_argument(
        '--stats-only',
        action='store_true',
        help='Only compute statistics, do not write output'
    )
    
    args = parser.parse_args()
    
    # Load mentions
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Loading mentions from: {args.input}")
    mentions = load_mentions(args.input)
    print(f"Loaded {len(mentions)} mentions")
    
    # Build gold clusters
    print(f"Building gold clusters (min_mentions={args.min_mentions})...")
    gold_clusters = build_gold_clusters(mentions, min_mentions=args.min_mentions)
    
    # Compute statistics
    stats = compute_statistics(gold_clusters)
    
    # Print summary
    print("\n" + "=" * 60)
    print("Gold Cluster Statistics:")
    print(f"  Total clusters (unique ORCIDs): {stats['total_clusters']}")
    print(f"  Total annotated mentions: {stats['total_mentions']}")
    print(f"  Average cluster size: {stats['avg_cluster_size']:.2f}")
    print(f"  Min cluster size: {stats['min_cluster_size']}")
    print(f"  Max cluster size: {stats['max_cluster_size']}")
    print("  Size distribution:")
    for k, v in sorted(stats['size_distribution'].items()):
        print(f"    {k}: {v}")
    print("=" * 60)
    
    if args.stats_only:
        print("Stats only mode - not writing output file")
        return
    
    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    output_data = {
        'metadata': {
            'source': str(args.input),
            'min_mentions': args.min_mentions,
            **stats
        },
        'clusters': gold_clusters
    }
    
    print(f"Writing gold clusters to: {args.output}")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print("Done!")


if __name__ == '__main__':
    main()
