# -*- coding: utf-8 -*-
"""
FINI Baseline: First Initial + Surname
FINI基线：姓氏+名字首字母 / FINI базовый: фамилия + первый инициал

Clusters authors by surname + first initial of given name.
This is a simple, commonly-used baseline for author disambiguation.
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


def extract_surname_and_initial(raw_name: str, lastname: str = '', firstname: str = '') -> str:
    """
    Extract normalized "surname + first initial" key.
    
    Args:
        raw_name: Full name string
        lastname: Parsed last name (if available)
        firstname: Parsed first name (if available)
        
    Returns:
        Normalized key like "wang_x" or "smith_j"
    """
    # Use parsed fields if available
    if lastname and firstname:
        surname = normalize_name(lastname)
        initial = normalize_name(firstname)[:1] if firstname else ''
        return f"{surname}_{initial}" if initial else surname
    
    # Parse from raw name
    raw_name = normalize_name(raw_name)
    if not raw_name:
        return ''
    
    # Handle comma-separated names: "Smith, John"
    if ',' in raw_name:
        parts = raw_name.split(',')
        surname = parts[0].strip()
        given = parts[1].strip() if len(parts) > 1 else ''
        initial = given[:1] if given else ''
        return f"{surname}_{initial}" if initial else surname
    
    # Handle space-separated: assume "Firstname Lastname" or "Lastname Firstname"
    parts = raw_name.split()
    if len(parts) == 1:
        return parts[0]
    
    # Heuristic: if first part is short (1-2 chars), it's likely a given name
    # Otherwise, assume first part is given name (Western style)
    if len(parts[0]) <= 2:
        surname = parts[-1]
        initial = parts[0][:1]
    else:
        # More complex - use last part as surname, first part for initial
        surname = parts[-1]
        initial = parts[0][:1]
    
    return f"{surname}_{initial}" if initial else surname


def cluster_by_fini(mentions: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """
    Cluster mentions by First Initial + Surname.
    
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
        
        key = extract_surname_and_initial(raw_name, lastname, firstname)
        if key:
            clusters[f"fini:{key}"].append(mention_id)
    
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
        description='FINI Baseline Clustering / FINI基线聚类'
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
    
    print("Clustering by FINI (surname + first initial)...")
    clusters = cluster_by_fini(mentions)
    
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
            'method': 'FINI',
            'description': 'Surname + First Initial',
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
