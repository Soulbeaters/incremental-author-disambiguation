# -*- coding: utf-8 -*-
"""
作者消歧引擎 / Движок устранения неоднозначности авторов / Author Disambiguation Engine

实现风险控制的增量消歧框架，支持三分决策（MERGE/NEW/UNKNOWN）
Реализует фреймворк инкрементальной дизамбигуации с контролем риска
Implements risk-controlled incremental disambiguation framework

核心功能 / Основные функции / Core features:
1. 双阈值三分决策 / Двухпороговое тройное решение / Dual-threshold three-way decision
2. Fellegi-Sunter证据聚合 / Агрегация доказательств Феллеги-Сантера / Fellegi-Sunter evidence aggregation
3. 审计追踪记录 / Аудит-трассировка / Auditable decision trace
4. 多键blocking检索 / Многоключевая блокировка / Multi-key blocking retrieval

中文注释：作者消歧核心模块
Русский комментарий: Основной модуль дизамбигуации авторов
"""

import logging
from typing import List, Optional, Tuple, Set, Dict, Any
try:
    from Levenshtein import ratio
except ImportError:
    # 如果没有Levenshtein库，使用简单的相似度计算
    # Если библиотека Levenshtein отсутствует, используем простое вычисление
    def ratio(s1: str, s2: str) -> float:
        """简单的字符串相似度计算 / Простое вычисление сходства строк"""
        if s1 == s2:
            return 1.0
        if not s1 or not s2:
            return 0.0
        set1 = set(s1.lower().split())
        set2 = set(s2.lower().split())
        if not set1 or not set2:
            return 0.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0


from models.author import Author
from models.database import AuthorDatabase
from disambiguation_engine.similarity_scorer import SimilarityScorer
from disambiguation_engine.decision_types import Decision, DecisionResult
from disambiguation_engine.decision_trace import DecisionTraceLogger


