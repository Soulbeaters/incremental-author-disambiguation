# 测试数据集 / Тестовый набор данных / Test Dataset

## 数据概述 / Обзор данных / Data Overview

本目录包含项目测试所需的真实学术数据集。这些数据用于验证系统的作者消歧和文章去重功能。

Эта директория содержит реальные академические наборы данных, необходимые для тестирования проекта. Данные используются для верификации функций устранения неоднозначности авторов и дедупликации статей.

This directory contains real academic datasets required for project testing. The data is used to verify the system's author disambiguation and article deduplication functions.

---

## 数据文件 / Файлы данных / Data Files

### 1. authors.json
**描述 / Описание / Description:**
- 初始作者数据集 / Начальный набор данных авторов / Initial author dataset
- 用于建立基础作者数据库 / Используется для создания базовой БД авторов / Used to build the base author database

**统计 / Статистика / Statistics:**
- 总作者数 / Всего авторов / Total authors: 8,997
- 文件大小 / Размер файла / File size: ~864 KB

**数据结构 / Структура данных / Data Structure:**
```json
[
  {
    "article_id": 765695999,
    "original_name": "Tang Tianxiang",
    "lastname": "Tang",
    "firstname": "Tianxiang"
  },
  ...
]
```

**字段说明 / Описание полей / Field Description:**
- `article_id`: 文章ID / ID статьи / Article ID
- `original_name`: 原始姓名 / Исходное имя / Original name
- `lastname`: 姓 / Фамилия / Last name
- `firstname`: 名 / Имя / First name

### 2. dois.json
**描述 / Описание / Description:**
- DOI列表数据集 / Список DOI / DOI list dataset
- 用于测试Crossref API集成和文章去重 / Для тестирования интеграции Crossref API и дедупликации / Used to test Crossref API integration and article deduplication

**统计 / Статистика / Statistics:**
- 总DOI数 / Всего DOI / Total DOIs: 7,723
- 文件大小 / Размер файла / File size: ~216 KB

**数据结构 / Структура данных / Data Structure:**
```json
[
  "",
  "10.1002/2014jb011246",
  "10.1002/adem.202001491",
  ...
]
```

**注意 / Примечание / Note:**
- 第一个元素为空字符串（在测试中会被过滤）
- Первый элемент - пустая строка (фильтруется при тестировании)
- First element is an empty string (filtered during testing)

---

## 数据来源 / Источник данных / Data Source

### 学术数据 / Академические данные / Academic Data
所有数据均来自公开的学术出版物和Crossref数据库：
- ✅ 作者姓名：来自学术论文的公开署名 / Имена авторов из публичных подписей / Author names from public publications
- ✅ DOI：公开的数字对象标识符 / Публичные идентификаторы / Public Digital Object Identifiers
- ✅ 无隐私数据：不包含个人联系方式或敏感信息 / Нет личных данных / No personal contact or sensitive information

### 数据收集 / Сбор данных / Data Collection
数据收集自ИСТИНА科学计量系统的真实使用场景，用于：
- 系统功能验证 / Верификация функциональности системы / System functionality verification
- 算法性能测试 / Тестирование производительности алгоритмов / Algorithm performance testing
- 可复现的研究结果 / Воспроизводимые результаты исследования / Reproducible research results

---

## 完整数据集下载 / Скачать полный набор / Full Dataset Download

### 🔗 Google Drive访问 / Доступ через Google Drive / Google Drive Access

所有测试数据文件已上传至Google Drive，便于导师和研究者下载和使用：

Все файлы тестовых данных загружены на Google Drive для удобного доступа научного руководителя и исследователей:

All test data files have been uploaded to Google Drive for easy access by advisors and researchers:

