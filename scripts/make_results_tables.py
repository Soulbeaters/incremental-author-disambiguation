# -*- coding: utf-8 -*-
"""
Generate LaTeX Tables from Results
从结果生成LaTeX表格 / Генерация LaTeX таблиц из результатов

Converts experiment results (CSV/JSON) to LaTeX table format.
"""

import argparse
import json
import csv
import sys
from pathlib import Path
from typing import List, Dict, Any


def load_csv(path: str) -> List[Dict[str, Any]]:
    """Load data from CSV file."""
    rows = []
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convert numeric strings to floats
            for k, v in row.items():
                try:
                    row[k] = float(v)
                except (ValueError, TypeError):
                    pass
            rows.append(row)
    return rows


def load_json(path: str) -> Dict[str, Any]:
    """Load data from JSON file."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def format_metric(value: float, precision: int = 2) -> str:
    """Format a metric value as percentage string."""
    return f"{value * 100:.{precision}f}"


def generate_baselines_table(data: List[Dict[str, Any]]) -> str:
    """Generate LaTeX table for baseline comparison."""
    lines = [
        r"\begin{table}[h]",
        r"\centering",
        r"\caption{Сравнение базовых методов / Baseline Methods Comparison}",
        r"\label{tab:baselines}",
        r"\begin{tabular}{lccccc}",
        r"\toprule",
        r"Метод & B³ P & B³ R & B³ F1 & Pair F1 & Конфликт \\",
        r"\midrule"
    ]
    
    method_names = {
        'fini': 'FINI',
        'aini': 'AINI',
        'old_heuristic': 'Старый метод'
    }
    
    for row in data:
        method = method_names.get(row['method'], row['method'])
        b3_p = format_metric(row['b3_precision'])
        b3_r = format_metric(row['b3_recall'])
        b3_f1 = format_metric(row['b3_f1'])
        pair_f1 = format_metric(row['pairwise_f1'])
        conflict = format_metric(row['conflict_rate'])
        
        lines.append(f"{method} & {b3_p}\\% & {b3_r}\\% & {b3_f1}\\% & {pair_f1}\\% & {conflict}\\% \\\\")
    
    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}"
    ])
    
    return "\n".join(lines)


def generate_ablation_table(data: List[Dict[str, Any]]) -> str:
    """Generate LaTeX table for Chinese name ablation study."""
    lines = [
        r"\begin{table}[h]",
        r"\centering",
        r"\caption{Ablation: Модуль китайских имён / Chinese Name Module Ablation}",
        r"\label{tab:cn_ablation}",
        r"\begin{tabular}{llcccc}",
        r"\toprule",
        r"Подмножество & CN модуль & B³ P & B³ R & B³ F1 & Pair F1 \\",
        r"\midrule"
    ]
    
    for row in data:
        subset = row.get('subset', 'all')
        cn_enabled = 'Вкл' if row.get('cn_enabled', False) else 'Выкл'
        b3_p = format_metric(row.get('b3_precision', 0))
        b3_r = format_metric(row.get('b3_recall', 0))
        b3_f1 = format_metric(row.get('b3_f1', 0))
        pair_f1 = format_metric(row.get('pairwise_f1', 0))
        
        lines.append(f"{subset} & {cn_enabled} & {b3_p}\\% & {b3_r}\\% & {b3_f1}\\% & {pair_f1}\\% \\\\")
    
    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}"
    ])
    
    return "\n".join(lines)


def generate_summary_table(data: Dict[str, Any]) -> str:
    """Generate summary statistics table."""
    lines = [
        r"\begin{table}[h]",
        r"\centering",
        r"\caption{Статистика набора данных / Dataset Statistics}",
        r"\label{tab:dataset_stats}",
        r"\begin{tabular}{lr}",
        r"\toprule",
        r"Характеристика & Значение \\",
        r"\midrule"
    ]
    
    # Add rows for each statistic
    stats = [
        ('Всего упоминаний', data.get('total_mentions', '-')),
        ('Уникальных ORCID', data.get('unique_orcids', '-')),
        ('Упоминаний с ORCID', data.get('mentions_with_orcid', '-')),
        ('Кластеров в gold', data.get('gold_clusters', '-')),
        ('Dev-набор', data.get('dev_mentions', '-')),
        ('Test-набор', data.get('test_mentions', '-')),
    ]
    
    for label, value in stats:
        if isinstance(value, (int, float)):
            value = f"{value:,}"
        lines.append(f"{label} & {value} \\\\")
    
    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}"
    ])
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Generate LaTeX Tables / 生成LaTeX表格'
    )
    parser.add_argument(
        '--input', '-i',
        type=str,
        required=True,
        help='Input CSV or JSON file'
    )
    parser.add_argument(
        '--type', '-t',
        type=str,
        choices=['baselines', 'ablation', 'summary'],
        default='baselines',
        help='Table type to generate'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default=None,
        help='Output file (default: stdout)'
    )
    
    args = parser.parse_args()
    
    # Load data
    input_path = Path(args.input)
    if input_path.suffix == '.csv':
        data = load_csv(args.input)
    else:
        data = load_json(args.input)
    
    # Generate table
    if args.type == 'baselines':
        if isinstance(data, dict):
            data = data.get('results', [])
        latex = generate_baselines_table(data)
    elif args.type == 'ablation':
        if isinstance(data, dict):
            data = data.get('results', [])
        latex = generate_ablation_table(data)
    elif args.type == 'summary':
        latex = generate_summary_table(data)
    else:
        print(f"Unknown table type: {args.type}")
        sys.exit(1)
    
    # Output
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(latex)
        print(f"Saved to: {args.output}")
    else:
        print(latex)


if __name__ == '__main__':
    main()
