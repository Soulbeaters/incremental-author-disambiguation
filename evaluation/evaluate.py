# -*- coding: utf-8 -*-
"""
作者消歧评测脚本 / Скрипт оценки дизамбигуации авторов
Author disambiguation evaluation script

中文注释：实现B³ F1和pairwise F1评测指标，评估消歧系统质量
Русский комментарий: Реализация метрик B³ F1 и pairwise F1 для оценки качества дизамбигуации

评测指标 / Метрики / Metrics:
1. B³ (B-cubed) F1: 基于聚类的precision/recall，在entity层面计算
   B³ F1: Кластерно-ориентированная метрика, вычисляет precision/recall на уровне сущностей
2. Pairwise F1: 基于mention对的precision/recall
   Pairwise F1: Метрика на основе пар упоминаний
"""

import json
import sys
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any
from collections import defaultdict
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class DisambiguationEvaluator:
    """
    作者消歧评测器 / Оценщик дизамбигуации авторов

    实现B³ F1和pairwise F1评测指标
    Реализует метрики B³ F1 и pairwise F1
    """

    def __init__(self, gold_set: Dict[str, Any], predicted_clusters: Dict[str, List[int]]):
        """
        初始化评测器 / Инициализация оценщика

        Args:
            gold_set: 金标准数据集（from build_orcid_goldset.py）
            predicted_clusters: 预测的聚类结果 {cluster_id: [mention_ids]}
        """
        self.gold_set = gold_set
        self.predicted_clusters = predicted_clusters
        self.logger = logging.getLogger(__name__)

        # 提取ground truth / Извлечение ground truth
        self.ground_truth = gold_set['ground_truth']  # mention_id -> orcid

        # 构建gold clusters mapping / Построение отображения золотых кластеров
        self.gold_clusters_by_mention = {}  # mention_id -> gold_cluster_id
        for mention_id_str, orcid in self.ground_truth.items():
            self.gold_clusters_by_mention[int(mention_id_str)] = orcid

        # 构建predicted clusters mapping / Построение отображения предсказанных кластеров
        self.predicted_clusters_by_mention = {}  # mention_id -> predicted_cluster_id
        for cluster_id, mention_ids in self.predicted_clusters.items():
            for mention_id in mention_ids:
                self.predicted_clusters_by_mention[mention_id] = cluster_id

    def evaluate_bcubed(self) -> Dict[str, float]:
        """
        计算B³ (B-cubed) precision, recall, F1
        Вычисление B³ precision, recall, F1

        B³算法原理 / Принцип алгоритма B³:
        - 对每个mention，计算其与同cluster中其他mentions的正确率
        - Для каждого упоминания вычисляет правильность относительно других упоминаний в том же кластере

        Returns:
            {'precision': float, 'recall': float, 'f1': float}
        """
        self.logger.info("计算B³指标 / Вычисление метрик B³...")

        precisions = []
        recalls = []

        # 遍历所有mentions / Итерация по всем упоминаниям
        for mention_id in self.gold_clusters_by_mention.keys():
            gold_cluster = self.gold_clusters_by_mention[mention_id]
            predicted_cluster = self.predicted_clusters_by_mention.get(mention_id)

            if predicted_cluster is None:
                # mention未被预测，precision=1.0（单独成cluster），recall=0（未找到其他同类）
                # упоминание не предсказано
                precisions.append(1.0)
                recalls.append(0.0)
                continue

            # 找出预测cluster中的所有mentions / Найти все упоминания в предсказанном кластере
            predicted_mentions = set(self.predicted_clusters.get(predicted_cluster, []))

            # 找出gold cluster中的所有mentions / Найти все упоминания в золотом кластере
            gold_mentions = set()
            for mid, gcluster in self.gold_clusters_by_mention.items():
                if gcluster == gold_cluster:
                    gold_mentions.add(mid)

            # 计算intersection / Вычисление пересечения
            correct = len(predicted_mentions & gold_mentions)

            # Precision: 预测cluster中有多少是正确的
            # Precision: сколько правильных в предсказанном кластере
            precision = correct / len(predicted_mentions) if len(predicted_mentions) > 0 else 0.0

            # Recall: gold cluster中有多少被找到了
            # Recall: сколько найдено из золотого кластера
            recall = correct / len(gold_mentions) if len(gold_mentions) > 0 else 0.0

            precisions.append(precision)
            recalls.append(recall)

        # 计算平均 / Вычисление среднего
        avg_precision = sum(precisions) / len(precisions) if precisions else 0.0
        avg_recall = sum(recalls) / len(recalls) if recalls else 0.0

        # 计算F1 / Вычисление F1
        f1 = 2 * (avg_precision * avg_recall) / (avg_precision + avg_recall) if (avg_precision + avg_recall) > 0 else 0.0

        return {
            'precision': avg_precision,
            'recall': avg_recall,
            'f1': f1
        }

    def evaluate_pairwise(self) -> Dict[str, float]:
        """
        计算Pairwise precision, recall, F1
        Вычисление pairwise precision, recall, F1

        Pairwise算法原理 / Принцип алгоритма pairwise:
        - 生成所有mention对 / Генерация всех пар упоминаний
        - 计算有多少对被正确聚类/分离 / Вычисление правильно кластеризованных/разделённых пар

        Returns:
            {'precision': float, 'recall': float, 'f1': float, 'tp': int, 'fp': int, 'fn': int}
        """
        self.logger.info("计算Pairwise指标 / Вычисление метрик pairwise...")

        # 生成gold pairs和predicted pairs / Генерация золотых и предсказанных пар
        gold_pairs = self._generate_pairs_from_clusters(self.gold_clusters_by_mention)
        predicted_pairs = self._generate_pairs_from_clusters(self.predicted_clusters_by_mention)

        # 计算TP, FP, FN / Вычисление TP, FP, FN
        tp = len(gold_pairs & predicted_pairs)  # True positives: 正确聚到一起的对
        fp = len(predicted_pairs - gold_pairs)  # False positives: 错误聚到一起的对
        fn = len(gold_pairs - predicted_pairs)  # False negatives: 应该聚到一起但没聚的对

        # 计算precision, recall, F1
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        return {
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'tp': tp,
            'fp': fp,
            'fn': fn,
            'gold_pairs_count': len(gold_pairs),
            'predicted_pairs_count': len(predicted_pairs)
        }

    def _generate_pairs_from_clusters(self, clusters_by_mention: Dict[int, str]) -> Set[Tuple[int, int]]:
        """
        从cluster mapping生成mention对 / Генерация пар упоминаний из кластеров

        Args:
            clusters_by_mention: {mention_id: cluster_id}

        Returns:
            Set of (mention_id1, mention_id2) pairs where mention_id1 < mention_id2
        """
        # 反向索引：cluster_id -> [mention_ids]
        cluster_to_mentions = defaultdict(list)
        for mention_id, cluster_id in clusters_by_mention.items():
            cluster_to_mentions[cluster_id].append(mention_id)

        # 生成所有同cluster内的mention对
        pairs = set()
        for cluster_id, mention_ids in cluster_to_mentions.items():
            # 生成组合 / Генерация комбинаций
            for i in range(len(mention_ids)):
                for j in range(i + 1, len(mention_ids)):
                    m1, m2 = mention_ids[i], mention_ids[j]
                    # 确保顺序一致（小的在前）/ Обеспечение согласованности порядка
                    if m1 > m2:
                        m1, m2 = m2, m1
                    pairs.add((m1, m2))

        return pairs

    def evaluate_all(self) -> Dict[str, Any]:
        """
        执行所有评测 / Выполнение всех оценок

        Returns:
            完整的评测结果 / Полные результаты оценки
        """
        self.logger.info("开始评测 / Начало оценки...")

        bcubed_metrics = self.evaluate_bcubed()
        pairwise_metrics = self.evaluate_pairwise()

        # 构建完整结果 / Построение полного результата
        results = {
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'gold_set_source': self.gold_set['metadata']['source'],
                'total_mentions': len(self.gold_clusters_by_mention),
                'gold_clusters_count': len(set(self.gold_clusters_by_mention.values())),
                'predicted_clusters_count': len(self.predicted_clusters)
            },
            'bcubed': bcubed_metrics,
            'pairwise': pairwise_metrics,
            'summary': {
                'bcubed_f1': bcubed_metrics['f1'],
                'pairwise_f1': pairwise_metrics['f1'],
                'average_f1': (bcubed_metrics['f1'] + pairwise_metrics['f1']) / 2
            }
        }

        self.logger.info("评测完成 / Оценка завершена")
        return results

    def print_results(self, results: Dict[str, Any]) -> None:
        """
        打印评测结果 / Печать результатов оценки

        Args:
            results: 评测结果 / Результаты оценки
        """
        print("\n" + "=" * 80)
        print("作者消歧评测结果 / Результаты оценки дизамбигуации авторов")
        print("=" * 80)

        print(f"\n【元数据 / Метаданные】")
        meta = results['metadata']
        print(f"  总mentions数 / Всего упоминаний: {meta['total_mentions']}")
        print(f"  Gold clusters数 / Золотых кластеров: {meta['gold_clusters_count']}")
        print(f"  Predicted clusters数 / Предсказанных кластеров: {meta['predicted_clusters_count']}")

        print(f"\n【B³ (B-cubed) 指标】")
        bcubed = results['bcubed']
        print(f"  Precision: {bcubed['precision']:.4f}")
        print(f"  Recall:    {bcubed['recall']:.4f}")
        print(f"  F1:        {bcubed['f1']:.4f}")

        print(f"\n【Pairwise 指标】")
        pairwise = results['pairwise']
        print(f"  Precision: {pairwise['precision']:.4f}")
        print(f"  Recall:    {pairwise['recall']:.4f}")
        print(f"  F1:        {pairwise['f1']:.4f}")
        print(f"  详细 / Детали:")
        print(f"    - True Positives (TP):  {pairwise['tp']}")
        print(f"    - False Positives (FP): {pairwise['fp']}")
        print(f"    - False Negatives (FN): {pairwise['fn']}")
        print(f"    - Gold pairs总数:       {pairwise['gold_pairs_count']}")
        print(f"    - Predicted pairs总数:  {pairwise['predicted_pairs_count']}")

        print(f"\n【总结 / Итого】")
        summary = results['summary']
        print(f"  B³ F1:       {summary['bcubed_f1']:.4f}")
        print(f"  Pairwise F1: {summary['pairwise_f1']:.4f}")
        print(f"  平均F1 / Средний F1: {summary['average_f1']:.4f}")

        print("\n" + "=" * 80)


