# -*- coding: utf-8 -*-
"""
决策类型定义 / Определения типов решений / Decision Type Definitions

定义三分决策系统的核心数据结构：MERGE/NEW/UNKNOWN
Определяет основные структуры данных для системы тройного решения
Defines core data structures for three-way decision system

中文注释：决策类型与结果的数据结构
Русский комментарий: Структуры данных для типов решений и результатов
"""

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any
import json


class Decision(Enum):
    """
    三分决策枚举 / Перечисление тройного решения / Three-way decision enumeration

    MERGE: 确认匹配，合并到现有作者 / Подтверждённое совпадение, слияние
    NEW: 确认不匹配，创建新作者 / Подтверждённое несовпадение, создание нового автора
    UNKNOWN: 不确定，需要人工审核 / Неопределённо, требует ручной проверки
    """
    MERGE = "merge"       # score >= accept_threshold
    NEW = "new"           # score <= reject_threshold
    UNKNOWN = "unknown"   # reject_threshold < score < accept_threshold


@dataclass
class DecisionResult:
    """
    决策结果数据类 / Класс данных результата решения / Decision result dataclass

    包含完整的决策trace信息，用于可审计性和可解释性
    Содержит полную трассировку решения для аудита и объяснимости
    Contains complete decision trace for auditability and explainability

    Attributes:
        decision: 决策结果（MERGE/NEW/UNKNOWN）/ Результат решения
        best_author_id: 最佳匹配作者ID（仅当decision=MERGE时有效）/ ID лучшего совпадения
        score_total: 总分数（baseline模式：加权相似度；FS模式：log-likelihood ratio总和）
                     Общий балл / Total score
        score_components: 各特征分数明细 / Детализация баллов / Score breakdown by feature
        comparisons: 原始比较结果（特征值+bin）/ Сырые результаты сравнения / Raw comparison results
        thresholds: 使用的阈值配置 / Использованные пороги / Thresholds used
        topk: 前k个候选及其分数 / Топ-k кандидатов / Top-k candidates with scores
        reason: 决策理由（简短说明）/ Причина решения / Decision rationale
        deterministic_hash: 确定性hash（用于可复现性验证）/ Хэш для воспроизводимости
        mode: 使用的模式（baseline/fs）/ Использованный режим / Mode used
        run_id: 运行ID / ID запуска / Run ID
        candidate_count: 候选作者数量 / Количество кандидатов / Number of candidates
        blocking_keys: 使用的blocking键 / Ключи блокировки / Blocking keys used
    """
    decision: Decision
    score_total: float
    score_components: Dict[str, float]
    comparisons: Dict[str, Any]
    thresholds: Dict[str, float]
    mode: str  # "baseline" or "fs"

    # 可选字段 / Опциональные поля / Optional fields
    best_author_id: Optional[str] = None
    topk: List[Dict[str, Any]] = field(default_factory=list)
    reason: str = ""
    deterministic_hash: str = ""
    run_id: Optional[str] = None
    candidate_count: int = 0
    blocking_keys: List[str] = field(default_factory=list)

    def __post_init__(self):
        """
        后初始化：计算确定性hash / Постинициализация: вычисление хэша
        """
        if not self.deterministic_hash:
            self.deterministic_hash = self._compute_deterministic_hash()

        # 自动生成reason（如果为空）/ Автогенерация причины / Auto-generate reason
        if not self.reason:
            self.reason = self._generate_reason()

    def _compute_deterministic_hash(self) -> str:
        """
        计算确定性hash，用于验证可复现性
        Вычисление детерминированного хэша для проверки воспроизводимости
        Compute deterministic hash for reproducibility verification

        Returns:
            str: SHA256 hash（前12字符）/ SHA256 хэш (первые 12 символов)
        """
        # 构造可序列化的字典 / Создание сериализуемого словаря
        hash_data = {
            "decision": self.decision.value,
            "score_total": round(self.score_total, 6),  # 限制精度 / ограничить точность
            "score_components": {k: round(v, 6) for k, v in sorted(self.score_components.items())},
            "best_author_id": self.best_author_id,
            "mode": self.mode,
            "thresholds": {k: round(v, 6) for k, v in sorted(self.thresholds.items())},
        }

        # 序列化为JSON字符串（排序键以保证确定性）/ Сериализация в JSON
        hash_str = json.dumps(hash_data, sort_keys=True, ensure_ascii=False)

        # 计算SHA256 / Вычисление SHA256
        hash_obj = hashlib.sha256(hash_str.encode('utf-8'))
        return hash_obj.hexdigest()[:12]  # 返回前12字符 / первые 12 символов

    def _generate_reason(self) -> str:
        """
        自动生成决策理由 / Автогенерация причины решения / Auto-generate decision rationale

        Returns:
            str: 决策理由 / Причина решения
        """
        if self.decision == Decision.MERGE:
            return (
                f"Score {self.score_total:.3f} >= accept_threshold {self.thresholds.get('accept', 'N/A')}, "
                f"merged with author {self.best_author_id}"
            )
        elif self.decision == Decision.NEW:
            return (
                f"Score {self.score_total:.3f} <= reject_threshold {self.thresholds.get('reject', 'N/A')}, "
                f"created new author"
            )
        else:  # UNKNOWN
            accept = self.thresholds.get('accept', 'N/A')
            reject = self.thresholds.get('reject', 'N/A')
            return (
                f"Score {self.score_total:.3f} in uncertain range "
                f"({reject} < score < {accept}), requires manual review"
            )

    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典（用于JSON序列化）/ Преобразование в словарь / Convert to dictionary

        Returns:
            Dict: 可序列化的字典 / Сериализуемый словарь
        """
        return {
            "decision": self.decision.value,
            "best_author_id": self.best_author_id,
            "score_total": round(self.score_total, 6),
            "score_components": {k: round(v, 6) for k, v in self.score_components.items()},
            "comparisons": self.comparisons,
            "thresholds": self.thresholds,
            "topk": self.topk,
            "reason": self.reason,
            "deterministic_hash": self.deterministic_hash,
            "mode": self.mode,
            "run_id": self.run_id,
            "candidate_count": self.candidate_count,
            "blocking_keys": self.blocking_keys,
        }

    def to_json(self, **kwargs) -> str:
        """
        转换为JSON字符串 / Преобразование в JSON / Convert to JSON string

        Returns:
            str: JSON字符串 / JSON строка
        """
        return json.dumps(self.to_dict(), ensure_ascii=False, **kwargs)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DecisionResult':
        """
        从字典创建DecisionResult / Создание из словаря / Create from dictionary

        Args:
            data: 字典数据 / Данные словаря

        Returns:
            DecisionResult: 决策结果对象 / Объект результата решения
        """
        # 转换decision字符串为枚举 / Преобразование строки в enum
        decision = Decision(data['decision'])

        return cls(
            decision=decision,
            best_author_id=data.get('best_author_id'),
            score_total=data['score_total'],
            score_components=data['score_components'],
            comparisons=data.get('comparisons', {}),
            thresholds=data.get('thresholds', {}),
            topk=data.get('topk', []),
            reason=data.get('reason', ''),
            deterministic_hash=data.get('deterministic_hash', ''),
            mode=data.get('mode', 'unknown'),
            run_id=data.get('run_id'),
            candidate_count=data.get('candidate_count', 0),
            blocking_keys=data.get('blocking_keys', []),
        )

    def is_merge(self) -> bool:
        """是否为MERGE决策 / Является ли решением MERGE"""
        return self.decision == Decision.MERGE

    def is_new(self) -> bool:
        """是否为NEW决策 / Является ли решением NEW"""
        return self.decision == Decision.NEW

    def is_unknown(self) -> bool:
        """是否为UNKNOWN决策 / Является ли решением UNKNOWN"""
        return self.decision == Decision.UNKNOWN

    def __repr__(self) -> str:
        """字符串表示 / Строковое представление / String representation"""
        return (
            f"DecisionResult(decision={self.decision.value}, "
            f"score={self.score_total:.3f}, "
            f"best_author={self.best_author_id}, "
            f"mode={self.mode}, "
            f"hash={self.deterministic_hash})"
        )


# 测试代码 / Тестовый код / Test code
if __name__ == '__main__':
    print("=" * 80)
    print("Decision Types Module Test / Тест модуля типов решений")
    print("=" * 80)

    # 测试1：创建MERGE决策 / Тест 1: Создание решения MERGE
    print("\n[Test 1] MERGE Decision")
    merge_result = DecisionResult(
        decision=Decision.MERGE,
        best_author_id="au_12345",
        score_total=0.92,
        score_components={"name": 0.95, "orcid": 1.0, "coauthor": 0.75},
        comparisons={"name_bin": "exact", "orcid_bin": "match"},
        thresholds={"accept": 0.90, "reject": 0.20},
        mode="fs",
        run_id="test_run_001",
        candidate_count=5,
        blocking_keys=["surname:smith", "orcid:0000-0001-2345-6789"]
    )
    print(merge_result)
    print(f"  Reason: {merge_result.reason}")
    print(f"  Hash: {merge_result.deterministic_hash}")

    # 测试2：创建NEW决策 / Тест 2: Создание решения NEW
    print("\n[Test 2] NEW Decision")
    new_result = DecisionResult(
        decision=Decision.NEW,
        score_total=0.15,
        score_components={"name": 0.20, "orcid": 0.0, "coauthor": 0.10},
        comparisons={"name_bin": "low", "orcid_bin": "missing"},
        thresholds={"accept": 0.90, "reject": 0.20},
        mode="fs",
        run_id="test_run_001"
    )
    print(new_result)
    print(f"  Reason: {new_result.reason}")

    # 测试3：创建UNKNOWN决策 / Тест 3: Создание решения UNKNOWN
    print("\n[Test 3] UNKNOWN Decision")
    unknown_result = DecisionResult(
        decision=Decision.UNKNOWN,
        best_author_id="au_67890",
        score_total=0.55,
        score_components={"name": 0.60, "orcid": 0.0, "coauthor": 0.40},
        comparisons={"name_bin": "medium", "orcid_bin": "missing"},
        thresholds={"accept": 0.90, "reject": 0.20},
        topk=[
            {"author_id": "au_67890", "score": 0.55},
            {"author_id": "au_11111", "score": 0.48}
        ],
        mode="fs",
        run_id="test_run_001"
    )
    print(unknown_result)
    print(f"  Reason: {unknown_result.reason}")

    # 测试4：JSON序列化与反序列化 / Тест 4: Сериализация и десериализация JSON
    print("\n[Test 4] JSON Serialization/Deserialization")
    json_str = merge_result.to_json(indent=2)
    print("  JSON output (first 200 chars):")
    print(f"  {json_str[:200]}...")

    # 反序列化 / Десериализация
    reconstructed = DecisionResult.from_dict(json.loads(json_str))
    print(f"  Reconstructed: {reconstructed}")
    print(f"  Hash match: {reconstructed.deterministic_hash == merge_result.deterministic_hash}")

    # 测试5：确定性hash / Тест 5: Детерминированный хэш
    print("\n[Test 5] Deterministic Hash")
    result1 = DecisionResult(
        decision=Decision.MERGE,
        best_author_id="au_test",
        score_total=0.85,
        score_components={"name": 0.90, "orcid": 0.80},
        comparisons={},
        thresholds={"accept": 0.90, "reject": 0.20},
        mode="baseline"
    )
    result2 = DecisionResult(
        decision=Decision.MERGE,
        best_author_id="au_test",
        score_total=0.85,
        score_components={"name": 0.90, "orcid": 0.80},
        comparisons={},
        thresholds={"accept": 0.90, "reject": 0.20},
        mode="baseline"
    )
    print(f"  Result1 hash: {result1.deterministic_hash}")
    print(f"  Result2 hash: {result2.deterministic_hash}")
    print(f"  Hashes match: {result1.deterministic_hash == result2.deterministic_hash}")

    print("\n" + "=" * 80)
    print("All tests completed / Все тесты завершены")
    print("=" * 80)
