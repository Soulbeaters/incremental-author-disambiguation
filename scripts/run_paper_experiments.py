# -*- coding: utf-8 -*-
"""
完整论文实验脚本 / Full Paper Experiments Script

运行所有必要实验并生成论文用数据：
1. Baseline vs FS模式对比
2. 阈值敏感性分析
3. 决策分布统计
4. 输出LaTeX表格和JSON数据

作者: Ma Jiaxin
日期: 2026-01-11
"""

import json
import sys
import os
import logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any, Tuple

# 添加项目根目录
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from models.database import AuthorDatabase
from disambiguation_engine.author_merger import AuthorMerger
from disambiguation_engine.decision_types import Decision


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger('experiments')


def load_data(file_path: str, limit: int = None) -> List[Dict]:
    """加载Crossref数据"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    authors = data.get('authors', data)
    if limit:
        authors = authors[:limit]
    return authors


def build_gold_set(authors: List[Dict], min_mentions: int = 2) -> Dict:
    """构建ORCID金标准"""
    orcid_clusters = defaultdict(list)
    for i, author in enumerate(authors):
        orcid = author.get('orcid', '')
        if orcid:
            orcid_clusters[orcid].append(i)
    
    # 过滤
    filtered = {k: v for k, v in orcid_clusters.items() if len(v) >= min_mentions}
    mention_to_orcid = {}
    for orcid, mids in filtered.items():
        for mid in mids:
            mention_to_orcid[mid] = orcid
    
    return {
        'orcid_to_mentions': filtered,
        'mention_to_orcid': mention_to_orcid,
        'total_mentions': len(authors),
        'gold_mentions': len(mention_to_orcid),
        'unique_orcids': len(filtered)
    }


def run_single_experiment(
    authors: List[Dict],
    gold_set: Dict,
    mode: str,
    accept_threshold: float,
    reject_threshold: float
) -> Dict:
    """运行单次实验"""
    db = AuthorDatabase()
    merger = AuthorMerger(
        database=db,
        accept_threshold=accept_threshold,
        reject_threshold=reject_threshold,
        mode=mode
    )
    
    gold_mention_ids = set(gold_set['mention_to_orcid'].keys())
    
    stats = {'merge': 0, 'new': 0, 'unknown': 0, 'correct': 0, 'wrong': 0}
    mention_to_pred = {}
    
    for i, author_data in enumerate(authors):
        if i not in gold_mention_ids:
            continue
        
        mention = {
            'name': author_data.get('original_name', ''),
            'surname': author_data.get('surname', ''),
            'orcid': author_data.get('orcid', ''),
            'coauthors': author_data.get('coauthors', []),
            'journals': [author_data.get('journal', '')] if author_data.get('journal') else [],
            'affiliation': [author_data.get('affiliation', '')] if author_data.get('affiliation') else [],
        }
        
        result = merger.make_decision(mention)
        decision_name = result.decision.name
        
        if decision_name == 'MERGE':
            stats['merge'] += 1
            cluster_id = result.best_author_id
            # 检查正确性
            matched_author = db.find_by_id(cluster_id)
            if matched_author and matched_author.orcid == author_data.get('orcid'):
                stats['correct'] += 1
            else:
                stats['wrong'] += 1
            mention_to_pred[i] = cluster_id
        elif decision_name == 'NEW':
            stats['new'] += 1
            new_author = db.add_author({
                'canonical_name': mention['name'],
                'surnames': [mention.get('surname', '')],
                'orcid': mention.get('orcid', ''),
            })
            mention_to_pred[i] = new_author.author_id
        else:  # UNKNOWN
            stats['unknown'] += 1
            mention_to_pred[i] = f'unknown_{i}'
    
    # 计算指标
    total = stats['merge'] + stats['new'] + stats['unknown']
    precision = stats['correct'] / (stats['correct'] + stats['wrong']) if (stats['correct'] + stats['wrong']) > 0 else 0
    recall = stats['correct'] / len(gold_mention_ids) if gold_mention_ids else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    unknown_rate = stats['unknown'] / total if total > 0 else 0
    
    return {
        'mode': mode,
        'accept_threshold': accept_threshold,
        'reject_threshold': reject_threshold,
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'unknown_rate': unknown_rate,
        'merge': stats['merge'],
        'new': stats['new'],
        'unknown': stats['unknown'],
        'correct': stats['correct'],
        'wrong': stats['wrong'],
        'total': total
    }


def run_threshold_sweep(
    authors: List[Dict],
    gold_set: Dict,
    mode: str,
    logger: logging.Logger
) -> List[Dict]:
    """阈值扫描实验"""
    results = []
    
    if mode == 'baseline':
        # Baseline模式：0-1范围的阈值
        accept_thresholds = [0.95, 0.90, 0.85, 0.80, 0.75, 0.70, 0.65, 0.60, 0.55, 0.50]
        reject_thresholds = [0.10, 0.15, 0.20, 0.25, 0.30]
    else:
        # FS模式：LLR阈值
        accept_thresholds = [5.0, 4.0, 3.0, 2.5, 2.0, 1.5, 1.0, 0.5]
        reject_thresholds = [-3.0, -2.0, -1.0, 0.0]
    
    total_experiments = len(accept_thresholds) * len(reject_thresholds)
    current = 0
    
    for accept in accept_thresholds:
        for reject in reject_thresholds:
            if reject >= accept:
                continue
            current += 1
            logger.info(f"  [{current}/{total_experiments}] {mode}: accept={accept}, reject={reject}")
            
            result = run_single_experiment(authors, gold_set, mode, accept, reject)
            results.append(result)
            
            logger.info(f"    -> P={result['precision']:.3f}, R={result['recall']:.3f}, F1={result['f1']:.3f}, Unknown={result['unknown_rate']:.1%}")
    
    return results


def generate_latex_table(results: List[Dict], title: str) -> str:
    """生成LaTeX表格"""
    lines = [
        f"% {title}",
        "\\begin{table}[htbp]",
        "\\centering",
        f"\\caption{{{title}}}",
        "\\begin{tabular}{lcccccc}",
        "\\toprule",
        "Accept & Reject & Precision & Recall & F1 & Unknown\\% \\\\",
        "\\midrule",
    ]
    
    for r in sorted(results, key=lambda x: -x['f1'])[:10]:  # Top 10 by F1
        lines.append(
            f"{r['accept_threshold']:.2f} & {r['reject_threshold']:.2f} & "
            f"{r['precision']:.3f} & {r['recall']:.3f} & {r['f1']:.3f} & "
            f"{r['unknown_rate']*100:.1f}\\% \\\\"
        )
    
    lines.extend([
        "\\bottomrule",
        "\\end{tabular}",
        "\\end{table}",
    ])
    
    return '\n'.join(lines)


def main():
    logger = setup_logging()
    
    print("=" * 80)
    print("二号项目完整论文实验 / Project Two Full Paper Experiments")
    print("=" * 80)
    
    # 配置
    data_file = r'C:\istina\materia 材料\测试表单\crossref.json'
    output_dir = project_root / 'test_results' / 'paper_experiments'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    limit = 50000  # 使用50000条数据
    
    # 1. 加载数据
    logger.info(f"Loading data from {data_file}...")
    if not Path(data_file).exists():
        logger.error(f"Data file not found: {data_file}")
        return
    
    authors = load_data(data_file, limit=limit)
    logger.info(f"Loaded {len(authors)} authors")
    
    # 2. 构建金标准
    logger.info("Building ORCID gold set...")
    gold_set = build_gold_set(authors, min_mentions=2)
    logger.info(f"Gold set: {gold_set['gold_mentions']} mentions, {gold_set['unique_orcids']} unique ORCIDs")
    
    all_results = {
        'metadata': {
            'timestamp': datetime.now().isoformat(),
            'data_file': data_file,
            'limit': limit,
            'gold_mentions': gold_set['gold_mentions'],
            'unique_orcids': gold_set['unique_orcids'],
        },
        'baseline': [],
        'fs': [],
    }
    
    # 3. Baseline模式阈值扫描
    logger.info("\n" + "=" * 60)
    logger.info("BASELINE MODE THRESHOLD SWEEP")
    logger.info("=" * 60)
    
    baseline_results = run_threshold_sweep(authors, gold_set, 'baseline', logger)
    all_results['baseline'] = baseline_results
    
    # 4. FS模式阈值扫描
    logger.info("\n" + "=" * 60)
    logger.info("FELLEGI-SUNTER MODE THRESHOLD SWEEP")
    logger.info("=" * 60)
    
    fs_results = run_threshold_sweep(authors, gold_set, 'fs', logger)
    all_results['fs'] = fs_results
    
    # 5. 找最优配置
    best_baseline = max(baseline_results, key=lambda x: x['f1'])
    best_fs = max(fs_results, key=lambda x: x['f1'])
    
    all_results['best'] = {
        'baseline': best_baseline,
        'fs': best_fs,
    }
    
    # 6. 保存结果
    results_file = output_dir / 'full_experiments.json'
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    logger.info(f"\nResults saved to: {results_file}")
    
    # 7. 生成LaTeX表格
    latex_baseline = generate_latex_table(baseline_results, "Baseline Mode Results")
    latex_fs = generate_latex_table(fs_results, "Fellegi-Sunter Mode Results")
    
    latex_file = output_dir / 'paper_tables.tex'
    with open(latex_file, 'w', encoding='utf-8') as f:
        f.write(latex_baseline + '\n\n' + latex_fs)
    logger.info(f"LaTeX tables saved to: {latex_file}")
    
    # 8. 打印总结
    print("\n" + "=" * 80)
    print("EXPERIMENT RESULTS SUMMARY")
    print("=" * 80)
    
    print(f"\n【Best Baseline Configuration】")
    print(f"  Accept: {best_baseline['accept_threshold']}, Reject: {best_baseline['reject_threshold']}")
    print(f"  Precision: {best_baseline['precision']:.4f}")
    print(f"  Recall:    {best_baseline['recall']:.4f}")
    print(f"  F1:        {best_baseline['f1']:.4f}")
    print(f"  Unknown:   {best_baseline['unknown_rate']:.2%}")
    
    print(f"\n【Best Fellegi-Sunter Configuration】")
    print(f"  Accept: {best_fs['accept_threshold']}, Reject: {best_fs['reject_threshold']}")
    print(f"  Precision: {best_fs['precision']:.4f}")
    print(f"  Recall:    {best_fs['recall']:.4f}")
    print(f"  F1:        {best_fs['f1']:.4f}")
    print(f"  Unknown:   {best_fs['unknown_rate']:.2%}")
    
    print("\n" + "=" * 80)
    print(f"Full results: {results_file}")
    print(f"LaTeX tables: {latex_file}")
    print("=" * 80)


if __name__ == '__main__':
    main()
