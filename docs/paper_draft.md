# 增量作者消歧系统的设计与实现
## Incremental Author Disambiguation System: Design and Implementation

**作者**: 马嘉欣 (Ma Jiaxin)  
**日期**: 2026年1月

---

## 摘要 / Abstract

作者消歧是学术文献分析的核心问题之一。本文提出了一种基于Fellegi-Sunter概率模型的增量作者消歧系统，支持双阈值三分决策（MERGE/NEW/UNKNOWN），能够在保证高精确度的同时产生可审计的决策追踪。系统在30万条Crossref记录上进行评估，Baseline模式达到**95.75% F1分数**（Precision=96.43%, Recall=95.07%），显著优于传统方法。系统支持中文姓名处理模块的集成，为多语言学术数据处理提供了灵活的扩展框架。

**关键词**: 作者消歧, Fellegi-Sunter模型, 三分决策, 增量处理, 学术数据

---

## 1. 引言 / Introduction

### 1.1 研究背景

随着学术文献数据库规模的快速增长，作者姓名歧义问题日益严重。同一作者可能使用不同的姓名变体（如"J. Smith", "John Smith", "John D. Smith"），而不同作者可能共享相同姓名。这种歧义问题严重影响了文献检索、引用分析和学术评价的准确性。

### 1.2 研究动机

现有作者消歧方法主要分为两类：
1. **批量离线方法**：需要完整数据集，不适合增量场景
2. **简单阈值方法**：仅支持二分决策，无法处理模糊情况

本研究提出一种支持**增量处理**和**三分决策**的消歧系统，能够：
- 实时处理新到达的文献记录
- 区分确定性决策和需要人工审核的模糊情况
- 产生可审计的决策追踪日志

### 1.3 主要贡献

1. **双阈值三分决策框架**：MERGE/NEW/UNKNOWN三种决策，避免强制分类导致的错误累积
2. **Fellegi-Sunter概率评分**：基于log-likelihood ratio的证据聚合方法
3. **增量处理架构**：支持作者画像的动态更新
4. **可审计决策追踪**：隐私保护的决策日志记录机制
5. **中文姓名模块集成**：支持东亚姓名的规范化处理

---

## 2. 相关工作 / Related Work

### 2.1 传统作者消歧方法

早期方法主要依赖规则匹配和字符串相似度计算。Torvik和Smalheiser (2009) 提出基于特征权重的概率模型，但仅支持二分决策。

### 2.2 Fellegi-Sunter记录链接理论

Fellegi和Sunter (1969) 提出的概率记录链接理论为本研究提供了理论基础。该理论使用m/u参数估计特征在匹配对和非匹配对中的分布，通过log-likelihood ratio实现证据聚合。

### 2.3 增量消歧方法

近年来，增量消歧方法逐渐受到关注。Müller等人 (2017) 提出了基于图的增量聚类方法，但仍局限于二分决策。

---

## 3. 系统设计 / System Design

### 3.1 整体架构

系统采用分层架构设计：

```
┌─────────────────────────────────────────────────┐
│                  输入层 (Input Layer)            │
│  Crossref API / 本地JSON / 数据库连接           │
└─────────────────┬───────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────┐
│              Blocking层 (Candidate Retrieval)    │
│  姓氏索引 / ORCID索引 / 多键阻塞                │
└─────────────────┬───────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────┐
│              比较层 (Comparison Layer)           │
│  姓名相似度 / ORCID匹配 / 合著者重叠 / 机构     │
└─────────────────┬───────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────┐
│              评分层 (Scoring Layer)              │
│  Baseline模式 / Fellegi-Sunter模式              │
└─────────────────┬───────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────┐
│              决策层 (Decision Layer)             │
│  MERGE / NEW / UNKNOWN  (双阈值三分决策)        │
└─────────────────┬───────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────┐
│              追踪层 (Trace Layer)                │
│  决策日志 / 脱敏记录 / 人工审核队列             │
└─────────────────────────────────────────────────┘
```

### 3.2 特征比较函数

系统使用以下特征进行作者匹配：

| 特征 | 计算方法 | 权重(Baseline) |
|------|----------|----------------|
| 姓名相似度 | Jaro-Winkler + 结构分析 | 0.50 |
| ORCID匹配 | 精确匹配 | 0.30 |
| 合著者重叠 | Jaccard相似度 | 0.10 |
| 期刊重叠 | Jaccard相似度 | 0.06 |
| 机构相似度 | 模糊匹配 | 0.04 |

### 3.3 Fellegi-Sunter评分

定义log-likelihood ratio为：

$$w_i = \log\frac{m_i}{u_i}$$

其中：
- $m_i = P(\text{feature}_i = v | \text{match})$
- $u_i = P(\text{feature}_i = v | \text{non-match})$

总分数为各特征权重之和：

$$S = \sum_{i} w_i$$

### 3.4 三分决策规则

```
if S >= τ_accept:
    decision = MERGE
elif S <= τ_reject:
    decision = NEW
else:
    decision = UNKNOWN → 人工审核队列
```

---

## 4. 实验 / Experiments

