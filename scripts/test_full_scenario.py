# -*- coding: utf-8 -*-
"""
完整测试场景 / Полный тестовый сценарий / Complete Test Scenario

任务 2.5: 基于真实数据的完整测试
Task 2.5: Complete test based on real data

实现流程 / Процесс реализации / Implementation Process:
1. 从authors.json加载初始作者数据库（前1000个）
   Загрузка базы авторов из authors.json (первые 1000)
   Load initial author database from authors.json (first 1000)

2. 从dois.json读取DOI列表
   Чтение списка DOI из dois.json
   Read DOI list from dois.json

3. 整合所有模块进行测试：
   Интеграция всех модулей для тестирования:
   Integrate all modules for testing:
   - CrossrefClient (获取文章元数据 / получение метаданных / fetch metadata)
   - ArticleDeduplicator (防止重复文章 / предотвращение дубликатов / prevent duplicates)
   - AuthorMerger (作者匹配 / сопоставление авторов / author matching)
   - AuthorDatabase (作者管理 / управление авторами / author management)

4. 生成详细测试报告
   Генерация детального отчёта
   Generate detailed test report
"""

import sys
import os
import json
import logging
import argparse
from datetime import datetime
from typing import List, Dict, Any, Optional
from collections import defaultdict

# 添加项目根目录到路径 / Добавление корневой директории в путь
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from models.database import AuthorDatabase
from models.author import Author
from integrations.crossref_client import CrossrefClient
from disambiguation_engine.article_deduplicator import ArticleDeduplicator
from disambiguation_engine.author_merger import AuthorMerger
from cli_config import CLIConfig