class AuthorMerger:
    """
    作者消歧引擎 / Движок устранения неоднозначности авторов
    Author Disambiguation Engine

    实现双阈值三分决策框架，支持Baseline和Fellegi-Sunter两种模式
    Реализует фреймворк тройного решения с двумя порогами
    Implements dual-threshold three-way decision framework

    决策类型 / Типы решений / Decision types:
    - MERGE: score >= accept_threshold（合并到现有作者 / слияние）
    - NEW: score <= reject_threshold（创建新作者 / создание нового）
    - UNKNOWN: reject < score < accept（人工审核 / ручная проверка）

    Attributes:
        mode (str): 评分模式 "baseline" 或 "fs" / Режим оценки
        database (AuthorDatabase): 作者数据库（用于blocking检索）
        scorer (SimilarityScorer): 相似度评分器 / Оценщик сходства
        trace_logger (Optional[DecisionTraceLogger]): 决策追踪日志器
        accept_threshold (float): MERGE决策阈值 / Порог MERGE
        reject_threshold (float): NEW决策阈值 / Порог NEW
    """

    def __init__(
        self,
        database: AuthorDatabase,
        mode: str = "fs",
        accept_threshold: float = 0.90,
        reject_threshold: float = 0.20,
        scorer_config: Optional[Dict[str, Any]] = None,
        trace_logger: Optional[DecisionTraceLogger] = None,
        run_id: Optional[str] = None,
        topk: int = 5
    ):
        """
        初始化作者消歧引擎 / Инициализация движка дизамбигуации

        Args:
            database: 作者数据库实例 / Экземпляр базы данных авторов
            mode: 评分模式 "baseline"（加权相似度）或 "fs"（Fellegi-Sunter）
                  Режим оценки: "baseline" или "fs"
            accept_threshold: MERGE决策阈值（分数>=此值判定为MERGE）
                             Порог MERGE (оценка >= этого значения)
            reject_threshold: NEW决策阈值（分数<=此值判定为NEW）
                             Порог NEW (оценка <= этого значения)
            scorer_config: SimilarityScorer配置（可选，默认使用config.py）
                          Конфигурация SimilarityScorer
            trace_logger: 决策追踪日志器（可选）/ Логгер трассировки решений
            run_id: 运行ID（用于trace）/ ID запуска (для трассировки)
            topk: 返回前k个候选（用于UNKNOWN决策）/ Топ-k кандидатов
        """
        # 验证模式 / Проверка режима
        if mode not in ["baseline", "fs"]:
            raise ValueError(f"Invalid mode: {mode}. Must be 'baseline' or 'fs'")

        # 验证阈值 / Проверка порогов
        if reject_threshold >= accept_threshold:
            raise ValueError(
                f"reject_threshold ({reject_threshold}) must be < accept_threshold ({accept_threshold})"
            )

        self.database = database
        self.mode = mode
        self.accept_threshold = accept_threshold
        self.reject_threshold = reject_threshold
        self.topk = topk
        self.run_id = run_id
        self.trace_logger = trace_logger

        # 初始化scorer / Инициализация оценщика
        self.scorer = SimilarityScorer(config=scorer_config)

        self.logger = logging.getLogger(__name__)
        self.logger.info(
            f"AuthorMerger initialized / Инициализирован: mode={mode}, "
            f"accept_threshold={accept_threshold}, reject_threshold={reject_threshold}"
        )

    def make_decision(
        self,
        mention: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> DecisionResult:
        """
        对候选mention做三分决策 / Тройное решение для упоминания кандидата
        Three-way decision for candidate mention

        Args:
            mention: 候选作者mention（字典格式）/ Упоминание кандидата
                     必须包含 'name' 键，可选 'orcid', 'coauthors', 'journals', 'affiliation'
            metadata: 元数据（可选，用于trace记录）/ Метаданные (для трассировки)
                     例如: {"doi": "10.1234/...", "publication_title": "..."}

        Returns:
            DecisionResult: 决策结果对象，包含：
                - decision: Decision.MERGE / Decision.NEW / Decision.UNKNOWN
                - best_author_id: 最佳匹配作者ID（MERGE时有效）
                - score_total: 总分数
                - score_components: 各特征分数
                - comparisons: 原始比较结果
                - thresholds: 使用的阈值
                - topk: 前k个候选
                - reason: 决策理由
                - deterministic_hash: 可复现性hash
        """
        # 1. Blocking检索候选作者 / Блокирующий поиск кандидатов
        candidates = self.database.get_candidates(mention, max_candidates=100)
        blocking_keys_used = self._extract_blocking_keys(mention)

        self.logger.debug(
            f"Retrieved {len(candidates)} candidates via blocking for mention: "
            f"{mention.get('name', 'N/A')}"
        )

        # 2. 如果没有候选，直接判定为NEW / Если нет кандидатов, сразу NEW
        if not candidates:
            result = self._make_new_decision(
                mention=mention,
                score_total=0.0,
                score_components={},
                comparisons={},
                blocking_keys=blocking_keys_used
            )
            self._log_trace(result, mention, metadata)
            return result

        # 3. 对每个候选计算相似度 / Вычисление сходства для каждого кандидата
        scored_candidates = []
        for author in candidates:
            # Layer 1: 计算comparisons / Вычисление сравнений
            comparisons = self.scorer.compute_comparisons(mention, author)

            # Layer 2/3: 根据模式选择评分方法 / Выбор метода оценки
            if self.mode == "baseline":
                score, components = self.scorer.score_baseline(comparisons)
            else:  # fs
                score, components = self.scorer.score_fellegi_sunter(comparisons)

            scored_candidates.append({
                "author": author,
                "author_id": author.author_id,
                "score": score,
                "components": components,
                "comparisons": comparisons
            })

        # 4. 排序并选择最佳候选 / Сортировка и выбор лучшего
        scored_candidates.sort(key=lambda x: x["score"], reverse=True)
        best_candidate = scored_candidates[0]
        best_score = best_candidate["score"]
        best_author_id = best_candidate["author_id"]

        # 5. 三分决策逻辑 / Логика тройного решения
        if best_score >= self.accept_threshold:
            decision = Decision.MERGE
        elif best_score <= self.reject_threshold:
            decision = Decision.NEW
        else:
            decision = Decision.UNKNOWN

        # 6. 构建topk列表 / Построение списка топ-k
        topk_list = [
            {
                "author_id": cand["author_id"],
                "score": round(cand["score"], 6),
                "components": {k: round(v, 6) for k, v in cand["components"].items()}
            }
            for cand in scored_candidates[:self.topk]
        ]

        # 7. 构建DecisionResult / Создание DecisionResult
        result = DecisionResult(
            decision=decision,
            best_author_id=best_author_id if decision == Decision.MERGE else None,
            score_total=best_score,
            score_components=best_candidate["components"],
            comparisons=best_candidate["comparisons"],
            thresholds={
                "accept": self.accept_threshold,
                "reject": self.reject_threshold
            },
            mode=self.mode,
            topk=topk_list,
            run_id=self.run_id,
            candidate_count=len(candidates),
            blocking_keys=blocking_keys_used
        )

        # 8. 记录trace（如果启用）/ Запись трассировки
        self._log_trace(result, mention, metadata)

        # 9. 日志 / Логирование
        self.logger.info(
            f"Decision: {decision.value}, mention: {mention.get('name', 'N/A')}, "
            f"score: {best_score:.3f}, best_author: {best_author_id if decision == Decision.MERGE else 'N/A'}"
        )

        return result

    def _extract_blocking_keys(self, mention: Dict[str, Any]) -> List[str]:
        """
        提取mention的blocking keys / Извлечение ключей блокировки
        Extract blocking keys from mention

        Args:
            mention: 候选mention / Упоминание кандидата

        Returns:
            List[str]: blocking keys列表 / Список ключей блокировки
        """
        keys = []

        # ORCID key
        orcid = mention.get('orcid', '')
        if orcid:
            keys.append(f"orcid:{orcid}")

        # Surname key
        name = mention.get('name', '')
        if name:
            # 简单提取姓氏（最后一个词）/ Простое извлечение фамилии
            tokens = name.strip().split()
            if tokens:
                surname = tokens[-1].lower()
                keys.append(f"surname:{surname}")

                # Surname + initial
                if len(tokens) >= 2:
                    first_initial = tokens[0][0].upper() if tokens[0] else ''
                    if first_initial:
                        keys.append(f"surname_initial:{surname}_{first_initial}")

        return keys

    def _make_new_decision(
        self,
        mention: Dict[str, Any],
        score_total: float,
        score_components: Dict[str, float],
        comparisons: Dict[str, Any],
        blocking_keys: List[str]
    ) -> DecisionResult:
        """
        创建NEW决策结果 / Создание результата решения NEW
        Create NEW decision result

        Args:
            mention: 候选mention
            score_total: 总分
            score_components: 分数组件
            comparisons: 比较结果
            blocking_keys: blocking keys

        Returns:
            DecisionResult: NEW决策结果
        """
        return DecisionResult(
            decision=Decision.NEW,
            best_author_id=None,
            score_total=score_total,
            score_components=score_components,
            comparisons=comparisons,
            thresholds={
                "accept": self.accept_threshold,
                "reject": self.reject_threshold
            },
            mode=self.mode,
            topk=[],
            run_id=self.run_id,
            candidate_count=0,
            blocking_keys=blocking_keys
        )

    def _log_trace(
        self,
        result: DecisionResult,
        mention: Dict[str, Any],
        metadata: Optional[Dict[str, Any]]
    ) -> None:
        """
        记录决策trace / Запись трассировки решения
        Log decision trace

        Args:
            result: 决策结果 / Результат решения
            mention: 候选mention / Упоминание
            metadata: 元数据 / Метаданные
        """
        if self.trace_logger:
            try:
                self.trace_logger.append_trace(
                    decision_result=result,
                    mention_data=mention,
                    metadata=metadata
                )
            except Exception as e:
                self.logger.error(f"Failed to log trace: {e}", exc_info=True)

    # ========================================================================
    # 向后兼容方法（已废弃，请使用make_decision）
    # Методы обратной совместимости (устарели, используйте make_decision)
    # Backward compatibility methods (deprecated, use make_decision)
    # ========================================================================

    def find_matching_author(
        self,
        candidate: Dict[str, Any],
        existing_authors: List[Author] = None
    ) -> Tuple[Optional[Author], float]:
        """
        旧接口（已废弃）：查找匹配作者 / Старый интерфейс (устарел)
        DEPRECATED: Use make_decision() instead

        此方法保留用于向后兼容，但已被make_decision()替代
        Этот метод сохранён для обратной совместимости

        Args:
            candidate: 候选作者数据
            existing_authors: 忽略（使用database.get_candidates）

        Returns:
            (matched_author, score): 如果有匹配则返回，否则(None, 0.0)
        """
        self.logger.warning(
            "find_matching_author() is deprecated. Use make_decision() instead."
        )

        result = self.make_decision(candidate)

        if result.is_merge() and result.best_author_id:
            # 从database中检索作者对象
            author = self.database.get_author(result.best_author_id)
            return author, result.score_total
        else:
            return None, result.score_total

    def merge_authors(
        self,
        target_author: Author,
        source_author: Author
    ) -> Author:
        """
        合并两个作者实体 / Слияние двух сущностей автора

        将source_author的所有信息合并到target_author中
        Слияние всей информации из source_author в target_author

        参数 / Параметры / Parameters:
            target_author: 目标作者（保留）/ Целевой автор (сохраняется)
            source_author: 源作者（将被合并）/ Исходный автор (будет объединён)

        返回 / Возвращает / Returns:
            合并后的作者对象 / Объединённый объект автора
        """
        self.logger.info(
            f"合并作者 / Слияние авторов: "
            f"'{source_author.canonical_name}' -> '{target_author.canonical_name}'"
        )

        # 合并备选姓名 / Слияние альтернативных имён
        target_author.alternate_names.update(source_author.alternate_names)

        # 合并出版物 / Слияние публикаций
        target_author.publications.update(source_author.publications)
        target_author.publication_count = len(target_author.publications)

        # 合并关联记录 / Слияние связанных записей
        target_author.linked_records.update(source_author.linked_records)

        # 合并合著者 / Слияние соавторов
        target_author.coauthor_ids.update(source_author.coauthor_ids)
        target_author.collaboration_count = len(target_author.coauthor_ids)

        # 合并期刊 / Слияние журналов
        target_author.journals.update(source_author.journals)

        # 合并机构 / Слияние аффилиаций
        target_author.affiliations.update(source_author.affiliations)

        # 更新置信度（合并会降低置信度）/ Обновление уверенности (слияние снижает уверенность)
        target_author.confidence_score = min(
            target_author.confidence_score,
            source_author.confidence_score * 0.95
        )

        self.logger.info(
            f"合并完成 / Слияние завершено: "
            f"pubs={target_author.publication_count}, "
            f"records={len(target_author.linked_records)}, "
            f"confidence={target_author.confidence_score:.3f}"
        )

        return target_author

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取消歧引擎统计信息 / Получение статистики движка дизамбигуации
        Get disambiguation engine statistics

        Returns:
            Dict: 统计信息字典 / Словарь статистики
        """
        stats = {
            'mode': self.mode,
            'accept_threshold': self.accept_threshold,
            'reject_threshold': self.reject_threshold,
            'topk': self.topk,
            'run_id': self.run_id,
            'trace_enabled': self.trace_logger is not None
        }

        # 添加database统计（如果可用）/ Добавление статистики базы данных
        if hasattr(self.database, 'count_authors'):
            stats['total_authors'] = self.database.count_authors()

        return stats


# 测试代码 / Тестовый код / Test Code
if __name__ == '__main__':
    """
    注意 / Примечание / Note:
    此模块已重构为三分决策框架。旧测试代码已移除。
    Этот модуль переработан во фреймворк тройного решения. Старые тесты удалены.
    This module has been refactored to three-way decision framework. Old tests removed.

    请使用以下独立测试脚本 / Используйте следующие тестовые скрипты:
    - test_scorer_three_layers.py: 测试三层评分接口
    - test_decision_trace.py: 测试决策追踪记录
    - (待创建 / to be created): test_author_merger_threeway.py

    新接口示例 / Пример нового интерфейса / New interface example:
        from models.database import AuthorDatabase
        from disambiguation_engine.author_merger import AuthorMerger

        db = AuthorDatabase()
        merger = AuthorMerger(
            database=db,
            mode="fs",
            accept_threshold=0.90,
            reject_threshold=0.20
        )

        mention = {
            "name": "John Smith",
            "orcid": "0000-0001-2345-6789",
            "coauthors": ["au_100", "au_101"],
            "journals": ["Nature"],
            "affiliation": ["Harvard University"]
        }

        result = merger.make_decision(mention)
        print(f"Decision: {result.decision.value}")
        print(f"Score: {result.score_total:.3f}")
        print(f"Best author: {result.best_author_id}")
    """

    print("=" * 80)
    print("AuthorMerger已重构为三分决策框架 / Переработан во фреймворк тройного решения")
    print("=" * 80)
    print("\n请使用独立测试脚本进行测试 / Используйте отдельные тестовые скрипты")
    print("例如 / Например: python test_scorer_three_layers.py")
    print("\n新接口 / Новый интерфейс:")
    print("  merger.make_decision(mention) -> DecisionResult")
    print("  - decision: MERGE / NEW / UNKNOWN")
    print("  - score_total: 总分数 / общий балл")
    print("  - best_author_id: 最佳匹配作者ID / ID лучшего совпадения")
    print("=" * 80)

    # 简单示例（需要database实例）/ Простой пример
    print("\n若要运行完整测试，请创建test_author_merger_threeway.py")
    print("Для полного теста создайте test_author_merger_threeway.py")
