# -*- coding: utf-8 -*-
"""
完整评测脚本 / Полный скрипт оценки / Full Evaluation Script

测试二号项目的完整消歧流程，使用ORCID作为金标准进行评估
Тестирование полного процесса дизамбигуации с использованием ORCID в качестве золотого стандарта
"""

import json
import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any, Set, Tuple

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from models.author import Author
from models.database import AuthorDatabase
from disambiguation_engine.author_merger import AuthorMerger
from disambiguation_engine.similarity_scorer import SimilarityScorer
from disambiguation_engine.decision_types import Decision, DecisionResult
from disambiguation_engine.decision_trace import DecisionTraceLogger


def setup_logging(debug: bool = False) -> logging.Logger:
    """配置日志 / Настройка логирования"""
    logger = logging.getLogger('evaluation')
    level = logging.DEBUG if debug else logging.INFO
    logger.setLevel(level)
    
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(level)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


def load_crossref_data(file_path: str, limit: int = None) -> List[Dict[str, Any]]:
    """加载Crossref数据 / Загрузка данных Crossref"""
    path = Path(file_path)

    if path.suffix.lower() == '.jsonl':
        authors = []
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    authors.append(json.loads(line))
    else:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        authors = data.get('authors', data if isinstance(data, list) else [])

    for author in authors:
        if not author.get('original_name') and author.get('raw_name'):
            author['original_name'] = author['raw_name']
        if not author.get('surname') and author.get('lastname'):
            author['surname'] = author['lastname']
        if not author.get('journal') and author.get('venue'):
            author['journal'] = author['venue']

    if limit:
        authors = authors[:limit]
    
    return authors


def build_gold_set(authors: List[Dict[str, Any]], min_mentions: int = 2) -> Dict[str, Any]:
    """
    从作者数据构建ORCID金标准 / Построение золотого стандарта из данных авторов
    
    Returns:
        gold_set: {
            'orcid_to_mention_ids': {orcid: [mention_ids]},
            'mention_to_orcid': {mention_id: orcid},
            'mentions': {mention_id: author_data}
        }
    """
    orcid_clusters = defaultdict(list)
    mentions = {}
    
    for i, author in enumerate(authors):
        orcid = author.get('orcid', '')
        mention_id = i
        
        # 存储mention
        mentions[mention_id] = author
        
        # 如果有ORCID，加入cluster
        if orcid:
            orcid_clusters[orcid].append(mention_id)
    
    # 过滤：只保留有 >= min_mentions 的ORCID
    filtered_clusters = {
        orcid: mention_ids 
        for orcid, mention_ids in orcid_clusters.items() 
        if len(mention_ids) >= min_mentions
    }
    
    # 构建反向映射
    mention_to_orcid = {}
    for orcid, mention_ids in filtered_clusters.items():
        for mid in mention_ids:
            mention_to_orcid[mid] = orcid
    
    return {
        'orcid_to_mention_ids': filtered_clusters,
        'mention_to_orcid': mention_to_orcid,
        'mentions': mentions,
        'stats': {
            'total_mentions': len(authors),
            'mentions_with_orcid': sum(1 for a in authors if a.get('orcid')),
            'unique_orcids': len(orcid_clusters),
            'filtered_orcids': len(filtered_clusters),
            'mentions_in_gold_set': len(mention_to_orcid)
        }
    }


