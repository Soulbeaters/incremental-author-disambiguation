# 增量作者消歧系统 / Система инкрементального устранения неоднозначности авторов

## 项目概述 / Обзор проекта

本项目实现了一个完整的增量作者消歧系统，用于解决科学计量系统（如ИСТИНА）中的作者身份识别、文章去重和数据验证问题。系统集成了Crossref API用于获取学术文章元数据，并通过多维相似度计算实现智能的作者消歧和合并。

Этот проект реализует полную систему инкрементального устранения неоднозначности авторов для решения задач идентификации авторов, дедупликации статей и верификации данных в наукометрических системах (например, ИСТИНА). Система интегрирует Crossref API для получения метаданных научных статей и использует многомерный расчёт сходства для интеллектуального устранения неоднозначности и слияния авторов.

---

## 核心特性 / Основные характеристики

### 1. Crossref API 集成 / Интеграция Crossref API
- 通过DOI自动获取文章元数据 / Автоматическое получение метаданных по DOI
- 支持批量并发查询 / Поддержка пакетных параллельных запросов
- Etiquette优先级机制 / Механизм приоритета через этикет
- 完整的作者、期刊、ORCID信息解析 / Полный парсинг информации об авторах, журналах, ORCID

### 2. 智能文章去重 / Интеллектуальная дедупликация статей
- **DOI优先匹配** / **Приоритет DOI**: 最可靠的去重方式
- **标题相似度匹配** / **Сходство заголовков**: 基于Levenshtein距离的模糊匹配
- **双索引机制** / **Двойное индексирование**: DOI索引 + 标题索引
- 防止重复文章添加到系统 / Предотвращение добавления дубликатов статей

### 3. 多维作者消歧 / Многомерное устранение неоднозначности авторов
采用加权相似度计算，综合多个维度判断作者身份：
- **姓名相似度 (40%)** / **Сходство имён (40%)**: Levenshtein距离 + 备选姓名匹配
- **ORCID匹配 (30%)** / **Совпадение ORCID (30%)**: 唯一标识符精确匹配
- **合著者重叠 (15%)** / **Пересечение соавторов (15%)**: Jaccard相似度
- **期刊重叠 (10%)** / **Пересечение журналов (10%)**: 发表期刊匹配
- **机构相似度 (5%)** / **Сходство аффилиаций (5%)**: 所属机构匹配

### 4. 高效数据库管理 / Эффективное управление базой данных
- **多索引架构** / **Мультииндексная архитектура**: 姓氏、ORCID、ID索引
- **O(1)查找复杂度** / **Сложность поиска O(1)**: 极速作者查询
- **增量更新支持** / **Поддержка инкрементальных обновлений**: 实时添加新作者和文章

### 5. 灵活的CLI接口 / Гибкий CLI интерфейс
- 统一的命令行参数配置 / Единая конфигурация параметров командной строки
- 支持自定义数据文件路径 / Поддержка пользовательских путей к файлам данных
- 可配置的阈值和并发数 / Настраиваемые пороги и количество потоков
- 详细的日志和调试模式 / Подробное логирование и режим отладки

---

## 项目结构 / Структура проекта

```
author_disambiguation/
├── models/                              # 数据模型 / Модели данных
│   ├── __init__.py
│   ├── author.py                        # 作者数据模型 / Модель данных автора
│   ├── publication.py                   # 出版物数据模型 / Модель публикации
│   └── database.py                      # 作者数据库管理 / Управление БД авторов
│
├── disambiguation_engine/               # 消歧引擎 / Движок устранения неоднозначности
│   ├── __init__.py
│   ├── similarity_scorer.py             # 相似度评分器 / Оценщик сходства
│   ├── author_merger.py                 # 作者合并引擎 / Движок слияния авторов
│   └── article_deduplicator.py          # 文章去重器 / Дедупликатор статей
│
├── integrations/                        # 外部API集成 / Интеграция внешних API
│   ├── __init__.py
│   └── crossref_client.py               # Crossref API客户端 / Клиент Crossref API
│
├── scripts/                             # 测试脚本 / Тестовые скрипты
│   ├── demo_incremental_disambiguation.py  # 增量消歧演示
│   ├── demo_auto.py                     # 自动消歧演示
│   ├── test_with_real_dois.py           # 真实DOI测试
│   └── test_full_scenario.py            # 完整测试场景 / Полный тестовый сценарий
│
├── cli_config.py                        # CLI配置管理 / Управление конфигурацией CLI
├── config.py                            # 系统配置 / Системная конфигурация
├── requirements.txt                     # 依赖包列表 / Список зависимостей
└── README.md                            # 项目文档 / Документация проекта
```

