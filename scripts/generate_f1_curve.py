# -*- coding: utf-8 -*-
"""
Generate F1 vs Threshold curve from experimental data
"""

import json
from pathlib import Path

def create_f1_curve_html(baseline_data, fs_data, output_path):
    """Create interactive F1 vs Threshold curve"""
    
    # Filter valid data points (non-zero F1)
    bl_valid = [p for p in baseline_data if p['f1'] > 0]
    fs_valid = [p for p in fs_data if p['f1'] > 0]
    
    html = '''<!DOCTYPE html>
<html>
<head>
    <title>F1 vs Threshold - Author Disambiguation</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: 'Segoe UI', Arial, sans-serif; margin: 40px; background: #f5f5f5; }
        .container { max-width: 1000px; margin: 0 auto; background: white; border-radius: 12px; padding: 30px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); }
        h1 { color: #333; text-align: center; }
        .chart-container { margin: 20px 0; }
        canvas { max-height: 450px; }
        .summary { background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; }
        .summary h3 { margin-top: 0; }
        table { width: 100%; border-collapse: collapse; margin: 15px 0; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #eee; }
        th { background: #e9ecef; }
        .best { background: #d4edda; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h1>F1 Score vs Accept Threshold</h1>
        
        <div class="chart-container">
            <canvas id="f1Chart"></canvas>
        </div>
        
        <div class="summary">
            <h3>Analysis Summary</h3>
            <p><strong>Baseline Mode:</strong> F1 increases as threshold decreases (more permissive). Best F1 at threshold ~0.30.</p>
            <p><strong>FS Mode:</strong> Shows similar trend but with lower overall F1 due to higher Unknown rate.</p>
            <p><strong>Key Insight:</strong> Lower thresholds favor more MERGE decisions, improving recall but potentially reducing precision.</p>
        </div>
        
        <h3>Baseline Mode Data</h3>
        <table>
            <tr><th>Threshold</th><th>F1</th><th>Precision</th><th>Recall</th><th>Unknown</th></tr>
            <tbody id="bl-table"></tbody>
        </table>
        
        <h3>Fellegi-Sunter Mode Data</h3>
        <table>
            <tr><th>Accept / Reject</th><th>F1</th><th>Precision</th><th>Recall</th><th>Unknown</th></tr>
            <tbody id="fs-table"></tbody>
        </table>
    </div>
    
    <script>
        const baselineData = ''' + json.dumps(bl_valid) + ''';
        const fsData = ''' + json.dumps(fs_valid) + ''';
        
        // Sort by threshold
        baselineData.sort((a, b) => b.accept_threshold - a.accept_threshold);
        fsData.sort((a, b) => b.accept_threshold - a.accept_threshold);
        
        // Populate tables
        const blTable = document.getElementById('bl-table');
        const bestBL = baselineData.reduce((a, b) => a.f1 > b.f1 ? a : b, {f1: 0});
        baselineData.forEach(r => {
            const tr = document.createElement('tr');
            if (r.accept_threshold === bestBL.accept_threshold) tr.className = 'best';
            tr.innerHTML = `<td>${r.accept_threshold}</td><td>${(r.f1*100).toFixed(2)}%</td><td>${(r.precision*100).toFixed(2)}%</td><td>${(r.recall*100).toFixed(2)}%</td><td>${(r.unknown_rate*100).toFixed(1)}%</td>`;
            blTable.appendChild(tr);
        });
        
        const fsTable = document.getElementById('fs-table');
        const bestFS = fsData.reduce((a, b) => a.f1 > b.f1 ? a : b, {f1: 0});
        fsData.forEach(r => {
            const tr = document.createElement('tr');
            if (r.f1 === bestFS.f1) tr.className = 'best';
            tr.innerHTML = `<td>${r.accept_threshold} / ${r.reject_threshold}</td><td>${(r.f1*100).toFixed(2)}%</td><td>${(r.precision*100).toFixed(2)}%</td><td>${(r.recall*100).toFixed(2)}%</td><td>${(r.unknown_rate*100).toFixed(1)}%</td>`;
            fsTable.appendChild(tr);
        });
        
        // Draw chart
        const ctx = document.getElementById('f1Chart').getContext('2d');
        new Chart(ctx, {
            type: 'line',
            data: {
                datasets: [
                    {
                        label: 'Baseline Mode',
                        data: baselineData.map(p => ({x: p.accept_threshold, y: p.f1 * 100})),
                        borderColor: '#4e73df',
                        backgroundColor: 'rgba(78, 115, 223, 0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 8,
                        pointHoverRadius: 12,
                        borderWidth: 3
                    },
                    {
                        label: 'Fellegi-Sunter Mode',
                        data: fsData.map(p => ({x: p.accept_threshold, y: p.f1 * 100})),
                        borderColor: '#e74a3b',
                        backgroundColor: 'rgba(231, 74, 59, 0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 8,
                        pointHoverRadius: 12,
                        borderWidth: 3
                    }
                ]
            },
            options: {
                responsive: true,
                plugins: {
                    title: { display: true, text: 'F1 Score vs Accept Threshold', font: { size: 18, weight: 'bold' } },
                    legend: { position: 'bottom', labels: { font: { size: 14 } } },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return `F1: ${context.parsed.y.toFixed(2)}%`;
                            }
                        }
                    }
                },
                scales: {
                    x: { 
                        type: 'linear',
                        title: { display: true, text: 'Accept Threshold', font: { size: 14 } },
                        reverse: true  // Lower threshold = more permissive
                    },
                    y: { 
                        type: 'linear', 
                        min: 90, 
                        max: 100,
                        title: { display: true, text: 'F1 Score (%)', font: { size: 14 } } 
                    }
                }
            }
        });
    </script>
</body>
</html>'''
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Saved: {output_path}")


def main():
    # Load experimental data
    data_file = Path(__file__).parent.parent / 'test_results' / 'paper_experiments' / 'final_experiments.json'
    
    with open(data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    baseline = data['baseline']
    fs = data['fs']
    
    # Output
    output_path = data_file.parent / 'f1_threshold_curve.html'
    create_f1_curve_html(baseline, fs, output_path)
    
    print("\n=== Data Analysis ===")
    print(f"Baseline valid points: {len([p for p in baseline if p['f1'] > 0])}/{len(baseline)}")
    print(f"FS valid points: {len([p for p in fs if p['f1'] > 0])}/{len(fs)}")
    
    best_bl = max(baseline, key=lambda x: x['f1'])
    best_fs = max(fs, key=lambda x: x['f1'])
    
    print(f"\nBest Baseline: threshold={best_bl['accept_threshold']}, F1={best_bl['f1']*100:.2f}%")
    print(f"Best FS: accept={best_fs['accept_threshold']}, reject={best_fs['reject_threshold']}, F1={best_fs['f1']*100:.2f}%")


if __name__ == '__main__':
    main()
