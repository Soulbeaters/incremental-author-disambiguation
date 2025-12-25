# -*- coding: utf-8 -*-
"""
决策trace日志模块 / Модуль трейса решений / Decision Trace Logging Module

实现可审计但隐私保护的决策日志记录
Реализует аудируемое но приватное логирование решений
Implements auditable but privacy-preserving decision logging

中文注释：决策trace脱敏与记录
Русский комментарий: Редакция трейса решений и запись
"""

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from disambiguation_engine.decision_types import DecisionResult
else:
    try:
        from disambiguation_engine.decision_types import DecisionResult
    except ImportError:
        # 用于独立测试时 / Для изолированного тестирования
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from disambiguation_engine.decision_types import DecisionResult


class DecisionTraceLogger:
    """
    决策trace日志记录器 / Логгер трейса решений / Decision trace logger

    核心原则 / Основные принципы / Core principles:
    1. 不记录明文姓名，只记录hash和结构特征 / Не записывать имена в открытом виде
    2. 保留足够信息用于人工审核 / Сохранить достаточно информации для ручной проверки
    3. 支持确定性可复现验证 / Поддержка детерминированной воспроизводимости

    Attributes:
        trace_path: trace文件路径（JSONL格式）/ Путь к файлу трейса
        review_path: UNKNOWN池文件路径（JSONL格式）/ Путь к пулу UNKNOWN
        salt: 脱敏hash盐值 / Соль для хэширования
    """

    def __init__(
        self,
        trace_path: Optional[str] = None,
        review_path: Optional[str] = None,
        salt: Optional[str] = None
    ):
        """
        初始化trace日志记录器 / Инициализация логгера трейса

        Args:
            trace_path: trace输出路径 / Путь к трейсу
            review_path: UNKNOWN决策审核池路径 / Путь к пулу проверки UNKNOWN
            salt: hash盐值（用于姓名脱敏）/ Соль для хэширования имён
        """
        self.trace_path = Path(trace_path) if trace_path else None
        self.review_path = Path(review_path) if review_path else None

        # 从环境变量或参数获取盐值 / Получение соли из переменной окружения
        if salt is None:
            import os
            salt = os.environ.get('ISTINA_LOG_SALT', 'default_salt_change_in_production')

        self.salt = salt
        self.logger = logging.getLogger(__name__)

        # 创建输出目录（如果需要）/ Создание выходных директорий
        if self.trace_path:
            self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        if self.review_path:
            self.review_path.parent.mkdir(parents=True, exist_ok=True)

    def append_trace(
        self,
        decision_result: DecisionResult,
        mention_data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        写入决策trace记录（脱敏）/ Запись трейса решения (редактированного)

        Args:
            decision_result: 决策结果对象 / Объект результата решения
            mention_data: 原始mention数据（将被脱敏）/ Исходные данные (будут редактированы)
            metadata: 额外元数据（可选）/ Дополнительные метаданные
        """
        if not self.trace_path:
            return  # 未配置trace输出路径 / Путь не настроен

        # 构造脱敏后的trace记录 / Построение редактированной записи
        trace_record = self._build_redacted_trace(decision_result, mention_data, metadata)

        # 写入JSONL / Запись в JSONL
        try:
            with open(self.trace_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(trace_record, ensure_ascii=False) + '\n')
        except Exception as e:
            self.logger.error(f"Failed to write trace: {e}")

        # 如果是UNKNOWN决策，同时写入审核池 / Если UNKNOWN, также записать в пул проверки
        if decision_result.is_unknown() and self.review_path:
            self._append_review(decision_result, mention_data, metadata)

    def _append_review(
        self,
        decision_result: DecisionResult,
        mention_data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        写入UNKNOWN决策到审核池 / Запись решения UNKNOWN в пул проверки

        Args:
            decision_result: 决策结果 / Результат решения
            mention_data: mention数据 / Данные упоминания
            metadata: 元数据 / Метаданные
        """
        if not self.review_path:
            return

        # 审核池记录包含更多上下文信息以便人工审核
        # Записи для проверки содержат больше контекста для ручной проверки
        review_record = self._build_redacted_trace(decision_result, mention_data, metadata)
        review_record['review_status'] = 'pending'  # 待审核 / ожидает проверки
        review_record['review_timestamp'] = datetime.utcnow().isoformat()

        try:
            with open(self.review_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(review_record, ensure_ascii=False) + '\n')
        except Exception as e:
            self.logger.error(f"Failed to write review record: {e}")

    def _build_redacted_trace(
        self,
        decision_result: DecisionResult,
        mention_data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        构造脱敏后的trace记录 / Построение редактированной записи трейса

        **关键脱敏规则** / **Ключевые правила редакции** / **Key redaction rules**:
        1. 姓名 → hash + 结构特征（token数、长度、字符集）
           Имя → хэш + структурные признаки
        2. 机构/期刊 → 保留前缀hash（允许人工审核时参考）
           Аффилиации/журналы → хэш префикса
        3. ORCID → 允许明文（公开标识符）
           ORCID → разрешено в открытом виде (публичный идентификатор)
        4. 分数、bin、阈值 → 完整保留（统计分析需要）
           Баллы, бины, пороги → полностью сохранены

        Args:
            decision_result: 决策结果 / Результат решения
            mention_data: 原始mention数据 / Исходные данные упоминания
            metadata: 元数据 / Метаданные

        Returns:
            Dict: 脱敏后的trace记录 / Редактированная запись
        """
        # 脱敏mention数据 / Редактирование данных упоминания
        redacted_mention = self._redact_mention(mention_data)

        # 基础trace记录 / Базовая запись трейса
        trace = {
            "timestamp": datetime.utcnow().isoformat(),
            "run_id": decision_result.run_id,
            "mode": decision_result.mode,
            "decision": decision_result.decision.value,
            "score_total": round(decision_result.score_total, 6),
            "score_components": {
                k: round(v, 6) for k, v in decision_result.score_components.items()
            },
            "comparisons": decision_result.comparisons,  # bins是脱敏的 / бины редактированы
            "thresholds": decision_result.thresholds,
            "best_author_id": decision_result.best_author_id,
            "topk": decision_result.topk,
            "reason": decision_result.reason,
            "deterministic_hash": decision_result.deterministic_hash,
            "candidate_count": decision_result.candidate_count,
            "blocking_keys": decision_result.blocking_keys,
            "mention": redacted_mention,  # 脱敏后的mention / редактированное упоминание
        }

        # 添加元数据（如果有）/ Добавление метаданных
        if metadata:
            trace["metadata"] = metadata

        return trace

    def _redact_mention(self, mention_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        脱敏mention数据 / Редактирование данных упоминания

        Args:
            mention_data: 原始mention数据 / Исходные данные

        Returns:
            Dict: 脱敏后的mention / Редактированное упоминание
        """
        redacted = {}

        # 1. 姓名脱敏：hash + 结构特征 / Редакция имени: хэш + признаки
        if 'name' in mention_data and mention_data['name']:
            redacted['name'] = self._redact_name(mention_data['name'])

        # 2. ORCID：允许明文（公开标识符）/ ORCID: разрешено (публичный)
        if 'orcid' in mention_data:
            redacted['orcid'] = mention_data['orcid']

        # 3. 机构：hash前缀 / Аффилиация: хэш префикса
        if 'affiliation' in mention_data:
            affiliations = mention_data['affiliation']
            if isinstance(affiliations, str):
                affiliations = [affiliations]
            redacted['affiliation'] = [
                self._redact_affiliation(aff) for aff in affiliations if aff
            ]

        # 4. 合著者：数量（不记录明文）/ Соавторы: только количество
        if 'coauthors' in mention_data:
            coauthors = mention_data['coauthors']
            redacted['coauthor_count'] = len(coauthors) if coauthors else 0

        # 5. 期刊：hash前缀 / Журналы: хэш префикса
        if 'journals' in mention_data:
            journals = mention_data['journals']
            redacted['journal_count'] = len(journals) if journals else 0
            if journals:
                redacted['journal_samples'] = [
                    self._redact_text(j)[:16] for j in list(journals)[:2]
                ]

        return redacted

    def _redact_name(self, name: str) -> Dict[str, Any]:
        """
        脱敏姓名：hash + 结构特征 / Редакция имени: хэш + признаки

        返回结构 / Структура возврата / Return structure:
        {
            "hash": "a1b2c3...",
            "tokens": 2,  # token数量 / количество токенов
            "length": 10,  # 总字符数 / общая длина
            "script": "latin",  # 字符集类型 / тип скрипта
            "has_initial": true  # 是否有缩写 / есть ли инициал
        }

        Args:
            name: 原始姓名 / Исходное имя

        Returns:
            Dict: 脱敏后的姓名信息 / Редактированная информация
        """
        # Hash姓名 / Хэширование имени
        name_hash = self._hash_text(name)

        # 提取结构特征 / Извлечение структурных признаков
        tokens = name.split()
        length = len(name)

        # 检测字符集类型 / Определение типа скрипта
        script = self._detect_script(name)

        # 检测是否有缩写（如"J."） / Проверка на инициалы
        has_initial = bool(re.search(r'\b[A-Z]\.$', name))

        return {
            "hash": name_hash,
            "tokens": len(tokens),
            "length": length,
            "script": script,
            "has_initial": has_initial,
        }

    def _redact_affiliation(self, affiliation: str) -> str:
        """
        脱敏机构：保留前缀hash / Редакция аффилиации: хэш префикса

        Args:
            affiliation: 原始机构名 / Исходная аффилиация

        Returns:
            str: hash前缀（前16字符）/ хэш префикса (первые 16 символов)
        """
        return self._hash_text(affiliation)[:16]

    def _hash_text(self, text: str) -> str:
        """
        使用盐值hash文本 / Хэширование текста с солью

        Args:
            text: 待hash的文本 / Текст для хэширования

        Returns:
            str: SHA256 hash（前16字符）/ хэш (первые 16 символов)
        """
        salted_text = f"{text}||{self.salt}"
        hash_obj = hashlib.sha256(salted_text.encode('utf-8'))
        return hash_obj.hexdigest()[:16]

    def _redact_text(self, text: str) -> str:
        """通用文本脱敏 / Общая редакция текста"""
        return self._hash_text(text)[:12]

    def _detect_script(self, text: str) -> str:
        """
        检测文本字符集类型 / Определение типа скрипта текста

        Args:
            text: 文本 / Текст

        Returns:
            str: 字符集类型（latin/cyrillic/cjk/mixed）
                Тип скрипта
        """
        if not text:
            return "empty"

        # 统计字符类型 / Подсчёт типов символов
        latin_count = sum(1 for c in text if ord('a') <= ord(c.lower()) <= ord('z'))
        cyrillic_count = sum(1 for c in text if ord('а') <= ord(c.lower()) <= ord('я'))
        cjk_count = sum(1 for c in text if ord(c) >= 0x4E00 and ord(c) <= 0x9FFF)

        total_alpha = latin_count + cyrillic_count + cjk_count
        if total_alpha == 0:
            return "other"

        # 判断主要字符集 / Определение основного скрипта
        if latin_count / total_alpha > 0.7:
            return "latin"
        elif cyrillic_count / total_alpha > 0.7:
            return "cyrillic"
        elif cjk_count / total_alpha > 0.7:
            return "cjk"
        else:
            return "mixed"


# 测试代码 / Тестовый код / Test code
if __name__ == '__main__':
    import sys
    from pathlib import Path
    # 添加父目录到sys.path / Добавление родительской директории
    sys.path.insert(0, str(Path(__file__).parent.parent))

    import tempfile
    from disambiguation_engine.decision_types import Decision, DecisionResult

    print("=" * 80)
    print("Decision Trace Logger Test / Тест логгера трейса решений")
    print("=" * 80)

    # 创建临时文件 / Создание временных файлов
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_path = Path(tmpdir) / "trace.jsonl"
        review_path = Path(tmpdir) / "review.jsonl"

        # 创建logger / Создание логгера
        logger = DecisionTraceLogger(
            trace_path=str(trace_path),
            review_path=str(review_path),
            salt="test_salt_123"
        )

        # 测试1：MERGE决策 / Тест 1: решение MERGE
        print("\n[Test 1] MERGE Decision Trace")
        merge_decision = DecisionResult(
            decision=Decision.MERGE,
            best_author_id="au_12345",
            score_total=0.92,
            score_components={"name": 0.95, "orcid": 1.0, "coauthor": 0.75},
            comparisons={"name_bin": "exact", "orcid_bin": "match"},
            thresholds={"accept": 0.90, "reject": 0.20},
            mode="fs",
            run_id="test_run_001"
        )
        mention = {
            "name": "张伟",  # 中文名 / Китайское имя
            "orcid": "0000-0001-2345-6789",
            "affiliation": ["Tsinghua University"],
            "coauthors": ["Li Ming", "Wang Qiang"],
            "journals": ["Nature", "Science"]
        }
        logger.append_trace(merge_decision, mention)
        print(f"  [OK] Written to {trace_path}")

        # 测试2：UNKNOWN决策（会写入review池）/ Тест 2: решение UNKNOWN
        print("\n[Test 2] UNKNOWN Decision (Review Pool)")
        unknown_decision = DecisionResult(
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
        mention2 = {
            "name": "John Smith",
            "affiliation": ["MIT", "Harvard"],
            "journals": ["Cell"]
        }
        logger.append_trace(unknown_decision, mention2)
        print(f"  [OK] Written to {trace_path}")
        print(f"  [OK] Also written to review pool: {review_path}")

        # 验证输出 / Проверка вывода
        print("\n[Test 3] Verify Output")
        with open(trace_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            print(f"  Trace records: {len(lines)}")
            if lines:
                first_record = json.loads(lines[0])
                print(f"  First record keys: {list(first_record.keys())}")
                print(f"  Name redacted: {first_record['mention']['name']}")
                # 检查无明文姓名 / Проверка отсутствия открытых имён
                assert "张伟" not in lines[0], "Found plaintext Chinese name!"
                assert "hash" in first_record['mention']['name'], "Name hash not found!"
                print("  [OK] No plaintext names found")

        with open(review_path, 'r', encoding='utf-8') as f:
            review_lines = f.readlines()
            print(f"  Review pool records: {len(review_lines)}")
            if review_lines:
                review_record = json.loads(review_lines[0])
                assert review_record['review_status'] == 'pending'
                print(f"  [OK] Review record has status: {review_record['review_status']}")

    print("\n" + "=" * 80)
    print("All tests passed / Все тесты пройдены")
    print("=" * 80)