---

## 安装和环境配置 / Установка и настройка среды

### 1. 系统要求 / Системные требования
- Python 3.8+
- Windows / Linux / macOS
- 网络连接（用于Crossref API）/ Интернет-соединение (для Crossref API)

### 2. 安装依赖 / Установка зависимостей
```bash
cd "C:\program 2 in 2025\author_disambiguation"
pip install -r requirements.txt
```

主要依赖包 / Основные зависимости:
- `crossrefapi>=1.5.0` - Crossref API客户端
- `python-Levenshtein>=0.12.0` - 快速字符串相似度计算

---

## 快速开始 / Быстрый старт

### 1. 基础演示 / Базовая демонстрация
运行增量消歧演示程序：
```bash
python scripts/demo_incremental_disambiguation.py
```

### 2. 自动消歧演示 / Автоматическая демонстрация
```bash
python scripts/demo_auto.py
```

### 3. 真实DOI测试 / Тест с реальными DOI
```bash
python scripts/test_with_real_dois.py --dois-limit 100 --max-workers 5
```

### 4. 完整测试场景 / Полный тестовый сценарий
运行完整的端到端测试，使用真实数据：
```bash
python scripts/test_full_scenario.py \
    --initial-authors-limit 1000 \
    --dois-limit 500 \
    --max-workers 5 \
    --author-threshold 0.85 \
    --output test_results/full_scenario_report.json
```

---

## 详细使用指南 / Подробное руководство по использованию

### 1. 基本代码示例 / Пример базового кода

#### 1.1 Crossref API使用 / Использование Crossref API
```python
from integrations.crossref_client import CrossrefClient

# 创建客户端 / Создание клиента
client = CrossrefClient(email='your.email@example.com')

# 单个DOI查询 / Одиночный запрос DOI
article = client.get_work_by_doi('10.1038/nature12373')
print(f"Title: {article['title']}")
print(f"Authors: {len(article['authors'])}")

# 批量查询 / Пакетный запрос
dois = ['10.1038/nature12373', '10.1126/science.1248506']
results = client.batch_get_works(dois, max_workers=3)
print(f"Fetched {len(results)} articles")
```

#### 1.2 文章去重 / Дедупликация статей
```python
from disambiguation_engine.article_deduplicator import ArticleDeduplicator

# 创建去重器 / Создание дедупликатора
deduplicator = ArticleDeduplicator(title_similarity_threshold=0.95)

# 检查文章是否重复 / Проверка дубликата
article = {'doi': '10.1038/nature12373', 'title': 'Example Article'}
is_duplicate, existing = deduplicator.check_duplicate(article)

if not is_duplicate:
    deduplicator.add_article(article)
    print("Article added / Статья добавлена")
else:
    print("Duplicate detected / Обнаружен дубликат")

# 获取统计信息 / Получение статистики
stats = deduplicator.get_statistics()
print(f"Total articles indexed: {stats['total_articles']}")
```

#### 1.3 作者消歧和合并 / Устранение неоднозначности и слияние авторов
```python
from models.database import AuthorDatabase
from disambiguation_engine.author_merger import AuthorMerger

# 创建数据库和合并引擎 / Создание БД и движка слияния
db = AuthorDatabase()
merger = AuthorMerger(similarity_threshold=0.85)

# 添加初始作者 / Добавление начальных авторов
author1_data = {
    'name': 'John Smith',
    'orcid': '0000-0001-2345-6789',
    'affiliation': ['MIT'],
    'journals': ['Nature', 'Science']
}
db.add_author(author1_data)

# 新作者候选 / Новый кандидат в авторы
candidate = {
    'name': 'J. Smith',
    'orcid': '0000-0001-2345-6789',
    'coauthors': ['Jane Doe'],
    'journals': ['Nature']
}

# 查找匹配 / Поиск совпадения
existing_authors = db.get_all_authors()
matched_author, similarity = merger.find_matching_author(candidate, existing_authors)

if matched_author:
    print(f"Matched with: {matched_author.canonical_name}")
    print(f"Similarity: {similarity:.3f}")
else:
    # 创建新作者 / Создание нового автора
    new_author = db.add_author(candidate)
    print(f"Created new author: {new_author.canonical_name}")
```

### 2. CLI参数说明 / Описание параметров CLI

