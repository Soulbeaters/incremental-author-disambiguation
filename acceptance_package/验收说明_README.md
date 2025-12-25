# 作者消歧系统验收文件说明
## Author Disambiguation System - Acceptance Documentation
## Документация для приёмки системы дизамбигуации авторов

**项目名称**: 增量作者消歧系统（Incremental Author Disambiguation System）
**验收日期**: 2025-12-25
**研究者**: Ма Цзясин (Ma Jiaxin)
**机构**: МГУ (莫斯科国立大学)

---

## 目录结构 / Структура каталога / Directory Structure

```
验收文件_Author_Disambiguation/
├── 1_核心代码模块/          # 核心实现代码
│   ├── author.py            # Author数据模型
│   ├── database.py          # 内存数据库+多键blocking索引
│   ├── publication.py       # Publication数据模型
│   ├── decision_types.py    # 三分决策数据结构（MERGE/NEW/UNKNOWN）
│   ├── decision_trace.py    # 脱敏决策trace记录器
│   ├── similarity_scorer.py # 三层评分架构（comparison→baseline→FS）
│   └── author_merger.py     # 三分决策主引擎
├── 2_评测模块/              # ORCID金标准评测
│   ├── build_orcid_goldset.py  # 构建ORCID金标准数据集
│   └── evaluate.py             # B³ F1 + pairwise F1评测
├── 3_测试脚本/              # 验收测试脚本
│   ├── test_author_merger_threeway.py  # 三分决策逻辑单元测试
│   ├── test_scorer_three_layers.py     # 三层评分架构单元测试
│   └── test_full_scenario.py           # 完整场景集成测试
├── 4_测试结果示例/          # 已运行的测试结果
│   ├── test_trace.jsonl     # 决策trace示例（脱敏）
│   └── test_review.jsonl    # UNKNOWN决策待审核池示例
├── 5_配置文件/              # 系统配置
│   ├── config.py            # 双阈值、MU参数表、比较bins
│   └── cli_config.py        # 统一CLI参数管理
└── 验收说明_README.md       # 本文档
```

---

## 验收标准 / Критерии приёмки / Acceptance Criteria

### 1. 确定性验证 (Deterministic Execution)
**要求**: 相同输入 + 相同配置 + 相同种子 → 完全相同的输出

**验证方法**:
```bash
# 进入项目目录
cd "C:\program 2 in 2025"

# 运行第一次
python scripts/test_full_scenario.py \
  --crossref-authors "C:\istina\materia 材料\测试表单\crossref_authors.json" \
  --limit 100 \
  --seed 42 \
  --run-id det_test_1 \
  --trace-jsonl runs/det1/trace.jsonl

# 运行第二次
python scripts/test_full_scenario.py \
  --crossref-authors "C:\istina\materia 材料\测试表单\crossref_authors.json" \
  --limit 100 \
  --seed 42 \
  --run-id det_test_2 \
  --trace-jsonl runs/det2/trace.jsonl

# 比较两次trace文件（应完全一致）
diff runs/det1/trace.jsonl runs/det2/trace.jsonl
```

**预期结果**: 两次trace文件完全相同，diff无输出

---

### 2. 脱敏验证 (Name Redaction)
**要求**: trace文件中无明文姓名，仅有hash值和结构特征

**验证方法**:
```bash
# 运行测试
python scripts/test_full_scenario.py \
  --crossref-authors "C:\istina\materia 材料\测试表单\crossref_authors.json" \
  --limit 50 \
  --trace-jsonl runs/redaction_test/trace.jsonl

# 检查是否有明文姓名泄露（应返回空）
grep -E '"name":\s*"[A-Z][a-z]+\s+[A-Z]' runs/redaction_test/trace.jsonl
```

**预期结果**: grep返回空（无匹配），说明所有姓名已脱敏为hash

**脱敏示例**:
```json
{
  "mention_name_redacted": "hash_a3f2c1",
  "mention_name_structure": {
    "token_count": 2,
    "avg_token_length": 5.5,
    "script_type": "latin"
  }
}
```

---

### 3. 三分决策逻辑验证 (Three-Way Decision Logic)
**要求**: MERGE/NEW/UNKNOWN三种决策正确触发

**验证方法**:
```bash
# 运行单元测试
cd "C:\program 2 in 2025"
python test_author_merger_threeway.py
```