def run_disambiguation(
    authors: List[Dict[str, Any]],
    gold_set: Dict[str, Any],
    config: Dict[str, Any],
    logger: logging.Logger
) -> Tuple[Dict[str, List[int]], Dict[str, Any]]:
    """
    运行消歧算法 / Запуск алгоритма дизамбигуации
    
    Returns:
        predicted_clusters: {cluster_id: [mention_ids]}
        stats: 统计信息 / Статистика
    """
    # 初始化组件
    database = AuthorDatabase()
    merger = AuthorMerger(
        database=database,
        accept_threshold=config.get('accept_threshold', 0.90),
        reject_threshold=config.get('reject_threshold', 0.20),
        mode=config.get('mode', 'baseline')
    )
    
    # 统计
    stats = {
        'total_processed': 0,
        'merge_decisions': 0,
        'new_decisions': 0,
        'unknown_decisions': 0,
    }
    
    # 预测的clusters: author_id -> [mention_ids]
    predicted_clusters = defaultdict(list)
    mention_to_predicted = {}  # mention_id -> predicted_cluster_id
    
    # 只处理金标准中的mentions
    gold_mention_ids = set(gold_set['mention_to_orcid'].keys())
    
    logger.info(f"开始消歧处理 / Начало дизамбигуации: {len(gold_mention_ids)} mentions")
    
    for i, author_data in enumerate(authors):
        mention_id = i
        
        # 只处理金标准中的mentions
        if mention_id not in gold_mention_ids:
            continue
        
        stats['total_processed'] += 1
        
        # 构建mention字典
        mention = {
            'name': author_data.get('original_name', ''),
            'surname': author_data.get('surname', ''),
            'firstname': author_data.get('firstname', ''),
            'orcid': author_data.get('orcid', ''),
            'affiliation': [author_data.get('affiliation', '')] if author_data.get('affiliation') else [],
            'doi': author_data.get('doi', ''),
            'journals': [author_data.get('journal', '')] if author_data.get('journal') else [],
            'coauthors': author_data.get('coauthors', []) if isinstance(author_data.get('coauthors'), list) else [],
        }
        
        # 运行三分决策
        result = merger.make_decision(mention)
        
        if result.decision == Decision.MERGE:
            stats['merge_decisions'] += 1
            cluster_id = result.best_author_id
            predicted_clusters[cluster_id].append(mention_id)
            mention_to_predicted[mention_id] = cluster_id
        elif result.decision == Decision.NEW:
            stats['new_decisions'] += 1
            # 创建新author
            new_author = database.add_author({
                'canonical_name': mention['name'],
                'surnames': [mention.get('surname', '')],
                'orcid': mention.get('orcid', ''),
                'affiliations': mention.get('affiliation', []),
            })
            cluster_id = new_author.author_id
            predicted_clusters[cluster_id].append(mention_id)
            mention_to_predicted[mention_id] = cluster_id
        else:  # UNKNOWN
            stats['unknown_decisions'] += 1
            # UNKNOWN: 创建临时cluster（保守策略）
            temp_cluster_id = f"unknown_{mention_id}"
            predicted_clusters[temp_cluster_id].append(mention_id)
            mention_to_predicted[mention_id] = temp_cluster_id
        
        # 进度日志
        if stats['total_processed'] % 5000 == 0:
            logger.info(f"  已处理 / Обработано: {stats['total_processed']}")
    
    logger.info(f"消歧完成 / Дизамбигуация завершена:")
    logger.info(f"  - MERGE: {stats['merge_decisions']}")
    logger.info(f"  - NEW: {stats['new_decisions']}")
    logger.info(f"  - UNKNOWN: {stats['unknown_decisions']}")
    logger.info(f"  - Predicted clusters: {len(predicted_clusters)}")
    
    stats['mention_to_predicted'] = mention_to_predicted
    
    return dict(predicted_clusters), stats


def evaluate_bcubed(
    gold_set: Dict[str, Any],
    mention_to_predicted: Dict[int, str]
) -> Dict[str, float]:
    """
    计算B³ F1 / Вычисление B³ F1
    
    B³ precision: 对每个mention，计算其predicted cluster中属于同一gold cluster的比例
    B³ recall: 对每个mention，计算其gold cluster中被分到同一predicted cluster的比例
    """
    mention_to_gold = gold_set['mention_to_orcid']
    
    # 只评估有gold label的mentions
    mentions_to_eval = [m for m in mention_to_gold.keys() if m in mention_to_predicted]
    
    if not mentions_to_eval:
        return {'precision': 0.0, 'recall': 0.0, 'f1': 0.0}
    
    # 构建反向索引
    gold_clusters = gold_set['orcid_to_mention_ids']
    
    predicted_clusters_inv = defaultdict(set)
    for mid, cid in mention_to_predicted.items():
        predicted_clusters_inv[cid].add(mid)
    
    total_precision = 0.0
    total_recall = 0.0
    
    for mention_id in mentions_to_eval:
        gold_orcid = mention_to_gold[mention_id]
        pred_cluster_id = mention_to_predicted[mention_id]
        
        # 同一gold cluster的所有mentions
        gold_cluster_mentions = set(gold_clusters[gold_orcid])
        
        # 同一predicted cluster的所有mentions
        pred_cluster_mentions = predicted_clusters_inv[pred_cluster_id]
        
        # B³ precision: |intersection with gold| / |predicted cluster中有gold label的|
        pred_with_gold = pred_cluster_mentions & set(mention_to_gold.keys())
        if pred_with_gold:
            intersection = pred_cluster_mentions & gold_cluster_mentions
            precision_i = len(intersection) / len(pred_with_gold)
        else:
            precision_i = 0.0
        
        # B³ recall: |intersection with predicted| / |gold cluster|
        intersection = pred_cluster_mentions & gold_cluster_mentions
        recall_i = len(intersection) / len(gold_cluster_mentions)
        
        total_precision += precision_i
        total_recall += recall_i
    
    n = len(mentions_to_eval)
    precision = total_precision / n
    recall = total_recall / n
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    
    return {
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'evaluated_mentions': n
    }


