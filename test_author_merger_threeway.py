# -*- coding: utf-8 -*-
"""
测试AuthorMerger三分决策逻辑
Тест логики тройного решения AuthorMerger
Test script for AuthorMerger three-way decision logic
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到路径 / Добавление корня проекта в путь
sys.path.insert(0, str(Path(__file__).parent))

from models.author import Author
from models.database import AuthorDatabase
from disambiguation_engine.author_merger import AuthorMerger
from disambiguation_engine.decision_trace import DecisionTraceLogger
from disambiguation_engine.decision_types import Decision
from config import ACCEPT_THRESHOLD, REJECT_THRESHOLD

print("=" * 80)
print("测试AuthorMerger三分决策逻辑 / Тест логики тройного решения")
print("=" * 80)

# 1. 创建database并添加测试作者 / Создание базы данных с тестовыми авторами
print("\n[步骤1] 创建测试数据库 / Создание тестовой базы данных")
db = AuthorDatabase()

# 添加现有作者（使用字典数据）/ Добавление существующих авторов (словарь)
author1_data = {
    "name": "John Smith",
    "orcid": "0000-0001-2345-6789",
    "coauthors": ["au_100", "au_101", "au_102"],
    "journals": ["Nature", "Science"],
    "affiliation": ["Harvard University"]
}

author2_data = {
    "name": "Alice Wang",
    "orcid": "",
    "coauthors": ["au_200", "au_201"],
    "journals": ["Cell", "PLOS ONE"],
    "affiliation": ["Stanford University"]
}

author1 = db.add_author(author1_data)
author2 = db.add_author(author2_data)

print(f"  已添加 {len(db.authors)} 位作者 / Добавлено авторов: {len(db.authors)}")
print(f"    Author1 ID: {author1.author_id}, Name: {author1.canonical_name}")
print(f"    Author2 ID: {author2.author_id}, Name: {author2.canonical_name}")

# 2. 创建trace logger（可选）/ Создание логгера трассировки
print("\n[步骤2] 创建DecisionTraceLogger")
trace_path = Path(__file__).parent / "runs" / "test_trace.jsonl"
review_path = Path(__file__).parent / "runs" / "test_review.jsonl"

# 确保目录存在 / Убедиться, что директория существует
trace_path.parent.mkdir(parents=True, exist_ok=True)

# 清理旧文件 / Очистка старых файлов
if trace_path.exists():
    trace_path.unlink()
if review_path.exists():
    review_path.unlink()

trace_logger = DecisionTraceLogger(
    trace_path=str(trace_path),
    review_path=str(review_path)
)

print(f"  Trace路径 / Путь трассировки: {trace_path}")
print(f"  Review路径 / Путь обзора: {review_path}")

# 3. 创建AuthorMerger实例 / Создание экземпляра AuthorMerger
print("\n[步骤3] 创建AuthorMerger")

# 对于baseline模式，使用更合理的阈值 / Более разумные пороги для baseline
baseline_accept = 0.70  # baseline模式下0.70是合理的MERGE阈值
baseline_reject = 0.20

merger = AuthorMerger(
    database=db,
    mode="baseline",  # 使用baseline模式便于理解 / Используем baseline для понимания
    accept_threshold=baseline_accept,
    reject_threshold=baseline_reject,
    trace_logger=trace_logger,
    run_id="test_run_001",
    topk=3
)

stats = merger.get_statistics()
print(f"  模式 / Режим: {stats['mode']}")
print(f"  ACCEPT阈值 / Порог ACCEPT: {stats['accept_threshold']}")
print(f"  REJECT阈值 / Порог REJECT: {stats['reject_threshold']}")

# ============================================================================
# 测试场景 / Тестовые сценарии / Test scenarios
# ============================================================================

print("\n" + "=" * 80)
print("[测试场景1] 高相似度mention - 期望决策: MERGE")
print("=" * 80)

high_sim_mention = {
    "name": "John Smith",  # 姓名完全匹配 / Полное совпадение имени
    "orcid": "0000-0001-2345-6789",  # ORCID匹配 / Совпадение ORCID
    "coauthors": ["au_100", "au_101", "au_102"],  # 合著者重叠 / Пересечение соавторов
    "journals": ["Nature", "Science"],  # 期刊重叠 / Пересечение журналов
    "affiliation": ["Harvard University"]  # 机构匹配 / Совпадение аффилиации
}

result1 = merger.make_decision(high_sim_mention, metadata={"test_case": "high_similarity"})

print(f"\n决策结果 / Результат решения:")
print(f"  Decision: {result1.decision.value}")
print(f"  Best author ID: {result1.best_author_id}")
print(f"  Total score: {result1.score_total:.3f}")
print(f"  Score components: {result1.score_components}")
print(f"  Reason: {result1.reason}")
print(f"  Deterministic hash: {result1.deterministic_hash}")
print(f"  Top-{len(result1.topk)} candidates:")
for i, cand in enumerate(result1.topk, 1):
    print(f"    {i}. author_id={cand['author_id']}, score={cand['score']:.3f}")

if result1.is_merge():
    print("\n  [OK] 决策正确: MERGE")
else:
    print(f"\n  [FAIL] 期望MERGE，实际得到: {result1.decision.value}")

# ============================================================================
print("\n" + "=" * 80)
print("[测试场景2] 低相似度mention - 期望决策: NEW")
print("=" * 80)

low_sim_mention = {
    "name": "Robert Johnson",
    "orcid": "",
    "coauthors": ["au_500", "au_501"],  # 完全不同的合著者
    "journals": ["IEEE Transactions"],  # 完全不同的期刊
    "affiliation": ["MIT"]  # 完全不同的机构
}

result2 = merger.make_decision(low_sim_mention, metadata={"test_case": "low_similarity"})

print(f"\n决策结果 / Результат решения:")
print(f"  Decision: {result2.decision.value}")
print(f"  Best author ID: {result2.best_author_id}")
print(f"  Total score: {result2.score_total:.3f}")
print(f"  Score components: {result2.score_components}")
print(f"  Reason: {result2.reason}")

if result2.is_new():
    print("\n  [OK] 决策正确: NEW")
else:
    print(f"\n  [FAIL] 期望NEW，实际得到: {result2.decision.value}")

# ============================================================================
print("\n" + "=" * 80)
print("[测试场景3] 中等相似度mention - 期望决策: UNKNOWN")
print("=" * 80)

medium_sim_mention = {
    "name": "J. A. Smith",  # 姓名相似但不完全一致（同姓，可被blocking）
    "orcid": "",  # 没有ORCID
    "coauthors": ["au_100"],  # 少量合著者重叠
    "journals": ["Cell"],  # 不同期刊
    "affiliation": ["Harvard Medical School"]  # 机构部分匹配
}

result3 = merger.make_decision(medium_sim_mention, metadata={"test_case": "medium_similarity"})

print(f"\n决策结果 / Результат решения:")
print(f"  Decision: {result3.decision.value}")
print(f"  Best author ID: {result3.best_author_id}")
print(f"  Total score: {result3.score_total:.3f}")
print(f"  Score components: {result3.score_components}")
print(f"  Reason: {result3.reason}")
print(f"  Top-{len(result3.topk)} candidates:")
for i, cand in enumerate(result3.topk, 1):
    print(f"    {i}. author_id={cand['author_id']}, score={cand['score']:.3f}")

if result3.is_unknown():
    print("\n  [OK] 决策正确: UNKNOWN")
else:
    print(f"\n  [FAIL] 期望UNKNOWN，实际得到: {result3.decision.value}")

# ============================================================================
print("\n" + "=" * 80)
print("[验证] 检查decision trace文件 / Проверка файлов трассировки")
print("=" * 80)

if trace_path.exists():
    trace_count = len(list(open(trace_path, 'r', encoding='utf-8')))
    print(f"  [OK] Trace文件存在，记录数: {trace_count}")
else:
    print(f"  [FAIL] Trace文件不存在: {trace_path}")

if review_path.exists():
    review_count = len(list(open(review_path, 'r', encoding='utf-8')))
    print(f"  [OK] Review文件存在，UNKNOWN记录数: {review_count}")

    # UNKNOWN决策应该在review pool中
    if result3.is_unknown() and review_count > 0:
        print(f"  [OK] UNKNOWN决策已正确记录到review pool")
else:
    print(f"  Review文件不存在: {review_path} (如果没有UNKNOWN决策这是正常的)")

# ============================================================================
print("\n" + "=" * 80)
print("测试完成 / Тест завершён / Test completed")
print("=" * 80)

print("\n总结 / Итоги / Summary:")
print(f"  场景1 (MERGE): {'通过' if result1.is_merge() else '失败'}")
print(f"  场景2 (NEW): {'通过' if result2.is_new() else '失败'}")
print(f"  场景3 (UNKNOWN): {'通过' if result3.is_unknown() else '失败'}")

# 清理 / Очистка
print(f"\n测试文件保留在: {trace_path.parent}")