#### 2.1 完整测试场景参数 / Параметры полного тестового сценария
```bash
python scripts/test_full_scenario.py [OPTIONS]
```

**数据文件 / Файлы данных:**
- `--authors-file PATH` - 初始作者数据文件路径 / Путь к файлу начальных авторов
  - 默认 / По умолчанию: `C:\istina\materia 材料\测试表单\authors.json`
- `--dois-file PATH` - DOI列表文件路径 / Путь к файлу списка DOI
  - 默认 / По умолчанию: `C:\istina\materia 材料\测试表单\dois.json`

**输出配置 / Конфигурация вывода:**
- `--output PATH` - 测试报告输出路径 / Путь для вывода отчёта
  - 默认 / По умолчанию: `test_results/test_full_scenario_report.json`

**性能参数 / Параметры производительности:**
- `--initial-authors-limit N` - 加载初始作者数量限制 / Лимит начальных авторов
  - 默认 / По умолчанию: 1000
- `--dois-limit N` - 处理DOI数量限制 / Лимит обработки DOI
  - 默认 / По умолчанию: all (所有 / все)
- `--max-workers N` - 并发工作线程数 / Количество параллельных потоков
  - 默认 / По умолчанию: 5

**阈值配置 / Конфигурация порогов:**
- `--author-threshold FLOAT` - 作者相似度阈值 [0-1] / Порог сходства авторов
  - 默认 / По умолчанию: 0.85
- `--title-threshold FLOAT` - 标题相似度阈值 [0-1] / Порог сходства заголовков
  - 默认 / По умолчанию: 0.95

**调试选项 / Опции отладки:**
- `--verbose` - 详细输出模式 / Подробный вывод
- `--debug` - 调试模式（最详细输出）/ Режим отладки (самый подробный вывод)
- `--email EMAIL` - Crossref API联系邮箱 / Email для Crossref API

**示例 / Примеры:**
```bash
# 小规模测试 / Небольшой тест
python scripts/test_full_scenario.py \
    --initial-authors-limit 100 \
    --dois-limit 50 \
    --max-workers 3 \
    --verbose

# 大规模测试 / Масштабный тест
python scripts/test_full_scenario.py \
    --initial-authors-limit 5000 \
    --dois-limit 2000 \
    --max-workers 10 \
    --author-threshold 0.85 \
    --output results/large_test_report.json

# 调试模式 / Режим отладки
python scripts/test_full_scenario.py \
    --initial-authors-limit 10 \
    --dois-limit 5 \
    --debug
```

---

## 测试结果示例 / Пример результатов тестирования

### 测试配置 / Конфигурация теста
- 初始作者数 / Начальных авторов: 100
- 处理DOI数 / Обработано DOI: 50
- 并发线程 / Параллельных потоков: 3
- 作者阈值 / Порог авторов: 0.85

### 测试结果 / Результаты теста
```
【DOI处理】
  处理DOI总数: 50
  成功获取文章: 50
  失败DOI数: 0

【文章去重】
  检测到重复文章: 0
  按DOI索引: 50
  按标题索引: 50

【作者消歧】
  匹配现有作者: 3 (0.62%)
  创建新作者: 480
  最终作者总数: 580

【性能】
  总处理时间: 52.35 秒
  平均每DOI: 1.05 秒
```

详细的测试报告以JSON格式保存，包含：
- 测试元数据和配置 / Метаданные и конфигурация теста
- 详细统计信息 / Подробная статистика
- 数据库状态 / Состояние базы данных
- 失败DOI列表 / Список неудачных DOI
- 重复文章样本 / Примеры дубликатов статей

---

## 算法详解 / Подробное описание алгоритмов

### 1. 作者相似度计算 / Расчёт сходства авторов

系统采用多维加权相似度计算：

```
总相似度 = 0.40 × 姓名相似度
         + 0.30 × ORCID相似度
         + 0.15 × 合著者相似度
         + 0.10 × 期刊相似度
         + 0.05 × 机构相似度
```

**姓名相似度 / Сходство имён:**
- 使用Levenshtein距离计算编辑距离
- 支持备选姓名匹配（John Smith ↔ J. Smith）
- 标准化处理：小写化、移除标点、移除多余空格

**ORCID相似度 / Сходство ORCID:**
- 二值匹配：完全匹配=1.0，否则=0.0
- ORCID是全球唯一的研究者标识符
- 最可靠的作者识别方式

