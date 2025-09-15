# -*- coding: utf-8 -*-
"""
相似度评分器 / Модуль расчёта сходства

实现基于加权相似度的"白盒"模型，用于作者记录的相似度计算
Реализует "белую коробку" модель на основе взвешенного сходства для расчёта сходства записей авторов
"""

import re
import string
from typing import Dict, Set, Tuple, Any, Optional
from models.author import Author


class SimilarityScorer:
    """
    相似度评分器类 / Класс оценщика сходства

    使用多维度加权相似度计算，提供完全透明和可配置的作者消歧功能
    Использует многомерный расчёт взвешенного сходства, предоставляя полностью прозрачную
    и настраиваемую функциональность устранения неоднозначности авторов

    该类实现了基于"白盒"模型的相似度计算，支持姓名、合著者、期刊等多个维度，
    每个维度都有可配置的权重。所有计算过程都是透明的，便于调试和解释。
    Реализует расчёт сходства на основе модели "белой коробки", поддерживая множественные измерения
    (имена, соавторы, журналы и др.), каждое со своим настраиваемым весом.
    Все процессы вычисления прозрачны для отладки и объяснения.

    Attributes:
        weights (Dict[str, float]): 各维度权重配置 / Конфигурация весов по измерениям
        name_config (Dict[str, Any]): 姓名相似度配置 / Конфигурация сходства имён
        set_config (Dict[str, Any]): 集合相似度配置 / Конфигурация сходства множеств

    Example:
        >>> scorer = SimilarityScorer()
        >>> similarity, breakdown = scorer.calculate_weighted_similarity(author1, author2)
        >>> print(f"总相似度: {similarity:.3f}")
        >>> print(f"维度分解: {breakdown}")
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化相似度评分器 / Инициализация оценщика сходства

        Args:
            config: 配置字典，包含权重和参数设置 / Словарь конфигурации с настройками весов и параметров
        """
        # 导入默认配置 / Импорт конфигурации по умолчанию
        if config is None:
            from config import (
                SIMILARITY_WEIGHTS,
                NAME_SIMILARITY_CONFIG,
                SET_SIMILARITY_CONFIG
            )
            self.weights = SIMILARITY_WEIGHTS.copy()
            self.name_config = NAME_SIMILARITY_CONFIG.copy()
            self.set_config = SET_SIMILARITY_CONFIG.copy()
        else:
            self.weights = config.get('weights', {})
            self.name_config = config.get('name_config', {})
            self.set_config = config.get('set_config', {})

        # 验证权重配置 / Проверка конфигурации весов
        self._validate_weights()

    def _validate_weights(self) -> None:
        """验证权重配置的有效性 / Проверка валидности конфигурации весов"""
        total_weight = sum(self.weights.values())
        if abs(total_weight - 1.0) > 1e-6:
            raise ValueError(f"权重总和必须等于1.0，当前为: {total_weight}")

    def calculate_weighted_similarity(
        self,
        record_a: Author,
        record_b: Author
    ) -> Tuple[float, Dict[str, float]]:
        """
        计算两条作者记录的加权相似度 / Расчёт взвешенного сходства двух записей авторов

        这是相似度计算的核心方法，实现了多维度的加权相似度评分。
        支持姓名、合著者、期刊、研究领域、机构等多个维度，每个维度都可以配置权重。
        Это основной метод расчёта сходства, реализующий многомерный взвешенный скоринг.
        Поддерживает имена, соавторов, журналы, области исследований, аффилиации и другие измерения
        с настраиваемыми весами.

        算法特点 / Особенности алгоритма:
        - 白盒模型：所有计算步骤透明可解释 / Модель белой коробки: все шаги прозрачны
        - 维度化权重：每个特征维度独立计算 / Взвешенные измерения: каждая характеристика независима
        - 模型兼容：支持新旧Author数据模型 / Совместимость моделей: поддержка новых и старых моделей

        Args:
            record_a (Author): 第一条作者记录 / Первая запись автора
            record_b (Author): 第二条作者记录 / Вторая запись автора

        Returns:
            Tuple[float, Dict[str, float]]:
                - float: 总加权相似度分数 [0.0-1.0] / Общий взвешенный балл сходства [0.0-1.0]
                - Dict[str, float]: 各维度详细分数字典 / Словарь детальных баллов по измерениям
                  例如: {"name": 0.85, "coauthors": 0.60, "journals": 0.40}

        Raises:
            ValueError: 权重配置无效时 / При недействительной конфигурации весов
            AttributeError: 记录属性缺失时 / При отсутствии атрибутов записи

        Example:
            >>> scorer = SimilarityScorer()
            >>> author1 = Author(canonical_name="John Smith", journals={"Nature"})
            >>> author2 = Author(canonical_name="J. Smith", journals={"Science"})
            >>> similarity, breakdown = scorer.calculate_weighted_similarity(author1, author2)
            >>> print(f"相似度: {similarity:.3f}")
            >>> print(f"维度分解: {breakdown}")
        """
        dimension_scores = {}
        weighted_sum = 0.0

        # 计算姓名相似度 / Расчёт сходства имён
        if "name" in self.weights and self.weights["name"] > 0:
            # 兼容新旧Author模型 / Совместимость с новой и старой моделями Author
            name_a = getattr(record_a, 'canonical_name', getattr(record_a, 'name', ''))
            name_b = getattr(record_b, 'canonical_name', getattr(record_b, 'name', ''))
            name_score = self._calculate_name_similarity(name_a, name_b)
            dimension_scores["name"] = name_score
            weighted_sum += name_score * self.weights["name"]

        # 计算合著者相似度 / Расчёт сходства соавторов
        if "coauthors" in self.weights and self.weights["coauthors"] > 0:
            # 兼容新旧Author模型 / Совместимость с новой и старой моделями Author
            coauthors_a = getattr(record_a, 'coauthor_ids', getattr(record_a, 'coauthors', set()))
            coauthors_b = getattr(record_b, 'coauthor_ids', getattr(record_b, 'coauthors', set()))
            coauthor_score = self._calculate_coauthor_similarity(coauthors_a, coauthors_b)
            dimension_scores["coauthors"] = coauthor_score
            weighted_sum += coauthor_score * self.weights["coauthors"]

        # 计算期刊相似度 / Расчёт сходства журналов
        if "journals" in self.weights and self.weights["journals"] > 0:
            journals_a = getattr(record_a, 'journals', set())
            journals_b = getattr(record_b, 'journals', set())
            journal_score = self._calculate_journal_similarity(journals_a, journals_b)
            dimension_scores["journals"] = journal_score
            weighted_sum += journal_score * self.weights["journals"]

        # 可扩展的其他维度 / Расширяемые другие измерения
        if "research_fields" in self.weights and self.weights["research_fields"] > 0:
            field_score = self._calculate_set_similarity(
                record_a.research_fields, record_b.research_fields
            )
            dimension_scores["research_fields"] = field_score
            weighted_sum += field_score * self.weights["research_fields"]

        if "affiliations" in self.weights and self.weights["affiliations"] > 0:
            affiliation_score = self._calculate_set_similarity(
                record_a.affiliations, record_b.affiliations
            )
            dimension_scores["affiliations"] = affiliation_score
            weighted_sum += affiliation_score * self.weights["affiliations"]

        return weighted_sum, dimension_scores

    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """
        计算姓名相似度 / Расчёт сходства имён

        使用莱文斯坦距离作为基础算法 / Использует расстояние Левенштейна как базовый алгоритм

        Args:
            name1: 第一个姓名 / Первое имя
            name2: 第二个姓名 / Второе имя

        Returns:
            float: 姓名相似度分数 (0-1) / Балл сходства имён (0-1)
        """
        if not name1 or not name2:
            return 0.0

        # 标准化姓名 / Нормализация имён
        normalized_name1 = self._normalize_name(name1)
        normalized_name2 = self._normalize_name(name2)

        if normalized_name1 == normalized_name2:
            return 1.0

        # 计算莱文斯坦距离 / Расчёт расстояния Левенштейна
        levenshtein_distance = self._levenshtein_distance(normalized_name1, normalized_name2)
        max_len = max(len(normalized_name1), len(normalized_name2))

        if max_len == 0:
            return 0.0

        # 转换为相似度分数 / Преобразование в балл сходства
        similarity = 1.0 - (levenshtein_distance / max_len)
        return max(0.0, similarity)

    def _calculate_coauthor_similarity(self, coauthors1: Set[str], coauthors2: Set[str]) -> float:
        """
        计算合著者集合相似度 / Расчёт сходства множеств соавторов

        使用Jaccard相似系数 / Использует коэффициент сходства Жаккара

        Args:
            coauthors1: 第一个合著者集合 / Первое множество соавторов
            coauthors2: 第二个合著者集合 / Второе множество соавторов

        Returns:
            float: 合著者相似度分数 (0-1) / Балл сходства соавторов (0-1)
        """
        return self._calculate_jaccard_similarity(coauthors1, coauthors2)

    def _calculate_journal_similarity(self, journals1: Set[str], journals2: Set[str]) -> float:
        """
        计算期刊集合相似度 / Расчёт сходства множеств журналов

        Args:
            journals1: 第一个期刊集合 / Первое множество журналов
            journals2: 第二个期刊集合 / Второе множество журналов

        Returns:
            float: 期刊相似度分数 (0-1) / Балл сходства журналов (0-1)
        """
        return self._calculate_jaccard_similarity(journals1, journals2)

    def _calculate_set_similarity(self, set1: Set[str], set2: Set[str]) -> float:
        """
        通用集合相似度计算 / Универсальный расчёт сходства множеств

        Args:
            set1: 第一个集合 / Первое множество
            set2: 第二个集合 / Второе множество

        Returns:
            float: 集合相似度分数 (0-1) / Балл сходства множеств (0-1)
        """
        return self._calculate_jaccard_similarity(set1, set2)

    def _calculate_jaccard_similarity(self, set1: Set[str], set2: Set[str]) -> float:
        """
        计算Jaccard相似系数 / Расчёт коэффициента сходства Жаккара

        Args:
            set1: 第一个集合 / Первое множество
            set2: 第二个集合 / Второе множество

        Returns:
            float: Jaccard相似系数 (0-1) / Коэффициент сходства Жаккара (0-1)
        """
        if not set1 and not set2:
            return 1.0  # 两个空集合视为完全相似 / Два пустых множества считаются полностью похожими

        if not set1 or not set2:
            return 0.0  # 一个空集合和一个非空集合不相似 / Пустое и непустое множества не похожи

        # 标准化集合元素 / Нормализация элементов множества
        normalized_set1 = {self._normalize_string(item) for item in set1}
        normalized_set2 = {self._normalize_string(item) for item in set2}

        intersection = len(normalized_set1.intersection(normalized_set2))
        union = len(normalized_set1.union(normalized_set2))

        if union == 0:
            return 1.0

        return intersection / union

    def _normalize_name(self, name: str) -> str:
        """
        标准化姓名字符串 / Нормализация строки имени

        Args:
            name: 原始姓名 / Исходное имя

        Returns:
            str: 标准化后的姓名 / Нормализованное имя
        """
        if not name:
            return ""

        # 转换为小写 / Преобразование в нижний регистр
        if not self.name_config.get("case_sensitive", False):
            name = name.lower()

        # 移除标点符号 / Удаление знаков препинания
        if self.name_config.get("remove_punctuation", True):
            name = name.translate(str.maketrans("", "", string.punctuation))

        # 标准化空格 / Нормализация пробелов
        if self.name_config.get("normalize_spaces", True):
            name = re.sub(r'\s+', ' ', name).strip()

        return name

    def _normalize_string(self, text: str) -> str:
        """
        通用字符串标准化 / Универсальная нормализация строк

        Args:
            text: 原始字符串 / Исходная строка

        Returns:
            str: 标准化后的字符串 / Нормализованная строка
        """
        if not text:
            return ""

        # 转换为小写并移除多余空格 / Преобразование в нижний регистр и удаление лишних пробелов
        return re.sub(r'\s+', ' ', text.lower().strip())

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """
        计算莱文斯坦距离 / Расчёт расстояния Левенштейна

        动态规划实现的编辑距离算法 / Алгоритм редакционного расстояния с использованием динамического программирования

        Args:
            s1: 第一个字符串 / Первая строка
            s2: 第二个字符串 / Вторая строка

        Returns:
            int: 莱文斯坦距离 / Расстояние Левенштейна
        """
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = list(range(len(s2) + 1))

        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]