class TestScenario:
    """
    完整测试场景控制器 / Контроллер полного тестового сценария

    协调所有模块完成端到端测试
    Координирует все модули для сквозного тестирования
    Coordinates all modules for end-to-end testing
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化测试场景 / Инициализация тестового сценария

        Args:
            config: 配置字典 / Словарь конфигурации / Configuration dictionary
        """
        self.config = config
        self.logger = self._setup_logging()

        # 初始化各模块 / Инициализация модулей / Initialize modules
        self.db = AuthorDatabase()
        self.crossref_client = CrossrefClient(email=config.get('email', 'majiaxing@mail.ru'))
        self.deduplicator = ArticleDeduplicator(
            title_similarity_threshold=config.get('title_threshold', 0.95)
        )
        self.merger = AuthorMerger(
            similarity_threshold=config.get('author_threshold', 0.85)
        )

        # 统计信息 / Статистика / Statistics
        self.stats = {
            'initial_authors': 0,
            'dois_processed': 0,
            'dois_failed': 0,
            'articles_fetched': 0,
            'articles_deduplicated': 0,
            'authors_matched': 0,
            'authors_created': 0,
            'processing_time': 0.0
        }

        # 详细记录 / Детальные записи / Detailed logs
        self.failed_dois = []
        self.deduplicated_articles = []

    def _setup_logging(self) -> logging.Logger:
        """配置日志 / Настройка логирования / Configure logging"""
        logger = logging.getLogger(__name__)
        level = logging.DEBUG if self.config.get('debug') else \
                logging.INFO if self.config.get('verbose') else logging.WARNING
        logger.setLevel(level)

        # 控制台输出 / Вывод в консоль / Console output
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        return logger

    def load_initial_authors(self, authors_file: str, limit: int = 1000) -> None:
        """
        加载初始作者数据库 / Загрузка начальной базы авторов

        Args:
            authors_file: 作者文件路径 / Путь к файлу авторов
            limit: 加载数量限制 / Лимит загрузки / Loading limit
        """
        self.logger.info(f"加载初始作者数据库 / Загрузка базы авторов: {authors_file}")
        self.logger.info(f"限制数量 / Лимит: {limit}")

        try:
            with open(authors_file, 'r', encoding='utf-8') as f:
                authors_data = json.load(f)

            # 取前N个作者 / Взять первые N авторов / Take first N authors
            authors_to_load = authors_data[:limit]

            self.logger.info(f"正在添加 {len(authors_to_load)} 个作者到数据库...")

            for author_data in authors_to_load:
                # 构建作者数据 / Построение данных автора
                author_dict = {
                    'name': self._construct_full_name(author_data),
                    'orcid': author_data.get('orcid'),
                    'affiliation': author_data.get('affiliation', []),
                    'coauthors': [],
                    'journals': []
                }

                # 添加到数据库 / Добавление в базу данных
                author = self.db.add_author(author_dict)
                self.stats['initial_authors'] += 1

                self.logger.debug(f"已添加作者 / Добавлен автор: {author.canonical_name}")

            self.logger.info(f"✓ 成功加载 {self.stats['initial_authors']} 个作者")
            self.logger.info(f"✓ Успешно загружено {self.stats['initial_authors']} авторов")

        except Exception as e:
            self.logger.error(f"加载作者失败 / Ошибка загрузки авторов: {e}")
            raise

    def _construct_full_name(self, author_data: Dict[str, Any]) -> str:
        """
        构建完整姓名 / Построение полного имени / Construct full name

        Args:
            author_data: 作者数据 / Данные автора / Author data

        Returns:
            完整姓名 / Полное имя / Full name
        """
        # 优先使用original_name / Приоритет original_name
        if 'original_name' in author_data and author_data['original_name']:
            return author_data['original_name']

        # 否则组合firstname和lastname / Иначе комбинация firstname и lastname
        firstname = author_data.get('firstname', '').strip()
        lastname = author_data.get('lastname', '').strip()

        if firstname and lastname:
            return f"{firstname} {lastname}"
        elif lastname:
            return lastname
        elif firstname:
            return firstname
        else:
            return "Unknown Author"

    def process_dois(self, dois_file: str, limit: Optional[int] = None) -> None:
        """
        处理DOI列表 / Обработка списка DOI / Process DOI list

        Args:
            dois_file: DOI文件路径 / Путь к файлу DOI
            limit: 处理数量限制 / Лимит обработки / Processing limit
        """
        self.logger.info(f"加载DOI列表 / Загрузка списка DOI: {dois_file}")

        try:
            with open(dois_file, 'r', encoding='utf-8') as f:
                dois = json.load(f)

            # 过滤空DOI / Фильтрация пустых DOI / Filter empty DOIs
            dois = [doi for doi in dois if doi and doi.strip()]

            if limit:
                dois = dois[:limit]

            self.logger.info(f"共 {len(dois)} 个有效DOI待处理")
            self.logger.info(f"Всего {len(dois)} действительных DOI для обработки")

            start_time = datetime.now()

            # 批量获取文章元数据 / Пакетное получение метаданных
            self.logger.info("开始批量获取文章元数据 / Начало пакетного получения метаданных...")

            results = self.crossref_client.batch_get_works(
                dois,
                max_workers=self.config.get('max_workers', 5)
            )

            # 处理每篇文章 / Обработка каждой статьи / Process each article
            # batch_get_works 返回成功的文章列表 / возвращает список успешных статей
            self.stats['dois_processed'] = len(dois)
            self.stats['articles_fetched'] = len(results)
            self.stats['dois_failed'] = self.stats['dois_processed'] - self.stats['articles_fetched']

            for article_data in results:
                self.logger.debug(f"成功获取文章 / Получена статья: {article_data.get('title', 'Untitled')}")

                # 检查文章去重 / Проверка дедупликации статей
                is_duplicate, existing_article = self.deduplicator.check_duplicate(article_data)

                if is_duplicate:
                    self.stats['articles_deduplicated'] += 1
                    self.deduplicated_articles.append({
                        'doi': article_data.get('doi', 'Unknown'),
                        'title': article_data.get('title', 'Untitled')
                    })
                    self.logger.debug(f"检测到重复文章 / Обнаружен дубликат: {article_data.get('doi', 'Unknown')}")
                    continue

                # 添加文章到去重索引 / Добавление в индекс дедупликации
                self.deduplicator.add_article(article_data)

                # 处理文章作者 / Обработка авторов статьи
                self._process_article_authors(article_data)

            end_time = datetime.now()
            self.stats['processing_time'] = (end_time - start_time).total_seconds()

            self.logger.info("✓ DOI处理完成 / Обработка DOI завершена")

        except Exception as e:
            self.logger.error(f"处理DOI失败 / Ошибка обработки DOI: {e}")
            raise

    def _process_article_authors(self, article_data: Dict[str, Any]) -> None:
        """
        处理文章的所有作者 / Обработка всех авторов статьи

        Args:
            article_data: 文章数据 / Данные статьи / Article data
        """
        authors = article_data.get('authors', [])

        for author_info in authors:
            # Crossref返回的字段名是'full_name'而不是'name'
            # Crossref возвращает 'full_name' вместо 'name'
            author_name = author_info.get('full_name', '') or author_info.get('name', '')
            if not author_name:
                continue

            # 准备作者候选信息 / Подготовка информации кандидата
            candidate = {
                'name': author_name,
                'orcid': author_info.get('orcid'),
                'coauthors': [a.get('full_name', a.get('name', '')) for a in authors
                             if a.get('full_name', a.get('name', '')) != author_name],
                'journals': [article_data.get('journal')] if article_data.get('journal') else [],
                'affiliation': author_info.get('affiliation', [])  # affiliation is a list
            }

            # 尝试匹配现有作者 / Попытка сопоставления с существующим автором
            # AuthorMerger需要作者列表，不是数据库对象 / AuthorMerger нужен список авторов, не объект БД
            existing_authors = self.db.get_all_authors()
            matched_author, similarity = self.merger.find_matching_author(candidate, existing_authors)

            if matched_author:
                # 匹配成功 / Сопоставление успешно / Match found
                self.stats['authors_matched'] += 1
                self.logger.debug(
                    f"作者匹配 / Сопоставлен автор: {author_name} -> {matched_author.canonical_name} "
                    f"(相似度 / сходство: {similarity:.2f})"
                )

                # 更新作者信息 / Обновление информации автора
                if candidate.get('journals'):
                    for journal in candidate['journals']:
                        matched_author.add_journal(journal)

                # affiliation是列表，需要遍历添加 / affiliation это список, нужно добавлять по одному
                if candidate.get('affiliation'):
                    affiliations = candidate['affiliation']
                    if isinstance(affiliations, list):
                        for aff in affiliations:
                            if aff:  # 跳过空字符串 / пропускаем пустые строки
                                matched_author.add_affiliation(aff)
                    elif isinstance(affiliations, str):
                        matched_author.add_affiliation(affiliations)

            else:
                # 创建新作者 / Создание нового автора / Create new author
                self.stats['authors_created'] += 1
                new_author = self.db.add_author(candidate)
                self.logger.debug(f"创建新作者 / Создан новый автор: {new_author.canonical_name}")

    def generate_report(self, output_file: Optional[str] = None) -> None:
        """
        生成测试报告 / Генерация тестового отчёта / Generate test report

        Args:
            output_file: 输出文件路径 / Путь к файлу вывода / Output file path
        """
        self.logger.info("生成测试报告 / Генерация отчёта...")

        # 获取数据库统计 / Получение статистики БД / Get DB statistics
        db_stats = self.db.get_statistics()
        dedup_stats = self.deduplicator.get_statistics()

        # 构建报告 / Построение отчёта / Build report
        report = {
            'test_metadata': {
                'timestamp': datetime.now().isoformat(),
                'configuration': self.config
            },
            'statistics': {
                'initial_authors': self.stats['initial_authors'],
                'dois_processed': self.stats['dois_processed'],
                'dois_failed': self.stats['dois_failed'],
                'articles_fetched': self.stats['articles_fetched'],
                'articles_deduplicated': self.stats['articles_deduplicated'],
                'authors_matched': self.stats['authors_matched'],
                'authors_created': self.stats['authors_created'],
                'processing_time_seconds': self.stats['processing_time'],
                'final_author_count': db_stats['total_authors'],
                'articles_indexed_by_doi': dedup_stats['indexed_by_doi'],
                'articles_indexed_by_title': dedup_stats['indexed_by_title']
            },
            'database_statistics': db_stats,
            'deduplication_statistics': dedup_stats,
            'failed_dois': self.failed_dois[:50],  # 前50个失败的DOI
            'deduplicated_articles_sample': self.deduplicated_articles[:20]  # 前20个重复文章
        }

        # 输出到文件 / Вывод в файл / Output to file
        if output_file:
            # 确保输出目录存在 / Убедиться, что директория существует
            import os
            output_dir = os.path.dirname(output_file)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)

            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            self.logger.info(f"报告已保存 / Отчёт сохранён: {output_file}")

        # 打印摘要 / Печать резюме / Print summary
        self._print_summary(report)

    def _print_summary(self, report: Dict[str, Any]) -> None:
        """
        打印测试摘要 / Печать резюме теста / Print test summary

        Args:
            report: 报告数据 / Данные отчёта / Report data
        """
        print("\n" + "=" * 80)
        print("测试报告摘要 / Резюме тестового отчёта / Test Report Summary")
        print("=" * 80)

        stats = report['statistics']

        print(f"\n【初始状态 / Начальное состояние / Initial State】")
        print(f"  初始作者数 / Начальных авторов: {stats['initial_authors']}")

        print(f"\n【DOI处理 / Обработка DOI / DOI Processing】")
        print(f"  处理DOI总数 / Всего обработано DOI: {stats['dois_processed']}")
        print(f"  成功获取文章 / Успешно получено статей: {stats['articles_fetched']}")
        print(f"  失败DOI数 / Неудачных DOI: {stats['dois_failed']}")

        print(f"\n【文章去重 / Дедупликация статей / Article Deduplication】")
        print(f"  检测到重复文章 / Обнаружено дубликатов: {stats['articles_deduplicated']}")
        print(f"  按DOI索引 / Индексировано по DOI: {stats['articles_indexed_by_doi']}")
        print(f"  按标题索引 / Индексировано по заголовкам: {stats['articles_indexed_by_title']}")

        print(f"\n【作者消歧 / Устранение неоднозначности авторов / Author Disambiguation】")
        print(f"  匹配现有作者 / Сопоставлено существующих: {stats['authors_matched']}")
        print(f"  创建新作者 / Создано новых: {stats['authors_created']}")
        print(f"  最终作者总数 / Итоговое количество авторов: {stats['final_author_count']}")

        print(f"\n【性能 / Производительность / Performance】")
        print(f"  总处理时间 / Общее время обработки: {stats['processing_time_seconds']:.2f} 秒 / секунд")
        if stats['dois_processed'] > 0:
            avg_time = stats['processing_time_seconds'] / stats['dois_processed']
            print(f"  平均每DOI / Среднее на DOI: {avg_time:.2f} 秒 / секунд")

        print("\n" + "=" * 80)

        # 计算准确率指标 / Вычисление метрик точности / Calculate accuracy metrics
        if stats['authors_matched'] + stats['authors_created'] > 0:
            match_rate = stats['authors_matched'] / (stats['authors_matched'] + stats['authors_created'])
            print(f"\n【质量指标 / Метрики качества / Quality Metrics】")
            print(f"  作者匹配率 / Коэффициент сопоставления авторов: {match_rate:.2%}")

        if stats['articles_fetched'] > 0:
            dedup_rate = stats['articles_deduplicated'] / stats['articles_fetched']
            print(f"  文章去重率 / Коэффициент дедупликации статей: {dedup_rate:.2%}")

        print("\n" + "=" * 80)


