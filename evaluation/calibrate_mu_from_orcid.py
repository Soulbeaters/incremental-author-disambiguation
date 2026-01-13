# -*- coding: utf-8 -*-
"""
Calibrate m/u Table from ORCID Pairs
从ORCID对校准m/u表 / Калибровка таблицы m/u по парам ORCID

Uses ORCID-matched pairs as positive examples and random non-matching pairs
as negative examples to estimate m/u probabilities per feature bin.

Usage:
    python evaluation/calibrate_mu_from_orcid.py \
        --mentions data/mentions.jsonl \
        --gold data/gold_clusters.json \
        --splits data/splits.json \
        --bins config/bins.yaml \
        --output config/mu_table.calibrated.yaml
"""

import argparse
import json
import yaml
import random
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Tuple, Set
from datetime import datetime


def load_mentions_jsonl(path: str) -> List[Dict[str, Any]]:
    """Load mentions from JSONL file."""
    mentions = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                mentions.append(json.loads(line))
    return mentions


def load_json(path: str) -> Dict[str, Any]:
    """Load JSON file."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_yaml(path: str) -> Dict[str, Any]:
    """Load YAML file."""
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def jaro_winkler_similarity(s1: str, s2: str) -> float:
    """Compute Jaro-Winkler similarity between two strings."""
    if not s1 or not s2:
        return 0.0
    if s1 == s2:
        return 1.0
    
    s1, s2 = s1.lower(), s2.lower()
    
    # Simple Jaro implementation
    len1, len2 = len(s1), len(s2)
    match_distance = max(len1, len2) // 2 - 1
    if match_distance < 0:
        match_distance = 0
    
    s1_matches = [False] * len1
    s2_matches = [False] * len2
    matches = 0
    transpositions = 0
    
    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)
        for j in range(start, end):
            if s2_matches[j] or s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break
    
    if matches == 0:
        return 0.0
    
    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1
    
    jaro = (matches / len1 + matches / len2 + 
            (matches - transpositions / 2) / matches) / 3
    
    # Winkler modification
    prefix = 0
    for i in range(min(4, len1, len2)):
        if s1[i] == s2[i]:
            prefix += 1
        else:
            break
    
    return jaro + 0.1 * prefix * (1 - jaro)


def get_name_bin(sim: float, bins_config: Dict) -> str:
    """Get bin name for name similarity value."""
    bins = bins_config.get('name_similarity', {}).get('bins', [])
    for b in bins:
        if b.get('min', 0) <= sim <= b.get('max', 1):
            return b['name']
    return 'none'


def get_affiliation_bin(sim: float, bins_config: Dict) -> str:
    """Get bin name for affiliation similarity value."""
    bins = bins_config.get('affiliation_similarity', {}).get('bins', [])
    for b in bins:
        if b.get('min', 0) <= sim <= b.get('max', 1):
            return b['name']
    return 'none'


def compute_feature_bins(
    m1: Dict[str, Any],
    m2: Dict[str, Any],
    bins_config: Dict
) -> Dict[str, str]:
    """
    Compute feature bin assignments for a pair of mentions.
    
    Returns:
        Dictionary mapping feature_name -> bin_name
    """
    result = {}
    
    # Name similarity
    name1 = m1.get('raw_name', '') or f"{m1.get('firstname', '')} {m1.get('lastname', '')}"
    name2 = m2.get('raw_name', '') or f"{m2.get('firstname', '')} {m2.get('lastname', '')}"
    name_sim = jaro_winkler_similarity(name1.strip(), name2.strip())
    result['name_similarity'] = get_name_bin(name_sim, bins_config)
    
    # ORCID match
    orcid1 = m1.get('orcid', '').strip()
    orcid2 = m2.get('orcid', '').strip()
    result['orcid_match'] = 'exact' if (orcid1 and orcid1 == orcid2) else 'none'
    
    # Affiliation similarity
    aff1 = m1.get('affiliation', '').lower().strip()
    aff2 = m2.get('affiliation', '').lower().strip()
    if aff1 and aff2:
        aff_sim = jaro_winkler_similarity(aff1, aff2)
    else:
        aff_sim = 0.0
    result['affiliation_similarity'] = get_affiliation_bin(aff_sim, bins_config)
    
    # Venue similarity
    venue1 = m1.get('venue', '').lower().strip()
    venue2 = m2.get('venue', '').lower().strip()
    if venue1 and venue2:
        if venue1 == venue2:
            result['venue_similarity'] = 'same'
        elif jaro_winkler_similarity(venue1, venue2) > 0.5:
            result['venue_similarity'] = 'similar'
        else:
            result['venue_similarity'] = 'different'
    else:
        result['venue_similarity'] = 'different'
    
    return result


def generate_pairs(
    mentions: List[Dict[str, Any]],
    gold_clusters: Dict[str, List[str]],
    dev_mention_ids: Set[str],
    num_negative: int = 10000,
    seed: int = 42
) -> Tuple[List[Tuple], List[Tuple]]:
    """
    Generate positive and negative pairs from dev set.
    
    Returns:
        (positive_pairs, negative_pairs) where each pair is (mention1, mention2)
    """
    random.seed(seed)
    
    # Index mentions by ID
    mention_by_id = {m['mention_id']: m for m in mentions}
    
    # Filter to dev set
    dev_mentions = [m for m in mentions if m['mention_id'] in dev_mention_ids]
    dev_by_id = {m['mention_id']: m for m in dev_mentions}
    
    # Generate positive pairs (same ORCID)
    positive_pairs = []
    for orcid, member_ids in gold_clusters.items():
        dev_members = [mid for mid in member_ids if mid in dev_by_id]
        for i in range(len(dev_members)):
            for j in range(i + 1, len(dev_members)):
                m1 = dev_by_id[dev_members[i]]
                m2 = dev_by_id[dev_members[j]]
                positive_pairs.append((m1, m2))
    
    # Generate negative pairs (different ORCIDs)
    orcid_ids = list(gold_clusters.keys())
    negative_pairs = []
    attempts = 0
    max_attempts = num_negative * 10
    
    while len(negative_pairs) < num_negative and attempts < max_attempts:
        attempts += 1
        if len(orcid_ids) < 2:
            break
        
        # Pick two different ORCIDs
        orcid1, orcid2 = random.sample(orcid_ids, 2)
        
        # Pick one mention from each
        members1 = [mid for mid in gold_clusters[orcid1] if mid in dev_by_id]
        members2 = [mid for mid in gold_clusters[orcid2] if mid in dev_by_id]
        
        if members1 and members2:
            m1 = dev_by_id[random.choice(members1)]
            m2 = dev_by_id[random.choice(members2)]
            negative_pairs.append((m1, m2))
    
    return positive_pairs, negative_pairs


def calibrate_from_pairs(
    positive_pairs: List[Tuple],
    negative_pairs: List[Tuple],
    bins_config: Dict,
    laplace_alpha: float = 1.0
) -> Dict[str, Dict]:
    """
    Calibrate m/u probabilities from pairs using Laplace smoothing.
    
    Args:
        positive_pairs: List of (m1, m2) pairs that are true matches
        negative_pairs: List of (m1, m2) pairs that are non-matches
        bins_config: Feature binning configuration
        laplace_alpha: Laplace smoothing parameter
        
    Returns:
        Calibrated m/u table
    """
    # Count feature bins for positive and negative pairs
    pos_counts = defaultdict(lambda: defaultdict(int))
    neg_counts = defaultdict(lambda: defaultdict(int))
    
    for m1, m2 in positive_pairs:
        bins = compute_feature_bins(m1, m2, bins_config)
        for feature, bin_name in bins.items():
            pos_counts[feature][bin_name] += 1
    
    for m1, m2 in negative_pairs:
        bins = compute_feature_bins(m1, m2, bins_config)
        for feature, bin_name in bins.items():
            neg_counts[feature][bin_name] += 1
    
    # Compute m/u probabilities with Laplace smoothing
    calibrated = {}
    
    for feature in pos_counts.keys() | neg_counts.keys():
        calibrated[feature] = {}
        all_bins = set(pos_counts[feature].keys()) | set(neg_counts[feature].keys())
        num_bins = len(all_bins)
        
        pos_total = sum(pos_counts[feature].values()) + laplace_alpha * num_bins
        neg_total = sum(neg_counts[feature].values()) + laplace_alpha * num_bins
        
        for bin_name in all_bins:
            pos_count = pos_counts[feature][bin_name] + laplace_alpha
            neg_count = neg_counts[feature][bin_name] + laplace_alpha
            
            m = pos_count / pos_total
            u = neg_count / neg_total
            
            calibrated[feature][bin_name] = {
                'm': round(m, 6),
                'u': round(u, 6),
                'pos_count': pos_counts[feature][bin_name],
                'neg_count': neg_counts[feature][bin_name]
            }
    
    return calibrated


def main():
    parser = argparse.ArgumentParser(
        description='Calibrate m/u Table from ORCID / 从ORCID校准m/u表'
    )
    parser.add_argument(
        '--mentions', '-m',
        type=str,
        default='data/mentions.jsonl',
        help='Mentions JSONL file'
    )
    parser.add_argument(
        '--gold', '-g',
        type=str,
        default='data/gold_clusters.json',
        help='Gold clusters JSON file'
    )
    parser.add_argument(
        '--splits', '-s',
        type=str,
        default='data/splits.json',
        help='Splits JSON file'
    )
    parser.add_argument(
        '--bins', '-b',
        type=str,
        default='config/bins.yaml',
        help='Feature bins YAML file'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='config/mu_table.calibrated.yaml',
        help='Output calibrated m/u table'
    )
    parser.add_argument(
        '--num-negative',
        type=int,
        default=10000,
        help='Number of negative pairs to sample'
    )
    parser.add_argument(
        '--laplace-alpha',
        type=float,
        default=1.0,
        help='Laplace smoothing parameter'
    )
    parser.add_argument(
        '--seed',
        type=int,
        default=42,
        help='Random seed'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("m/u Table Calibration from ORCID")
    print("=" * 60)
    
    # Load data
    print(f"\nLoading mentions from: {args.mentions}")
    mentions = load_mentions_jsonl(args.mentions)
    print(f"  Loaded {len(mentions)} mentions")
    
    print(f"Loading gold clusters from: {args.gold}")
    gold_data = load_json(args.gold)
    gold_clusters = gold_data.get('clusters', gold_data)
    print(f"  Loaded {len(gold_clusters)} clusters")
    
    print(f"Loading splits from: {args.splits}")
    splits_data = load_json(args.splits)
    dev_ids = set(splits_data.get('splits', {}).get('dev', {}).get('mention_ids', []))
    print(f"  Dev set: {len(dev_ids)} mentions")
    
    print(f"Loading bins config from: {args.bins}")
    bins_config = load_yaml(args.bins)
    
    # Generate pairs
    print(f"\nGenerating pairs (seed={args.seed})...")
    positive_pairs, negative_pairs = generate_pairs(
        mentions, gold_clusters, dev_ids,
        num_negative=args.num_negative,
        seed=args.seed
    )
    print(f"  Positive pairs: {len(positive_pairs)}")
    print(f"  Negative pairs: {len(negative_pairs)}")
    
    # Calibrate
    print(f"\nCalibrating (Laplace α={args.laplace_alpha})...")
    calibrated = calibrate_from_pairs(
        positive_pairs, negative_pairs,
        bins_config,
        laplace_alpha=args.laplace_alpha
    )
    
    # Build output
    output = {
        'version': '1.0',
        'calibration_source': 'orcid_dev_pairs',
        'calibration_date': datetime.now().strftime('%Y-%m-%d'),
        'calibration_params': {
            'num_positive_pairs': len(positive_pairs),
            'num_negative_pairs': len(negative_pairs),
            'laplace_alpha': args.laplace_alpha,
            'seed': args.seed
        },
        'features': {}
    }
    
    # Format features
    for feature, bins in calibrated.items():
        output['features'][feature] = {}
        for bin_name, values in bins.items():
            output['features'][feature][bin_name] = {
                'm': values['m'],
                'u': values['u']
            }
    
    # Add default thresholds
    output['thresholds'] = {
        'accept': 8.0,
        'reject': -3.0
    }
    output['prior_odds'] = 0.001
    
    # Save
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(output, f, allow_unicode=True, default_flow_style=False)
    
    print(f"\nSaved calibrated table to: {args.output}")
    
    # Print summary
    print("\n" + "-" * 40)
    print("Calibration Summary:")
    for feature, bins in calibrated.items():
        print(f"\n  {feature}:")
        for bin_name, values in sorted(bins.items()):
            ratio = values['m'] / values['u'] if values['u'] > 0 else float('inf')
            print(f"    {bin_name}: m={values['m']:.4f}, u={values['u']:.4f}, m/u={ratio:.2f}")
    
    print("\nDone!")


if __name__ == '__main__':
    main()
