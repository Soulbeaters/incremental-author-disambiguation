# -*- coding: utf-8 -*-
"""
最终论文实验：Baseline + FS + PR曲线

修复版：FS使用更宽松的阈值范围

作者: Ma Jiaxin
日期: 2026-01-11
"""

import json
import sys
import random
import logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from models.database import AuthorDatabase
from disambiguation_engine.author_merger import AuthorMerger


def setup_logging():
    logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')
    return logging.getLogger('final')


def load_data(file_path: str, limit: int = None) -> List[Dict]:
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    authors = data.get('authors', data)
    return authors[:limit] if limit else authors


def split_by_orcid(authors, init_ratio=0.5, seed=42):
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
        split = max(1, int(len(records) * init_ratio))
        for idx, author in records[:split]:
            init_set.append((idx, author, orcid))
        for idx, author in records[split:]:
            eval_set.append((idx, author, orcid))
    
    return {'init_set': init_set, 'eval_set': eval_set, 'total_orcids': len(valid_groups)}


def run_experiment(init_set, eval_set, mode, accept_threshold, reject_threshold):
    db = AuthorDatabase()
    orcid_to_author_id = {}
    
    for idx, author_data, orcid in init_set:
        name = author_data.get('original_name', '')
        if orcid not in orcid_to_author_id:
            new_author = db.add_author({'name': name, 'orcid': orcid,
                'journals': [author_data.get('journal', '')] if author_data.get('journal') else []})
            orcid_to_author_id[orcid] = new_author.author_id
    
    merger = AuthorMerger(database=db, accept_threshold=accept_threshold, 
                          reject_threshold=reject_threshold, mode=mode)
    
    stats = {'merge': 0, 'new': 0, 'unknown': 0, 'correct': 0, 'wrong': 0}
    
    for idx, author_data, true_orcid in eval_set:
        mention = {
            'name': author_data.get('original_name', ''),
            'surname': author_data.get('lastname', ''),
            'coauthors': author_data.get('coauthors', []) or [],
            'journals': [author_data.get('journal', '')] if author_data.get('journal') else [],
        }
        
        result = merger.make_decision(mention)
        decision = result.decision.name
        
        if decision == 'MERGE':
            stats['merge'] += 1
            matched = db.find_by_id(result.best_author_id)
            if matched and matched.orcid == true_orcid:
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
        'precision': precision, 'recall': recall, 'f1': f1, 'unknown_rate': unknown_rate, **stats, 'total': total
    }


