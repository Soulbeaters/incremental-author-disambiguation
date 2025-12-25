# -*- coding: utf-8 -*-
"""
测试similarity_scorer.py的三层输出接口
Тест трёхуровневого интерфейса similarity_scorer.py
Test script for three-layer output interface
"""

import sys
from pathlib import Path

# 添加项目根目录到路径 / Добавление корня проекта в путь
sys.path.insert(0, str(Path(__file__).parent))

from models.author import Author
from disambiguation_engine.similarity_scorer import SimilarityScorer
from config import SIMILARITY_WEIGHTS, MU_TABLE

print("=" * 80)
print("测试SimilarityScorer三层输出接口 / Тест трёхуровневого интерфейса")
print("=" * 80)

# 初始化scorer / Инициализация оценщика
scorer = SimilarityScorer()

# 创建测试数据 / Создание тестовых данных
# 1. 现有作者 / Существующий автор
existing_author = Author(
    author_id="au_001",
    canonical_name="John Smith",
    orcid="0000-0001-2345-6789"
)
existing_author.coauthor_ids = {"au_100", "au_101", "au_102"}
existing_author.journals = {"Nature", "Science"}
existing_author.affiliations = {"Harvard University", "MIT"}

# 2. 高相似度mention（应该是MERGE）/ Высокосхожее упоминание
high_similarity_mention = {
    "name": "J. Smith",
    "orcid": "0000-0001-2345-6789",
    "coauthors": ["au_100", "au_101", "au_103"],
    "journals": ["Nature"],
    "affiliation": ["Harvard University"]
}

# 3. 低相似度mention（应该是NEW）/ Низкосхожее упоминание
low_similarity_mention = {
    "name": "Alice Wang",
    "orcid": "",
    "coauthors": ["au_200", "au_201"],
    "journals": ["Cell"],
    "affiliation": ["Stanford University"]
}

# 4. 中等相似度mention（应该是UNKNOWN）/ Среднесхожее упоминание
medium_similarity_mention = {
    "name": "J. Smyth",
    "orcid": "",
    "coauthors": ["au_100"],
    "journals": ["Cell"],
    "affiliation": ["Harvard Medical School"]
}

print("\n[测试1] 高相似度mention（期望：MERGE）")
print("-" * 80)

# Layer 1: compute_comparisons
comparisons_high = scorer.compute_comparisons(high_similarity_mention, existing_author)
print("Layer 1 - Comparisons:")
print(f"  name_sim: {comparisons_high['name_sim']:.3f}, bin: {comparisons_high['name_bin']}")
print(f"  orcid_match: {comparisons_high['orcid_match']}, bin: {comparisons_high['orcid_bin']}")
print(f"  coauthor_sim: {comparisons_high['coauthor_sim']:.3f}, bin: {comparisons_high['coauthor_bin']}")
print(f"  journal_sim: {comparisons_high['journal_sim']:.3f}, bin: {comparisons_high['journal_bin']}")
print(f"  affiliation_sim: {comparisons_high['affiliation_sim']:.3f}, bin: {comparisons_high['affiliation_bin']}")

# Layer 2: score_baseline
score_baseline_high, components_baseline = scorer.score_baseline(comparisons_high)
print("\nLayer 2 - Baseline Score:")
print(f"  Total: {score_baseline_high:.3f}")
print(f"  Components: {components_baseline}")

# Layer 3: score_fellegi_sunter
score_fs_high, components_fs = scorer.score_fellegi_sunter(comparisons_high)
print("\nLayer 3 - Fellegi-Sunter Score:")
print(f"  Total LLR: {score_fs_high:.3f}")
print(f"  Components: {components_fs}")

print("\n" + "=" * 80)
print("[测试2] 低相似度mention（期望：NEW）")
print("-" * 80)

