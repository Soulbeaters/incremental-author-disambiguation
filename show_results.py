# -*- coding: utf-8 -*-
import json

with open('test_results/ablation_study_results.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print("="*70)
print("消融实验结果汇总")
print("="*70)

for r in data['results']:
    method = r['method']
    precision = r.get('precision', 0) * 100
    recall = r.get('recall', 0) * 100
    f1 = r.get('f1', 0) * 100
    correct = r.get('correct', 0)
    wrong = r.get('wrong', 0)
    total = r.get('total', 0)
    
    print(f"\n{method}")
    print(f"  Precision: {precision:.2f}%")
    print(f"  Recall:    {recall:.2f}%")
    print(f"  F1:        {f1:.2f}%")
    print(f"  Correct:   {correct}")
    print(f"  Wrong:     {wrong}")
    print(f"  Total:     {total}")

print("\n" + "="*70)
