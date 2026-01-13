# -*- coding: utf-8 -*-
"""
Make Chinese Stressed Mentions (Enhanced)
创建中文名称压力测试数据 / Создание стресс-теста китайских имён

Enhanced with:
- stress_report.json generation
- Hard assertions for validity
- Priority for ORCID-labeled Chinese mentions
- Weighted operation distribution

Usage:
    python data/make_chinese_stressed_mentions.py \
        --input data/mentions_orcid_blind.jsonl \
        --gold data/gold_clusters.json \
        --output data/mentions_orcid_blind_stress.jsonl \
        --seed 42 --rate 0.3
"""

import argparse
import json
import random
import hashlib
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Set, Tuple
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))


def load_gold_mention_ids(gold_path: str) -> Set[str]:
    """Load mention IDs covered by gold clusters."""
    ids = set()
    if not Path(gold_path).exists():
        return ids
    with open(gold_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    clusters = data.get('clusters', data)
    for cluster_ids in clusters.values():
        ids.update(cluster_ids)
    return ids


def detect_chinese_mentions(mentions_path: str) -> Set[str]:
    """Detect Chinese mentions using heuristic."""
    from evaluation.subsets import is_romanized_chinese
    
    chinese_ids = set()
    with open(mentions_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            mention = json.loads(line)
            raw_name = mention.get('raw_name', '') or mention.get('original_name', '')
            if is_romanized_chinese(raw_name):
                chinese_ids.add(mention['mention_id'])
    return chinese_ids


def select_operation_weighted(rng: random.Random) -> str:
    """
    Select operation with weighted distribution.
    swap_order: 40%, punctuation/spacing: 40%, initials: 20%
    """
    r = rng.random()
    if r < 0.40:
        return 'swap_order'
    elif r < 0.60:
        return 'punctuation'
    elif r < 0.80:
        return 'remove_space'
    else:
        return 'initialize_given'


def perturb_chinese_name(name: str, rng: random.Random) -> Tuple[str, str]:
    """
    Apply weighted perturbation to a Chinese name.
    
    Returns:
        (perturbed_name, operation_applied)
    """
    if not name or not name.strip():
        return name, 'none'
    
    # Parse name parts
    parts = name.strip().split()
    if len(parts) < 2:
        if ',' in name:
            parts = [p.strip() for p in name.split(',')]
        else:
            parts = [name]
    
    # Select operation
    op = select_operation_weighted(rng)
    result = name
    
    if op == 'swap_order' and len(parts) >= 2:
        result = ' '.join(reversed(parts))
        
    elif op == 'initialize_given' and len(parts) >= 2:
        family = parts[0]
        given = parts[1] if len(parts) > 1 else ''
        if given and len(given) > 1:
            result = f"{family} {given[0]}."
        else:
            # Fallback to swap if can't initialize
            result = ' '.join(reversed(parts))
            op = 'swap_order_fallback'
            
    elif op == 'remove_space':
        if rng.random() < 0.5:
            result = result.replace(' ', '')
        else:
            result = result.replace(' ', '-')
            
    elif op == 'punctuation':
        if ',' in result:
            result = result.replace(',', '').replace('  ', ' ')
        else:
            parts = result.split()
            if len(parts) >= 2:
                result = f"{parts[0]}, {' '.join(parts[1:])}"
    
    return result.strip(), op


def make_stressed_mentions(
    input_path: str,
    output_path: str,
    gold_path: str,
    seed: int = 42,
    rate: float = 0.3
) -> Dict[str, Any]:
    """
    Create stressed mentions with priority for ORCID-labeled Chinese mentions.
    """
    rng = random.Random(seed)
    
    # Load gold mention IDs
    gold_ids = load_gold_mention_ids(gold_path)
    print(f"  Gold mention IDs: {len(gold_ids)}")
    
    # Detect Chinese mentions
    chinese_ids = detect_chinese_mentions(input_path)
    print(f"  Chinese mentions: {len(chinese_ids)}")
    
    # Priority: Chinese ∩ Gold (ORCID-labeled)
    priority_ids = chinese_ids & gold_ids
    print(f"  Priority (Chinese ∩ Gold): {len(priority_ids)}")
    
    # Load all mentions
    mentions = []
    with open(input_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                mentions.append(json.loads(line))
    
    # Separate priority and non-priority
    priority_mentions = [m for m in mentions if m.get('mention_id', '') in priority_ids]
    other_chinese = [m for m in mentions if m.get('mention_id', '') in (chinese_ids - priority_ids)]
    
    # Calculate how many to stress
    target_stressed = int(len(chinese_ids) * rate)
    priority_to_stress = min(len(priority_mentions), int(target_stressed * 0.8))
    other_to_stress = target_stressed - priority_to_stress
    
    print(f"  Target stressed: {target_stressed}")
    print(f"  Priority to stress: {priority_to_stress}")
    print(f"  Other to stress: {other_to_stress}")
    
    # Select mentions to stress (prioritize ORCID-labeled)
    rng.shuffle(priority_mentions)
    rng.shuffle(other_chinese)
    
    to_stress_ids = set()
    for m in priority_mentions[:priority_to_stress]:
        to_stress_ids.add(m['mention_id'])
    for m in other_chinese[:other_to_stress]:
        to_stress_ids.add(m['mention_id'])
    
    # Apply perturbations
    stats = {
        'total_mentions': 0,
        'chinese_mentions': 0,
        'stressed_mentions': 0,
        'unchanged': 0,
        'ops_distribution': Counter(),
        'stressed_ids': [],
        'verification_samples': []
    }
    
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f_out:
        for mention in mentions:
            stats['total_mentions'] += 1
            mention_id = mention.get('mention_id', '')
            
            if mention_id in chinese_ids:
                stats['chinese_mentions'] += 1
            
            if mention_id in to_stress_ids:
                raw_name = mention.get('raw_name', '') or mention.get('original_name', '')
                
                # Save original
                mention['raw_name_original'] = raw_name
                
                # Perturb
                perturbed, op = perturb_chinese_name(raw_name, rng)
                mention['raw_name'] = perturbed
                mention['stress_op'] = op
                
                if 'original_name' in mention:
                    mention['original_name'] = perturbed
                
                stats['stressed_mentions'] += 1
                stats['stressed_ids'].append(mention_id)
                stats['ops_distribution'][op] += 1
                
                # Collect verification samples
                if len(stats['verification_samples']) < 50:
                    stats['verification_samples'].append({
                        'mention_id': mention_id,
                        'original': raw_name,
                        'perturbed': perturbed,
                        'op': op,
                        'changed': raw_name != perturbed
                    })
            
            f_out.write(json.dumps(mention, ensure_ascii=False) + '\n')
    
    # Add derived stats
    stats['stressed_ratio_actual'] = stats['stressed_mentions'] / max(1, stats['chinese_mentions'])
    stats['intersection_with_gold'] = len(priority_ids)
    stats['stressed_in_gold'] = len(set(stats['stressed_ids']) & gold_ids)
    
    return stats


def generate_stress_report(stats: Dict, output_dir: Path, seed: int, rate: float):
    """Generate stress_report.json with full verification data."""
    rng = random.Random(seed + 1)  # Different seed for sampling
    
    # Sample 20 stressed IDs
    stressed_sample = stats['stressed_ids'][:20] if len(stats['stressed_ids']) >= 20 else stats['stressed_ids']
    
    # Check verification samples
    verification_results = stats['verification_samples']
    changed_count = sum(1 for v in verification_results if v['changed'])
    change_ratio = changed_count / max(1, len(verification_results))
    
    report = {
        'timestamp': datetime.now().isoformat(),
        'seed': seed,
        'target_rate': rate,
        'total_mentions': stats['total_mentions'],
        'chinese_mentions_count': stats['chinese_mentions'],
        'stressed_mentions_count': stats['stressed_mentions'],
        'stressed_ratio_actual': stats['stressed_ratio_actual'],
        'intersection_with_eval_labeled_count': stats['intersection_with_gold'],
        'stressed_in_gold_count': stats['stressed_in_gold'],
        'stressed_ids_sample': stressed_sample,
        'ops_distribution': dict(stats['ops_distribution']),
        'verification': {
            'samples_checked': len(verification_results),
            'actually_changed': changed_count,
            'change_ratio': change_ratio,
            'samples': verification_results[:10]  # First 10 for inspection
        }
    }
    
    report_path = output_dir / 'stress_report.json'
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    return report


def run_assertions(stats: Dict, rate: float):
    """Run hard assertions to verify stress is valid."""
    print("\n" + "=" * 50)
    print("Running Hard Assertions")
    print("=" * 50)
    
    errors = []
    
    # Assertion 1: stressed_count > 0
    if stats['stressed_mentions'] == 0:
        errors.append("FAIL: stressed_mentions_count == 0 (no perturbations applied)")
    else:
        print(f"  ✓ stressed_mentions_count = {stats['stressed_mentions']} > 0")
    
    # Assertion 2: ratio >= rate * 0.6
    min_ratio = rate * 0.6
    if stats['stressed_ratio_actual'] < min_ratio:
        errors.append(f"FAIL: stressed_ratio ({stats['stressed_ratio_actual']:.3f}) < {min_ratio:.3f}")
    else:
        print(f"  ✓ stressed_ratio = {stats['stressed_ratio_actual']:.3f} >= {min_ratio:.3f}")
    
    # Assertion 3: verification samples show real changes
    verification = stats['verification_samples']
    if verification:
        changed = sum(1 for v in verification if v['changed'])
        change_pct = changed / len(verification)
        if change_pct < 0.80:
            errors.append(f"FAIL: change_ratio ({change_pct:.1%}) < 80%")
        else:
            print(f"  ✓ change_ratio = {change_pct:.1%} >= 80%")
    
    # Assertion 4: stressed mentions intersect with gold
    if stats['stressed_in_gold'] < 50 and stats['intersection_with_gold'] >= 50:
        errors.append(f"FAIL: stressed_in_gold ({stats['stressed_in_gold']}) < 50 (stress doesn't affect evaluated mentions)")
    else:
        print(f"  ✓ stressed_in_gold = {stats['stressed_in_gold']}")
    
    if errors:
        print("\n" + "!" * 50)
        print("ASSERTION FAILURES:")
        for e in errors:
            print(f"  {e}")
        print("!" * 50)
        print("\nAborting: STRESS data is invalid. Please check configuration.")
        sys.exit(1)
    
    print("\n  All assertions passed!")


def main():
    parser = argparse.ArgumentParser(
        description='Make Chinese Stressed Mentions (Enhanced)'
    )
    parser.add_argument('--input', '-i', type=str, default='data/mentions_orcid_blind.jsonl')
    parser.add_argument('--output', '-o', type=str, default='data/mentions_orcid_blind_stress.jsonl')
    parser.add_argument('--gold', '-g', type=str, default='data/gold_clusters.json')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--rate', type=float, default=0.3)
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Make Chinese Stressed Mentions (Enhanced)")
    print("=" * 60)
    print(f"Input: {args.input}")
    print(f"Output: {args.output}")
    print(f"Gold: {args.gold}")
    print(f"Seed: {args.seed}")
    print(f"Rate: {args.rate}")
    print(f"Ops: swap_order(40%), punct(20%), space(20%), init(20%)")
    
    if not Path(args.input).exists():
        print(f"Error: Input file not found: {args.input}")
        sys.exit(1)
    
    print("\nGenerating stressed mentions...")
    stats = make_stressed_mentions(
        args.input, args.output, args.gold,
        seed=args.seed, rate=args.rate
    )
    
    print(f"\nStatistics:")
    print(f"  Total mentions: {stats['total_mentions']}")
    print(f"  Chinese mentions: {stats['chinese_mentions']}")
    print(f"  Stressed: {stats['stressed_mentions']} ({stats['stressed_ratio_actual']:.1%})")
    print(f"  In gold: {stats['stressed_in_gold']}")
    print(f"  Ops: {dict(stats['ops_distribution'])}")
    
    # Generate report
    output_dir = Path(args.output).parent
    report = generate_stress_report(stats, output_dir, args.seed, args.rate)
    print(f"\nStress report saved to: {output_dir / 'stress_report.json'}")
    
    # Run assertions
    run_assertions(stats, args.rate)
    
    # Save Chinese IDs
    ids_file = output_dir / 'chinese_subset_ids.txt'
    chinese_ids = detect_chinese_mentions(args.input)
    with open(ids_file, 'w', encoding='utf-8') as f:
        for mid in sorted(chinese_ids):
            f.write(mid + '\n')
    
    print(f"\nOutput saved to: {args.output}")
    print("Done!")


if __name__ == '__main__':
    main()