**合著者相似度 / Сходство соавторов:**
```
Jaccard系数 = |交集| / |并集|
```
- 共同合著者越多，相似度越高
- 反映研究合作网络的重叠程度

**期刊相似度 / Сходство журналов:**
- Jaccard系数计算发表期刊重叠
- 标准化处理期刊名称（移除"Journal of"等常见词）

**机构相似度 / Сходство аффилиаций:**
- 最高相似度匹配（支持多个机构）
- 标准化处理：university→univ, institute→inst

### 2. 文章去重策略 / Стратегия дедупликации статей

**两阶段去重 / Двухэтапная дедупликация:**

1. **DOI精确匹配** （优先级最高）
   - O(1)时间复杂度
   - 100%准确率

2. **标题模糊匹配** （后备方案）
   - 标准化标题（小写、移除标点、移除停用词）
   - Levenshtein相似度计算
   - 默认阈值：0.95

### 3. 数据库索引结构 / Структура индексов БД

```python
AuthorDatabase:
  - authors: List[Author]                    # 主存储
  - surname_index: Dict[str, List[Author]]   # 姓氏索引
  - orcid_index: Dict[str, Author]           # ORCID索引
  - id_index: Dict[str, Author]              # ID索引
```

查找性能 / Производительность поиска:
- 按ORCID查找：O(1)
- 按ID查找：O(1)
- 按姓氏查找：O(k)，其中k是同姓作者数量

---

## 系统性能 / Производительность системы

### 性能指标 / Показатели производительности

**Crossref API查询 / Запросы к Crossref API:**
- 单个DOI查询：~0.5-1.5秒 / запрос
- 批量查询（并发=5）：~1.0秒/DOI
- 受网络延迟和API限流影响

**作者消歧 / Устранение неоднозначности авторов:**
- 100作者数据库：<0.01秒/查询
- 1000作者数据库：<0.05秒/查询
- 10000作者数据库：<0.5秒/查询

**文章去重 / Дедупликация статей:**
- DOI匹配：O(1)，<0.001秒
- 标题匹配：O(n)，n为已索引文章数

### 优化建议 / Рекомендации по оптимизации

1. **批量处理** / **Пакетная обработка**
   - 使用batch_get_works()进行批量DOI查询
   - 调整max_workers参数平衡速度和API限制

2. **缓存机制** / **Механизм кэширования**
   - Crossref结果可缓存避免重复查询
   - 文章去重索引持久化

3. **阈值调优** / **Настройка порогов**
   - 提高阈值：减少误匹配，但可能漏掉真实匹配
   - 降低阈值：增加匹配率，但可能产生误匹配
   - 建议范围：0.80-0.90

---

## 配置说明 / Описание конфигурации

### 系统配置文件 / Файл конфигурации системы

`config.py` 包含全局配置：

```python
# 相似度权重 / Веса сходства
SIMILARITY_WEIGHTS = {
    'name': 0.40,
    'orcid': 0.30,
    'coauthor': 0.15,
    'journal': 0.10,
    'affiliation': 0.05
}

# 阈值 / Пороги
SIMILARITY_THRESHOLD = 0.85          # 作者匹配阈值
TITLE_SIMILARITY_THRESHOLD = 0.95    # 标题去重阈值

# API配置 / Конфигурация API
CROSSREF_EMAIL = 'majiaxing@mail.ru'
CROSSREF_MAX_WORKERS = 5
```

### CLI配置 / Конфигурация CLI

`cli_config.py` 提供统一的CLI参数管理：

```python
from cli_config import CLIConfig

# 创建解析器 / Создание парсера
parser = CLIConfig.create_base_parser(
    description='My Script',
    add_data_files=True,
    add_output_files=True,
    add_config=True
)

args = parser.parse_args()
```

---

## 错误处理和日志 / Обработка ошибок и логирование

### 日志级别 / Уровни логирования

系统支持三种日志级别：

1. **正常模式** / **Обычный режим** (WARNING):
   - 仅显示警告和错误
   - 适合生产环境

2. **详细模式** / **Подробный режим** (INFO): `--verbose`
   - 显示处理进度和关键操作
   - 适合监控和调试

3. **调试模式** / **Режим отладки** (DEBUG): `--debug`
   - 显示所有详细信息
   - 包括相似度计算细节
   - 适合开发和问题诊断

### 常见错误处理 / Обработка распространённых ошибок

**网络错误 / Сетевые ошибки:**
```python
# Crossref API调用失败会记录警告并继续处理
# При сбое API регистрируется предупреждение и обработка продолжается
logger.warning(f"Failed to fetch DOI {doi}: {error}")
```

