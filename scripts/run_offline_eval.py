# -*- coding: utf-8 -*-
"""
离线评估脚本 / Offline Evaluation Script
无需网络即可运行的评估，使用仓库内置样例数据

作者: Ma Jiaxin
日期: 2026-01-08
"""

import json
import sys
import argparse
from pathlib import Path
from typing import Dict, Any, List
from collections import defaultdict

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from models.database import AuthorDatabase
from disambiguation_engine.author_merger import AuthorMerger


def load_sample_data(data_file: Path) -> List[Dict[str, Any]]:
    """加载样例数据"""
    with open(data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('authors', data) if isinstance(data, dict) else data


def run_offline_evaluation(
    data_file: Path,
    mode: str = "baseline",
    accept_threshold: float = 0.50,
    reject_threshold: float = 0.20,
    seed: int = 42,
    init_ratio: float = 0.5
) -> Dict[str, Any]:
    """
    运行离线评估
    
    Args:
        data_file: 数据文件路径
        mode: 评分模式 (baseline/fs)
        accept_threshold: MERGE阈值
        reject_threshold: NEW阈值
        seed: 随机种子
        init_ratio: 初始化数据比例
    
    Returns:
        评估结果字典
    """
    import random
    random.seed(seed)
    
    # 加载数据
    records = load_sample_data(data_file)
    print(f"Loaded {len(records)} records from {data_file.name}")
    
    # 按ORCID分组
    groups = defaultdict(list)
    for record in records:
        orcid = record.get('orcid', '')
        if orcid:
            groups[orcid].append(record)
    
    valid_groups = {k: v for k, v in groups.items() if len(v) >= 2}
    print(f"Valid ORCID groups: {len(valid_groups)}")
    
    if not valid_groups:
        return {"error": "No valid ORCID groups found (need >=2 records per ORCID)"}
    
    # 分割数据
    init_mentions = []
    eval_mentions = []
    
    for orcid, recs in valid_groups.items():
        random.shuffle(recs)
        split = max(1, int(len(recs) * init_ratio))
        init_mentions.extend([(r, orcid) for r in recs[:split]])
        eval_mentions.extend([(r, orcid) for r in recs[split:]])
    
    print(f"Init: {len(init_mentions)}, Eval: {len(eval_mentions)}")
    
    # 初始化
    db = AuthorDatabase()
    
    for record, orcid in init_mentions:
        name = record.get('original_name', record.get('name', '')).strip()
        db.add_author({
            'name': name,
            'orcid': orcid,
        })
    
    merger = AuthorMerger(
        database=db,
        accept_threshold=accept_threshold,
        reject_threshold=reject_threshold,
        mode=mode
    )
    
    # 评估
    correct = 0
    wrong = 0
    merge_count = 0
    new_count = 0
    unknown_count = 0
    
    for record, true_orcid in eval_mentions:
        name = record.get('original_name', record.get('name', '')).strip()
        mention = {
            'name': name,
            'orcid': '',
            'surname': record.get('lastname', name.split()[-1] if name else '')
        }
        
        result = merger.make_decision(mention)
        decision = result.decision.name if hasattr(result.decision, 'name') else str(result.decision)
        
        if decision == 'MERGE':
            merge_count += 1
            matched = db.find_by_id(result.best_author_id)
            if matched and matched.orcid == true_orcid:
                correct += 1
            else:
                wrong += 1
        elif decision == 'NEW':
            new_count += 1
        else:
            unknown_count += 1
    
    total = len(eval_mentions)
    precision = correct / (correct + wrong) if (correct + wrong) > 0 else 0
    recall = correct / total if total > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    
    return {
        'data_file': str(data_file),
        'mode': mode,
        'seed': seed,
        'thresholds': {'accept': accept_threshold, 'reject': reject_threshold},
        'data_stats': {
            'total_records': len(records),
            'valid_groups': len(valid_groups),
            'init_size': len(init_mentions),
            'eval_size': len(eval_mentions)
        },
        'metrics': {
            'precision': round(precision, 4),
            'recall': round(recall, 4),
            'f1': round(f1, 4)
        },
        'decisions': {
            'merge': merge_count,
            'new': new_count,
            'unknown': unknown_count,
            'correct': correct,
            'wrong': wrong
        }
    }


def main():
    parser = argparse.ArgumentParser(
        description='Offline evaluation for author disambiguation'
    )
    parser.add_argument(
        '--input', '-i',
        type=str,
        default='test_data/sample_offline.json',
        help='Input data file (JSON)'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='test_results/offline_eval_results.json',
        help='Output results file'
    )
    parser.add_argument(
        '--mode', '-m',
        type=str,
        default='baseline',
        choices=['baseline', 'fs'],
        help='Scoring mode'
    )
    parser.add_argument('--seed', type=int, default=42, help='Random seed')
    
    args = parser.parse_args()
    
    # 检查输入文件
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = project_root / args.input
    
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        print("Please provide a valid data file with --input")
        sys.exit(1)
    
    # 运行评估
    results = run_offline_evaluation(
        data_file=input_path,
        mode=args.mode,
        seed=args.seed
    )
    
    # 输出结果
    print("\n" + "="*60)
    print("OFFLINE EVALUATION RESULTS")
    print("="*60)
    print(f"Mode: {results.get('mode')}")
    print(f"Seed: {results.get('seed')}")
    print()
    print("Metrics:")
    metrics = results.get('metrics', {})
    print(f"  Precision: {metrics.get('precision', 0)*100:.2f}%")
    print(f"  Recall:    {metrics.get('recall', 0)*100:.2f}%")
    print(f"  F1:        {metrics.get('f1', 0)*100:.2f}%")
    print()
    
    # 保存结果
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = project_root / args.output
    output_path.parent.mkdir(exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"Results saved to: {output_path}")


if __name__ == '__main__':
    main()