def evaluate_pairwise(
    gold_set: Dict[str, Any],
    mention_to_predicted: Dict[int, str]
) -> Dict[str, Any]:
    """
    计算Pairwise F1 / Вычисление pairwise F1
    """
    mention_to_gold = gold_set['mention_to_orcid']
    gold_clusters = gold_set['orcid_to_mention_ids']
    
    # 只评估有gold label的mentions
    mentions_to_eval = set(m for m in mention_to_gold.keys() if m in mention_to_predicted)
    
    if len(mentions_to_eval) < 2:
        return {'precision': 0.0, 'recall': 0.0, 'f1': 0.0, 'tp': 0, 'fp': 0, 'fn': 0}
    
    # 生成gold pairs
    gold_pairs = set()
    for orcid, mention_ids in gold_clusters.items():
        mention_ids_in_eval = [m for m in mention_ids if m in mentions_to_eval]
        for i in range(len(mention_ids_in_eval)):
            for j in range(i + 1, len(mention_ids_in_eval)):
                pair = (min(mention_ids_in_eval[i], mention_ids_in_eval[j]),
                       max(mention_ids_in_eval[i], mention_ids_in_eval[j]))
                gold_pairs.add(pair)
    
    # 生成predicted pairs
    predicted_clusters_inv = defaultdict(list)
    for mid, cid in mention_to_predicted.items():
        if mid in mentions_to_eval:
            predicted_clusters_inv[cid].append(mid)
    
    pred_pairs = set()
    for cid, mention_ids in predicted_clusters_inv.items():
        for i in range(len(mention_ids)):
            for j in range(i + 1, len(mention_ids)):
                pair = (min(mention_ids[i], mention_ids[j]),
                       max(mention_ids[i], mention_ids[j]))
                pred_pairs.add(pair)
    
    # TP, FP, FN
    tp = len(gold_pairs & pred_pairs)
    fp = len(pred_pairs - gold_pairs)
    fn = len(gold_pairs - pred_pairs)
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    
    return {
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'tp': tp,
        'fp': fp,
        'fn': fn,
        'gold_pairs': len(gold_pairs),
        'pred_pairs': len(pred_pairs)
    }


