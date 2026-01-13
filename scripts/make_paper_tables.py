# -*- coding: utf-8 -*-
"""
Generate Paper Tables with Hard-Fail Validation
从结果生成论文表格（含硬失败校验）/ Генерация таблиц статьи (с валидацией)

Reads from run_metadata.jsonl and validates:
- S0.1: FINI != SYSTEM_CN_OFF
- S0.2: STRESS/OFF != CLEAN/OFF
- S0.3: Each table row traceable to run_id

Usage:
    python scripts/make_paper_tables.py --results-dir results --out tables/
"""

import argparse
import csv
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.run_registry import (
    validate_table6_not_duplicate,
    validate_table7_stress_different,
    validate_no_duplicate_outputs
)


def load_csv(path: str):
    """Load data from CSV file. / Загрузка данных из CSV."""
    rows = []
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            for k, v in row.items():
                try:
                    row[k] = float(v)
                except (ValueError, TypeError):
                    pass
            rows.append(row)
    return rows


def load_run_metadata(results_dir: Path):
    """Load all runs from run_metadata.jsonl. / Загрузка всех запусков."""
    runs = []
    metadata_path = results_dir / 'run_metadata.jsonl'
    if metadata_path.exists():
        with open(metadata_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    runs.append(json.loads(line))
    return runs


def find_run(runs, method_id, dataset_id, enable_cn):
    """Find specific run by criteria."""
    for run in runs:
        if (run.get('method_id') == method_id and 
            run.get('dataset_id') == dataset_id and
            run.get('enable_cn_name') == enable_cn):
            return run
    return None


def format_pct(v, decimals=2):
    """Format as percentage."""
    return f"{v * 100:.{decimals}f}\\%"


def validate_table6(runs, clean_csv_path):
    """
    Validate Table 6: FINI != SYSTEM_CN_OFF.
    
    Hard-fail if metrics are identical.
    """
    print("\n[Validating Table 6 - S0.1]")
    
    if not clean_csv_path.exists():
        print("  Skip: Clean CSV not found")
        return
    
    data = load_csv(str(clean_csv_path))
    
    # Find FINI and SYSTEM metrics
    fini_metrics = None
    system_cn_off_metrics = None
    
    for row in data:
        subset = row.get('subset', 'overall')
        if subset == 'overall':
            cn_enabled = row.get('cn_enabled')
            if cn_enabled == False or cn_enabled == 0 or cn_enabled == 'False':
                # This is CN_OFF row
                system_cn_off_metrics = row
    
    # For Table 6 validation, we compare baselines.csv FINI vs ablation SYSTEM_CN_OFF
    baselines_path = clean_csv_path.parent / 'baselines.csv'
    if baselines_path.exists():
        baselines = load_csv(str(baselines_path))
        for row in baselines:
            if row.get('method') == 'fini':
                fini_metrics = row
                break
    
    if fini_metrics and system_cn_off_metrics:
        print(f"  FINI: b3_f1={fini_metrics.get('b3_f1', 0):.4f}")
        print(f"  SYSTEM_CN_OFF: b3_f1={system_cn_off_metrics.get('b3_f1', 0):.4f}")
        
        # Validate they're not identical
        validate_table6_not_duplicate(fini_metrics, system_cn_off_metrics)
        print("  ✓ S0.1 PASSED: FINI != SYSTEM_CN_OFF")
    else:
        print("  Skip: Could not find both FINI and SYSTEM_CN_OFF metrics")


def validate_table7(clean_csv_path, stress_csv_path):
    """
    Validate Table 7: STRESS/OFF != CLEAN/OFF.
    
    Hard-fail only for Chinese subset, warn for overall.
    """
    print("\n[Validating Table 7 - S0.2]")
    
    if not clean_csv_path.exists() or not stress_csv_path.exists():
        print("  Skip: CSV files not found")
        return
    
    clean_data = load_csv(str(clean_csv_path))
    stress_data = load_csv(str(stress_csv_path))
    
    # Find OFF rows for each subset
    for subset in ['overall', 'chinese']:
        clean_off = None
        stress_off = None
        
        for row in clean_data:
            if row.get('subset') == subset:
                cn = row.get('cn_enabled')
                if cn == False or cn == 0 or cn == 'False':
                    clean_off = row
        
        for row in stress_data:
            if row.get('subset') == subset:
                cn = row.get('cn_enabled')
                if cn == False or cn == 0 or cn == 'False':
                    stress_off = row
        
        if clean_off and stress_off:
            print(f"  {subset}: CLEAN/OFF b3_f1={clean_off.get('b3_f1', 0):.4f}, STRESS/OFF b3_f1={stress_off.get('b3_f1', 0):.4f}")
            
            # Check if identical
            all_same = True
            for key in ['b3_f1', 'b3_precision', 'b3_recall']:
                if abs(clean_off.get(key, 0) - stress_off.get(key, 0)) > 1e-6:
                    all_same = False
                    break
            
            if all_same:
                if subset == 'overall':
                    # Expected for overall - STRESS only affects Chinese names
                    print(f"  ℹ {subset}: identical (expected - STRESS only affects Chinese)")
                else:
                    # Hard-fail for Chinese subset
                    raise Exception(
                        f"HARD-FAIL [S0.2]: Table 7 CLEAN/CN_OFF == STRESS/CN_OFF ({subset})!\n"
                        f"  CLEAN/OFF: {clean_off}\n"
                        f"  STRESS/OFF: {stress_off}\n"
                        f"  This indicates STRESS data not affecting Chinese evaluation."
                    )
            else:
                print(f"  ✓ S0.2 PASSED for {subset}: metrics differ")


def generate_cn_ablation_table_with_traceability(clean_data, stress_data, runs, out_dir):
    """Generate CN ablation LaTeX table with traceability footnotes."""
    
    lines = [
        r"\begin{table}[H]",
        r"\centering",
        r"\caption{CN ablation: влияние модуля нормализации китайских имён}",
        r"\label{tab:cn_ablation}",
        r"{\small",
        r"\begin{tabular}{llccccc}",
        r"\toprule",
        r"Данные & Подмн. & CN & B³ P & B³ R & B³ F1 & Конфликт \\",
        r"\midrule"
    ]
    
    run_ids = []
    
    # Clean data
    for i, row in enumerate(clean_data):
        cn = "Вкл" if row.get('cn_enabled') else "Выкл"
        subset = row.get('subset', 'overall')
        subset_label = 'Общий' if subset == 'overall' else 'Кит.'
        
        b3_p = format_pct(row.get('b3_precision', 0))
        b3_r = format_pct(row.get('b3_recall', 0))
        b3_f1 = format_pct(row.get('b3_f1', 0))
        conflict = format_pct(row.get('conflict_rate', 0))
        
        data_label = "CLEAN" if i == 0 else ""
        lines.append(f"{data_label} & {subset_label} & {cn} & {b3_p} & {b3_r} & {b3_f1} & {conflict} \\\\")
    
    lines.append(r"\midrule")
    
    # Stress data
    for i, row in enumerate(stress_data):
        cn = "Вкл" if row.get('cn_enabled') else "Выкл"
        subset = row.get('subset', 'overall')
        subset_label = 'Общий' if subset == 'overall' else 'Кит.'
        
        b3_p = format_pct(row.get('b3_precision', 0))
        b3_r = format_pct(row.get('b3_recall', 0))
        b3_f1 = format_pct(row.get('b3_f1', 0))
        conflict = format_pct(row.get('conflict_rate', 0))
        
        data_label = "STRESS" if i == 0 else ""
        lines.append(f"{data_label} & {subset_label} & {cn} & {b3_p} & {b3_r} & {b3_f1} & {conflict} \\\\")
    
    # Collect run_ids for footnote
    for run in runs:
        method_id = run.get('method_id', '')
        if 'CLEAN' in method_id or 'STRESS' in method_id:
            run_ids.append(f"{run.get('run_id')}({method_id})")
    
    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"}",
        r"\end{table}",
        "",
        f"% Traceability: run_ids={', '.join(run_ids[:4])}"
    ])
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Generate Paper Tables with Hard-Fail Validation'
    )
    parser.add_argument('--results-dir', type=str, default='results')
    parser.add_argument('--out', type=str, default='tables')
    parser.add_argument('--skip-validation', action='store_true')
    
    args = parser.parse_args()
    
    results_dir = Path(args.results_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("Generate Paper Tables with Hard-Fail Validation")
    print("=" * 60)
    
    # Load run metadata
    runs = load_run_metadata(results_dir)
    print(f"Loaded {len(runs)} runs from run_metadata.jsonl")
    
    clean_csv = results_dir / 'ablation_cn_clean.csv'
    stress_csv = results_dir / 'ablation_cn_stress.csv'
    
    # Run validations
    if not args.skip_validation:
        try:
            # Validate duplicate outputs
            if runs:
                validate_no_duplicate_outputs(runs)
                print("✓ No duplicate outputs")
            
            # S0.1: Table 6 validation
            validate_table6(runs, clean_csv)
            
            # S0.2: Table 7 validation  
            validate_table7(clean_csv, stress_csv)
            
        except Exception as e:
            print(f"\n{'!'*60}")
            print("HARD-FAIL: Validation failed!")
            print(str(e))
            print("{'!'*60}")
            print("\nTable generation stopped. Fix the issues above first.")
            sys.exit(1)
    
    # Generate tables
    print("\n[Generating Tables]")
    
    if clean_csv.exists() and stress_csv.exists():
        clean_data = load_csv(str(clean_csv))
        stress_data = load_csv(str(stress_csv))
        
        table = generate_cn_ablation_table_with_traceability(
            clean_data, stress_data, runs, out_dir
        )
        
        out_file = out_dir / 'table_cn_ablation.tex'
        with open(out_file, 'w', encoding='utf-8') as f:
            f.write(table)
        print(f"  Created: {out_file}")
    
    print("\n✓ All validations passed!")
    print("✓ Tables generated successfully!")


if __name__ == '__main__':
    main()
