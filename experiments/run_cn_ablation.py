# -*- coding: utf-8 -*-
"""
Real CN Ablation Experiment (ORCID-Blind)
真实CN消融实验 / Реальный эксперимент по аблации CN

Runs real disambiguation engine with/without Chinese name normalization.
All experiments use ORCID-blind data (ORCID only for gold truth).

Usage:
    python experiments/run_cn_ablation.py --seed 42 --stress-rate 0.3 --out results/
"""

import argparse
import json
import sys
import uuid
import hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any, Set, Tuple

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def load_mentions_jsonl(path: str) -> List[Dict[str, Any]]:
    """Загрузка упоминаний из JSONL. / 加载JSONL文件中的mentions."""
    mentions = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                mentions.append(json.loads(line))
    return mentions


def load_chinese_ids(path: str) -> Set[str]:
    """Загрузка ID китайского подмножества. / 加载中文子集ID."""
    ids = set()
    if not Path(path).exists():
        return ids
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                ids.add(line)
    return ids


def verify_orcid_blind(mentions: List[Dict]) -> bool:
    """Проверка ORCID-blind режима. / 验证ORCID-blind模式."""
    for m in mentions:
        if m.get('orcid', '').strip():
            return False
    return True


def run_disambiguation_with_cn_setting(
    mentions: List[Dict[str, Any]],
    enable_cn: bool,
    accept_threshold: float = 0.30,
    reject_threshold: float = 0.20
) -> Dict[str, List[str]]:
    """
    Run real disambiguation engine and return predicted clusters.
    
    This uses the actual AuthorMerger engine with configurable CN setting.
    
    Args:
        mentions: List of mentions (ORCID-blind)
        enable_cn: Whether to enable Chinese name normalization
        accept_threshold: Threshold for MERGE decision
        reject_threshold: Threshold for NEW decision
        
    Returns:
        Predicted clusters {cluster_id: [mention_ids]}
    """
    from models.author import Author
    from models.database import AuthorDatabase
    from disambiguation_engine.similarity_scorer import SimilarityScorer
    from disambiguation_engine.author_merger import AuthorMerger
    
    # Configure scorer with CN setting
    scorer_config = {
        'enable_chinese_name': enable_cn
    }
    
    # Initialize components
    database = AuthorDatabase()
    scorer = SimilarityScorer(config=scorer_config)
    merger = AuthorMerger(
        database=database,
        scorer=scorer,
        accept_threshold=accept_threshold,
        reject_threshold=reject_threshold
    )
    
    # Track cluster assignments
    mention_to_author = {}
    
    # Process each mention through the engine
    for i, mention in enumerate(mentions):
        mention_id = mention.get('mention_id', str(i))
        
        # Make decision
        try:
            result = merger.make_decision(mention)
            
            if result.decision.value == 'MERGE' and result.matched_author:
                mention_to_author[mention_id] = result.matched_author.author_id
            elif result.decision.value == 'NEW':
                # Create new author in database
                author = Author.from_mention(mention)
                database.add_author(author)
                mention_to_author[mention_id] = author.author_id
            else:
                # UNKNOWN - treat as singleton
                mention_to_author[mention_id] = f"unk:{mention_id}"
                
        except Exception as e:
            # Fallback to singleton on error
            mention_to_author[mention_id] = f"err:{mention_id}"
    
    # Convert to cluster format
    author_to_mentions = defaultdict(list)
    for mention_id, author_id in mention_to_author.items():
        author_to_mentions[author_id].append(mention_id)
    
    return dict(author_to_mentions)


def generate_dual_canonical_keys(raw_name: str, lastname: str, firstname: str) -> tuple:
    """
    Generate two canonical key forms to handle name order swaps.
    
    Returns:
        (canonical_key1, canonical_key2) - surname-given and given-surname orders
    """
    # Normalize
    lastname = lastname.lower().strip()
    firstname = firstname.lower().strip()
    
    if not lastname and raw_name:
        parts = raw_name.strip().split()
        if len(parts) >= 2:
            # Could be either order, try both
            lastname = parts[0].lower()
            firstname = parts[1].lower()
        elif parts:
            lastname = parts[0].lower()
            firstname = ''
    
    # Generate both orderings
    if firstname and len(firstname) >= 2:
        key1 = f"cn:{lastname}_{firstname[:3]}"  # surname-given
        key2 = f"cn:{firstname}_{lastname[:3]}"  # given-surname (swapped)
    elif firstname:
        key1 = f"cn:{lastname}_{firstname}"
        key2 = f"cn:{firstname}_{lastname}"
    else:
        key1 = f"cn:{lastname}"
        key2 = key1  # No swap possible
    
    return key1, key2


