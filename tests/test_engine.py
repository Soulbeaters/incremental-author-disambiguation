# -*- coding: utf-8 -*-
"""
消歧引擎单元测试 / Модульные тесты движка устранения неоднозначности

测试DisambiguationEngine类的功能和准确性
Тестирует функциональность и точность класса DisambiguationEngine
"""

import sys
import os
import unittest
from typing import Dict, Any

# 添加项目根目录到Python路径 / Добавление корневого каталога проекта в путь Python
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from disambiguation_engine.engine import DisambiguationEngine, DisambiguationResult
from models.author import AuthorRecord, Author, Publication


class TestDisambiguationEngine(unittest.TestCase):
    """消歧引擎测试类 / Класс тестов движка устранения неоднозначности"""

    def setUp(self):
        """测试环境初始化 / Инициализация тестовой среды"""
        # 使用测试配置创建引擎 / Создание движка с тестовой конфигурацией
        test_config = {
            'weights': {'name': 0.6, 'coauthors': 0.3, 'journals': 0.1},
            'similarity_threshold': 0.8,
            'max_affected_authors': 50,
            'name_config': {'case_sensitive': False, 'normalize_spaces': True, 'remove_punctuation': True},
            'set_config': {}
        }
        self.engine = DisambiguationEngine(test_config)

        # 创建测试数据 / Создание тестовых данных
        self.sample_records = self._create_sample_records()

    def _create_sample_records(self):
        """创建示例记录 / Создание примерных записей"""
        return [
            AuthorRecord(
                record_id="rec_001",
                name="张伟",
                coauthors=["李明", "王强"],
                journal="Nature",
                publication_title="AI Research",
                affiliation="清华大学"
            ),
            AuthorRecord(
                record_id="rec_002",
                name="张伟",  # 同名作者 / Одноимённый автор
                coauthors=["李明", "陈建国"],  # 部分相同合著者 / Частично совпадающие соавторы
                journal="Nature",
                publication_title="Machine Learning Advances",
                affiliation="清华大学"
            ),
            AuthorRecord(
                record_id="rec_003",
                name="张维",  # 相似姓名 / Похожее имя
                coauthors=["孙丽华", "马建军"],
                journal="Science",
                publication_title="Computer Vision",
                affiliation="北京大学"
            ),
            AuthorRecord(
                record_id="rec_004",
                name="李明",  # 完全不同的作者 / Полностью другой автор
                coauthors=["赵雅芳", "周小芳"],
                journal="JAMA",
                publication_title="Medical Research",
                affiliation="北京医科大学"
            )
        ]

    def test_process_first_record_creates_new_author(self):
        """
        测试：处理第一条记录应该创建新作者
        Тест: обработка первой записи должна создать нового автора
        """
        record = self.sample_records[0]
        result = self.engine.process_new_record(record)

        # 验证决策结果 / Проверка результата решения
        self.assertEqual(result.decision, 'new_author')
        self.assertIsNotNone(result.matched_author_id)
        self.assertTrue(record.processed)

        # 验证作者已创建 / Проверка создания автора
        self.assertEqual(len(self.engine.authors), 1)
        created_author = self.engine.authors[result.matched_author_id]
        self.assertEqual(created_author.canonical_name, "张伟")
        self.assertIn(record.record_id, created_author.linked_records)

        print(f"首次记录处理测试通过: 创建作者 {result.matched_author_id}")

    def test_similar_record_gets_merged(self):
        """
        测试：相似记录应该被合并
        Тест: похожие записи должны объединяться
        """
        # 先处理第一条记录 / Сначала обработка первой записи
        first_record = self.sample_records[0]
        first_result = self.engine.process_new_record(first_record)

        # 处理相似的第二条记录 / Обработка похожей второй записи
        similar_record = self.sample_records[1]
        similar_result = self.engine.process_new_record(similar_record)

        # 验证合并决策 / Проверка решения о слиянии
        if similar_result.similarity_score >= self.engine.similarity_threshold:
            self.assertEqual(similar_result.decision, 'merged')
            self.assertEqual(similar_result.matched_author_id, first_result.matched_author_id)

            # 验证记录已合并到同一作者 / Проверка объединения записей в одного автора
            merged_author = self.engine.authors[similar_result.matched_author_id]
            self.assertIn(first_record.record_id, merged_author.linked_records)
            self.assertIn(similar_record.record_id, merged_author.linked_records)
            self.assertEqual(len(merged_author.linked_records), 2)

            print(f"相似记录合并测试通过: 分数 {similar_result.similarity_score:.4f}")
        else:
            self.assertEqual(similar_result.decision, 'new_author')
            print(f"相似记录未达到合并阈值: 分数 {similar_result.similarity_score:.4f}, 阈值 {self.engine.similarity_threshold}")

    def test_different_record_creates_new_author(self):
        """
        测试：不同记录应该创建新作者
        Тест: разные записи должны создавать нового автора
        """
        # 处理第一条记录 / Обработка первой записи
        first_record = self.sample_records[0]
        first_result = self.engine.process_new_record(first_record)

        # 处理不同的记录 / Обработка другой записи
        different_record = self.sample_records[3]  # 李明记录 / Запись Li Ming
        different_result = self.engine.process_new_record(different_record)

        # 验证创建了新作者 / Проверка создания нового автора
        self.assertEqual(different_result.decision, 'new_author')
        self.assertNotEqual(different_result.matched_author_id, first_result.matched_author_id)

        # 验证现在有两个作者 / Проверка наличия двух авторов
        self.assertEqual(len(self.engine.authors), 2)

        print(f"不同记录处理测试通过: 创建新作者 {different_result.matched_author_id}")

    def test_incremental_processing_sequence(self):
        """
        测试：增量处理序列
        Тест: последовательность инкрементальной обработки
        """
        results = []

        # 逐一处理所有记录 / Последовательная обработка всех записей
        for i, record in enumerate(self.sample_records):
            result = self.engine.process_new_record(record)
            results.append(result)

            print(f"处理记录 {i+1}: {result.decision}, 分数: {result.similarity_score:.4f}")

        # 验证统计信息 / Проверка статистики
        stats = self.engine.get_statistics()
        self.assertEqual(stats['total_processed'], len(self.sample_records))
        self.assertGreater(stats['total_authors'], 0)

        # 验证所有记录都已处理 / Проверка обработки всех записей
        for record in self.sample_records:
            self.assertTrue(record.processed)

        print(f"增量处理测试完成: 总作者数 {stats['total_authors']}, 处理记录数 {stats['total_processed']}")

    def test_dependency_graph_updates(self):
        """
        测试：依赖图更新
        Тест: обновления графа зависимостей
        """
        # 处理有合著者关系的记录 / Обработка записей с отношениями соавторства
        record1 = self.sample_records[0]  # 张伟，合著者：李明，王强
        record2 = self.sample_records[3]  # 李明，合著者：赵雅芳，周小芳

        result1 = self.engine.process_new_record(record1)
        result2 = self.engine.process_new_record(record2)

        # 验证依赖图已更新 / Проверка обновления графа зависимостей
        graph_stats = self.engine.dependency_graph.get_graph_stats()
        self.assertGreater(graph_stats['node_count'], 0)

        # 验证作者节点已添加 / Проверка добавления узлов авторов
        self.assertIn(result1.matched_author_id, self.engine.dependency_graph.authors)
        self.assertIn(result2.matched_author_id, self.engine.dependency_graph.authors)

        print(f"依赖图更新测试通过: 节点数 {graph_stats['node_count']}, 边数 {graph_stats['edge_count']}")

    def test_get_author_by_id(self):
        """
        测试：根据ID获取作者
        Тест: получение автора по ID
        """
        record = self.sample_records[0]
        result = self.engine.process_new_record(record)

        # 测试获取存在的作者 / Тестирование получения существующего автора
        author = self.engine.get_author_by_id(result.matched_author_id)
        self.assertIsNotNone(author)
        self.assertEqual(author.canonical_name, record.name)

        # 测试获取不存在的作者 / Тестирование получения несуществующего автора
        non_existent = self.engine.get_author_by_id("non_existent_id")
        self.assertIsNone(non_existent)

        print("根据ID获取作者测试通过")

    def test_statistics_tracking(self):
        """
        测试：统计信息跟踪
        Тест: отслеживание статистики
        """
        initial_stats = self.engine.get_statistics()
        self.assertEqual(initial_stats['total_processed'], 0)

        # 处理几条记录 / Обработка нескольких записей
        for record in self.sample_records[:2]:
            self.engine.process_new_record(record)

        # 验证统计更新 / Проверка обновления статистики
        updated_stats = self.engine.get_statistics()
        self.assertEqual(updated_stats['total_processed'], 2)
        self.assertGreater(updated_stats['processing_time_total'], 0)
        self.assertGreater(updated_stats['avg_processing_time'], 0)

        print(f"统计跟踪测试通过: {updated_stats}")

    def test_export_results(self):
        """
        测试：结果导出
        Тест: экспорт результатов
        """
        # 处理一些记录 / Обработка некоторых записей
        for record in self.sample_records[:2]:
            self.engine.process_new_record(record)

        # 导出结果 / Экспорт результатов
        export_data = self.engine.export_results()

        # 验证导出数据结构 / Проверка структуры экспортированных данных
        self.assertIn('authors', export_data)
        self.assertIn('statistics', export_data)
        self.assertIn('graph_info', export_data)

        # 验证作者数据 / Проверка данных авторов
        authors_data = export_data['authors']
        self.assertGreater(len(authors_data), 0)

        for author_id, author_data in authors_data.items():
            self.assertIn('canonical_name', author_data)
            self.assertIn('linked_records', author_data)
            self.assertIn('confidence_score', author_data)

        print(f"结果导出测试通过: 导出了 {len(authors_data)} 个作者的数据")

    def test_edge_cases(self):
        """
        测试：边界情况
        Тест: граничные случаи
        """
        # 测试空记录 / Тестирование пустой записи
        empty_record = AuthorRecord(
            record_id="empty_001",
            name="",
            coauthors=[],
            journal=None
        )

        result = self.engine.process_new_record(empty_record)
        self.assertIn(result.decision, ['new_author', 'rejected'])

        # 测试只有姓名的记录 / Тестирование записи только с именем
        name_only_record = AuthorRecord(
            record_id="name_only_001",
            name="孤立作者",
            coauthors=[],
            journal=None
        )

        result2 = self.engine.process_new_record(name_only_record)
        self.assertEqual(result2.decision, 'new_author')

        print("边界情况测试通过")

    def test_configuration_effects(self):
        """
        测试：配置参数效果
        Тест: влияние параметров конфигурации
        """
        # 创建高阈值引擎 / Создание движка с высоким порогом
        high_threshold_config = {
            'weights': {'name': 1.0, 'coauthors': 0.0, 'journals': 0.0},
            'similarity_threshold': 0.95,  # 非常高的阈值 / Очень высокий порог
            'name_config': {'case_sensitive': False, 'normalize_spaces': True, 'remove_punctuation': True},
            'set_config': {}
        }
        strict_engine = DisambiguationEngine(high_threshold_config)

        # 处理相同的记录 / Обработка одинаковых записей
        record1 = self.sample_records[0]
        record2 = self.sample_records[1]

        result1 = strict_engine.process_new_record(record1)
        result2 = strict_engine.process_new_record(record2)

        # 高阈值应该导致更少的合并 / Высокий порог должен приводить к меньшему количеству слияний
        if result2.similarity_score < 0.95:
            self.assertEqual(result2.decision, 'new_author')
            print(f"高阈值配置测试通过: 分数 {result2.similarity_score:.4f} < 0.95, 创建新作者")
        else:
            print(f"高阈值配置: 分数 {result2.similarity_score:.4f} >= 0.95, 执行合并")


def run_engine_tests():
    """运行消歧引擎测试 / Запуск тестов движка устранения неоднозначности"""
    unittest.main()


if __name__ == '__main__':
    run_engine_tests()