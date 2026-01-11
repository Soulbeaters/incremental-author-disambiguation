# -*- coding: utf-8 -*-
"""
完整论文实验脚本 v2 / Full Paper Experiments Script v2

修复版本：正确分割数据为初始化集和评估集

运行实验：
1. 用50%数据初始化作者库
2. 用剩余50%评估消歧性能
3. 阈值敏感性分析
4. 输出论文用表格

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
from disambiguation_engine.decision_types import Decision


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger('experiments')


def load_data(file_path: str, limit: int = None) -> List[Dict]:
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    authors = data.get('authors', data)
    if limit:
        authors = authors[:limit]
    return authors


def split_by_orcid(authors: List[Dict], init_ratio: float = 0.5, seed: int = 42) -> Dict:
    """按ORCID分组并分割为初始化集和评估集"""
    random.seed(seed)
    
    # 按ORCID分组
    orcid_groups = defaultdict(list)
    for i, author in enumerate(authors):
        orcid = author.get('orcid', '')
        if orcid:
            orcid_groups[orcid].append((i, author))
    
    # 只保留有>=2条记录的ORCID
    valid_groups = {k: v for k, v in orcid_groups.items() if len(v) >= 2}
    
    init_set = []  # (index, author_data, orcid)
    eval_set = []
    
    for orcid, records in valid_groups.items():
        random.shuffle(records)
        split_point = max(1, int(len(records) * init_ratio))
        
        for idx, author in records[:split_point]:
            init_set.append((idx, author, orcid))
        for idx, author in records[split_point:]:
            eval_set.append((idx, author, orcid))
    
    return {
        'init_set': init_set,
        'eval_set': eval_set,
        'total_orcids': len(valid_groups),
        'init_count': len(init_set),
        'eval_count': len(eval_set),
    }


def run_experiment(
    init_set: List,
    eval_set: List,
    mode: str,
    accept_threshold: float,
    reject_threshold: float,
    logger: logging.Logger = None
) -> Dict:
    """运行单次实验"""
    # 初始化数据库
    db = AuthorDatabase()
    
    # 用初始化集建立作者库
    orcid_to_author_id = {}
    for idx, author_data, orcid in init_set:
        name = author_data.get('original_name', '')
        lastname = author_data.get('lastname', '')  # 修复：使用lastname
        
        if orcid not in orcid_to_author_id:
            # 创建新作者 - 使用'name'键而不是'canonical_name'
            new_author = db.add_author({
                'name': name,  # 修复：database.add_author使用'name'键
                'orcid': orcid,
                'journals': [author_data.get('journal', '')] if author_data.get('journal') else [],
                'affiliations': [author_data.get('affiliation', '')] if author_data.get('affiliation') else [],
            })
            orcid_to_author_id[orcid] = new_author.author_id
        else:
            # 合并到现有作者
            existing = db.find_by_id(orcid_to_author_id[orcid])
            if existing:
                if lastname:
                    existing.alternate_names.add(name)
                if author_data.get('journal'):
                    existing.journals.add(author_data['journal'])
    
    # 创建merger
    merger = AuthorMerger(
        database=db,
        accept_threshold=accept_threshold,
        reject_threshold=reject_threshold,
        mode=mode
    )
    
    # 评估
    stats = {'merge': 0, 'new': 0, 'unknown': 0, 'correct': 0, 'wrong': 0}
    
    for idx, author_data, true_orcid in eval_set:
        mention = {
            'name': author_data.get('original_name', ''),
            'surname': author_data.get('lastname', ''),  # 修复：使用lastname
            'orcid': '',  # 不提供ORCID（真实场景）
            'coauthors': author_data.get('coauthors', []) or [],
            'journals': [author_data.get('journal', '')] if author_data.get('journal') else [],
            'affiliation': [author_data.get('affiliation', '')] if author_data.get('affiliation') else [],
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
            # NEW决策：如果这个ORCID在库中存在，则是错误的
            if true_orcid in orcid_to_author_id:
                stats['wrong'] += 1
            else:
                stats['correct'] += 1
        else:  # UNKNOWN
            stats['unknown'] += 1
    
    # 计算指标
    total = len(eval_set)
    merge_attempts = stats['merge']
    
    # Precision: 在MERGE决策中，正确的比例
    precision = stats['correct'] / (stats['correct'] + stats['wrong']) if (stats['correct'] + stats['wrong']) > 0 else 0
    
    # Recall: 应该MERGE的里面，实际MERGE的比例
    # 因为所有eval_set的ORCID都在init_set中有，所以理想情况应该全部MERGE
    expected_merges = len(eval_set)
    recall = stats['correct'] / expected_merges if expected_merges > 0 else 0
    
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
        **stats,
        'total': total,
        'db_size': len(db.authors)
    }


def run_threshold_sweep(init_set, eval_set, mode: str, logger) -> List[Dict]:
    """阈值扫描"""
    results = []
    
    if mode == 'baseline':
        accepts = [0.95, 0.90, 0.85, 0.80, 0.75, 0.70, 0.65, 0.60, 0.55, 0.50, 0.45, 0.40]
        rejects = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35]
    else:
        accepts = [6.0, 5.0, 4.0, 3.0, 2.5, 2.0, 1.5, 1.0, 0.5, 0.0]
        rejects = [-4.0, -3.0, -2.0, -1.0, 0.0]
    
    total = sum(1 for a in accepts for r in rejects if r < a)
    current = 0
    
    for accept in accepts:
        for reject in rejects:
            if reject >= accept:
                continue
            current += 1
            logger.info(f"  [{current}/{total}] {mode}: accept={accept}, reject={reject}")
            
            result = run_experiment(init_set, eval_set, mode, accept, reject, logger)
            results.append(result)
            
            logger.info(f"    P={result['precision']:.3f}, R={result['recall']:.3f}, F1={result['f1']:.3f}, Unk={result['unknown_rate']:.1%}")
    
    return results


def main():
    logger = setup_logging()
    
    print("=" * 80)
    print("二号项目完整论文实验 v2 / Project Two Full Paper Experiments v2")
    print("=" * 80)
    
    data_file = r'C:\istina\materia 材料\测试表单\crossref.json'
    output_dir = project_root / 'test_results' / 'paper_experiments'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    limit = 100000  # 使用更多数据
    
    # 1. 加载数据
    logger.info(f"Loading data...")
    authors = load_data(data_file, limit=limit)
    logger.info(f"Loaded {len(authors)} authors")
    
    # 2. 分割数据
    logger.info("Splitting data by ORCID...")
    split = split_by_orcid(authors, init_ratio=0.5, seed=42)
    logger.info(f"Init set: {split['init_count']}, Eval set: {split['eval_count']}, ORCIDs: {split['total_orcids']}")
    
    all_results = {
        'metadata': {
            'timestamp': datetime.now().isoformat(),
            'data_file': data_file,
            'limit': limit,
            'init_count': split['init_count'],
            'eval_count': split['eval_count'],
            'total_orcids': split['total_orcids'],
            'init_ratio': 0.5,
            'seed': 42,
        },
        'baseline': [],
        'fs': [],
    }
    
    # 3. Baseline阈值扫描
    logger.info("\n" + "=" * 60)
    logger.info("BASELINE MODE THRESHOLD SWEEP")
    logger.info("=" * 60)
    all_results['baseline'] = run_threshold_sweep(split['init_set'], split['eval_set'], 'baseline', logger)
    
    # 4. FS阈值扫描
    logger.info("\n" + "=" * 60)
    logger.info("FELLEGI-SUNTER MODE THRESHOLD SWEEP")
    logger.info("=" * 60)
    all_results['fs'] = run_threshold_sweep(split['init_set'], split['eval_set'], 'fs', logger)
    
    # 5. 找最优
    best_baseline = max(all_results['baseline'], key=lambda x: x['f1'])
    best_fs = max(all_results['fs'], key=lambda x: x['f1'])
    all_results['best'] = {'baseline': best_baseline, 'fs': best_fs}
    
    # 6. 保存
    results_file = output_dir / 'full_experiments_v2.json'
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    logger.info(f"\nResults saved to: {results_file}")
    
    # 7. 打印总结
    print("\n" + "=" * 80)
    print("EXPERIMENT RESULTS SUMMARY")
    print("=" * 80)
    
    print(f"\nData: {split['eval_count']} eval mentions, {split['total_orcids']} ORCIDs")
    
    print(f"\n【Best Baseline】 accept={best_baseline['accept_threshold']}, reject={best_baseline['reject_threshold']}")
    print(f"  Precision: {best_baseline['precision']:.4f}")
    print(f"  Recall:    {best_baseline['recall']:.4f}")
    print(f"  F1:        {best_baseline['f1']:.4f}")
    print(f"  Unknown:   {best_baseline['unknown_rate']:.2%}")
    
    print(f"\n【Best FS】 accept={best_fs['accept_threshold']}, reject={best_fs['reject_threshold']}")
    print(f"  Precision: {best_fs['precision']:.4f}")
    print(f"  Recall:    {best_fs['recall']:.4f}")
    print(f"  F1:        {best_fs['f1']:.4f}")
    print(f"  Unknown:   {best_fs['unknown_rate']:.2%}")
    
    print("\n" + "=" * 80)


if __name__ == '__main__':
    main()
