# -*- coding: utf-8 -*-
"""
完整消融实验 + PR曲线绘制 / Full Ablation Study + PR Curve Plotting

包括:
1. 修复FS模式（更合理的阈值范围）
2. 中文姓名模块消融实验
3. 绘制PR曲线

作者: Ma Jiaxin
日期: 2026-01-11
"""

import json
import sys
import random
import logging
import math
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any, Tuple

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from models.database import AuthorDatabase
from disambiguation_engine.author_merger import AuthorMerger
from disambiguation_engine.decision_types import Decision


def setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    return logging.getLogger('ablation')


def load_data(file_path: str, limit: int = None) -> List[Dict]:
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    authors = data.get('authors', data)
    return authors[:limit] if limit else authors


def split_by_orcid(authors: List[Dict], init_ratio: float = 0.5, seed: int = 42) -> Dict:
    random.seed(seed)
    orcid_groups = defaultdict(list)
    for i, author in enumerate(authors):
        orcid = author.get('orcid', '')
        if orcid:
            orcid_groups[orcid].append((i, author))
    
    valid_groups = {k: v for k, v in orcid_groups.items() if len(v) >= 2}
    init_set, eval_set = [], []
    
    for orcid, records in valid_groups.items():
        random.shuffle(records)
        split_point = max(1, int(len(records) * init_ratio))
        for idx, author in records[:split_point]:
            init_set.append((idx, author, orcid))
        for idx, author in records[split_point:]:
            eval_set.append((idx, author, orcid))
    
    return {'init_set': init_set, 'eval_set': eval_set, 'total_orcids': len(valid_groups)}


def run_experiment(init_set, eval_set, mode, accept_threshold, reject_threshold, logger=None) -> Dict:
    db = AuthorDatabase()
    orcid_to_author_id = {}
    
    for idx, author_data, orcid in init_set:
        name = author_data.get('original_name', '')
        if orcid not in orcid_to_author_id:
            new_author = db.add_author({
                'name': name,
                'orcid': orcid,
                'journals': [author_data.get('journal', '')] if author_data.get('journal') else [],
            })
            orcid_to_author_id[orcid] = new_author.author_id
    
    merger = AuthorMerger(database=db, accept_threshold=accept_threshold, 
                          reject_threshold=reject_threshold, mode=mode)
    
    stats = {'merge': 0, 'new': 0, 'unknown': 0, 'correct': 0, 'wrong': 0}
    
    for idx, author_data, true_orcid in eval_set:
        mention = {
            'name': author_data.get('original_name', ''),
            'surname': author_data.get('lastname', ''),
            'orcid': '',
            'coauthors': author_data.get('coauthors', []) or [],
            'journals': [author_data.get('journal', '')] if author_data.get('journal') else [],
        }
        
        result = merger.make_decision(mention)
        decision = result.decision.name
        
        if decision == 'MERGE':
            stats['merge'] += 1
            matched_author = db.find_by_id(result.best_author_id)
            if matched_author and matched_author.orcid == true_orcid:
                stats['correct'] += 1
            else:
                stats['wrong'] += 1
        elif decision == 'NEW':
            stats['new'] += 1
            if true_orcid in orcid_to_author_id:
                stats['wrong'] += 1
        else:
            stats['unknown'] += 1
    
    total = len(eval_set)
    precision = stats['correct'] / (stats['correct'] + stats['wrong']) if (stats['correct'] + stats['wrong']) > 0 else 0
    recall = stats['correct'] / total if total > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    unknown_rate = stats['unknown'] / total if total > 0 else 0
    
    return {
        'mode': mode, 'accept_threshold': accept_threshold, 'reject_threshold': reject_threshold,
        'precision': precision, 'recall': recall, 'f1': f1, 'unknown_rate': unknown_rate,
        **stats, 'total': total
    }


def run_fs_with_adjusted_thresholds(init_set, eval_set, logger) -> List[Dict]:
    """FS模式使用调整后的阈值范围（更低的accept阈值）"""
    results = []
    # FS LLR分数通常在-5到+5范围，使用更低的阈值
    accepts = [3.0, 2.5, 2.0, 1.5, 1.0, 0.5, 0.0, -0.5]
    rejects = [-3.0, -2.0, -1.5, -1.0, -0.5]
    
    total = sum(1 for a in accepts for r in rejects if r < a)
    current = 0
    
    for accept in accepts:
        for reject in rejects:
            if reject >= accept:
                continue
            current += 1
            logger.info(f"  [{current}/{total}] FS: accept={accept}, reject={reject}")
            result = run_experiment(init_set, eval_set, 'fs', accept, reject, logger)
            results.append(result)
            logger.info(f"    P={result['precision']:.3f} R={result['recall']:.3f} F1={result['f1']:.3f} Unk={result['unknown_rate']:.1%}")
    
    return results


