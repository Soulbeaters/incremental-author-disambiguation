# -*- coding: utf-8 -*-
"""
Evaluate Clusters CLI
聚类评估命令行工具 / CLI инструмент оценки кластеризации

CLI for running cluster-based evaluation using B³ and Pairwise metrics.

Usage:
    python evaluation/evaluate_clusters.py --gold X --pred Y --output results/
    python evaluation/evaluate_clusters.py --gold X --pred Y --splits Z --subset test
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Set, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.cluster_metrics import (
    b3_precision_recall_f1,
    pairwise_precision_recall_f1,
    orcid_conflict_merge_rate,
    evaluate_all_metrics,
    filter_clusters_by_mentions
)


def load_json(path: str) -> Dict[str, Any]:
    """Load JSON file."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_clusters(path: str) -> Dict[str, List[str]]:
    """Load clusters from JSON, handling both wrapped and direct formats."""
    data = load_json(path)
    if 'clusters' in data:
        return data['clusters']
    return data


def load_mention_subset(splits_path: str, subset: str) -> Set[str]:
    """Load mention IDs for a specific split (dev/test)."""
    data = load_json(splits_path)
    splits = data.get('splits', data)
    
    if subset not in splits:
        raise ValueError(f"Split '{subset}' not found. Available: {list(splits.keys())}")
    
    return set(splits[subset].get('mention_ids', []))


def load_mentions_jsonl(path: str) -> List[Dict[str, Any]]:
    """Load mentions from JSONL file."""
    mentions = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                mentions.append(json.loads(line))
    return mentions


def is_chinese_name(name: str) -> bool:
    """
    Check if a name appears to be romanized Chinese.
    Uses simple heuristics based on common Chinese surnames and patterns.
    """
    if not name:
        return False
    
    name_lower = name.lower().strip()
    parts = name_lower.replace(',', ' ').replace('.', ' ').split()
    
    # Common Chinese surnames (pinyin)
    chinese_surnames = {
        'wang', 'li', 'zhang', 'liu', 'chen', 'yang', 'huang', 'zhao', 'wu', 'zhou',
        'xu', 'sun', 'ma', 'zhu', 'hu', 'guo', 'he', 'lin', 'luo', 'gao',
        'liang', 'zheng', 'xie', 'song', 'tang', 'feng', 'han', 'deng', 'cao', 'peng',
        'zeng', 'xiao', 'tian', 'dong', 'pan', 'yuan', 'cai', 'jiang', 'du', 'ye',
        'cheng', 'wei', 'su', 'lu', 'ding', 'ren', 'shen', 'yao', 'lu', 'xue',
        'shi', 'qian', 'dai', 'hou', 'meng', 'shao', 'qiu', 'bai', 'yin', 'chang',
        'lei', 'tan', 'fang', 'wan', 'jin', 'zou', 'jia', 'yan', 'hao', 'long',
        'kong', 'qin', 'xia', 'jing', 'ning', 'wen'
    }
    
    if not parts:
        return False
    
    # Check if first or last part is a Chinese surname
    return parts[0] in chinese_surnames or parts[-1] in chinese_surnames


def get_chinese_subset_ids(mentions: List[Dict[str, Any]]) -> Set[str]:
    """Get mention IDs for mentions with romanized Chinese names."""
    chinese_ids = set()
    for m in mentions:
        name = m.get('raw_name', '') or m.get('original_name', '')
        if is_chinese_name(name):
            chinese_ids.add(m['mention_id'])
    return chinese_ids


