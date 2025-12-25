# 验收文件清单 / Список файлов для приёмки / File Inventory

## 验收日期: 2025-12-25

---

## 1. 核心代码模块 (7个文件)

| 文件名 | 行数 | 功能描述 |
|-------|------|---------|
| `author.py` | 180 | Author数据模型类，包含姓名、ORCID、机构、合著者等属性 |
| `database.py` | 520 | 内存数据库，支持多键blocking索引（ORCID/姓氏/机构） |
| `publication.py` | 120 | Publication数据模型类 |
| `decision_types.py` | 315 | 三分决策数据结构（Decision枚举、DecisionResult类） |
| `decision_trace.py` | 280 | 脱敏决策trace记录器（JSONL格式，姓名hash化） |
| `similarity_scorer.py` | 450 | 三层评分架构（comparison→baseline→Fellegi-Sunter） |
| `author_merger.py` | 520 | 三分决策主引擎（MERGE/NEW/UNKNOWN判定） |

**总计**: 约2,385行代码

---

## 2. 评测模块 (2个文件)

| 文件名 | 行数 | 功能描述 |
|-------|------|---------|
| `build_orcid_goldset.py` | 442 | 从Crossref提取ORCID作者构建金标准数据集 |
| `evaluate.py` | 378 | B³ F1和pairwise F1评测指标实现 |

**总计**: 约820行代码

---

## 3. 测试脚本 (3个文件)

| 文件名 | 行数 | 功能描述 |
|-------|------|---------|
| `test_author_merger_threeway.py` | 222 | 三分决策逻辑单元测试（3个场景） |
| `test_scorer_three_layers.py` | 180 | 三层评分架构单元测试 |
| `test_full_scenario.py` | 450 | 完整场景集成测试脚本 |

**总计**: 约852行代码

---

## 4. 测试结果示例 (2个文件)

| 文件名 | 大小 | 功能描述 |
|-------|------|---------|
| `test_trace.jsonl` | 3.2KB | 决策trace示例（3条记录，脱敏） |
| `test_review.jsonl` | 1.3KB | UNKNOWN决策待审核池示例（1条记录） |

---

## 5. 配置文件 (2个文件)

| 文件名 | 行数 | 功能描述 |
|-------|------|---------|
| `config.py` | 280 | 系统配置（双阈值、MU参数表、比较bins、权重） |
| `cli_config.py` | 513 | 统一CLI参数管理类（支持baseline/FS模式切换） |

**总计**: 约793行代码

---

## 关键技术指标 / Технические показатели / Key Metrics

### 代码规模
- **核心模块**: 2,385行
- **评测模块**: 820行
- **测试脚本**: 852行
- **配置文件**: 793行
- **总代码量**: 约4,850行

### 架构特点
- **三分决策**: MERGE/NEW/UNKNOWN
- **双阈值**: accept=0.90, reject=0.20
- **评分方法**: Fellegi-Sunter证据聚合
- **隐私保护**: 姓名hash化 + 结构特征保留
- **确定性**: 固定随机种子 + 稳定排序

### 评测指标
- **B³ F1**: 基于聚类的precision/recall
- **Pairwise F1**: 基于mention对的precision/recall
- **Gold Standard**: ORCID作为ground truth

---

## 验收检查清单 / Чек-лист для приёмки / Acceptance Checklist

- [x] **代码完整性**: 所有模块编译通过
- [x] **Bug修复**: 修复了database.py缺少get_author()方法的bug
- [x] **AI痕迹清除**: 无AI生成标记
- [x] **脱敏验证**: trace文件无明文姓名
- [x] **三分决策测试**: 3个场景全部通过
- [ ] **确定性验证**: 待运行（相同输入→相同输出）
- [ ] **50 DOI演示**: 待运行
- [ ] **ORCID金标准评测**: 待运行（B³ F1 + pairwise F1）

---

## 文件完整性校验 / Проверка целостности / File Integrity

### 核心模块 (MD5校验，可选)
```bash
cd "1_核心代码模块"
md5sum *.py
```

### 预期文件数量
- 核心代码模块: 7个文件
- 评测模块: 2个文件
- 测试脚本: 3个文件
- 测试结果示例: 2个文件
- 配置文件: 2个文件
- 说明文档: 2个文件（README + 本清单）

**总计**: 18个文件

---

## 使用快速指南 / Краткое руководство / Quick Start Guide

### 1. 运行三分决策测试
```bash
cd "C:\program 2 in 2025"
python test_author_merger_threeway.py
```

### 2. 运行50 DOI演示
```bash
python scripts/test_full_scenario.py \
  --crossref-authors "C:\istina\materia 材料\测试表单\crossref_authors.json" \
  --limit 50 \
  --verbose
```

### 3. 构建ORCID金标准
```bash
python evaluation/build_orcid_goldset.py \
  --crossref-file "C:\istina\materia 材料\测试表单\crossref.json" \
  --output evaluation/gold_sets/orcid_gold_set.json
```

### 4. 运行评测
```bash
python evaluation/evaluate.py \
  --gold-set evaluation/gold_sets/orcid_gold_set.json \
  --predicted runs/orcid_eval/predicted_clusters.json \
  --output evaluation/results/eval_results.json
```

---

**创建日期**: 2025-12-25
**验收负责人**: Ма Цзясин
**项目版本**: 2.0
