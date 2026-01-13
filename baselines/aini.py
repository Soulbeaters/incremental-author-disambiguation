# -*- coding: utf-8 -*-
"""
AINI Baseline: All Initials + Surname
AINI基线：姓氏+所有名字首字母 / AINI базовый: фамилия + все инициалы

Clusters authors by surname + all initials of given name(s).
More discriminative than FINI for authors with middle names.
"""

import json
import argparse
import sys
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Any


def normalize_name(name: str) -> str:
    """Normalize a name by lowercasing and removing extra whitespace."""
    return ' '.join(name.lower().split())


def extract_surname_and_all_initials(raw_name: str, lastname: str = '', firstname: str = '') -> str:
    """
    Extract normalized "surname + all initials" key.
    
    Args:
        raw_name: Full name string
        lastname: Parsed last name (if available)
        firstname: Parsed first name (if available)
        
    Returns:
        Normalized key like "wang_xy" or "smith_ja"
    """
    # Use parsed fields if available
    if lastname:
        surname = normalize_name(lastname)
        # Extract all initials from firstname
        initials = ''
        if firstname:
            # Handle hyphenated names and multi-word names
            fn_parts = normalize_name(firstname).replace('-', ' ').split()
            initials = ''.join(p[:1] for p in fn_parts if p)
        return f"{surname}_{initials}" if initials else surname
    
    # Parse from raw name
    raw_name = normalize_name(raw_name)
    if not raw_name:
        return ''
    
    # Handle comma-separated names: "Smith, John Michael"
    if ',' in raw_name:
        parts = raw_name.split(',')
        surname = parts[0].strip()
        given_str = parts[1].strip() if len(parts) > 1 else ''
        given_parts = given_str.replace('-', ' ').split()
        initials = ''.join(p[:1] for p in given_parts if p)
        return f"{surname}_{initials}" if initials else surname
    
    # Handle space-separated
    parts = raw_name.split()
    if len(parts) == 1:
        return parts[0]
    
    # Assume last part is surname, all others are given names
    surname = parts[-1]
    given_parts = parts[:-1]
    initials = ''.join(p[:1] for p in given_parts if p)
    
    return f"{surname}_{initials}" if initials else surname


def cluster_by_aini(mentions: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """
    Cluster mentions by All Initials + Surname.
    
    Args:
        mentions: List of mention dictionaries
        
    Returns:
        Dictionary mapping cluster_key -> list of mention_ids
    """
    clusters = defaultdict(list)
    
    for m in mentions:
        mention_id = m.get('mention_id', '')
        if not mention_id:
            continue
        
        raw_name = m.get('raw_name', '') or m.get('original_name', '')
        lastname = m.get('lastname', '')
        firstname = m.get('firstname', '')
        
        key = extract_surname_and_all_initials(raw_name, lastname, firstname)
        if key:
            clusters[f"aini:{key}"].append(mention_id)
    
    return dict(clusters)


def load_mentions_jsonl(path: str) -> List[Dict[str, Any]]:
    """Load mentions from JSONL file."""
    mentions = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                mentions.append(json.loads(line))
    return mentions


def main():
    parser = argparse.ArgumentParser(
        description='AINI Baseline Clustering / AINI基线聚类'
    )
    parser.add_argument(
        '--input', '-i',
        type=str,
        required=True,
        help='Input mentions JSONL file'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        required=True,
        help='Output clusters JSON file'
    )
    
    args = parser.parse_args()
    
    print(f"Loading mentions from: {args.input}")
    mentions = load_mentions_jsonl(args.input)
    print(f"Loaded {len(mentions)} mentions")
    
    print("Clustering by AINI (surname + all initials)...")
    clusters = cluster_by_aini(mentions)
    
    # Statistics
    num_clusters = len(clusters)
    total_mentions = sum(len(v) for v in clusters.values())
    avg_size = total_mentions / num_clusters if num_clusters > 0 else 0
    
    print(f"Created {num_clusters} clusters")
    print(f"Average cluster size: {avg_size:.2f}")
    
    # Save output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    output_data = {
        'metadata': {
            'method': 'AINI',
            'description': 'Surname + All Initials',
            'num_clusters': num_clusters,
            'total_mentions': total_mentions,
            'avg_cluster_size': avg_size
        },
        'clusters': clusters
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"Saved to: {args.output}")


if __name__ == '__main__':
    main()