def main():
    parser = argparse.ArgumentParser(
        description='二号项目完整评测 / Полная оценка проекта №2'
    )
    parser.add_argument(
        '--data-file',
        type=str,
        default=r'C:\istina\materia 材料\测试表单\crossref.json',
        help='Crossref数据文件 / Файл данных Crossref'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=50000,
        help='限制处理的作者数 / Лимит авторов для обработки'
    )
    parser.add_argument(
        '--min-mentions',
        type=int,
        default=2,
        help='最小ORCID mentions数 / Минимум упоминаний на ORCID'
    )
    parser.add_argument(
        '--mode',
        type=str,
        choices=['baseline', 'fs'],
        default='baseline',
        help='评分模式 / Режим оценки: baseline (加权) или fs (Fellegi-Sunter)'
    )
    parser.add_argument(
        '--accept-threshold',
        type=float,
        default=0.90,
        help='MERGE阈值 / Порог MERGE'
    )
    parser.add_argument(
        '--reject-threshold',
        type=float,
        default=0.20,
        help='NEW阈值 / Порог NEW'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='test_results/evaluation_results.json',
        help='输出结果文件 / Файл результатов'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Debug模式 / Режим отладки'
    )
    
    args = parser.parse_args()
    logger = setup_logging(args.debug)
    
    print("=" * 80)
    print("二号项目评测 / Оценка проекта №2")
    print("Incremental Author Disambiguation - Evaluation")
    print("=" * 80)
    
    # 1. 加载数据
    logger.info(f"加载数据 / Загрузка данных: {args.data_file}")
    authors = load_crossref_data(args.data_file, limit=args.limit)
    logger.info(f"加载了 {len(authors)} 条作者记录 / Загружено записей авторов: {len(authors)}")
    
    # 2. 构建金标准
    logger.info("构建ORCID金标准 / Построение золотого стандарта ORCID...")
    gold_set = build_gold_set(authors, min_mentions=args.min_mentions)
    
    print("\n【ORCID金标准统计 / Статистика золотого стандарта】")
    print(f"  总mentions: {gold_set['stats']['total_mentions']}")
    print(f"  有ORCID的mentions: {gold_set['stats']['mentions_with_orcid']}")
    print(f"  唯一ORCID数: {gold_set['stats']['unique_orcids']}")
    print(f"  过滤后ORCID (>={args.min_mentions} mentions): {gold_set['stats']['filtered_orcids']}")
    print(f"  金标准mention总数: {gold_set['stats']['mentions_in_gold_set']}")
    
    # 3. 运行消歧
    logger.info("\n运行消歧算法 / Запуск алгоритма дизамбигуации...")
    config = {
        'mode': args.mode,
        'accept_threshold': args.accept_threshold,
        'reject_threshold': args.reject_threshold,
    }
    
    start_time = datetime.now()
    predicted_clusters, disamb_stats = run_disambiguation(authors, gold_set, config, logger)
    elapsed = (datetime.now() - start_time).total_seconds()
    
    print(f"\n【消歧统计 / Статистика дизамбигуации】")
    print(f"  处理时间 / Время обработки: {elapsed:.2f}s")
    print(f"  总处理mentions: {disamb_stats['total_processed']}")
    print(f"  MERGE决策: {disamb_stats['merge_decisions']}")
    print(f"  NEW决策: {disamb_stats['new_decisions']}")
    print(f"  UNKNOWN决策: {disamb_stats['unknown_decisions']}")
    print(f"  预测clusters数: {len(predicted_clusters)}")
    
    # 4. 评测
    logger.info("\n评测消歧结果 / Оценка результатов дизамбигуации...")
    
    bcubed = evaluate_bcubed(gold_set, disamb_stats['mention_to_predicted'])
    pairwise = evaluate_pairwise(gold_set, disamb_stats['mention_to_predicted'])
    
    print("\n" + "=" * 80)
    print("【评测结果 / Результаты оценки / Evaluation Results】")
    print("=" * 80)
    
    print(f"\n📊 B³ F1 指标 / Метрики B³ F1:")
    print(f"  Precision: {bcubed['precision']:.4f}")
    print(f"  Recall:    {bcubed['recall']:.4f}")
    print(f"  F1:        {bcubed['f1']:.4f}")
    
    print(f"\n📊 Pairwise 指标 / Метрики pairwise:")
    print(f"  Precision: {pairwise['precision']:.4f}")
    print(f"  Recall:    {pairwise['recall']:.4f}")
    print(f"  F1:        {pairwise['f1']:.4f}")
    print(f"  TP: {pairwise['tp']}, FP: {pairwise['fp']}, FN: {pairwise['fn']}")
    print(f"  Gold pairs: {pairwise['gold_pairs']}, Predicted pairs: {pairwise['pred_pairs']}")
    
    print("=" * 80)
    
    # 5. 保存结果
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    results = {
        'metadata': {
            'timestamp': datetime.now().isoformat(),
            'data_file': args.data_file,
            'limit': args.limit,
            'min_mentions': args.min_mentions,
            'mode': args.mode,
            'accept_threshold': args.accept_threshold,
            'reject_threshold': args.reject_threshold,
            'elapsed_seconds': elapsed,
        },
        'gold_set_stats': gold_set['stats'],
        'disambiguation_stats': {
            'total_processed': disamb_stats['total_processed'],
            'merge_decisions': disamb_stats['merge_decisions'],
            'new_decisions': disamb_stats['new_decisions'],
            'unknown_decisions': disamb_stats['unknown_decisions'],
            'predicted_clusters': len(predicted_clusters),
        },
        'evaluation': {
            'bcubed': bcubed,
            'pairwise': pairwise,
        }
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    logger.info(f"\n结果已保存 / Результаты сохранены: {output_path}")
    
    print(f"\n✅ 评测完成 / Оценка завершена!")
    print(f"   结果文件 / Файл результатов: {output_path}")


if __name__ == '__main__':
    main()
