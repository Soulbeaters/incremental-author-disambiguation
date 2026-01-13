# -*- coding: utf-8 -*-
"""
Export Disambiguation Results to Cluster Format
将消歧结果导出为聚类格式 / Экспорт результатов дизамбигуации в формат кластеров

Converts the disambiguation decisions (MERGE/NEW/UNKNOWN) into cluster format
for evaluation with B³ and Pairwise metrics.

UNKNOWN decisions are treated as singleton clusters.
"""

import argparse
import json
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Set


def load_mentions_jsonl(path: str) -> List[Dict[str, Any]]:
    """Load mentions from JSONL file."""
    mentions = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                mentions.append(json.loads(line))
    return mentions


def decisions_to_clusters(
    decisions: List[Dict[str, Any]],
    unknown_as_singleton: bool = True
) -> Dict[str, List[str]]:
    """
    Convert disambiguation decisions to clusters.
    
    Args:
        decisions: List of decision records with format:
            {
                'mention_id': str,
                'decision': 'MERGE' | 'NEW' | 'UNKNOWN',
                'author_id': str (for MERGE decisions),
                ...
            }
        unknown_as_singleton: If True, UNKNOWN decisions become singleton clusters
        
    Returns:
        Dictionary mapping cluster_id -> list of mention_ids
    """
    clusters = defaultdict(list)
    unknown_counter = 0
    new_counter = 0
    
    for d in decisions:
        mention_id = d.get('mention_id', '')
        if not mention_id:
            continue
        
        decision = d.get('decision', '').upper()
        author_id = d.get('author_id', '')
        
        if decision == 'MERGE' and author_id:
            # Merged into existing author
            cluster_id = f"author:{author_id}"
            clusters[cluster_id].append(mention_id)
            
        elif decision == 'NEW':
            # New author created
            new_author_id = d.get('new_author_id', f"new_{new_counter}")
            cluster_id = f"new:{new_author_id}"
            clusters[cluster_id].append(mention_id)
            new_counter += 1
            
        elif decision == 'UNKNOWN':
            if unknown_as_singleton:
                # Each UNKNOWN is its own cluster
                cluster_id = f"unk:{mention_id}"
                clusters[cluster_id].append(mention_id)
            else:
                # Skip UNKNOWN mentions
                pass
        else:
            # Unknown decision type - treat as singleton
            cluster_id = f"other:{mention_id}"
            clusters[cluster_id].append(mention_id)
    
    return dict(clusters)


def merge_based_clusters(
    mentions: List[Dict[str, Any]],
    merged_pairs: List[tuple]
) -> Dict[str, List[str]]:
    """
    Create clusters from a list of merged pairs using Union-Find.
    
    Args:
        mentions: List of mention dictionaries
        merged_pairs: List of (mention_id_1, mention_id_2) tuples that are merged
        
    Returns:
        Dictionary mapping cluster_id -> list of mention_ids
    """
    # Union-Find data structure
    parent = {}
    
    def find(x):
        if x not in parent:
            parent[x] = x
        if parent[x] != x:
            parent[x] = find(parent[x])  # Path compression
        return parent[x]
    
    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py
    
    # Initialize all mentions
    for m in mentions:
        mid = m.get('mention_id', '')
        if mid:
            parent[mid] = mid
    
    # Apply merges
    for m1, m2 in merged_pairs:
        union(m1, m2)
    
    # Group by root
    clusters = defaultdict(list)
    for mid in parent:
        root = find(mid)
        clusters[f"cluster:{root}"].append(mid)
    
    return dict(clusters)


def main():
    parser = argparse.ArgumentParser(
        description='Export Predictions to Cluster Format / 导出预测结果为聚类格式'
    )
    parser.add_argument(
        '--input', '-i',
        type=str,
        required=True,
        help='Input decisions JSON file'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        required=True,
        help='Output clusters JSON file'
    )
    parser.add_argument(
        '--format',
        type=str,
        choices=['decisions', 'pairs'],
        default='decisions',
        help='Input format: decisions (per-mention) or pairs (merged pairs)'
    )
    parser.add_argument(
        '--mentions',
        type=str,
        default=None,
        help='Mentions JSONL file (required for pairs format)'
    )
    parser.add_argument(
        '--unknown-as-singleton',
        action='store_true',
        default=True,
        help='Treat UNKNOWN decisions as singleton clusters'
    )
    
    args = parser.parse_args()
    
    print(f"Loading decisions from: {args.input}")
    with open(args.input, 'r', encoding='utf-8') as f:
        input_data = json.load(f)
    
    if args.format == 'decisions':
        # Per-mention decision format
        if isinstance(input_data, list):
            decisions = input_data
        else:
            decisions = input_data.get('decisions', input_data.get('results', []))
        
        print(f"Processing {len(decisions)} decisions")
        clusters = decisions_to_clusters(
            decisions,
            unknown_as_singleton=args.unknown_as_singleton
        )
    else:
        # Merged pairs format
        if not args.mentions:
            print("Error: --mentions required for pairs format")
            sys.exit(1)
        
        mentions = load_mentions_jsonl(args.mentions)
        merged_pairs = input_data.get('merged_pairs', input_data)
        
        print(f"Processing {len(merged_pairs)} merged pairs")
        clusters = merge_based_clusters(mentions, merged_pairs)
    
    # Statistics
    num_clusters = len(clusters)
    total_mentions = sum(len(v) for v in clusters.values())
    singletons = sum(1 for v in clusters.values() if len(v) == 1)
    
    print(f"Created {num_clusters} clusters")
    print(f"  Total mentions: {total_mentions}")
    print(f"  Singletons: {singletons}")
    
    # Save output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    output_data = {
        'metadata': {
            'source': str(args.input),
            'format': args.format,
            'unknown_as_singleton': args.unknown_as_singleton,
            'num_clusters': num_clusters,
            'total_mentions': total_mentions,
            'singletons': singletons
        },
        'clusters': clusters
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"Saved to: {args.output}")


if __name__ == '__main__':
    main()
