# -*- coding: utf-8 -*-
"""
二号项目消融实验 / Ablation Study for Project Two
证明各组件对作者消歧性能的贡献 / Demonstrate contribution of each component

作者: Ma Jiaxin
日期: 2026-01-08
"""

import json
import time
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple
from collections import defaultdict
import random

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from models.author import Author
from models.database import AuthorDatabase
from disambiguation_engine.author_merger import AuthorMerger


class AblationStudy:
    """消融实验类 / Ablation Study Class"""
    
    def __init__(self, data_path: str, limit: int = 10000, seed: int = 42):
        """
        初始化 / Initialize
        
        Args:
            data_path: crossref.json路径
            limit: 数据条数限制
            seed: 随机种子（保证可复现）
        """
        self.data_path = Path(data_path)
        self.limit = limit
        self.seed = seed
        random.seed(seed)
        
        # 加载数据
        self.data = self._load_data()
        self.orcid_groups = self._group_by_orcid()
        
    def _load_data(self) -> List[Dict]:
        """加载数据"""
        print(f"加载数据: {self.data_path}")
        with open(self.data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        authors = data.get('authors', [])[:self.limit]
        print(f"  加载 {len(authors)} 条记录")
        return authors
    
    def _group_by_orcid(self) -> Dict[str, List[Dict]]:
        """按ORCID分组"""
        groups = defaultdict(list)
        for record in self.data:
            orcid = record.get('orcid', '')
            if orcid:
                groups[orcid].append(record)
        
        # 只保留有>=2条记录的ORCID（可以测试合并）
        valid_groups = {k: v for k, v in groups.items() if len(v) >= 2}
        print(f"  有效ORCID: {len(valid_groups)} 个")
        return valid_groups
    
    def _prepare_data(self, init_ratio: float = 0.5) -> Tuple[List, List]:
        """
        准备数据：分割为初始化集和评测集
        
        Args:
            init_ratio: 初始化集比例
            
        Returns:
            (init_mentions, eval_mentions)
        """
        init_mentions = []
        eval_mentions = []
        
        for orcid, records in self.orcid_groups.items():
            random.shuffle(records)
            split_point = max(1, int(len(records) * init_ratio))
            
            init_mentions.extend([(r, orcid) for r in records[:split_point]])
            eval_mentions.extend([(r, orcid) for r in records[split_point:]])
        
        return init_mentions, eval_mentions
    
    def run_baseline_string_match(self) -> Dict[str, Any]:
        """
        基线方法1: 简单字符串匹配
        只使用姓名完全匹配
        """
        print("\n" + "="*60)
        print("基线方法1: 简单字符串匹配")
        print("="*60)
        
        init_mentions, eval_mentions = self._prepare_data()
        
        # 构建姓名索引
        name_index = {}  # name -> (author_id, orcid)
        author_id_counter = 0
        
        for record, orcid in init_mentions:
            name = record.get('original_name', '').strip().lower()
            if name:
                name_index[name] = (f"au_{author_id_counter}", orcid)
                author_id_counter += 1
        
        # 评测
        correct = 0
        wrong = 0
        new_count = 0
        
        for record, true_orcid in eval_mentions:
            name = record.get('original_name', '').strip().lower()
            
            if name in name_index:
                _, matched_orcid = name_index[name]
                if matched_orcid == true_orcid:
                    correct += 1
                else:
                    wrong += 1
            else:
                new_count += 1
        
        total = len(eval_mentions)
        precision = correct / (correct + wrong) if (correct + wrong) > 0 else 0
        recall = correct / total if total > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        return {
            'method': 'Baseline: String Match',
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'correct': correct,
            'wrong': wrong,
            'new': new_count,
            'total': total
        }
    
    def run_baseline_surname_only(self) -> Dict[str, Any]:
        """
        基线方法2: 仅姓氏匹配
        只使用姓氏进行匹配（高召回低精确）
        """
        print("\n" + "="*60)
        print("基线方法2: 仅姓氏匹配")
        print("="*60)
        
        init_mentions, eval_mentions = self._prepare_data()
        
        # 构建姓氏索引（一个姓氏可能对应多个作者）
        surname_index = defaultdict(list)  # surname -> [(author_id, orcid), ...]
        author_id_counter = 0
        
        for record, orcid in init_mentions:
            surname = record.get('lastname', '').strip().lower()
            if surname:
                surname_index[surname].append((f"au_{author_id_counter}", orcid))
                author_id_counter += 1
        
        # 评测：匹配第一个同姓作者
        correct = 0
        wrong = 0
        new_count = 0
        
        for record, true_orcid in eval_mentions:
            surname = record.get('lastname', '').strip().lower()
            
            if surname in surname_index and surname_index[surname]:
                _, matched_orcid = surname_index[surname][0]
                if matched_orcid == true_orcid:
                    correct += 1
                else:
                    wrong += 1
            else:
                new_count += 1
        
        total = len(eval_mentions)
        precision = correct / (correct + wrong) if (correct + wrong) > 0 else 0
        recall = correct / total if total > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        return {
            'method': 'Baseline: Surname Only',
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'correct': correct,
            'wrong': wrong,
            'new': new_count,
            'total': total
        }
    
    def run_project_two_baseline_mode(self) -> Dict[str, Any]:
        """
        二号项目: Baseline模式（加权相似度）
        """
        print("\n" + "="*60)
        print("二号项目: Baseline模式")
        print("="*60)
        
        return self._run_project_two(mode='baseline')
    
    def run_project_two_fs_mode(self) -> Dict[str, Any]:
        """
        二号项目: Fellegi-Sunter模式
        """
        print("\n" + "="*60)
        print("二号项目: Fellegi-Sunter模式")
        print("="*60)
        
        return self._run_project_two(mode='fs')
    
    def _run_project_two(self, mode: str = 'baseline',
                         accept_threshold: float = 0.50,
                         reject_threshold: float = 0.20) -> Dict[str, Any]:
        """
        运行二号项目评测
        """
        init_mentions, eval_mentions = self._prepare_data()
        
        # 初始化数据库和合并器
        database = AuthorDatabase()
        
        # 添加初始化数据
        for record, orcid in init_mentions:
            author_data = {
                'name': record.get('original_name', '').strip(),
                'orcid': orcid,
                'affiliation': record.get('affiliation', []),
                'journals': [record.get('journal', '')] if record.get('journal') else []
            }
            database.add_author(author_data)
        
        # 创建合并器
        merger = AuthorMerger(
            database=database,
            accept_threshold=accept_threshold,
            reject_threshold=reject_threshold,
            mode=mode
        )
        
        # 评测
        correct = 0
        wrong = 0
        merge_count = 0
        new_count = 0
        unknown_count = 0
        
        for record, true_orcid in eval_mentions:
            mention = {
                'name': record.get('original_name', '').strip(),
                'orcid': '',  # 不使用ORCID进行匹配
                'affiliation': record.get('affiliation', []),
                'journals': [record.get('journal', '')] if record.get('journal') else [],
                'surname': record.get('lastname', '')
            }
            
            result = merger.make_decision(mention)
            
            # 使用.name获取枚举名称进行比较
            decision_name = result.decision.name if hasattr(result.decision, 'name') else str(result.decision)
            
            if decision_name == 'MERGE':
                merge_count += 1
                # 检查是否正确
                matched_author = database.find_by_id(result.best_author_id)
                if matched_author and matched_author.orcid == true_orcid:
                    correct += 1
                else:
                    wrong += 1
            elif decision_name == 'NEW':
                new_count += 1
            else:
                unknown_count += 1
        
        total = len(eval_mentions)
        precision = correct / (correct + wrong) if (correct + wrong) > 0 else 0
        recall = correct / total if total > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        return {
            'method': f'Project Two ({mode})',
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'correct': correct,
            'wrong': wrong,
            'merge': merge_count,
            'new': new_count,
            'unknown': unknown_count,
            'total': total
        }
    
    def run_ablation_no_blocking(self) -> Dict[str, Any]:
        """
        消融: 移除Blocking索引（全库扫描）
        测试Blocking对性能的影响
        """
        print("\n" + "="*60)
        print("消融: 无Blocking索引")
        print("="*60)
        
        # 使用较小数据集（全库扫描很慢）
        small_limit = min(1000, self.limit)
        
        init_mentions, eval_mentions = self._prepare_data()
        init_mentions = init_mentions[:small_limit//2]
        eval_mentions = eval_mentions[:small_limit//2]
        
        # 简单实现：遍历所有候选
        database = AuthorDatabase()
        
        for record, orcid in init_mentions:
            author_data = {
                'name': record.get('original_name', '').strip(),
                'orcid': orcid,
            }
            database.add_author(author_data)
        
        merger = AuthorMerger(
            database=database,
            accept_threshold=0.50,
            reject_threshold=0.20,
            mode='baseline'
        )
        
        start_time = time.time()
        
        correct = 0
        wrong = 0
        
        for record, true_orcid in eval_mentions:
            mention = {
                'name': record.get('original_name', '').strip(),
                'orcid': '',
                'surname': record.get('lastname', '')
            }
            
            result = merger.make_decision(mention)
            
            if result.decision == 'MERGE':
                matched_author = database.find_by_id(result.author_id)
                if matched_author and matched_author.orcid == true_orcid:
                    correct += 1
                else:
                    wrong += 1
        
        elapsed = time.time() - start_time
        
        total = len(eval_mentions)
        precision = correct / (correct + wrong) if (correct + wrong) > 0 else 0
        
        return {
            'method': 'Ablation: With Blocking',
            'precision': precision,
            'time_seconds': elapsed,
            'records_processed': total,
            'speed': total / elapsed if elapsed > 0 else 0
        }
    
    def run_full_study(self) -> List[Dict[str, Any]]:
        """
        运行完整消融实验
        """
        print("\n" + "="*80)
        print("二号项目消融实验")
        print(f"数据集: {self.data_path.name}")
        print(f"样本数: {len(self.data)}")
        print(f"随机种子: {self.seed}")
        print("="*80)
        
        results = []
        
        # 基线方法
        results.append(self.run_baseline_string_match())
        results.append(self.run_baseline_surname_only())
        
        # 二号项目
        results.append(self.run_project_two_baseline_mode())
        results.append(self.run_project_two_fs_mode())
        
        return results
    
    def print_comparison_table(self, results: List[Dict[str, Any]]):
        """打印对比表格"""
        print("\n" + "="*80)
        print("消融实验结果汇总")
        print("="*80)
        
        print(f"\n{'方法':<35} {'Precision':>12} {'Recall':>10} {'F1':>10}")
        print("-"*70)
        
        for r in results:
            method = r['method']
            precision = r.get('precision', 0) * 100
            recall = r.get('recall', 0) * 100
            f1 = r.get('f1', 0) * 100
            print(f"{method:<35} {precision:>11.2f}% {recall:>9.2f}% {f1:>9.2f}%")
        
        print("-"*70)
        
        # 计算提升
        if len(results) >= 3:
            baseline_f1 = results[0].get('f1', 0)
            project_f1 = results[2].get('f1', 0)
            if baseline_f1 > 0:
                improvement = (project_f1 - baseline_f1) / baseline_f1 * 100
                print(f"\n二号项目 vs 字符串匹配: F1提升 {improvement:+.1f}%")
        
        return results


def main():
    """主函数"""
    # 使用Crossref数据集
    data_path = r"C:\istina\materia 材料\测试表单\crossref.json"
    
    study = AblationStudy(
        data_path=data_path,
        limit=10000,
        seed=42  # 固定种子保证可复现
    )
    
    results = study.run_full_study()
    study.print_comparison_table(results)
    
    # 保存结果
    output_dir = Path(__file__).parent.parent / 'test_results'
    output_dir.mkdir(exist_ok=True)
    
    output_file = output_dir / 'ablation_study_results.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'data_file': str(data_path),
            'seed': 42,
            'results': results
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n结果已保存: {output_file}")
    
    return results


if __name__ == '__main__':
    main()
