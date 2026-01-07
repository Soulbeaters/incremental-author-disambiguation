# -*- coding: utf-8 -*-
"""
模拟真实场景的评测脚本 / Скрипт оценки с моделированием реальных условий
Simulates real-world scenario: initialize database then process new mentions

使用场景：
1. 前50%的ORCID mentions用于初始化数据库
2. 后50%的mentions用于评测消歧效果
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
from disambiguation_engine.decision_types import Decision


def setup_logging(debug: bool = False) -> logging.Logger:
    logger = logging.getLogger('eval_v2')
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
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    authors = data.get('authors', [])
    if limit:
        authors = authors[:limit]
    
    return authors


def main():
    parser = argparse.ArgumentParser(
        description='真实场景评测 / Оценка в реальных условиях'
    )
    parser.add_argument(
        '--data-file',
        type=str,
        default=r'C:\istina\materia 材料\测试表单\crossref.json',
        help='Crossref数据文件'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=100000,
        help='总作者记录限制'
    )
    parser.add_argument(
        '--init-ratio',
        type=float,
        default=0.5,
        help='用于初始化的数据比例'
    )
    parser.add_argument(
        '--min-mentions',
        type=int,
        default=2,
        help='最小ORCID mentions数'
    )
    parser.add_argument(
        '--mode',
        type=str,
        choices=['baseline', 'fs'],
        default='baseline',
        help='评分模式'
    )
    parser.add_argument(
        '--accept-threshold',
        type=float,
        default=0.85,
        help='MERGE阈值'
    )
    parser.add_argument(
        '--reject-threshold',
        type=float,
        default=0.25,
        help='NEW阈值'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='test_results/evaluation_realistic.json',
        help='输出结果文件'
    )
    parser.add_argument('--debug', action='store_true')
    
    args = parser.parse_args()
    logger = setup_logging(args.debug)
    
    print("=" * 80)
    print("二号项目 - 真实场景评测 / Realistic Scenario Evaluation")
    print("=" * 80)
    
    # 加载数据
    logger.info(f"加载数据: {args.data_file}")
    authors = load_crossref_data(args.data_file, limit=args.limit)
    logger.info(f"加载 {len(authors)} 条记录")
    
    # 按ORCID分组
    orcid_groups = defaultdict(list)
    for i, author in enumerate(authors):
        orcid = author.get('orcid', '')
        if orcid:
            orcid_groups[orcid].append((i, author))
    
    # 过滤：只处理有>=min_mentions的ORCID
    valid_orcids = {k: v for k, v in orcid_groups.items() if len(v) >= args.min_mentions}
    
    print(f"\n【数据统计】")
    print(f"  总记录数: {len(authors)}")
    print(f"  有ORCID的唯一值: {len(orcid_groups)}")
    print(f"  有效ORCID (>={args.min_mentions} mentions): {len(valid_orcids)}")
    
    # 划分数据：每个ORCID的前半部分用于初始化，后半部分用于评测
    init_mentions = []
    eval_mentions = []
    
    for orcid, mention_list in valid_orcids.items():
        split_idx = max(1, int(len(mention_list) * args.init_ratio))
        init_mentions.extend(mention_list[:split_idx])
        eval_mentions.extend(mention_list[split_idx:])
    
    print(f"  初始化mentions: {len(init_mentions)}")
    print(f"  评测mentions: {len(eval_mentions)}")
    
    # 初始化数据库
    logger.info("\n初始化作者数据库...")
    database = AuthorDatabase()
    
    orcid_to_author_id = {}  # ORCID -> database author_id 映射
    
    for idx, author_data in init_mentions:
        orcid = author_data.get('orcid', '')
        
        if orcid not in orcid_to_author_id:
            # 首次见到此ORCID，创建新作者
            new_author = database.add_author({
                'name': author_data.get('original_name', ''),
                'orcid': orcid,
                'affiliation': [author_data.get('affiliation', '')] if author_data.get('affiliation') else [],
                'journals': [author_data.get('journal', '')] if author_data.get('journal') else [],
            })
            orcid_to_author_id[orcid] = new_author.author_id
        else:
            # 已有此ORCID的作者，更新其信息
            existing_id = orcid_to_author_id[orcid]
            existing_author = database.find_by_id(existing_id)
            if existing_author:
                if author_data.get('journal'):
                    existing_author.journals.add(author_data.get('journal'))
                if author_data.get('affiliation'):
                    existing_author.affiliations.add(author_data.get('affiliation'))
    
    print(f"  数据库作者数: {database.get_author_count()}")
    
    # 运行消歧评测
    logger.info("\n运行消歧评测...")
    
    merger = AuthorMerger(
        database=database,
        accept_threshold=args.accept_threshold,
        reject_threshold=args.reject_threshold,
        mode=args.mode
    )
    
    stats = {
        'total': len(eval_mentions),
        'merge': 0,
        'new': 0,
        'unknown': 0,
        'correct_merge': 0,  # MERGE且正确
        'wrong_merge': 0,    # MERGE但错误
    }
    
    start_time = datetime.now()
    
    for idx, author_data in eval_mentions:
        orcid = author_data.get('orcid', '')
        gold_author_id = orcid_to_author_id.get(orcid)
        
        mention = {
            'name': author_data.get('original_name', ''),
            'surname': author_data.get('lastname', ''),
            'firstname': author_data.get('firstname', ''),
            'orcid': author_data.get('orcid', ''),
            'affiliation': [author_data.get('affiliation', '')] if author_data.get('affiliation') else [],
            'journals': [author_data.get('journal', '')] if author_data.get('journal') else [],
        }
        
        result = merger.make_decision(mention)
        
        if result.decision == Decision.MERGE:
            stats['merge'] += 1
            if result.best_author_id == gold_author_id:
                stats['correct_merge'] += 1
            else:
                stats['wrong_merge'] += 1
        elif result.decision == Decision.NEW:
            stats['new'] += 1
        else:
            stats['unknown'] += 1
    
    elapsed = (datetime.now() - start_time).total_seconds()
    
    # 计算指标
    precision = stats['correct_merge'] / stats['merge'] if stats['merge'] > 0 else 0.0
    recall = stats['correct_merge'] / stats['total'] if stats['total'] > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    
    print("\n" + "=" * 80)
    print("【评测结果 / Evaluation Results】")
    print("=" * 80)
    
    print(f"\n📊 决策统计:")
    print(f"  评测mentions: {stats['total']}")
    print(f"  MERGE: {stats['merge']} ({100*stats['merge']/stats['total']:.1f}%)")
    print(f"  NEW: {stats['new']} ({100*stats['new']/stats['total']:.1f}%)")
    print(f"  UNKNOWN: {stats['unknown']} ({100*stats['unknown']/stats['total']:.1f}%)")
    
    print(f"\n📊 MERGE质量:")
    print(f"  正确MERGE: {stats['correct_merge']}")
    print(f"  错误MERGE: {stats['wrong_merge']}")
    print(f"  Precision: {precision:.4f}")
    print(f"  Recall: {recall:.4f}")
    print(f"  F1: {f1:.4f}")
    
    print(f"\n⏱️ 性能:")
    print(f"  处理时间: {elapsed:.2f}s")
    print(f"  速度: {stats['total']/elapsed:.1f} mentions/s")
    
    print("=" * 80)
    
    # 保存结果
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    results = {
        'metadata': {
            'timestamp': datetime.now().isoformat(),
            'data_file': args.data_file,
            'limit': args.limit,
            'init_ratio': args.init_ratio,
            'mode': args.mode,
            'accept_threshold': args.accept_threshold,
            'reject_threshold': args.reject_threshold,
            'elapsed_seconds': elapsed,
        },
        'data_stats': {
            'total_records': len(authors),
            'valid_orcids': len(valid_orcids),
            'init_mentions': len(init_mentions),
            'eval_mentions': len(eval_mentions),
            'database_authors': database.get_author_count(),
        },
        'decision_stats': stats,
        'metrics': {
            'precision': precision,
            'recall': recall,
            'f1': f1,
        }
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 结果已保存: {output_path}")


if __name__ == '__main__':
    main()
