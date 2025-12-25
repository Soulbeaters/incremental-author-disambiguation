# -*- coding: utf-8 -*-
"""
相似度评分器 / Модуль расчёта сходства

实现多种评分模式的作者相似度计算：
1. Baseline模式：加权相似度（原有方法）
2. Fellegi-Sunter模式：证据聚合 + log-likelihood ratio

Реализует несколько режимов оценки сходства авторов
Implements multiple scoring modes for author similarity
"""

import re
import string
import math
import logging
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
                SET_SIMILARITY_CONFIG,
                COMPARISON_BINS,
                MU_TABLE,
                ENABLE_CHINESE_NAME_NORMALIZATION
            )
            self.weights = SIMILARITY_WEIGHTS.copy()
            self.name_config = NAME_SIMILARITY_CONFIG.copy()
            self.set_config = SET_SIMILARITY_CONFIG.copy()
            self.comparison_bins = COMPARISON_BINS.copy()
            self.mu_table = MU_TABLE  # 深拷贝在外部load_mu_table中完成
            self.enable_chinese_name = ENABLE_CHINESE_NAME_NORMALIZATION
        else:
            self.weights = config.get('weights', {})
            self.name_config = config.get('name_config', {})
            self.set_config = config.get('set_config', {})
            self.comparison_bins = config.get('comparison_bins', {})
            self.mu_table = config.get('mu_table', {})
            self.enable_chinese_name = config.get('enable_chinese_name', False)

        # 验证权重配置 / Проверка конфигурации весов
        self._validate_weights()

        # 初始化日志 / Инициализация логирования
        self.logger = logging.getLogger(__name__)

        # 尝试导入Chinese-name模块（懒加载）/ Попытка импорта модуля китайских имён
        self.chinese_name_module = None
        if self.enable_chinese_name:
            try:
                # TODO: 实际路径根据一号项目部署调整
                # Фактический путь зависит от развёртывания проекта №1
                import sys
                from pathlib import Path
                # 尝试导入（暂时fallback）
                # self.chinese_name_module = ...
                self.logger.info("Chinese-name module integration enabled (stub)")
            except ImportError:
                self.logger.warning(
                    "Chinese-name module not available, falling back to standard name processing"
                )
                self.enable_chinese_name = False

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

    # ========================================================================
    # 三层输出接口 / Трёхуровневый интерфейс / Three-layer output interface
    # ========================================================================

    def compute_comparisons(
        self,
        mention: Dict[str, Any],
        author: Author
    ) -> Dict[str, Any]:
        """
        第1层：计算比较结果（raw值 + bin）/ Уровень 1: Вычисление сравнений
        Layer 1: Compute comparisons (raw values + bins)

        为每个特征计算原始相似度值，并分配到对应的bin
        Вычисляет сырые значения сходства для каждого признака и назначает в бины
        Computes raw similarity values for each feature and assigns to bins

        Args:
            mention: 候选作者mention（字典格式）/ Упоминание кандидата
            author: 现有作者对象 / Существующий объект автора

        Returns:
            Dict包含每个特征的comparison结果：
            {
                "name_sim": 0.85,  # 原始相似度 / сырое значение
                "name_bin": "high",  # 分箱结果 / результат биннинга
                "orcid_match": True/False,
                "orcid_bin": "match"/"missing",
                "coauthor_sim": 0.30,
                "coauthor_bin": "medium",
                ...
            }
        """
        comparisons = {}

        # 1. 姓名相似度（含Chinese-name增强）/ Сходство имён (с китайским усилением)
        mention_name = mention.get('name', '')
        author_name = author.canonical_name

        if mention_name and author_name:
            # Chinese-name增强（如果启用）/ Усиление китайских имён
            normalized_mention_name = mention_name
            chinese_name_confidence = "unknown"

            if self.enable_chinese_name and self.chinese_name_module:
                # TODO: 调用一号项目模块
                # normalized_mention_name, confidence = self.chinese_name_module.normalize(mention_name)
                # chinese_name_confidence = self._bin_chinese_name_confidence(confidence)
                pass

            # 计算姓名相似度 / Вычисление сходства имён
            name_sim = self._calculate_name_similarity(normalized_mention_name, author_name)
            comparisons['name_sim'] = name_sim
            comparisons['name_bin'] = self._bin_name_similarity(name_sim)

            # Chinese-name特征（独立）/ Признак китайского имени
            if self.enable_chinese_name:
                comparisons['chinese_name_confidence'] = chinese_name_confidence
                comparisons['chinese_name_bin'] = chinese_name_confidence
        else:
            comparisons['name_sim'] = 0.0
            comparisons['name_bin'] = "none"

        # 2. ORCID匹配 / Совпадение ORCID
        mention_orcid = mention.get('orcid', '')
        if mention_orcid and author.orcid:
            orcid_match = (self._clean_orcid(mention_orcid) == self._clean_orcid(author.orcid))
            comparisons['orcid_match'] = orcid_match
            comparisons['orcid_bin'] = "match" if orcid_match else "missing"
        else:
            comparisons['orcid_match'] = False
            comparisons['orcid_bin'] = "missing"

        # 3. 合著者重叠 / Пересечение соавторов
        mention_coauthors = set(mention.get('coauthors', []))
        author_coauthors = author.coauthor_ids
        if mention_coauthors and author_coauthors:
            coauthor_sim = self._calculate_jaccard_similarity(mention_coauthors, author_coauthors)
            comparisons['coauthor_sim'] = coauthor_sim
            comparisons['coauthor_bin'] = self._bin_coauthor_similarity(coauthor_sim)
        else:
            comparisons['coauthor_sim'] = 0.0
            comparisons['coauthor_bin'] = "none"

        # 4. 期刊重叠 / Пересечение журналов
        mention_journals = set(mention.get('journals', []))
        author_journals = author.journals
        if mention_journals and author_journals:
            journal_sim = self._calculate_journal_similarity(mention_journals, author_journals)
            comparisons['journal_sim'] = journal_sim
            comparisons['journal_bin'] = self._bin_journal_similarity(journal_sim)
        else:
            comparisons['journal_sim'] = 0.0
            comparisons['journal_bin'] = "none"

        # 5. 机构相似度 / Сходство аффилиаций
        mention_affiliations = mention.get('affiliation', [])
        if isinstance(mention_affiliations, str):
            mention_affiliations = [mention_affiliations]
        author_affiliations = list(author.affiliations)

        if mention_affiliations and author_affiliations:
            affiliation_sim = self._calculate_affiliation_similarity_max(
                mention_affiliations, author_affiliations
            )
            comparisons['affiliation_sim'] = affiliation_sim
            comparisons['affiliation_bin'] = self._bin_affiliation_similarity(affiliation_sim)
        else:
            comparisons['affiliation_sim'] = 0.0
            comparisons['affiliation_bin'] = "none"

        return comparisons

    def score_baseline(self, comparisons: Dict[str, Any]) -> Tuple[float, Dict[str, float]]:
        """
        第2层：Baseline评分（加权相似度）/ Уровень 2: Базовая оценка
        Layer 2: Baseline scoring (weighted similarity)

        使用SIMILARITY_WEIGHTS对原始相似度加权求和
        Использует SIMILARITY_WEIGHTS для взвешенной суммы сырых значений
        Uses SIMILARITY_WEIGHTS to compute weighted sum of raw similarities

        Args:
            comparisons: compute_comparisons的输出 / Выход из compute_comparisons

        Returns:
            (total_score, components):
                - total_score: 总分 [0.0-1.0] / Общий балл
                - components: 各特征贡献 / Вклад каждого признака
        """
        components = {}
        total_score = 0.0

        # 姓名 / Имя
        if "name" in self.weights and self.weights["name"] > 0:
            name_contrib = comparisons.get('name_sim', 0.0) * self.weights["name"]
            components['name'] = name_contrib
            total_score += name_contrib

        # 合著者 / Соавторы
        if "coauthors" in self.weights and self.weights["coauthors"] > 0:
            coauthor_contrib = comparisons.get('coauthor_sim', 0.0) * self.weights["coauthors"]
            components['coauthors'] = coauthor_contrib
            total_score += coauthor_contrib

        # 期刊 / Журналы
        if "journals" in self.weights and self.weights["journals"] > 0:
            journal_contrib = comparisons.get('journal_sim', 0.0) * self.weights["journals"]
            components['journals'] = journal_contrib
            total_score += journal_contrib

        # 可扩展其他维度 / Расширяемые другие измерения
        # (机构、研究领域等，如果在weights中定义)

        return total_score, components

    def score_fellegi_sunter(
        self,
        comparisons: Dict[str, Any],
        mu_table: Optional[Dict[str, Dict[str, Dict[str, float]]]] = None
    ) -> Tuple[float, Dict[str, float]]:
        """
        第3层：Fellegi-Sunter评分（证据聚合）/ Уровень 3: Оценка Fellegi-Sunter
        Layer 3: Fellegi-Sunter scoring (evidence aggregation)

        使用m/u参数计算log-likelihood ratio (LLR)并求和
        Использует параметры m/u для вычисления log-likelihood ratio и суммирования
        Uses m/u parameters to compute log-likelihood ratio and aggregate

        公式 / Формула / Formula:
            S = Σ w_i = Σ log(m_i / u_i)
            其中 m_i = P(feature=bin | match), u_i = P(feature=bin | non-match)

        Args:
            comparisons: compute_comparisons的输出 / Выход из compute_comparisons
            mu_table: m/u参数表（可选，默认使用self.mu_table）

        Returns:
            (total_score, components_llr):
                - total_score: 总log-likelihood ratio / Общий LLR
                - components_llr: 各特征的LLR贡献 / Вклад LLR каждого признака
        """
        if mu_table is None:
            mu_table = self.mu_table

        components_llr = {}
        total_score = 0.0

        # 定义特征映射：(comparison_bin_key, mu_table_feature_key)
        # Определение сопоставления признаков
        feature_mappings = [
            ('name_bin', 'name'),
            ('orcid_bin', 'orcid'),
            ('coauthor_bin', 'coauthor'),
            ('journal_bin', 'journal'),
            ('affiliation_bin', 'affiliation'),
        ]

        # 如果启用Chinese-name，添加该特征 / Если включено, добавить признак
        if self.enable_chinese_name and 'chinese_name_bin' in comparisons:
            feature_mappings.append(('chinese_name_bin', 'chinese_name'))

        for comp_key, mu_key in feature_mappings:
            if comp_key in comparisons:
                bin_value = comparisons[comp_key]

                # 查找m/u参数 / Поиск параметров m/u
                if mu_key in mu_table and bin_value in mu_table[mu_key]:
                    m = mu_table[mu_key][bin_value]['m']
                    u = mu_table[mu_key][bin_value]['u']

                    # 计算log-likelihood ratio / Вычисление LLR
                    # 处理极端情况 / Обработка крайних случаев
                    if u == 0:
                        # 避免除零 / Избегание деления на ноль
                        llr = math.log(m / 1e-10) if m > 0 else 0.0
                    elif m == 0:
                        llr = math.log(1e-10 / u)
                    else:
                        llr = math.log(m / u)

                    components_llr[mu_key] = llr
                    total_score += llr
                else:
                    # bin或特征未在mu_table中定义，跳过
                    # Бин или признак не определён в mu_table
                    self.logger.debug(
                        f"Feature {mu_key} or bin {bin_value} not found in MU table, skipping"
                    )

        return total_score, components_llr

    # ========================================================================
    # Binning辅助方法 / Вспомогательные методы биннинга / Binning helpers
    # ========================================================================

    def _bin_name_similarity(self, sim: float) -> str:
        """将姓名相似度分箱 / Биннинг сходства имён / Bin name similarity"""
        if sim >= 0.95:
            return "exact"
        elif sim >= 0.75:
            return "high"
        elif sim >= 0.50:
            return "medium"
        elif sim > 0.0:
            return "low"
        else:
            return "none"

    def _bin_coauthor_similarity(self, sim: float) -> str:
        """将合著者相似度分箱 / Биннинг сходства соавторов"""
        if sim >= 0.50:
            return "high"
        elif sim >= 0.20:
            return "medium"
        elif sim > 0.0:
            return "low"
        else:
            return "none"

    def _bin_journal_similarity(self, sim: float) -> str:
        """将期刊相似度分箱 / Биннинг сходства журналов"""
        if sim >= 0.50:
            return "high"
        elif sim >= 0.20:
            return "medium"
        elif sim > 0.0:
            return "low"
        else:
            return "none"

    def _bin_affiliation_similarity(self, sim: float) -> str:
        """将机构相似度分箱 / Биннинг сходства аффилиаций"""
        if sim >= 0.90:
            return "exact"
        elif sim >= 0.70:
            return "high"
        elif sim >= 0.40:
            return "medium"
        elif sim > 0.0:
            return "low"
        else:
            return "none"

    def _calculate_affiliation_similarity_max(
        self,
        affiliations1: list,
        affiliations2: list
    ) -> float:
        """
        计算机构相似度（最大值策略）/ Расчёт сходства аффилиаций (макс)
        Calculate affiliation similarity (max strategy)

        Args:
            affiliations1: 候选机构列表 / Список аффилиаций кандидата
            affiliations2: 作者机构列表 / Список аффилиаций автора

        Returns:
            float: 最高的机构相似度 / Максимальное сходство
        """
        if not affiliations1 or not affiliations2:
            return 0.0

        max_sim = 0.0
        for aff1 in affiliations1:
            for aff2 in affiliations2:
                # 使用Levenshtein相似度 / Использование сходства Левенштейна
                norm_aff1 = self._normalize_affiliation(aff1)
                norm_aff2 = self._normalize_affiliation(aff2)

                if norm_aff1 == norm_aff2:
                    return 1.0  # 完全匹配 / Точное совпадение

                # 计算相似度 / Вычисление сходства
                lev_dist = self._levenshtein_distance(norm_aff1, norm_aff2)
                max_len = max(len(norm_aff1), len(norm_aff2))
                if max_len > 0:
                    sim = 1.0 - (lev_dist / max_len)
                    max_sim = max(max_sim, sim)

        return max_sim

    def _normalize_affiliation(self, affiliation: str) -> str:
        """
        标准化机构名称 / Нормализация названия учреждения

        Args:
            affiliation: 原始机构名 / Исходное название

        Returns:
            str: 标准化后的机构名 / Нормализованное название
        """
        if not affiliation:
            return ''

        # 转小写 / Нижний регистр
        aff = affiliation.lower().strip()

        # 移除常见后缀 / Удаление распространённых суффиксов
        aff = re.sub(r'\buniversity\b', 'univ', aff)
        aff = re.sub(r'\binstitute\b', 'inst', aff)
        aff = re.sub(r'\bdepartment\b', 'dept', aff)

        # 移除标点和多余空格 / Удаление пунктуации и лишних пробелов
        aff = re.sub(r'[^\w\s]', '', aff)
        aff = ' '.join(aff.split())

        return aff

    def _clean_orcid(self, orcid: str) -> str:
        """
        清理ORCID格式 / Очистка формата ORCID

        Args:
            orcid: 原始ORCID / Исходный ORCID

        Returns:
            str: 清理后的ORCID / Очищенный ORCID
        """
        if not orcid:
            return ''

        # 移除URL前缀 / Удаление URL префикса
        orcid = orcid.replace('http://orcid.org/', '')
        orcid = orcid.replace('https://orcid.org/', '')

        return orcid.strip()