**预期输出**:
```
[测试场景1] 高相似度mention - 期望决策: MERGE
  Decision: merge
  [OK] 决策正确: MERGE

[测试场景2] 低相似度mention - 期望决策: NEW
  Decision: new
  [OK] 决策正确: NEW

[测试场景3] 中等相似度mention - 期望决策: UNKNOWN
  Decision: unknown
  [OK] 决策正确: UNKNOWN

总结:
  场景1 (MERGE): 通过
  场景2 (NEW): 通过
  场景3 (UNKNOWN): 通过
```

---

### 4. 50 DOI演示测试 (50 DOI Demonstration)
**要求**: 处理50个真实DOI，展示完整流程

**验证方法**:
```bash
python scripts/test_full_scenario.py \
  --crossref-authors "C:\istina\materia 材料\测试表单\crossref_authors.json" \
  --limit 50 \
  --run-id demo_50_dois \
  --trace-jsonl runs/demo_50/trace.jsonl \
  --review-jsonl runs/demo_50/review.jsonl \
  --output runs/demo_50/results.json \
  --verbose
```

**预期结果**:
- 生成 `runs/demo_50/trace.jsonl`（包含50个决策记录）
- 生成 `runs/demo_50/review.jsonl`（UNKNOWN决策池）
- 生成 `runs/demo_50/results.json`（最终聚类结果）
- 生成 `runs/demo_50/run_manifest.json`（运行元数据）

---

### 5. ORCID金标准评测 (ORCID Gold Set Evaluation)
**要求**: 使用ORCID作为ground truth，计算B³ F1和pairwise F1

**验证方法**:

**Step 1: 构建金标准数据集**
```bash
python evaluation/build_orcid_goldset.py \
  --crossref-file "C:\istina\materia 材料\测试表单\crossref.json" \
  --output evaluation/gold_sets/orcid_gold_set.json \
  --min-mentions 2
```

**Step 2: 运行消歧系统生成预测结果**
```bash
python scripts/test_full_scenario.py \
  --crossref-authors "C:\istina\materia 材料\测试表单\crossref_authors.json" \
  --output runs/orcid_eval/predicted_clusters.json
```

**Step 3: 运行评测**
```bash
python evaluation/evaluate.py \
  --gold-set evaluation/gold_sets/orcid_gold_set.json \
  --predicted runs/orcid_eval/predicted_clusters.json \
  --output evaluation/results/eval_results.json \
  --verbose
```

**预期输出示例**:
```
================================================================================
作者消歧评测结果 / Результаты оценки дизамбигуации авторов
================================================================================

【元数据 / Метаданные】
  总mentions数: 28,810
  Gold clusters数: 9,420
  Predicted clusters数: 9,150

【B³ (B-cubed) 指标】
  Precision: 0.9250
  Recall:    0.8830
  F1:        0.9035

【Pairwise 指标】
  Precision: 0.9180
  Recall:    0.8650
  F1:        0.8907
  详细:
    - True Positives (TP):  125,430
    - False Positives (FP): 11,250
    - False Negatives (FN): 19,580

【总结】
  B³ F1:       0.9035
  Pairwise F1: 0.8907
  平均F1:      0.8971
```

---

## 核心技术实现 / Техническая реализация / Technical Implementation

### 三分决策框架 (Three-Way Decision Framework)
- **MERGE** (合并): `score >= accept_threshold` (默认0.90)
- **NEW** (新建): `score <= reject_threshold` (默认0.20)
- **UNKNOWN** (待审核): `reject_threshold < score < accept_threshold`

### Fellegi-Sunter证据聚合 (Evidence Aggregation)
```python
# 对每个特征比较结果，使用m/u参数计算log-likelihood ratio
for feature, bin_value in comparisons.items():
    m = MU_TABLE[feature][bin_value]["m"]  # P(比较结果|同一作者)
    u = MU_TABLE[feature][bin_value]["u"]  # P(比较结果|不同作者)
    llr = log2(m / u)
    total_score += llr
```

### 多键blocking索引 (Multi-Key Blocking)
避免O(N)全扫描，使用4种blocking策略：
1. ORCID精确匹配
2. 姓氏匹配
3. 姓氏+首字母匹配
4. 机构匹配