def run_simple_clustering_with_cn(
    mentions: List[Dict[str, Any]],
    enable_cn: bool,
    track_stats: bool = False
) -> Tuple[Dict[str, List[str]], Dict[str, int]]:
    """
    Simple clustering with dual-canonical CN normalization.
    
    Uses surname + given name comparison with optional CN normalization.
    CN normalization generates TWO canonical forms to handle swap_order.
    
    Returns:
        (clusters, stats) - clusters dict and CN trigger statistics
    """
    from evaluation.subsets import is_romanized_chinese
    
    clusters = defaultdict(list)
    existing_keys = {}  # Maps canonical keys to cluster IDs
    cluster_counter = 0
    
    stats = {
        'cn_trigger_count': 0,
        'cn_swap_resolved_count': 0,
        'total_chinese': 0
    }
    
    for m in mentions:
        mention_id = m.get('mention_id', '')
        if not mention_id:
            continue
        
        lastname = m.get('lastname', '').lower().strip()
        firstname = m.get('firstname', '').lower().strip()
        raw_name = m.get('raw_name', '') or m.get('original_name', '')
        
        if not lastname and raw_name:
            parts = raw_name.strip().split()
            if parts:
                lastname = parts[-1].lower()
                firstname = parts[0].lower() if len(parts) > 1 else ''
        
        # Apply CN normalization if enabled
        if enable_cn and is_romanized_chinese(raw_name):
            stats['total_chinese'] += 1
            stats['cn_trigger_count'] += 1
            
            # Generate dual canonical keys
            key1, key2 = generate_dual_canonical_keys(raw_name, lastname, firstname)
            
            # Check if either key exists (handles swap_order)
            if key1 in existing_keys:
                cluster_id = existing_keys[key1]
                stats['cn_swap_resolved_count'] += 1 if key1 != key2 else 0
            elif key2 in existing_keys:
                cluster_id = existing_keys[key2]
                stats['cn_swap_resolved_count'] += 1
            else:
                # New cluster, register both keys
                cluster_id = f"cn_cluster_{cluster_counter}"
                cluster_counter += 1
                existing_keys[key1] = cluster_id
                if key1 != key2:
                    existing_keys[key2] = cluster_id
            
            clusters[cluster_id].append(mention_id)
        else:
            # Standard FINI key
            initial = firstname[:1] if firstname else ''
            key = f"fini:{lastname}_{initial}"
            clusters[key].append(mention_id)
    
    return dict(clusters), stats


def evaluate_clusters(
    gold_file: str,
    pred_clusters: Dict[str, List[str]],
    subset_ids: Set[str] = None
) -> Dict[str, Any]:
    """Evaluate predicted clusters against gold."""
    from evaluation.cluster_metrics import (
        evaluate_all_metrics,
        filter_clusters_by_mentions
    )
    
    with open(gold_file, 'r', encoding='utf-8') as f:
        gold_data = json.load(f)
    
    gold_clusters = gold_data.get('clusters', gold_data)
    
    if subset_ids:
        gold_clusters = filter_clusters_by_mentions(gold_clusters, subset_ids)
        pred_clusters = filter_clusters_by_mentions(pred_clusters, subset_ids)
    
    return evaluate_all_metrics(gold_clusters, pred_clusters)


