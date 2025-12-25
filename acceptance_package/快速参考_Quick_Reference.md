# 快速参考卡 / Справочная карточка / Quick Reference Card

## 增量作者消歧系统 - 验收测试命令

---

## 验收测试命令速查表

### 1️⃣ 确定性验证 (Deterministic Execution Test)
```bash
cd "C:\program 2 in 2025"

# 第一次运行
python scripts/test_full_scenario.py \
  --crossref-authors "C:\istina\materia 材料\测试表单\crossref_authors.json" \
  --limit 100 --seed 42 --run-id det1 \
  --trace-jsonl runs/det1/trace.jsonl

# 第二次运行（相同参数）
python scripts/test_full_scenario.py \
  --crossref-authors "C:\istina\materia 材料\测试表单\crossref_authors.json" \
  --limit 100 --seed 42 --run-id det2 \
  --trace-jsonl runs/det2/trace.jsonl

# 比较（应完全相同）
diff runs/det1/trace.jsonl runs/det2/trace.jsonl
```
**预期结果**: diff无输出

---

### 2️⃣ 脱敏验证 (Name Redaction Test)
```bash
# 运行测试
python scripts/test_full_scenario.py \
  --crossref-authors "C:\istina\materia 材料\测试表单\crossref_authors.json" \
  --limit 50 --trace-jsonl runs/redaction/trace.jsonl

# 检查明文姓名泄露（应返回空）
grep -E '"name":\s*"[A-Z][a-z]+\s+[A-Z]' runs/redaction/trace.jsonl
```
**预期结果**: 无匹配（grep返回空）

---

### 3️⃣ 三分决策测试 (Three-Way Decision Test)
```bash
python test_author_merger_threeway.py
```
**预期输出**:
```
[测试场景1] MERGE  ✓
[测试场景2] NEW    ✓
[测试场景3] UNKNOWN ✓
```

---

### 4️⃣ 50 DOI演示 (50 DOI Demonstration)
```bash
python scripts/test_full_scenario.py \
  --crossref-authors "C:\istina\materia 材料\测试表单\crossref_authors.json" \
  --limit 50 \
  --run-id demo_50 \
  --trace-jsonl runs/demo_50/trace.jsonl \
  --review-jsonl runs/demo_50/review.jsonl \
  --output runs/demo_50/results.json \
  --verbose
```
**输出文件**:
- `runs/demo_50/trace.jsonl`
- `runs/demo_50/review.jsonl`
- `runs/demo_50/results.json`
- `runs/demo_50/run_manifest.json`

---

### 5️⃣ ORCID金标准评测 (ORCID Gold Set Evaluation)

**Step 1: 构建金标准**
```bash
python evaluation/build_orcid_goldset.py \
  --crossref-file "C:\istina\materia 材料\测试表单\crossref.json" \
  --output evaluation/gold_sets/orcid_gold_set.json \
  --min-mentions 2
```

**Step 2: 生成预测结果**
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

---

## 关键参数说明

### 运行模式
- `--baseline-mode`: 单阈值加权相似度（原始方法）
- `--fs-mode`: Fellegi-Sunter双阈值（默认，推荐）

### 双阈值配置
- `--accept-threshold 0.90`: MERGE决策阈值（>= 0.90 → MERGE）
- `--reject-threshold 0.20`: NEW决策阈值（<= 0.20 → NEW）
- 中间区域 (0.20 < score < 0.90) → UNKNOWN

### 输出文件
- `--trace-jsonl <path>`: 决策trace输出路径
- `--review-jsonl <path>`: UNKNOWN决策待审核池
- `--output <path>`: 最终聚类结果
- `--report <path>`: 人类可读报告

### 实验可复现性
- `--run-id <id>`: 运行标识符
- `--seed <n>`: 随机种子（默认42）
- `--limit <n>`: 限制处理数量

### 其他
- `--verbose`: 详细输出
- `--debug`: 调试模式
- `--language ru|zh|en`: 输出语言

---

## 配置文件快速修改

### config.py - 修改双阈值
```python
# 找到以下行并修改
ACCEPT_THRESHOLD = 0.90  # MERGE门槛
REJECT_THRESHOLD = 0.20  # NEW门槛
```

### config.py - 修改MU参数
```python
MU_TABLE = {
    "name": {
        "exact": {"m": 0.95, "u": 0.01},   # 姓名完全匹配
        "high": {"m": 0.80, "u": 0.05},    # 高度相似
        # ... 修改m/u值
    }
}
```

---

## 常用目录路径

### 测试数据
```
C:\istina\materia 材料\测试表单\
  ├── crossref.json              (31,502篇文章)
  ├── crossref_authors.json      (410,724位作者)
  ├── crossref_batch2.json       (30,000篇文章)
  └── crossref_orcid_history.json
```

### 项目目录
```
C:\program 2 in 2025\
  ├── models/                    # 数据模型
  ├── disambiguation_engine/     # 消歧引擎
  ├── evaluation/                # 评测模块
  ├── scripts/                   # 测试脚本
  └── runs/                      # 运行结果
```

### 验收文件包
```
桌面\验收文件_Author_Disambiguation\
  ├── 1_核心代码模块/
  ├── 2_评测模块/
  ├── 3_测试脚本/
  ├── 4_测试结果示例/
  ├── 5_配置文件/
  ├── 验收说明_README.md
  ├── 文件清单_File_Inventory.md
  └── 快速参考_Quick_Reference.md
```

---

## 检查结果文件

### 查看trace文件
```bash
# 查看前10条记录
head -10 runs/demo_50/trace.jsonl

# 统计决策类型分布
grep -o '"decision":"[^"]*"' runs/demo_50/trace.jsonl | sort | uniq -c
```

### 查看评测结果
```bash
cat evaluation/results/eval_results.json | python -m json.tool
```

---

## 故障排查

### 问题1: 文件不存在
```bash
# 检查文件路径
ls -la "C:\istina\materia 材料\测试表单\crossref_authors.json"
```

### 问题2: 模块导入错误
```bash
# 确保在项目根目录运行
cd "C:\program 2 in 2025"
python -c "import disambiguation_engine"
```

### 问题3: Unicode编码错误
```bash
# Windows环境设置UTF-8
chcp 65001
```

---

**版本**: 2.0
**更新日期**: 2025-12-25
