# -*- coding: utf-8 -*-
"""
相似度评分器单元测试 / Модульные тесты оценщика сходства

测试SimilarityScorer类的功能和准确性
Тестирует функциональность и точность класса SimilarityScorer
"""

import sys
import os
import unittest
from typing import Dict, Any

# 添加项目根目录到Python路径 / Добавление корневого каталога проекта в путь Python
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.author import Author
from disambiguation_engine.similarity_scorer import SimilarityScorer
from config import SIMILARITY_THRESHOLD


class TestSimilarityScorer(unittest.TestCase):
    """相似度评分器测试类 / Класс тестов оценщика сходства"""

    def setUp(self):
        """测试环境初始化 / Инициализация тестовой среды"""
        # 使用默认配置创建评分器 / Создание оценщика с конфигурацией по умолчанию
        self.scorer = SimilarityScorer()

        # 创建测试用的作者记录 / Создание записей авторов для тестирования
        self.identical_author_1 = Author(
            author_id="test_001",
            canonical_name="张三",
            coauthor_ids={"李四", "王五", "赵六"},
            journals={"Nature", "Science", "Cell"},
            affiliations={"清华大学"}
        )

        self.identical_author_2 = Author(
            author_id="test_002",
            canonical_name="张三",
            coauthor_ids={"李四", "王五", "赵六"},
            journals={"Nature", "Science", "Cell"},
            affiliations={"清华大学"}
        )

        self.similar_author = Author(
            author_id="test_003",
            canonical_name="张珊",  # 姓名略有不同 / Имя слегка отличается
            coauthor_ids={"李四", "王五"},  # 部分合著者相同 / Частично совпадающие соавторы
            journals={"Nature", "Science"},  # 部分期刊相同 / Частично совпадающие журналы
            affiliations={"清华大学"}
        )

        self.different_author = Author(
            author_id="test_004",
            canonical_name="陈小明",
            coauthor_ids={"孙七", "周八", "吴九"},
            journals={"JAMA", "Lancet", "NEJM"},
            affiliations={"北京大学"}
        )

        self.empty_author = Author(
            author_id="test_005",
            canonical_name="空作者",
            coauthor_ids=set(),
            journals=set(),
            affiliations=set()
        )

    def test_identical_records_high_similarity(self):
        """
        测试：相同记录应该获得接近1.0的高相似度分数
        Тест: идентичные записи должны получать высокий балл сходства близкий к 1.0
        """
        similarity_score, dimension_scores = self.scorer.calculate_weighted_similarity(
            self.identical_author_1, self.identical_author_2
        )

        # 验证总体相似度应该非常高 / Проверка, что общее сходство должно быть очень высоким
        self.assertGreater(similarity_score, 0.95)
        self.assertLessEqual(similarity_score, 1.0)

        # 验证各维度分数 / Проверка баллов по измерениям
        self.assertAlmostEqual(dimension_scores.get("name", 0), 1.0, places=2)
        self.assertAlmostEqual(dimension_scores.get("coauthors", 0), 1.0, places=2)
        self.assertAlmostEqual(dimension_scores.get("journals", 0), 1.0, places=2)

        print(f"相同记录测试 - 总相似度: {similarity_score:.4f}, 维度分数: {dimension_scores}")

    def test_completely_different_records_low_similarity(self):
        """
        测试：完全不同的记录应该获得较低的相似度分数
        Тест: полностью разные записи должны получать низкий балл сходства
        """
        similarity_score, dimension_scores = self.scorer.calculate_weighted_similarity(
            self.identical_author_1, self.different_author
        )

        # 验证总体相似度应该很低 / Проверка, что общее сходство должно быть низким
        self.assertLess(similarity_score, SIMILARITY_THRESHOLD)
        self.assertGreaterEqual(similarity_score, 0.0)

        # 验证各维度分数都应该很低 / Проверка, что баллы по всем измерениям должны быть низкими
        for dimension, score in dimension_scores.items():
            self.assertLessEqual(score, 0.5)

        print(f"不同记录测试 - 总相似度: {similarity_score:.4f}, 维度分数: {dimension_scores}")

    def test_partially_similar_records_moderate_similarity(self):
        """
        测试：部分相似的记录应该获得中等相似度分数，验证加权计算的准确性
        Тест: частично похожие записи должны получать средний балл сходства, проверка точности взвешенного расчёта
        """
        similarity_score, dimension_scores = self.scorer.calculate_weighted_similarity(
            self.identical_author_1, self.similar_author
        )

        # 验证总体相似度在合理范围内 / Проверка, что общее сходство в разумных пределах
        self.assertGreater(similarity_score, 0.3)
        self.assertLess(similarity_score, SIMILARITY_THRESHOLD)

        # 验证姓名相似度应该较高（张三 vs 张珊）/ Проверка сходства имён должно быть высоким (张三 vs 张珊)
        self.assertGreater(dimension_scores.get("name", 0), 0.4)

        # 验证合著者相似度应该中等（部分重叠）/ Проверка сходства соавторов должно быть средним (частичное пересечение)
        coauthor_similarity = dimension_scores.get("coauthors", 0)
        self.assertGreater(coauthor_similarity, 0.0)
        self.assertLess(coauthor_similarity, 1.0)

        print(f"部分相似记录测试 - 总相似度: {similarity_score:.4f}, 维度分数: {dimension_scores}")

    def test_empty_records_handling(self):
        """
        测试：空记录的处理逻辑
        Тест: логика обработки пустых записей
        """
        # 测试空记录与正常记录的相似度 / Тест сходства пустой записи с нормальной записью
        similarity_score, dimension_scores = self.scorer.calculate_weighted_similarity(
            self.identical_author_1, self.empty_author
        )

        # 空记录与非空记录的相似度应该很低 / Сходство пустой и непустой записи должно быть низким
        self.assertLess(similarity_score, 0.5)

        # 测试两个空记录的相似度 / Тест сходства двух пустых записей
        empty_author_2 = Author(author_id="test_006", canonical_name="另一个空作者")
        similarity_score_empty, _ = self.scorer.calculate_weighted_similarity(
            self.empty_author, empty_author_2
        )

        print(f"空记录测试 - 与正常记录相似度: {similarity_score:.4f}, 两个空记录相似度: {similarity_score_empty:.4f}")

    def test_name_similarity_edge_cases(self):
        """
        测试：姓名相似度计算的边界情况
        Тест: граничные случаи расчёта сходства имён
        """
        # 创建测试用的姓名相似度计算场景 / Создание сценариев тестирования расчёта сходства имён
        test_cases = [
            ("张三", "张三", 1.0),  # 完全相同 / Полностью идентичные
            ("张三", "Zhang San", 0.0),  # 完全不同 / Полностью разные
            ("张三", "张珊", 0.5),  # 部分相似 / Частично похожие
            ("", "张三", 0.0),  # 空字符串 / Пустая строка
            ("Zhang Wei", "Zhang W", 0.7),  # 缩写情况 / Случай сокращения
        ]

        for name1, name2, expected_min_similarity in test_cases:
            author1 = Author(author_id=f"test_{name1}", canonical_name=name1)
            author2 = Author(author_id=f"test_{name2}", canonical_name=name2)

            # 使用仅计算姓名相似度的配置 / Использование конфигурации только для расчёта сходства имён
            name_only_config = {
                'weights': {'name': 1.0, 'coauthors': 0.0, 'journals': 0.0},
                'name_config': {'case_sensitive': False, 'normalize_spaces': True, 'remove_punctuation': True},
                'set_config': {}
            }
            name_scorer = SimilarityScorer(name_only_config)

            similarity_score, _ = name_scorer.calculate_weighted_similarity(author1, author2)

            print(f"姓名相似度测试: '{name1}' vs '{name2}' = {similarity_score:.4f}")

            # 验证相似度分数的合理性 / Проверка разумности балла сходства
            if expected_min_similarity == 1.0:
                self.assertGreater(similarity_score, 0.95)
            elif expected_min_similarity == 0.0:
                self.assertLess(similarity_score, 0.3)

    def test_custom_weights_configuration(self):
        """
        测试：自定义权重配置的功能
        Тест: функциональность пользовательской конфигурации весов
        """
        # 创建强调合著者相似度的配置 / Создание конфигурации с акцентом на сходство соавторов
        coauthor_focused_config = {
            'weights': {'name': 0.2, 'coauthors': 0.7, 'journals': 0.1},
            'name_config': {'case_sensitive': False, 'normalize_spaces': True, 'remove_punctuation': True},
            'set_config': {}
        }

        coauthor_scorer = SimilarityScorer(coauthor_focused_config)

        similarity_score, dimension_scores = coauthor_scorer.calculate_weighted_similarity(
            self.identical_author_1, self.similar_author
        )

        # 由于合著者权重更高，相似度应该相对较高 / Поскольку вес соавторов выше, сходство должно быть относительно высоким
        print(f"自定义权重测试 - 总相似度: {similarity_score:.4f}, 维度分数: {dimension_scores}")

        # 验证权重配置生效 / Проверка работы конфигурации весов
        self.assertEqual(coauthor_scorer.weights['coauthors'], 0.7)
        self.assertEqual(coauthor_scorer.weights['name'], 0.2)

    def test_invalid_weights_configuration(self):
        """
        测试：无效权重配置应该抛出异常
        Тест: неверная конфигурация весов должна вызывать исключение
        """
        # 测试权重总和不等于1的情况 / Тест случая когда сумма весов не равна 1
        invalid_config = {
            'weights': {'name': 0.5, 'coauthors': 0.7, 'journals': 0.2},  # 总和 = 1.4 / Сумма = 1.4
            'name_config': {},
            'set_config': {}
        }

        with self.assertRaises(ValueError):
            SimilarityScorer(invalid_config)

        print("无效权重配置测试通过 - 正确抛出ValueError异常")


def run_tests():
    """运行所有测试 / Запуск всех тестов"""
    unittest.main()


if __name__ == '__main__':
    run_tests()