# Layer 1
comparisons_low = scorer.compute_comparisons(low_similarity_mention, existing_author)
print("Layer 1 - Comparisons:")
print(f"  name_sim: {comparisons_low['name_sim']:.3f}, bin: {comparisons_low['name_bin']}")
print(f"  orcid_match: {comparisons_low['orcid_match']}, bin: {comparisons_low['orcid_bin']}")
print(f"  coauthor_sim: {comparisons_low['coauthor_sim']:.3f}, bin: {comparisons_low['coauthor_bin']}")
print(f"  journal_sim: {comparisons_low['journal_sim']:.3f}, bin: {comparisons_low['journal_bin']}")
print(f"  affiliation_sim: {comparisons_low['affiliation_sim']:.3f}, bin: {comparisons_low['affiliation_bin']}")

# Layer 2
score_baseline_low, components_baseline_low = scorer.score_baseline(comparisons_low)
print("\nLayer 2 - Baseline Score:")
print(f"  Total: {score_baseline_low:.3f}")
print(f"  Components: {components_baseline_low}")

# Layer 3
score_fs_low, components_fs_low = scorer.score_fellegi_sunter(comparisons_low)
print("\nLayer 3 - Fellegi-Sunter Score:")
print(f"  Total LLR: {score_fs_low:.3f}")
print(f"  Components: {components_fs_low}")

print("\n" + "=" * 80)
print("[测试3] 中等相似度mention（期望：UNKNOWN）")
print("-" * 80)

# Layer 1
comparisons_medium = scorer.compute_comparisons(medium_similarity_mention, existing_author)
print("Layer 1 - Comparisons:")
print(f"  name_sim: {comparisons_medium['name_sim']:.3f}, bin: {comparisons_medium['name_bin']}")
print(f"  orcid_match: {comparisons_medium['orcid_match']}, bin: {comparisons_medium['orcid_bin']}")
print(f"  coauthor_sim: {comparisons_medium['coauthor_sim']:.3f}, bin: {comparisons_medium['coauthor_bin']}")
print(f"  journal_sim: {comparisons_medium['journal_sim']:.3f}, bin: {comparisons_medium['journal_bin']}")
print(f"  affiliation_sim: {comparisons_medium['affiliation_sim']:.3f}, bin: {comparisons_medium['affiliation_bin']}")

# Layer 2
score_baseline_medium, components_baseline_medium = scorer.score_baseline(comparisons_medium)
print("\nLayer 2 - Baseline Score:")
print(f"  Total: {score_baseline_medium:.3f}")
print(f"  Components: {components_baseline_medium}")

# Layer 3
score_fs_medium, components_fs_medium = scorer.score_fellegi_sunter(comparisons_medium)
print("\nLayer 3 - Fellegi-Sunter Score:")
print(f"  Total LLR: {score_fs_medium:.3f}")
print(f"  Components: {components_fs_medium}")

print("\n" + "=" * 80)
print("[验证] 阈值判断预览 / Предварительная проверка порогов")
print("-" * 80)

from config import ACCEPT_THRESHOLD, REJECT_THRESHOLD

print(f"配置阈值 / Пороги: ACCEPT={ACCEPT_THRESHOLD}, REJECT={REJECT_THRESHOLD}")
print(f"\n高相似度mention - Baseline: {score_baseline_high:.3f}")
if score_baseline_high >= ACCEPT_THRESHOLD:
    print("  [OK] 决策: MERGE (baseline mode)")
elif score_baseline_high <= REJECT_THRESHOLD:
    print("  决策: NEW (baseline mode)")
else:
    print("  决策: UNKNOWN (baseline mode)")

print(f"\n低相似度mention - Baseline: {score_baseline_low:.3f}")
if score_baseline_low >= ACCEPT_THRESHOLD:
    print("  决策: MERGE (baseline mode)")
elif score_baseline_low <= REJECT_THRESHOLD:
    print("  [OK] 决策: NEW (baseline mode)")
else:
    print("  决策: UNKNOWN (baseline mode)")

print(f"\n中等相似度mention - Baseline: {score_baseline_medium:.3f}")
if score_baseline_medium >= ACCEPT_THRESHOLD:
    print("  决策: MERGE (baseline mode)")
elif score_baseline_medium <= REJECT_THRESHOLD:
    print("  决策: NEW (baseline mode)")
else:
    print("  [OK] 决策: UNKNOWN (baseline mode)")

print("\n" + "=" * 80)
print("测试完成 / Тест завершён / Test completed")
print("=" * 80)