def main():
    """主函数 / Главная функция / Main function"""
    # 解析命令行参数 / Разбор аргументов командной строки
    parser = CLIConfig.create_base_parser(
        description='完整测试场景 / Полный тестовый сценарий / Complete Test Scenario',
        add_data_files=True,
        add_output_files=True,
        add_config=True
    )

    # 添加特定参数 / Добавление специфичных параметров
    parser.add_argument(
        '--initial-authors-limit',
        type=int,
        default=1000,
        help='初始作者数量限制 / Лимит начальных авторов / Initial authors limit (default: 1000)'
    )

    parser.add_argument(
        '--dois-limit',
        type=int,
        default=None,
        help='DOI处理数量限制 / Лимит обработки DOI / DOI processing limit (default: all)'
    )

    parser.add_argument(
        '--title-threshold',
        type=float,
        default=0.95,
        help='标题相似度阈值 / Порог сходства заголовков / Title similarity threshold (default: 0.95)'
    )

    parser.add_argument(
        '--author-threshold',
        type=float,
        default=0.85,
        help='作者相似度阈值 / Порог сходства авторов / Author similarity threshold (default: 0.85)'
    )

    parser.add_argument(
        '--email',
        type=str,
        default='majiaxing@mail.ru',
        help='Crossref API联系邮箱 / Email для Crossref API / Crossref API contact email'
    )

    args = parser.parse_args()

    # 构建配置 / Построение конфигурации / Build configuration
    config = {
        'authors_file': args.authors_file,
        'dois_file': args.dois_file,
        'output_file': args.output,
        'initial_authors_limit': args.initial_authors_limit,
        'dois_limit': args.dois_limit,
        'title_threshold': args.title_threshold,
        'author_threshold': args.author_threshold,
        'max_workers': args.max_workers,
        'email': args.email,
        'verbose': args.verbose,
        'debug': args.debug
    }

    # 打印配置 / Печать конфигурации / Print configuration
    print("=" * 80)
    print("完整测试场景启动 / Запуск полного тестового сценария")
    print("Complete Test Scenario Starting")
    print("=" * 80)
    print(f"\n配置 / Конфигурация / Configuration:")
    print(f"  作者文件 / Файл авторов: {config['authors_file']}")
    print(f"  DOI文件 / Файл DOI: {config['dois_file']}")
    print(f"  初始作者限制 / Лимит начальных авторов: {config['initial_authors_limit']}")
    print(f"  DOI限制 / Лимит DOI: {config['dois_limit'] or '全部 / все / all'}")
    print(f"  作者相似度阈值 / Порог сходства авторов: {config['author_threshold']}")
    print(f"  标题相似度阈值 / Порог сходства заголовков: {config['title_threshold']}")
    print(f"  并发工作数 / Рабочих потоков: {config['max_workers']}")
    print("=" * 80 + "\n")

    # 创建并运行测试场景 / Создание и запуск тестового сценария
    scenario = TestScenario(config)

    try:
        # 步骤1: 加载初始作者 / Шаг 1: Загрузка начальных авторов
        scenario.load_initial_authors(
            config['authors_file'],
            limit=config['initial_authors_limit']
        )

        # 步骤2: 处理DOI / Шаг 2: Обработка DOI
        scenario.process_dois(
            config['dois_file'],
            limit=config['dois_limit']
        )

        # 步骤3: 生成报告 / Шаг 3: Генерация отчёта
        scenario.generate_report(output_file=config['output_file'])

        print("\n[OK] 测试完成 / Тест завершён / Test completed successfully!")

    except KeyboardInterrupt:
        print("\n\n[WARN] 测试被用户中断 / Тест прерван пользователем / Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n[ERROR] 测试失败 / Тест не удался / Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