def main():
    parser = argparse.ArgumentParser(
        description='Evaluate Clusters / 评估聚类结果'
    )
    parser.add_argument(
        '--gold', '-g',
        type=str,
        required=True,
        help='Gold clusters JSON file'
    )
    parser.add_argument(
        '--pred', '-p',
        type=str,
        required=True,
        help='Predicted clusters JSON file'
    )
    parser.add_argument(
        '--splits', '-s',
        type=str,
        default=None,
        help='Splits JSON file (optional, for filtering by dev/test)'
    )
    parser.add_argument(
        '--subset',
        type=str,
        default=None,
        choices=['dev', 'test', 'chinese'],
        help='Subset to evaluate on (dev, test, or chinese)'
    )
    parser.add_argument(
        '--mentions',
        type=str,
        default=None,
        help='Mentions JSONL file (required for --subset chinese)'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default=None,
        help='Output JSON file for results'
    )
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Only output JSON, no verbose printing'
    )
    
    args = parser.parse_args()
    
    # Load clusters
    if not args.quiet:
        print(f"Loading gold clusters from: {args.gold}")
    gold_clusters = load_clusters(args.gold)
    
    if not args.quiet:
        print(f"Loading predicted clusters from: {args.pred}")
    pred_clusters = load_clusters(args.pred)
    
    # Filter by subset if specified
    if args.subset:
        if args.subset == 'chinese':
            if not args.mentions:
                print("Error: --mentions required for --subset chinese", file=sys.stderr)
                sys.exit(1)
            if not args.quiet:
                print(f"Loading mentions for Chinese subset from: {args.mentions}")
            mentions = load_mentions_jsonl(args.mentions)
            mention_subset = get_chinese_subset_ids(mentions)
        else:
            if not args.splits:
                print(f"Error: --splits required for --subset {args.subset}", file=sys.stderr)
                sys.exit(1)
            if not args.quiet:
                print(f"Loading {args.subset} split from: {args.splits}")
            mention_subset = load_mention_subset(args.splits, args.subset)
        
        if not args.quiet:
            print(f"Filtering to {len(mention_subset)} mentions in '{args.subset}' subset")
        
        gold_clusters = filter_clusters_by_mentions(gold_clusters, mention_subset)
        pred_clusters = filter_clusters_by_mentions(pred_clusters, mention_subset)
    
    # Run evaluation
    if not args.quiet:
        print("\nRunning evaluation...")
    
    results = evaluate_all_metrics(gold_clusters, pred_clusters)
    
    # Add metadata
    results['metadata'] = {
        'gold_file': str(args.gold),
        'pred_file': str(args.pred),
        'subset': args.subset,
        'gold_clusters_count': len(gold_clusters),
        'pred_clusters_count': len(pred_clusters),
        'gold_mentions_count': sum(len(v) for v in gold_clusters.values()),
        'pred_mentions_count': sum(len(v) for v in pred_clusters.values())
    }
    
    # Print results
    if not args.quiet:
        print("\n" + "=" * 60)
        print("Evaluation Results")
        if args.subset:
            print(f"  Subset: {args.subset}")
        print("=" * 60)
        
        print(f"\nB-Cubed (B³) Metrics:")
        print(f"  Precision: {results['b3']['precision']:.4f}")
        print(f"  Recall:    {results['b3']['recall']:.4f}")
        print(f"  F1:        {results['b3']['f1']:.4f}")
        
        print(f"\nPairwise Metrics:")
        print(f"  Precision: {results['pairwise']['precision']:.4f}")
        print(f"  Recall:    {results['pairwise']['recall']:.4f}")
        print(f"  F1:        {results['pairwise']['f1']:.4f}")
        print(f"  (TP={results['pairwise']['tp']}, FP={results['pairwise']['fp']}, FN={results['pairwise']['fn']})")
        
        print(f"\nORCID Conflict Analysis:")
        print(f"  Conflict clusters: {results['orcid_conflicts']['conflict_clusters']}")
        print(f"  Conflict rate: {results['orcid_conflicts']['conflict_rate']:.4f}")
        
        print("\n" + "=" * 60)
    
    # Output to file if specified
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        if not args.quiet:
            print(f"Results saved to: {args.output}")
    else:
        # Print JSON to stdout if no output file
        if args.quiet:
            print(json.dumps(results, ensure_ascii=False, indent=2))
    
    if not args.quiet:
        print("\nDone!")


if __name__ == '__main__':
    main()