def run_baseline_sweep(init_set, eval_set, logger) -> List[Dict]:
    """Baseline阈值扫描（用于PR曲线）"""
    results = []
    # 更细粒度的阈值用于绘制PR曲线
    accepts = [0.95, 0.90, 0.85, 0.80, 0.75, 0.70, 0.65, 0.60, 0.55, 0.50, 0.45, 0.40, 0.35, 0.30]
    reject = 0.20  # 固定reject阈值
    
    for i, accept in enumerate(accepts):
        logger.info(f"  [{i+1}/{len(accepts)}] baseline: accept={accept}")
        result = run_experiment(init_set, eval_set, 'baseline', accept, reject, logger)
        results.append(result)
        logger.info(f"    P={result['precision']:.3f} R={result['recall']:.3f} F1={result['f1']:.3f}")
    
    return results


def generate_pr_curve_data(results: List[Dict]) -> Dict:
    """生成PR曲线数据"""
    # 按recall排序
    sorted_results = sorted(results, key=lambda x: x['recall'])
    
    points = []
    for r in sorted_results:
        if r['precision'] > 0 or r['recall'] > 0:
            points.append({
                'precision': r['precision'],
                'recall': r['recall'],
                'f1': r['f1'],
                'threshold': r['accept_threshold'],
                'unknown_rate': r['unknown_rate']
            })
    
    return {'points': points, 'mode': results[0]['mode'] if results else 'unknown'}


def create_pr_curve_html(baseline_data: Dict, fs_data: Dict, output_path: Path):
    """创建PR曲线HTML可视化"""
    html = '''<!DOCTYPE html>
<html>
<head>
    <title>PR Curve - Project Two</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #333; text-align: center; }
        .chart-container { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin: 20px 0; }
        canvas { max-height: 500px; }
        .stats { display: flex; gap: 20px; flex-wrap: wrap; justify-content: center; margin-top: 20px; }
        .stat-box { background: white; padding: 20px; border-radius: 8px; text-align: center; min-width: 150px; }
        .stat-value { font-size: 24px; font-weight: bold; color: #2196F3; }
        .stat-label { color: #666; font-size: 14px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>二号项目 Precision-Recall 曲线</h1>
        <h2 style="text-align:center;color:#666;">Project Two: Author Disambiguation</h2>
        
        <div class="chart-container">
            <canvas id="prChart"></canvas>
        </div>
        
        <div class="stats">
            <div class="stat-box">
                <div class="stat-value" id="best-f1">-</div>
                <div class="stat-label">Best F1 (Baseline)</div>
            </div>
            <div class="stat-box">
                <div class="stat-value" id="best-precision">-</div>
                <div class="stat-label">Best Precision</div>
            </div>
            <div class="stat-box">
                <div class="stat-value" id="best-recall">-</div>
                <div class="stat-label">Best Recall</div>
            </div>
        </div>
    </div>
    
    <script>
        const baselineData = ''' + json.dumps(baseline_data['points']) + ''';
        const fsData = ''' + json.dumps(fs_data['points']) + ''';
        
        // Find best F1
        const bestBaseline = baselineData.reduce((a, b) => a.f1 > b.f1 ? a : b, {f1: 0});
        document.getElementById('best-f1').textContent = (bestBaseline.f1 * 100).toFixed(1) + '%';
        document.getElementById('best-precision').textContent = (bestBaseline.precision * 100).toFixed(1) + '%';
        document.getElementById('best-recall').textContent = (bestBaseline.recall * 100).toFixed(1) + '%';
        
        const ctx = document.getElementById('prChart').getContext('2d');
        new Chart(ctx, {
            type: 'line',
            data: {
                datasets: [
                    {
                        label: 'Baseline Mode',
                        data: baselineData.map(p => ({x: p.recall * 100, y: p.precision * 100})),
                        borderColor: '#2196F3',
                        backgroundColor: 'rgba(33, 150, 243, 0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 5,
                        pointHoverRadius: 8
                    },
                    {
                        label: 'Fellegi-Sunter Mode',
                        data: fsData.map(p => ({x: p.recall * 100, y: p.precision * 100})),
                        borderColor: '#FF5722',
                        backgroundColor: 'rgba(255, 87, 34, 0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 5,
                        pointHoverRadius: 8
                    }
                ]
            },
            options: {
                responsive: true,
                plugins: {
                    title: { display: true, text: 'Precision-Recall Curve', font: { size: 18 } },
                    legend: { position: 'bottom' }
                },
                scales: {
                    x: { type: 'linear', min: 0, max: 100, title: { display: true, text: 'Recall (%)' } },
                    y: { type: 'linear', min: 0, max: 100, title: { display: true, text: 'Precision (%)' } }
                }
            }
        });
    </script>
</body>
</html>'''
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)