def create_pr_curve_html(baseline_points, fs_points, output_path):
    """创建交互式PR曲线HTML"""
    html = '''<!DOCTYPE html>
<html>
<head>
    <title>PR Curve - Project Two Disambiguation</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: 'Segoe UI', Arial, sans-serif; margin: 40px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; }
        .container { max-width: 1000px; margin: 0 auto; background: white; border-radius: 16px; padding: 40px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }
        h1 { color: #333; text-align: center; margin-bottom: 10px; }
        h2 { color: #666; text-align: center; font-weight: normal; margin-top: 0; }
        .chart-container { margin: 30px 0; }
        canvas { max-height: 500px; }
        .stats { display: flex; gap: 20px; justify-content: center; margin: 30px 0; flex-wrap: wrap; }
        .stat-box { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 25px 35px; border-radius: 12px; text-align: center; color: white; min-width: 140px; }
        .stat-value { font-size: 32px; font-weight: bold; }
        .stat-label { font-size: 14px; opacity: 0.9; margin-top: 5px; }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #eee; }
        th { background: #f8f9fa; font-weight: 600; }
        .highlight { background: #e8f4f8; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Precision-Recall Curve</h1>
        <h2>二号项目: 增量作者消歧系统 / Project Two: Incremental Author Disambiguation</h2>
        
        <div class="stats">
            <div class="stat-box">
                <div class="stat-value" id="best-f1">-</div>
                <div class="stat-label">Best F1 Score</div>
            </div>
            <div class="stat-box">
                <div class="stat-value" id="best-precision">-</div>
                <div class="stat-label">Precision</div>
            </div>
            <div class="stat-box">
                <div class="stat-value" id="best-recall">-</div>
                <div class="stat-label">Recall</div>
            </div>
            <div class="stat-box">
                <div class="stat-value" id="best-unknown">-</div>
                <div class="stat-label">Unknown Rate</div>
            </div>
        </div>
        
        <div class="chart-container">
            <canvas id="prChart"></canvas>
        </div>
        
        <h3>Baseline Mode Results</h3>
        <table>
            <tr><th>Accept Threshold</th><th>Precision</th><th>Recall</th><th>F1</th><th>Unknown</th></tr>
            <tbody id="baseline-table"></tbody>
        </table>
        
        <h3>Fellegi-Sunter Mode Results</h3>
        <table>
            <tr><th>Accept / Reject</th><th>Precision</th><th>Recall</th><th>F1</th><th>Unknown</th></tr>
            <tbody id="fs-table"></tbody>
        </table>
    </div>
    
    <script>
        const baselineData = ''' + json.dumps(baseline_points) + ''';
        const fsData = ''' + json.dumps(fs_points) + ''';
        
        // 找最优
        const best = baselineData.reduce((a, b) => a.f1 > b.f1 ? a : b, {f1: 0});
        document.getElementById('best-f1').textContent = (best.f1 * 100).toFixed(1) + '%';
        document.getElementById('best-precision').textContent = (best.precision * 100).toFixed(1) + '%';
        document.getElementById('best-recall').textContent = (best.recall * 100).toFixed(1) + '%';
        document.getElementById('best-unknown').textContent = (best.unknown_rate * 100).toFixed(1) + '%';
        
        // 填充表格
        const blTable = document.getElementById('baseline-table');
        baselineData.sort((a,b) => b.f1 - a.f1).forEach((r, i) => {
            const tr = document.createElement('tr');
            if (i === 0) tr.className = 'highlight';
            tr.innerHTML = `<td>${r.accept_threshold}</td><td>${(r.precision*100).toFixed(1)}%</td><td>${(r.recall*100).toFixed(1)}%</td><td>${(r.f1*100).toFixed(1)}%</td><td>${(r.unknown_rate*100).toFixed(1)}%</td>`;
            blTable.appendChild(tr);
        });
        
        const fsTable = document.getElementById('fs-table');
        fsData.sort((a,b) => b.f1 - a.f1).forEach((r, i) => {
            const tr = document.createElement('tr');
            if (i === 0) tr.className = 'highlight';
            tr.innerHTML = `<td>${r.accept_threshold} / ${r.reject_threshold}</td><td>${(r.precision*100).toFixed(1)}%</td><td>${(r.recall*100).toFixed(1)}%</td><td>${(r.f1*100).toFixed(1)}%</td><td>${(r.unknown_rate*100).toFixed(1)}%</td>`;
            fsTable.appendChild(tr);
        });
        
        // 绘制图表
        const ctx = document.getElementById('prChart').getContext('2d');
        new Chart(ctx, {
            type: 'line',
            data: {
                datasets: [
                    {
                        label: 'Baseline Mode',
                        data: baselineData.map(p => ({x: p.recall * 100, y: p.precision * 100})),
                        borderColor: '#667eea',
                        backgroundColor: 'rgba(102, 126, 234, 0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 6,
                        pointHoverRadius: 10,
                        borderWidth: 3
                    },
                    {
                        label: 'Fellegi-Sunter Mode',
                        data: fsData.filter(p => p.precision > 0 || p.recall > 0).map(p => ({x: p.recall * 100, y: p.precision * 100})),
                        borderColor: '#f5576c',
                        backgroundColor: 'rgba(245, 87, 108, 0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 6,
                        pointHoverRadius: 10,
                        borderWidth: 3
                    }
                ]
            },
            options: {
                responsive: true,
                plugins: {
                    title: { display: true, text: 'Precision vs Recall Curve', font: { size: 20, weight: 'bold' } },
                    legend: { position: 'bottom', labels: { font: { size: 14 } } }
                },
                scales: {
                    x: { type: 'linear', min: 0, max: 100, title: { display: true, text: 'Recall (%)', font: { size: 14 } } },
                    y: { type: 'linear', min: 0, max: 100, title: { display: true, text: 'Precision (%)', font: { size: 14 } } }
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
    print("FINAL PAPER EXPERIMENTS - Project Two")
    print("=" * 80)
    
    data_file = r'C:\istina\materia 材料\测试表单\crossref.json'
    output_dir = project_root / 'test_results' / 'paper_experiments'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    limit = 50000
    
    print("Loading data...")
    authors = load_data(data_file, limit=limit)
    print(f"Loaded {len(authors)} authors")
    
    print("Splitting data...")
    split = split_by_orcid(authors, init_ratio=0.5, seed=42)
    print(f"Init: {len(split['init_set'])}, Eval: {len(split['eval_set'])}, ORCIDs: {split['total_orcids']}")
    
    results = {'baseline': [], 'fs': []}
    
    # Baseline扫描
    print("\n--- BASELINE MODE ---")
    baseline_accepts = [0.95, 0.90, 0.85, 0.80, 0.75, 0.70, 0.65, 0.60, 0.55, 0.50, 0.45, 0.40, 0.35, 0.30]
    for i, accept in enumerate(baseline_accepts):
        print(f"  [{i+1}/{len(baseline_accepts)}] accept={accept}")
        r = run_experiment(split['init_set'], split['eval_set'], 'baseline', accept, 0.20)
        results['baseline'].append(r)
        print(f"    P={r['precision']*100:.1f}% R={r['recall']*100:.1f}% F1={r['f1']*100:.1f}%")
    
    # FS扫描 - 使用更宽的阈值
    print("\n--- FELLEGI-SUNTER MODE ---")
    fs_configs = [
        (-1.0, -4.0), (-0.5, -4.0), (0.0, -4.0), (0.5, -4.0), (1.0, -4.0),
        (-1.0, -3.0), (-0.5, -3.0), (0.0, -3.0), (0.5, -3.0), (1.0, -3.0),
        (-1.5, -5.0), (-2.0, -5.0), (-2.5, -5.0), (-3.0, -6.0),
    ]
    for i, (accept, reject) in enumerate(fs_configs):
        print(f"  [{i+1}/{len(fs_configs)}] accept={accept}, reject={reject}")
        r = run_experiment(split['init_set'], split['eval_set'], 'fs', accept, reject)
        results['fs'].append(r)
        print(f"    P={r['precision']*100:.1f}% R={r['recall']*100:.1f}% F1={r['f1']*100:.1f}% Unk={r['unknown_rate']*100:.1f}%")
    
    # 找最优
    best_baseline = max(results['baseline'], key=lambda x: x['f1'])
    best_fs = max(results['fs'], key=lambda x: x['f1']) if results['fs'] else {}
    
    # 创建PR曲线HTML
    html_path = output_dir / 'pr_curve_final.html'
    create_pr_curve_html(results['baseline'], results['fs'], html_path)
    print(f"\nPR Curve saved to: {html_path}")
    
    # 保存JSON
    results_file = output_dir / 'final_experiments.json'
    results['best'] = {'baseline': best_baseline, 'fs': best_fs}
    results['metadata'] = {
        'timestamp': datetime.now().isoformat(),
        'limit': limit,
        'init_count': len(split['init_set']),
        'eval_count': len(split['eval_set']),
    }
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Results saved to: {results_file}")
    
    # 打印总结
    print("\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    print(f"\nBest Baseline: accept={best_baseline['accept_threshold']}")
    print(f"  Precision: {best_baseline['precision']*100:.2f}%")
    print(f"  Recall:    {best_baseline['recall']*100:.2f}%")
    print(f"  F1:        {best_baseline['f1']*100:.2f}%")
    print(f"  Unknown:   {best_baseline['unknown_rate']*100:.1f}%")
    
    if best_fs:
        print(f"\nBest FS: accept={best_fs['accept_threshold']}, reject={best_fs['reject_threshold']}")
        print(f"  Precision: {best_fs['precision']*100:.2f}%")
        print(f"  Recall:    {best_fs['recall']*100:.2f}%")
        print(f"  F1:        {best_fs['f1']*100:.2f}%")
        print(f"  Unknown:   {best_fs['unknown_rate']*100:.1f}%")
    
    print("\n" + "=" * 80)


if __name__ == '__main__':
    main()