def load_gold_set(gold_set_file: str) -> Dict[str, Any]:
    """加载金标准数据集 / Загрузка золотого стандарта"""
    with open(gold_set_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_predicted_clusters(predicted_file: str) -> Dict[str, List[int]]:
    """
    加载预测的聚类结果 / Загрузка предсказанных кластеров

    Args:
        predicted_file: 预测结果文件路径（JSON格式）
                       Expected format: {cluster_id: [mention_ids]}

    Returns:
        {cluster_id: [mention_ids]}
    """
    with open(predicted_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_results(results: Dict[str, Any], output_file: str) -> None:
    """
    保存评测结果 / Сохранение результатов оценки

    Args:
        results: 评测结果
        output_file: 输出文件路径
    """
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n✓ 评测结果已保存 / Результаты сохранены: {output_file}")


def main():
    """主函数 / Главная функция"""
    parser = argparse.ArgumentParser(
        description='作者消歧评测 / Оценка дизамбигуации авторов'
    )
    parser.add_argument(
        '--gold-set',
        type=str,
        required=True,
        help='金标准数据集文件 / Файл золотого стандарта (from build_orcid_goldset.py)'
    )
    parser.add_argument(
        '--predicted',
        type=str,
        required=True,
        help='预测的聚类结果文件 / Файл предсказанных кластеров (JSON: {cluster_id: [mention_ids]})'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='evaluation/results/eval_results.json',
        help='输出评测结果文件 / Файл результатов оценки'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='详细输出 / Подробный вывод'
    )

    args = parser.parse_args()

    # 设置日志 / Настройка логирования
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # 加载数据 / Загрузка данных
    print("加载金标准数据集 / Загрузка золотого стандарта...")
    gold_set = load_gold_set(args.gold_set)

    print("加载预测结果 / Загрузка предсказаний...")
    predicted_clusters = load_predicted_clusters(args.predicted)

    # 执行评测 / Выполнение оценки
    evaluator = DisambiguationEvaluator(gold_set, predicted_clusters)
    results = evaluator.evaluate_all()

    # 打印结果 / Печать результатов
    evaluator.print_results(results)

    # 保存结果 / Сохранение результатов
    save_results(results, args.output)


if __name__ == '__main__':
    main()
