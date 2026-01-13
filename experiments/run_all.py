# -*- coding: utf-8 -*-
"""
Unified Experiment Runner
统一实验运行器 / Единый запускатор экспериментов

Runs all baseline and system experiments with consistent evaluation.

Usage:
    python experiments/run_all.py --seed 42 --out results/
"""

import argparse
import json
import sys
import os
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def run_baseline(
    method: str,
    mentions_file: str,
    output_dir: Path,
    **kwargs
) -> Dict[str, Any]:
    """
    Run a baseline method and return its clusters.
    
    Args:
        method: Baseline method name (fini, aini, old_heuristic)
        mentions_file: Path to mentions JSONL
        output_dir: Directory for output files
        **kwargs: Additional args for specific baselines
        
    Returns:
        Dictionary with method name and output path
    """
    output_file = output_dir / f"{method}_clusters.json"
    
    if method == 'fini':
        from baselines.fini import cluster_by_fini, load_mentions_jsonl
        mentions = load_mentions_jsonl(mentions_file)
        clusters = cluster_by_fini(mentions)
    elif method == 'aini':
        from baselines.aini import cluster_by_aini, load_mentions_jsonl
        mentions = load_mentions_jsonl(mentions_file)
        clusters = cluster_by_aini(mentions)
    elif method == 'old_heuristic':
        from baselines.old_heuristic import cluster_by_old_heuristic_orcid_blind, load_mentions_jsonl
        mentions = load_mentions_jsonl(mentions_file)
        clusters = cluster_by_old_heuristic_orcid_blind(
            mentions,
            affiliation_threshold=kwargs.get('affiliation_threshold', 0.3)
        )
    else:
        raise ValueError(f"Unknown baseline method: {method}")
    
    # Save clusters
    output_data = {
        'metadata': {
            'method': method,
            'source': mentions_file,
            'num_clusters': len(clusters),
            'total_mentions': sum(len(v) for v in clusters.values())
        },
        'clusters': clusters
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    return {'method': method, 'output': str(output_file), 'clusters': clusters}


def evaluate_clusters(
    gold_file: str,
    pred_clusters: Dict[str, List[str]],
    subset_ids: set = None
) -> Dict[str, Any]:
    """
    Evaluate predicted clusters against gold.
    
    Args:
        gold_file: Path to gold clusters JSON
        pred_clusters: Predicted clusters dict
        subset_ids: Optional set of mention IDs to filter to
        
    Returns:
        Evaluation results
    """
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
        description='Run All Experiments / 运行所有实验'
    )
    parser.add_argument(
        '--mentions', '-m',
        type=str,
        default='data/mentions_orcid_blind.jsonl',
        help='Mentions JSONL file (default: ORCID-blind for fair evaluation)'
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
        '--out', '-o',
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
        '--subset',
        type=str,
        choices=['all', 'test', 'dev', 'chinese'],
        default='test',
        help='Subset to evaluate on'
    )
    parser.add_argument(
        '--eval-orcid-blind',
        action='store_true',
        default=True,
        help='Use ORCID-blind evaluation (default: True). ORCID only for gold truth.'
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("Major Revision - Unified Experiment Runner")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Seed: {args.seed}")
    print(f"Evaluation subset: {args.subset}")
    print(f"EVAL_MODE: {'ORCID_BLIND' if args.eval_orcid_blind else 'STANDARD'}")
    print()
    
    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Check inputs
    if not Path(args.mentions).exists():
        print(f"Error: Mentions file not found: {args.mentions}")
        sys.exit(1)
    if not Path(args.gold).exists():
        print(f"Error: Gold file not found: {args.gold}")
        sys.exit(1)
    
    # ORCID-blind verification (防呆检查)
    if args.eval_orcid_blind:
        print("Verifying ORCID-blind input...")
        with open(args.mentions, 'r', encoding='utf-8') as f:
            sample_count = 0
            has_orcid = False
            for line in f:
                if sample_count >= 100:
                    break
                line = line.strip()
                if line:
                    mention = json.loads(line)
                    if mention.get('orcid', '').strip():
                        has_orcid = True
                        break
                    sample_count += 1
            
            if has_orcid:
                print("ERROR: Input mentions file contains ORCID values!")
                print("       Use data/mentions_orcid_blind.jsonl for fair evaluation.")
                print("       Or run: python data/make_orcid_blind_mentions.py")
                sys.exit(1)
        print("  ✓ Verified: No ORCID in input (ORCID-blind)")
    
    # Load subset IDs if needed
    subset_ids = None
    if args.subset != 'all' and Path(args.splits).exists():
        with open(args.splits, 'r', encoding='utf-8') as f:
            splits_data = json.load(f)
        
        if args.subset in ['test', 'dev']:
            splits = splits_data.get('splits', splits_data)
            if args.subset in splits:
                subset_ids = set(splits[args.subset].get('mention_ids', []))
                print(f"Using {args.subset} split: {len(subset_ids)} mentions")
        elif args.subset == 'chinese':
            from evaluation.subsets import get_chinese_subset_ids
            from baselines.fini import load_mentions_jsonl
            mentions = load_mentions_jsonl(args.mentions)
            subset_ids = get_chinese_subset_ids(mentions)
            print(f"Using Chinese subset: {len(subset_ids)} mentions")
    
    # Run baselines
    baselines = ['fini', 'aini', 'old_heuristic']
    results = []
    
    print("\n" + "-" * 50)
    print("Running Baselines")
    print("-" * 50)
    
    for method in baselines:
        print(f"\n[{method.upper()}]")
        baseline_result = run_baseline(method, args.mentions, output_dir)
        
        # Evaluate
        eval_result = evaluate_clusters(
            args.gold,
            baseline_result['clusters'],
            subset_ids
        )
        
        results.append({
            'method': method,
            'output_file': baseline_result['output'],
            'b3_f1': eval_result['b3']['f1'],
            'b3_precision': eval_result['b3']['precision'],
            'b3_recall': eval_result['b3']['recall'],
            'pairwise_f1': eval_result['pairwise']['f1'],
            'pairwise_precision': eval_result['pairwise']['precision'],
            'pairwise_recall': eval_result['pairwise']['recall'],
            'conflict_rate': eval_result['orcid_conflicts']['conflict_rate']
        })
        
        print(f"  B³ F1: {eval_result['b3']['f1']:.4f}")
        print(f"  Pairwise F1: {eval_result['pairwise']['f1']:.4f}")
        print(f"  Conflict Rate: {eval_result['orcid_conflicts']['conflict_rate']:.4f}")
    
    # Save summary
    summary = {
        'metadata': {
            'timestamp': datetime.now().isoformat(),
            'seed': args.seed,
            'mentions_file': args.mentions,
            'gold_file': args.gold,
            'subset': args.subset,
            'subset_size': len(subset_ids) if subset_ids else 'all'
        },
        'results': results
    }
    
    summary_file = output_dir / 'experiment_summary.json'
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    # Generate CSV
    csv_file = output_dir / 'baselines.csv'
    with open(csv_file, 'w', encoding='utf-8') as f:
        f.write("method,b3_f1,b3_precision,b3_recall,pairwise_f1,pairwise_precision,pairwise_recall,conflict_rate\n")
        for r in results:
            f.write(f"{r['method']},{r['b3_f1']:.4f},{r['b3_precision']:.4f},{r['b3_recall']:.4f},"
                   f"{r['pairwise_f1']:.4f},{r['pairwise_precision']:.4f},{r['pairwise_recall']:.4f},"
                   f"{r['conflict_rate']:.4f}\n")
    
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"\n{'Method':<15} {'B³ F1':>10} {'Pairwise F1':>12} {'Conflict':>10}")
    print("-" * 50)
    for r in results:
        print(f"{r['method']:<15} {r['b3_f1']:>10.4f} {r['pairwise_f1']:>12.4f} {r['conflict_rate']:>10.4f}")
    
    print(f"\nResults saved to: {output_dir}")
    print(f"  - {summary_file}")
    print(f"  - {csv_file}")
    print("\nDone!")


if __name__ == '__main__':
    main()