**📥 [下载测试数据 / Скачать тестовые данные / Download Test Data](https://drive.google.com/drive/folders/1BHyZJt8MhTPz6isMRoBIT2NVQuf1H6Eq?usp=sharing)**

**Google Drive包含的文件 / Файлы на Google Drive / Files on Google Drive:**
1. `authors.json` (864 KB) - 8,997条初始作者记录
2. `dois.json` (216 KB) - 7,723个测试DOI
3. 其他项目相关数据文件 / Другие файлы данных проекта / Other project data files

**使用说明 / Инструкции / Instructions:**
1. 点击上方链接访问Google Drive文件夹
2. 下载所需的数据文件
3. 将文件放置在 `test_data/` 目录下
4. 运行测试脚本进行验证

**数据完整性 / Целостность данных / Data Integrity:**
- ✅ 所有数据经过验证和测试
- ✅ 与GitHub仓库中的数据完全一致
- ✅ 适用于所有测试场景和脚本

---

## 使用方法 / Использование / Usage

### 快速测试 / Быстрый тест / Quick Test
```bash
# 小规模测试（100作者 + 50 DOIs）
python scripts/test_full_scenario.py \
    --authors-file test_data/authors.json \
    --dois-file test_data/dois.json \
    --initial-authors-limit 100 \
    --dois-limit 50 \
    --verbose
```

### 中等规模测试 / Средний тест / Medium Test
```bash
# 中等规模（1000作者 + 500 DOIs）
python scripts/test_full_scenario.py \
    --authors-file test_data/authors.json \
    --dois-file test_data/dois.json \
    --initial-authors-limit 1000 \
    --dois-limit 500 \
    --max-workers 5
```

### 完整测试 / Полный тест / Full Test
```bash
# 完整数据集测试
python scripts/test_full_scenario.py \
    --authors-file test_data/authors.json \
    --dois-file test_data/dois.json \
    --max-workers 10 \
    --output test_results/full_test.json
```

---

## 测试结果示例 / Пример результатов / Example Results

使用提供的测试数据，典型的测试结果：

**配置 / Конфигурация / Configuration:**
- 初始作者 / Начальных авторов: 100
- 处理DOI / Обработано DOI: 50
- 并发线程 / Потоков: 3

**结果 / Результаты / Results:**
```
【DOI处理】
  成功获取: 50/50 (100%)
  平均时间: ~1.05秒/DOI

【作者消歧】
  匹配现有: 3 (0.62%)
  创建新的: 480
  最终总数: 580

【性能】
  总时间: 52.35秒
```

---

## 数据使用说明 / Инструкции / Instructions

### 默认路径配置 / Конфигурация путей / Path Configuration

系统默认使用这些数据文件：
```python
# 在 cli_config.py 中
DEFAULT_PATHS = {
    'authors_file': 'test_data/authors.json',
    'dois_file': 'test_data/dois.json',
}
```

### 自定义数据 / Пользовательские данные / Custom Data

如果使用自己的数据，确保格式匹配：

**authors.json 格式要求：**
```json
[
  {
    "article_id": <int>,
    "original_name": <string>,
    "lastname": <string>,
    "firstname": <string>
  }
]
```

**dois.json 格式要求：**
```json
[
  "<doi_string>",
  "10.xxxx/yyyy",
  ...
]
```

---

## 数据质量 / Качество данных / Data Quality

### 数据完整性 / Целостность / Integrity
- ✅ 所有作者记录包含完整姓名信息
- ✅ DOI列表经过清洗（移除空值）
- ✅ 数据格式符合系统要求

### 数据代表性 / Репрезентативность / Representativeness
- ✅ 涵盖多个学科领域
- ✅ 包含多语言作者姓名（中文、英文等）
- ✅ DOI来自多个出版商

---

## 数据更新 / Обновления / Updates

**当前版本 / Текущая версия / Current Version:** 1.0.0
**更新日期 / Дата обновления / Update Date:** 2025-11-11

如需更大规模的测试数据或特定领域的数据，请联系项目维护者。

Для более крупных наборов данных или данных из конкретных областей обратитесь к maintainer проекта.

For larger datasets or domain-specific data, please contact the project maintainer.

---

## 引用说明 / Цитирование / Citation

如果在研究中使用此数据集，请引用本项目：

```
Ma Jiaxin. (2025). Incremental Author Disambiguation System.
Moscow State University.
GitHub: https://github.com/Soulbeaters/incremental-author-disambiguation
```

---

## 许可证 / Лицензия / License

测试数据用于科研和教育目的，遵循MIT许可证。数据来源于公开的学术出版物。

Тестовые данные предназначены для исследовательских и образовательных целей, следуют лицензии MIT. Данные получены из публичных академических публикаций.

Test data is for research and educational purposes, following the MIT license. Data is sourced from public academic publications.