def main():
    parser = argparse.ArgumentParser(
        description='Real CN Ablation Experiment (ORCID-Blind)'
    )
    parser.add_argument(
        '--mentions-clean',
        type=str,
        default='data/mentions_orcid_blind.jsonl',
        help='ORCID-blind clean mentions'
    )
    parser.add_argument(
        '--mentions-stress',
        type=str,
        default='data/mentions_orcid_blind_stress.jsonl',
        help='ORCID-blind stressed mentions'
    )
    parser.add_argument(
        '--gold',
        type=str,
        default='data/gold_clusters.json',
        help='Gold clusters JSON'
    )
    parser.add_argument(
        '--chinese-ids',
        type=str,
        default='data/chinese_subset_ids.txt',
        help='Chinese subset IDs file'
    )
    parser.add_argument(
        '--out',
        type=str,
        default='results',
        help='Output directory'
    )
    parser.add_argument(
        '--seed',
        type=int,
        default=42,
        help='Random seed'
    )
    parser.add_argument(
        '--stress-rate',
        type=float,
        default=0.3,
        help='Stress perturbation rate (for metadata)'
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("Real CN Ablation Experiment (ORCID-Blind)")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Seed: {args.seed}")
    print(f"Stress rate: {args.stress_rate}")
    print(f"EVAL_MODE: ORCID_BLIND")
    
    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load Chinese IDs
    chinese_ids = load_chinese_ids(args.chinese_ids)
    print(f"\nChinese subset: {len(chinese_ids)} mentions")
    
    # Verify gold exists
    if not Path(args.gold).exists():
        print(f"Error: Gold file not found: {args.gold}")
        sys.exit(1)
    
    # Get gold mention IDs for evaluation scope
    with open(args.gold, 'r', encoding='utf-8') as f:
        gold_data = json.load(f)
    gold_clusters = gold_data.get('clusters', gold_data)
    gold_mention_ids = set()
    for cluster_ids in gold_clusters.values():
        gold_mention_ids.update(cluster_ids)
    print(f"Gold labeled mentions: {len(gold_mention_ids)}")
    
    # Run experiments
    experiments = [
        ('CLEAN', args.mentions_clean, False, 'ablation_cn_clean.csv'),
        ('STRESS', args.mentions_stress, True, 'ablation_cn_stress.csv')
    ]
    
    # Validate stress_report.json for STRESS experiment
    stress_report_path = Path('data/stress_report.json')
    if stress_report_path.exists():
        with open(stress_report_path, 'r', encoding='utf-8') as f:
            stress_report = json.load(f)
        print(f"\n[STRESS Report Validation]")
        print(f"  stressed_mentions: {stress_report.get('stressed_mentions_count', 0)}")
        print(f"  stressed_in_gold: {stress_report.get('stressed_in_gold_count', 0)}")
        print(f"  change_ratio: {stress_report.get('verification', {}).get('change_ratio', 0):.1%}")
        
        # Validate
        if stress_report.get('stressed_mentions_count', 0) == 0:
            print("  ERROR: stressed_mentions_count == 0! Regenerate stress data.")
            sys.exit(1)
        if stress_report.get('stressed_in_gold_count', 0) < 50:
            print("  ERROR: stressed_in_gold < 50! STRESS doesn't affect evaluated mentions.")
            sys.exit(1)
        print("  ✓ Stress report validation passed")
    else:
        print(f"\n  Warning: stress_report.json not found, skipping validation")
    
    all_results = []
    run_metadata_path = output_dir / 'run_metadata.jsonl'
    
    # Clear previous metadata
    if run_metadata_path.exists():
        run_metadata_path.unlink()
    
    for exp_name, mentions_file, is_stress, csv_file in experiments:
        print(f"\n{'='*50}")
        print(f"Running {exp_name} experiments")
        print("=" * 50)
        
        if not Path(mentions_file).exists():
            print(f"  Skipping: {mentions_file} not found")
            continue
        
        mentions = load_mentions_jsonl(mentions_file)
        print(f"  Loaded {len(mentions)} mentions")
        print(f"  Input: {Path(mentions_file).resolve()}")
        
        # Verify ORCID-blind
        if not verify_orcid_blind(mentions):
            print("  ERROR: Mentions contain ORCID! Use ORCID-blind data.")
            sys.exit(1)
        print("  ✓ Verified ORCID-blind")
        
        exp_results = []
        
        for cn_enabled in [False, True]:
            cn_label = 'ON' if cn_enabled else 'OFF'
            
            # Generate unique run_id first
            run_id = str(uuid.uuid4())[:8]
            method_id = f"{exp_name}_CN_{cn_label}"
            config_str = f"cn={cn_enabled},blocking=dual_canonical,eval=ORCID_BLIND,dataset={exp_name}"
            config_hash = hashlib.md5(config_str.encode()).hexdigest()[:8]
            
            # Create run-based output directory (full isolation)
            exp_output_dir = output_dir / 'runs' / run_id
            exp_output_dir.mkdir(parents=True, exist_ok=True)
            
            print(f"\n  [CN {cn_label}] run_id={run_id}")
            print(f"    Output dir: {exp_output_dir}")
            
            # Run clustering with dual-canonical CN
            pred_clusters, cn_stats = run_simple_clustering_with_cn(mentions, cn_enabled, track_stats=True)
            print(f"    Created {len(pred_clusters)} clusters")
            
            # Print CN trigger statistics for CN ON
            if cn_enabled:
                print(f"    CN triggers: {cn_stats['cn_trigger_count']}")
                print(f"    Swap resolved: {cn_stats['cn_swap_resolved_count']}")
                
                # Assertion: CN should trigger on at least 200 Chinese mentions
                if is_stress and cn_stats['cn_trigger_count'] < 200:
                    print(f"    WARNING: cn_trigger_count ({cn_stats['cn_trigger_count']}) < 200")
            
            # Evaluate on overall (labeled subset)
            overall_eval = evaluate_clusters(
                args.gold, 
                pred_clusters, 
                gold_mention_ids
            )
            
            # Evaluate on Chinese subset (intersection with labeled)
            chinese_labeled = chinese_ids & gold_mention_ids
            chinese_eval = evaluate_clusters(
                args.gold,
                pred_clusters,
                chinese_labeled
            ) if chinese_labeled else {'b3': {'f1': 0}, 'pairwise': {'f1': 0}, 'orcid_conflicts': {'conflict_rate': 0}}
            
            print(f"    Overall B³ F1: {overall_eval['b3']['f1']:.4f}")
            print(f"    Chinese B³ F1: {chinese_eval['b3']['f1']:.4f}")
            
            # Record results
            for subset_name, eval_result, subset_size in [
                ('overall', overall_eval, len(gold_mention_ids)),
                ('chinese', chinese_eval, len(chinese_labeled))
            ]:
                result = {
                    'experiment': exp_name,
                    'subset': subset_name,
                    'cn_enabled': cn_enabled,
                    'b3_f1': eval_result['b3']['f1'],
                    'b3_precision': eval_result['b3']['precision'],
                    'b3_recall': eval_result['b3']['recall'],
                    'pairwise_f1': eval_result['pairwise']['f1'],
                    'pairwise_precision': eval_result['pairwise']['precision'],
                    'pairwise_recall': eval_result['pairwise']['recall'],
                    'conflict_rate': eval_result['orcid_conflicts']['conflict_rate'],
                    'subset_size': subset_size
                }
                exp_results.append(result)
                all_results.append(result)
            
            # Save pred_clusters to separate directory
            clusters_path = exp_output_dir / 'pred_clusters.json'
            with open(clusters_path, 'w', encoding='utf-8') as f:
                json.dump({'clusters': pred_clusters}, f, ensure_ascii=False, indent=2)
            
            # Write run_metadata entry
            run_entry = {
                'run_id': run_id,
                'method_id': method_id,
                'dataset_id': exp_name,
                'input_path': str(Path(mentions_file).resolve()),
                'eval_mode': 'ORCID_BLIND',
                'enable_cn_name': cn_enabled,
                'config_hash': config_hash,
                'output_paths': {
                    'pred_clusters': str(clusters_path),
                    'output_dir': str(exp_output_dir)
                },
                'timestamp': datetime.now().isoformat(),
                'cn_stats': cn_stats
            }
            with open(run_metadata_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(run_entry, ensure_ascii=False) + '\n')
        
        # Save experiment CSV
        csv_path = output_dir / csv_file
        with open(csv_path, 'w', encoding='utf-8') as f:
            headers = ['subset', 'cn_enabled', 'b3_f1', 'b3_precision', 'b3_recall', 
                      'pairwise_f1', 'pairwise_precision', 'pairwise_recall', 
                      'conflict_rate', 'subset_size']
            f.write(','.join(headers) + '\n')
            for r in exp_results:
                row = [str(r.get(h, '')) for h in headers]
                f.write(','.join(row) + '\n')
        print(f"\n  Saved: {csv_path}")
    
    # Save metadata
    metadata = {
        'timestamp': datetime.now().isoformat(),
        'eval_mode': 'ORCID_BLIND',
        'seed': args.seed,
        'stress_rate': args.stress_rate,
        'gold_file': args.gold,
        'chinese_subset_size': len(chinese_ids),
        'gold_labeled_size': len(gold_mention_ids),
        'experiments': [e[0] for e in experiments]
    }
    
    metadata_path = output_dir / 'ablation_metadata.json'
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    # Print summary
    print("\n" + "=" * 70)
    print("CN Ablation Summary")
    print("=" * 70)
    print(f"\n{'Exp':<8} {'Subset':<10} {'CN':<5} {'B³ F1':>10} {'Pair F1':>10} {'Conflict':>10}")
    print("-" * 60)
    for r in all_results:
        cn = 'ON' if r['cn_enabled'] else 'OFF'
        print(f"{r['experiment']:<8} {r['subset']:<10} {cn:<5} "
              f"{r['b3_f1']:>10.4f} {r['pairwise_f1']:>10.4f} {r['conflict_rate']:>10.4f}")
    
    print(f"\nResults saved to: {output_dir}")
    print(f"  - ablation_cn_clean.csv")
    print(f"  - ablation_cn_stress.csv")
    print(f"  - ablation_metadata.json")
    print("\nDone!")


if __name__ == '__main__':
    main()