**数据验证 / Валидация данных:**
```python
# 空字段和无效数据会被安全忽略
# Пустые поля и недействительные данные безопасно игнорируются
if not author_name:
    continue
```

**文件操作 / Файловые операции:**
```python
# 自动创建输出目录
# Автоматическое создание выходных директорий
if not os.path.exists(output_dir):
    os.makedirs(output_dir, exist_ok=True)
```

---

## 测试和验证 / Тестирование и верификация

### 代码质量保证 / Обеспечение качества кода

项目包含全面的代码审查报告：`CODE_REVIEW_REPORT.md`

**已修复的关键问题 / Исправленные критические проблемы:**
- ✅ Author模型ORCID字段缺失
- ✅ AuthorDatabase字段名称不匹配
- ✅ Author构造函数参数错误
- ✅ ArticleDeduplicator统计方法类型错误

**测试覆盖 / Покрытие тестами:**
- ✅ 模型创建和字段访问
- ✅ 数据库CRUD操作
- ✅ 作者相似度计算
- ✅ 文章去重逻辑
- ✅ Crossref API集成
- ✅ 端到端测试场景

### 验证步骤 / Шаги верификации

1. **语法检查** / **Проверка синтаксиса**: 所有模块通过Python编译
2. **模块导入** / **Импорт модулей**: 核心模块成功导入
3. **功能测试** / **Функциональное тестирование**: 所有功能测试通过
4. **性能测试** / **Тестирование производительности**: 满足性能要求

---

## 技术栈 / Технологический стек

### 核心技术 / Основные технологии
- **Python 3.8+**: 主要编程语言
- **crossrefapi**: Crossref REST API官方客户端
- **python-Levenshtein**: 快速字符串相似度计算

### 数据结构 / Структуры данных
- **dataclasses**: 类型安全的数据模型
- **typing**: 完整的类型注解
- **Set/Dict**: 高效的索引和查找

### 并发处理 / Параллельная обработка
- **ThreadPoolExecutor**: 多线程并发
- **concurrent.futures**: Future对象管理

### API集成 / Интеграция API
- **Crossref REST API**: 学术元数据检索
- **Etiquette机制**: API优先级提升

---

## 未来开发计划 / Планы дальнейшей разработки

### 阶段1：持久化和缓存 / Этап 1: Персистентность и кэширование
- [ ] SQLite/PostgreSQL数据库集成
- [ ] Crossref查询结果缓存
- [ ] 增量数据导入导出

### 阶段2：高级消歧算法 / Этап 2: Продвинутые алгоритмы
- [ ] 机器学习相似度模型
- [ ] 作者关系图分析
- [ ] 时间序列分析（考虑发表时间）

### 阶段3：Web界面 / Этап 3: Веб-интерфейс
- [ ] RESTful API服务
- [ ] 交互式Web管理界面
- [ ] 批量数据上传和导出

### 阶段4：ИСТИНА集成 / Этап 4: Интеграция с ИСТИНА
- [ ] ИСТИНА API连接
- [ ] 实时数据同步
- [ ] 自动化验证流程

---

## 贡献指南 / Руководство по участию

欢迎贡献代码和提出改进建议！

### 开发流程 / Процесс разработки
1. Fork项目 / Форк проекта
2. 创建功能分支 / Создание ветки функции
3. 提交代码并测试 / Коммит кода и тестирование
4. 发起Pull Request / Создание Pull Request

### 代码规范 / Стандарты кода
- 遵循PEP 8编码规范
- 保持三语言注释（中文、俄语、英语）
- 编写单元测试覆盖新功能
- 更新文档说明

---

## 许可证 / Лицензия

本项目用于科研和教育目的，遵循MIT许可证。

Этот проект предназначен для исследовательских и образовательных целей и следует лицензии MIT.

---

## 联系方式 / Контактная информация

**作者 / Автор**: Ма Цзясин (Ma Jiaxin)

**机构 / Учреждение**: МГУ имени М.В. Ломоносова (莫斯科国立大学)

**研究方向 / Направление исследований**: Вопросы ввода и верификации больших данных в интерактивных наукометрических системах

**GitHub**: https://github.com/Soulbeaters/incremental-author-disambiguation

**项目仓库 / Репозиторий проекта**: https://github.com/Soulbeaters/incremental-author-disambiguation

---

**版本 / Версия**: 1.0.0

**最后更新 / Последнее обновление**: 2025-11-11
