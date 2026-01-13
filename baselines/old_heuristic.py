# -*- coding: utf-8 -*-
"""
Old Heuristic Baseline (ORCID-Blind)
旧启发式基线 (ORCID盲) / Старый эвристический базовый метод (ORCID-слепой)

A deployable baseline that uses FINI + affiliation gate.
Does NOT use ORCID for clustering - only uses features available in production.

Usage:
    python baselines/old_heuristic.py \
        --input data/mentions_orcid_blind.jsonl \
        --output results/old_heuristic_clusters.json
"""

import argparse
import json
import re
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Optional


def load_mentions_jsonl(path: str) -> List[Dict[str, Any]]:
    """Load mentions from JSONL file."""
    mentions = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                mentions.append(json.loads(line))
    return mentions


def normalize_string(s: str) -> str:
    """Normalize string for comparison."""
    if not s:
        return ''
    s = s.lower().strip()
    s = re.sub(r'[^\w\s]', '', s)
    s = re.sub(r'\s+', ' ', s)
    return s


def extract_fini_key(mention: Dict[str, Any]) -> str:
    """
    Extract FINI key (surname + first initial) for blocking.
    """
    lastname = mention.get('lastname', '').strip().lower()
    firstname = mention.get('firstname', '').strip().lower()
    
    if not lastname:
        raw_name = mention.get('raw_name', '') or mention.get('original_name', '')
        parts = raw_name.strip().split()
        if parts:
            lastname = parts[-1].lower()
            firstname = parts[0].lower() if len(parts) > 1 else ''
    
    initial = firstname[:1] if firstname else ''
    return f"{lastname}_{initial}".strip('_')


def extract_affiliation_tokens(affiliation: str) -> set:
    """Extract normalized tokens from affiliation."""
    if not affiliation:
        return set()
    tokens = normalize_string(affiliation).split()
    # Filter short tokens
    return {t for t in tokens if len(t) > 2}


def affiliation_similarity(mention1: Dict, mention2: Dict) -> float:
    """Calculate affiliation Jaccard similarity."""
    aff1 = mention1.get('affiliation', '')
    aff2 = mention2.get('affiliation', '')
    
    tokens1 = extract_affiliation_tokens(aff1)
    tokens2 = extract_affiliation_tokens(aff2)
    
    if not tokens1 or not tokens2:
        return 0.0
    
    intersection = len(tokens1 & tokens2)
    union = len(tokens1 | tokens2)
    
    return intersection / union if union > 0 else 0.0


def cluster_by_old_heuristic_orcid_blind(
    mentions: List[Dict[str, Any]],
    affiliation_threshold: float = 0.3
) -> Dict[str, List[str]]:
    """
    Cluster mentions using ORCID-blind old heuristic.
    
    This method:
    1. Groups by FINI key (surname + first initial)
    2. Within each FINI group, checks affiliation similarity
    3. Merges only if affiliation similarity > threshold
    
    Args:
        mentions: List of mention dicts
        affiliation_threshold: Minimum affiliation similarity to merge
        
    Returns:
        Dictionary mapping cluster_id -> list of mention_ids
    """
    # First pass: group by FINI key
    fini_groups = defaultdict(list)
    
    for m in mentions:
        mention_id = m.get('mention_id', '')
        if not mention_id:
            continue
        
        fini_key = extract_fini_key(m)
        fini_groups[fini_key].append(m)
    
    # Second pass: apply affiliation gate within each FINI group
    clusters = {}
    cluster_counter = 0
    
    for fini_key, group_mentions in fini_groups.items():
        if len(group_mentions) == 1:
            # Singleton - direct assign
            cluster_id = f"old_heuristic:{cluster_counter}"
            clusters[cluster_id] = [group_mentions[0]['mention_id']]
            cluster_counter += 1
            continue
        
        # For multiple mentions, use union-find with affiliation gate
        n = len(group_mentions)
        parent = list(range(n))
        
        def find(x):
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]
        
        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py
        
        # Compare all pairs in group
        for i in range(n):
            for j in range(i + 1, n):
                aff_sim = affiliation_similarity(group_mentions[i], group_mentions[j])
                # Merge if affiliation is similar OR both have no affiliation
                aff1 = group_mentions[i].get('affiliation', '')
                aff2 = group_mentions[j].get('affiliation', '')
                
                if aff_sim >= affiliation_threshold or (not aff1 and not aff2):
                    union(i, j)
        
        # Extract clusters from union-find
        local_clusters = defaultdict(list)
        for i in range(n):
            root = find(i)
            local_clusters[root].append(group_mentions[i]['mention_id'])
        
        for mention_ids in local_clusters.values():
            cluster_id = f"old_heuristic:{cluster_counter}"
            clusters[cluster_id] = mention_ids
            cluster_counter += 1
    
    return clusters


def main():
    parser = argparse.ArgumentParser(
        description='Old Heuristic Baseline (ORCID-Blind) / 旧启发式基线'
    )
    parser.add_argument(
        '--input', '-i',
        type=str,
        default='data/mentions_orcid_blind.jsonl',
        help='Input mentions JSONL (must be ORCID-blind)'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='results/old_heuristic_clusters.json',
        help='Output clusters JSON'
    )
    parser.add_argument(
        '--affiliation-threshold',
        type=float,
        default=0.3,
        help='Affiliation similarity threshold for merging'
    )
    
    args = parser.parse_args()
    
    print(f"Loading mentions from: {args.input}")
    mentions = load_mentions_jsonl(args.input)
    print(f"  Loaded {len(mentions)} mentions")
    
    # Verify ORCID-blind
    for m in mentions[:100]:
        if m.get('orcid', '').strip():
            print("WARNING: Input file contains ORCID values! Use ORCID-blind data.")
            break
    
    print(f"Clustering by Old Heuristic (FINI + affiliation gate)...")
    print(f"  Affiliation threshold: {args.affiliation_threshold}")
    
    clusters = cluster_by_old_heuristic_orcid_blind(
        mentions,
        affiliation_threshold=args.affiliation_threshold
    )
    
    print(f"Created {len(clusters)} clusters")
    
    # Save
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            'metadata': {
                'method': 'old_heuristic_orcid_blind',
                'affiliation_threshold': args.affiliation_threshold,
                'num_clusters': len(clusters),
                'total_mentions': sum(len(v) for v in clusters.values())
            },
            'clusters': clusters
        }, f, ensure_ascii=False, indent=2)
    
    print(f"Saved to: {args.output}")


if __name__ == '__main__':
    main()