### 隐私保护脱敏 (Privacy-Preserving Redaction)
```python
# 姓名hash化
name_hash = hashlib.sha256(name.encode('utf-8')).hexdigest()[:12]

# 保留结构特征
structure = {
    "token_count": len(tokens),
    "avg_token_length": sum(len(t) for t in tokens) / len(tokens),
    "script_type": detect_script(name)  # latin/cyrillic/cjk
}
```

---

## 配置参数说明 / Параметры конфигурации / Configuration Parameters

### 双阈值配置 (Dual Thresholds)
```python
# config.py
ACCEPT_THRESHOLD = 0.90  # MERGE决策阈值
REJECT_THRESHOLD = 0.20  # NEW决策阈值
```

### MU参数表 (MU Parameter Table)
```python
MU_TABLE = {
    "name": {
        "exact": {"m": 0.95, "u": 0.01},   # 姓名完全匹配
        "high": {"m": 0.80, "u": 0.05},    # 高度相似
        "medium": {"m": 0.50, "u": 0.15},  # 中等相似
        "low": {"m": 0.20, "u": 0.30},     # 低相似度
        "none": {"m": 0.05, "u": 0.50}     # 无匹配
    },
    "orcid": {
        "match": {"m": 0.99, "u": 0.001},  # ORCID匹配（强证据）
        "missing": {"m": 0.50, "u": 0.50}  # 缺失（无信息）
    },
    # ... 其他特征
}
```

---

## 文件格式说明 / Форматы файлов / File Formats

### 决策trace文件 (decision_trace.jsonl)
每行一条JSONL记录：
```json
{
  "run_id": "demo_50_dois",
  "timestamp": "2025-12-25T14:30:45.123456",
  "decision": "merge",
  "score_total": 8.542,
  "score_components": {
    "name": 3.169,
    "orcid": 6.644,
    "coauthor": 1.322,
    "journal": 0.585,
    "affiliation": 2.322
  },
  "thresholds": {
    "accept": 0.90,
    "reject": 0.20
  },
  "best_author_id": "au_a3f2c1d4",
  "mention_name_redacted": "hash_x9k2m5",
  "mention_name_structure": {
    "token_count": 2,
    "avg_token_length": 5.5,
    "script_type": "latin"
  },
  "deterministic_hash": "a3f2c1d4e5f6"
}
```

### ORCID金标准文件 (orcid_gold_set.json)
```json
{
  "metadata": {
    "created_at": "2025-12-25T14:00:00",
    "source": "crossref.json",
    "total_mentions": 28810,
    "mentions_with_orcid": 28810,
    "orcid_coverage": 1.0
  },
  "gold_clusters": {
    "0000-0001-2345-6789": {
      "orcid": "0000-0001-2345-6789",
      "mention_count": 15,
      "mention_ids": [1, 42, 105, ...],
      "names": ["John Smith", "J. Smith", "J. A. Smith"],
      "affiliations": ["Harvard University", "MIT"]
    }
  },
  "ground_truth": {
    "1": "0000-0001-2345-6789",
    "42": "0000-0001-2345-6789",
    ...
  }
}
```

---

## 常见问题 / FAQ / Часто задаваемые вопросы

### Q1: 如何修改双阈值？
**A**: 编辑 `config.py`:
```python
ACCEPT_THRESHOLD = 0.85  # 降低MERGE门槛（更激进）
REJECT_THRESHOLD = 0.30  # 提高NEW门槛（更保守）
```

### Q2: 如何查看UNKNOWN决策？
**A**: 查看 `runs/<run_id>/review_pool.jsonl` 文件，包含所有待审核决策。

### Q3: 如何禁用中文姓名增强？
**A**: 运行时添加参数:
```bash
python scripts/test_full_scenario.py --disable-chinese-name
```

### Q4: 如何自定义MU参数？
**A**: 创建自定义MU表JSON文件，使用 `--mu-table` 参数加载：
```bash
python scripts/test_full_scenario.py --mu-table custom_mu.json
```

---

## 联系方式 / Контакты / Contact

**研究者**: Ма Цзясин (Ma Jiaxin)
**机构**: МГУ (莫斯科国立大学)
**GitHub**: https://github.com/Soulbeaters/incremental-author-disambiguation

**项目仓库**:
- 一号项目 (Chinese-name): https://github.com/Soulbeaters/Chinese-name
- 二号项目 (本项目): https://github.com/Soulbeaters/incremental-author-disambiguation

---

**验收日期**: 2025-12-25
**版本**: 2.0 (Incremental Author Disambiguation System)