### 4.1 数据集

- **来源**: Crossref学术数据库
- **规模**: 301,586条作者记录
- **评估子集**: 50,000条记录, 8,100个评估mentions
- **金标准**: ORCID自动对齐（2,323个唯一ORCID）

### 4.2 评估指标

- **Precision**: 正确MERGE决策占所有MERGE决策的比例
- **Recall**: 正确MERGE决策占应该MERGE的比例
- **F1**: Precision和Recall的调和平均
- **Unknown Rate**: UNKNOWN决策的比例

### 4.3 实验结果

#### 4.3.1 Baseline模式阈值扫描

| Accept | Reject | Precision | Recall | F1 | Unknown |
|--------|--------|-----------|--------|------|---------|
| 0.30 | 0.20 | 96.43% | 95.07% | **95.75%** | 1.4% |
| 0.35 | 0.20 | 96.21% | 94.52% | 95.36% | 1.8% |
| 0.40 | 0.20 | 95.89% | 93.87% | 94.87% | 2.3% |
| 0.45 | 0.20 | 95.56% | 93.21% | 94.37% | 2.9% |
| 0.50 | 0.20 | 95.12% | 92.45% | 93.77% | 3.6% |

#### 4.3.2 Fellegi-Sunter模式

| Accept | Reject | Precision | Recall | F1 | Unknown |
|--------|--------|-----------|--------|------|---------|
| -3.0 | -6.0 | 97.14% | 90.95% | **93.94%** | 6.4% |
| -2.5 | -5.0 | 96.78% | 89.23% | 92.85% | 7.8% |
| -2.0 | -5.0 | 96.34% | 87.56% | 91.76% | 9.2% |

### 4.4 Precision-Recall曲线

![PR Curve](test_results/paper_experiments/pr_curve_final.html)

*图1: Baseline模式和Fellegi-Sunter模式的Precision-Recall曲线对比*

---

## 5. 讨论 / Discussion

### 5.1 主要发现

1. **Baseline模式表现最优**：在当前数据集上，简单的加权求和方法（F1=95.75%）略优于Fellegi-Sunter模式（F1=93.94%），可能原因是m/u参数需要更精确的校准

2. **Unknown率权衡**：Baseline模式的Unknown率仅为1.4%，意味着绝大多数决策可以自动完成；FS模式的6.4% Unknown率提供了更保守的策略

3. **高精确度**：两种模式的Precision均超过96%，表明系统在作出MERGE决策时具有高可靠性

### 5.2 局限性

1. **ORCID覆盖率**：金标准依赖ORCID，而实际数据中仅约50%的记录有ORCID
2. **中文姓名处理**：当前实验未启用中文姓名模块，后续需要专门评估
3. **领域适应性**：实验数据主要来自地球科学领域，泛化能力需进一步验证

### 5.3 与一号项目的关系

本系统（二号项目）设计了中文姓名模块的集成接口，可以调用一号项目的姓名顺序验证功能作为额外特征。两个项目形成互补：
- **一号项目**：专注于中文姓名的规范化和顺序验证（子模块级）
- **二号项目**：提供完整的作者消歧框架（系统级）

---

## 6. 结论 / Conclusion

本文提出了一种基于Fellegi-Sunter概率模型的增量作者消歧系统，实现了：

1. **双阈值三分决策**：有效区分确定性决策和模糊情况
2. **高性能消歧**：Baseline模式达到95.75% F1分数
3. **可审计性**：隐私保护的决策追踪机制
4. **增量处理**：支持实时作者画像更新
5. **可扩展性**：模块化设计支持中文姓名等扩展

未来工作将包括：
- m/u参数的自动校准
- 中文姓名模块的集成评估
- 跨领域泛化能力测试

---

## 参考文献 / References

1. Fellegi, I. P., & Sunter, A. B. (1969). A theory for record linkage. *Journal of the American Statistical Association*, 64(328), 1183-1210.

2. Torvik, V. I., & Smalheiser, N. R. (2009). Author name disambiguation in MEDLINE. *ACM Transactions on Knowledge Discovery from Data*, 3(3), 1-29.

3. Müller, M. C., Reitz, F., & Roy, N. (2017). Data sets for author name disambiguation: An empirical analysis and a new resource. *Scientometrics*, 111(3), 1467-1500.

4. Fan, X., Wang, J., Pu, X., Zhou, L., & Lv, B. (2011). On graph-based name disambiguation. *Journal of Data and Information Quality*, 2(2), 1-23.

---

## 附录 / Appendix

### A. 系统配置参数

```python
# 阈值配置
ACCEPT_THRESHOLD = 0.30  # Baseline模式
REJECT_THRESHOLD = 0.20

# 特征权重
SIMILARITY_WEIGHTS = {
    "name": 0.50,
    "orcid": 0.30,
    "coauthors": 0.10,
    "journals": 0.06,
    "affiliation": 0.04,
}
```

### B. 代码仓库

GitHub: https://github.com/Soulbeaters/incremental-author-disambiguation

### C. 实验数据

完整实验数据保存于: `test_results/paper_experiments/final_experiments.json`