def main():
    logger = setup_logging()
    
    print("=" * 80)
    print("消融实验 + PR曲线 / Ablation Study + PR Curve")
    print("=" * 80)
    
    data_file = r'C:\istina\materia 材料\测试表单\crossref.json'
    output_dir = project_root / 'test_results' / 'paper_experiments'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    limit = 50000  # 使用50k数据加速
    
    # 1. 加载数据
    logger.info("Loading data...")
    authors = load_data(data_file, limit=limit)
    logger.info(f"Loaded {len(authors)} authors")
    
    # 2. 分割数据
    logger.info("Splitting data...")
    split = split_by_orcid(authors, init_ratio=0.5, seed=42)
    logger.info(f"Init: {len(split['init_set'])}, Eval: {len(split['eval_set'])}")
    
    all_results = {
        'metadata': {
            'timestamp': datetime.now().isoformat(),
            'data_file': data_file,
            'limit': limit,
            'init_count': len(split['init_set']),
            'eval_count': len(split['eval_set']),
        },
        'baseline': [],
        'fs_adjusted': [],
    }
    
    # 3. Baseline扫描（PR曲线用）
    logger.info("\n" + "=" * 60)
    logger.info("BASELINE MODE SWEEP (for PR curve)")
    logger.info("=" * 60)
    all_results['baseline'] = run_baseline_sweep(split['init_set'], split['eval_set'], logger)
    
    # 4. FS模式（修复后的阈值）
    logger.info("\n" + "=" * 60)
    logger.info("FELLEGI-SUNTER MODE (adjusted thresholds)")
    logger.info("=" * 60)
    all_results['fs_adjusted'] = run_fs_with_adjusted_thresholds(split['init_set'], split['eval_set'], logger)
    
    # 5. 找最优
    best_baseline = max(all_results['baseline'], key=lambda x: x['f1'])
    best_fs = max(all_results['fs_adjusted'], key=lambda x: x['f1']) if all_results['fs_adjusted'] else {}
    all_results['best'] = {'baseline': best_baseline, 'fs': best_fs}
    
    # 6. 生成PR曲线数据
    baseline_pr = generate_pr_curve_data(all_results['baseline'])
    fs_pr = generate_pr_curve_data(all_results['fs_adjusted'])
    
    # 7. 创建HTML可视化
    html_path = output_dir / 'pr_curve.html'
    create_pr_curve_html(baseline_pr, fs_pr, html_path)
    logger.info(f"\nPR curve saved to: {html_path}")
    
    # 8. 保存JSON数据
    results_file = output_dir / 'ablation_pr_results.json'
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    logger.info(f"Results saved to: {results_file}")
    
    # 9. 打印总结
    print("\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    
    print(f"\n【Best Baseline】 accept={best_baseline['accept_threshold']}")
    print(f"  Precision: {best_baseline['precision']*100:.2f}%")
    print(f"  Recall:    {best_baseline['recall']*100:.2f}%")
    print(f"  F1:        {best_baseline['f1']*100:.2f}%")
    print(f"  Unknown:   {best_baseline['unknown_rate']*100:.1f}%")
    
    if best_fs:
        print(f"\n【Best FS (adjusted)】 accept={best_fs['accept_threshold']}, reject={best_fs['reject_threshold']}")
        print(f"  Precision: {best_fs['precision']*100:.2f}%")
        print(f"  Recall:    {best_fs['recall']*100:.2f}%")
        print(f"  F1:        {best_fs['f1']*100:.2f}%")
        print(f"  Unknown:   {best_fs['unknown_rate']*100:.1f}%")
    
    print(f"\nPR Curve HTML: {html_path}")
    print("=" * 80)


if __name__ == '__main__':
    main()
