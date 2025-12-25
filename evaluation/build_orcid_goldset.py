# -*- coding: utf-8 -*-
"""
构建ORCID金标准数据集 / Построение золотого стандарта ORCID
Build ORCID gold standard dataset for evaluation

中文注释：从Crossref数据中提取有ORCID的作者，构建消歧评测的金标准
Русский комментарий: Извлечение авторов с ORCID из данных Crossref для построения золотого стандарта

功能 / Функции / Features:
1. 从Crossref数据提取所有有ORCID的作者mention / Извлечение упоминаний авторов с ORCID
2. 按ORCID聚类，构建ground truth / Кластеризация по ORCID для ground truth
3. 生成gold set JSON文件用于评测 / Генерация JSON файла золотого стандарта
4. 统计分析：ORCID覆盖率、重名率等 / Статистический анализ: покрытие ORCID, частота омонимов
"""

import json
import sys
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Set, Any
from collections import defaultdict, Counter
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class ORCIDGoldSetBuilder:
    """
    ORCID金标准构建器 / Построитель золотого стандарта ORCID

    从Crossref数据中提取有ORCID的作者，构建消歧评测的ground truth
    Извлекает авторов с ORCID из Crossref для построения ground truth
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化构建器 / Инициализация построителя

        Args:
            config: 配置字典 / Словарь конфигурации
        """
        self.config = config
        self.logger = self._setup_logging()

        # 数据结构 / Структуры данных
        self.orcid_clusters = defaultdict(list)  # orcid -> list of mentions
        self.mentions = []  # 所有mention列表 / Список всех упоминаний
        self.stats = {
            'total_articles': 0,
            'total_author_mentions': 0,
            'mentions_with_orcid': 0,
            'unique_orcids': 0,
            'avg_mentions_per_orcid': 0.0,
            'max_mentions_per_orcid': 0,
            'articles_with_orcid': 0,
        }

    def _setup_logging(self) -> logging.Logger:
        """配置日志 / Настройка логирования"""
        logger = logging.getLogger(__name__)
        level = logging.DEBUG if self.config.get('debug') else logging.INFO
        logger.setLevel(level)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        return logger

    def load_crossref_data(self, crossref_file: str, limit: int = None) -> None:
        """
        加载Crossref数据 / Загрузка данных Crossref

        Args:
            crossref_file: Crossref JSON文件路径
            limit: 限制加载数量 (用于测试) / Лимит загрузки
        """
        self.logger.info(f"加载Crossref数据 / Загрузка данных Crossref: {crossref_file}")

        try:
            with open(crossref_file, 'r', encoding='utf-8') as f:
                articles = json.load(f)

            if limit:
                articles = articles[:limit]
                self.logger.info(f"限制加载数量 / Ограничение загрузки: {limit}")

            self.stats['total_articles'] = len(articles)
            self.logger.info(f"加载了 {len(articles)} 篇文章 / Загружено статей: {len(articles)}")

            # 提取作者mentions / Извлечение упоминаний авторов
            self._extract_mentions(articles)

        except Exception as e:
            self.logger.error(f"加载失败 / Ошибка загрузки: {e}")
            raise

    def _extract_mentions(self, articles: List[Dict[str, Any]]) -> None:
        """
        从文章中提取作者mentions / Извлечение упоминаний авторов из статей

        Args:
            articles: 文章列表 / Список статей
        """
        self.logger.info("提取作者mentions / Извлечение упоминаний авторов...")

        mention_id = 0
        articles_with_orcid = 0

        for article in articles:
            authors = article.get('author', [])
            if not authors:
                continue

            article_has_orcid = False
            doi = article.get('DOI', '')
            journal = article.get('container-title', [''])[0] if article.get('container-title') else ''
            year = article.get('published', {}).get('date-parts', [[None]])[0][0]

            for author in authors:
                # 构建mention / Построение упоминания
                mention = self._build_mention(author, mention_id, doi, journal, year, authors)

                self.mentions.append(mention)
                self.stats['total_author_mentions'] += 1
                mention_id += 1

                # 如果有ORCID，加入cluster / Если есть ORCID, добавить в кластер
                if mention['orcid']:
                    cleaned_orcid = self._clean_orcid(mention['orcid'])
                    self.orcid_clusters[cleaned_orcid].append(mention)
                    self.stats['mentions_with_orcid'] += 1
                    article_has_orcid = True

            if article_has_orcid:
                articles_with_orcid += 1

        self.stats['articles_with_orcid'] = articles_with_orcid
        self.stats['unique_orcids'] = len(self.orcid_clusters)

        if self.stats['unique_orcids'] > 0:
            self.stats['avg_mentions_per_orcid'] = self.stats['mentions_with_orcid'] / self.stats['unique_orcids']
            self.stats['max_mentions_per_orcid'] = max(len(mentions) for mentions in self.orcid_clusters.values())

        self.logger.info(f"提取完成 / Извлечение завершено:")
        self.logger.info(f"  - 总mentions: {self.stats['total_author_mentions']}")
        self.logger.info(f"  - 有ORCID的mentions: {self.stats['mentions_with_orcid']}")
        self.logger.info(f"  - 唯一ORCID数: {self.stats['unique_orcids']}")

    def _build_mention(
        self,
        author: Dict[str, Any],
        mention_id: int,
        doi: str,
        journal: str,
        year: int,
        all_authors: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        构建单个author mention / Построение одного упоминания автора

        Args:
            author: Crossref作者数据
            mention_id: mention唯一ID
            doi: DOI
            journal: 期刊名
            year: 年份
            all_authors: 该文章所有作者（用于提取coauthors）

        Returns:
            mention字典 / Словарь упоминания
        """
        # 提取姓名 / Извлечение имени
        given = author.get('given', '')
        family = author.get('family', '')
        name = f"{given} {family}".strip() if given and family else (given or family)

        # 提取ORCID / Извлечение ORCID
        orcid = author.get('ORCID', '').replace('http://orcid.org/', '').replace('https://orcid.org/', '')

        # 提取机构 / Извлечение аффилиаций
        affiliations = []
        if 'affiliation' in author:
            for aff in author['affiliation']:
                if isinstance(aff, dict) and 'name' in aff:
                    affiliations.append(aff['name'])
                elif isinstance(aff, str):
                    affiliations.append(aff)

        # 提取coauthors / Извлечение соавторов
        coauthor_names = []
        for coauthor in all_authors:
            coauthor_given = coauthor.get('given', '')
            coauthor_family = coauthor.get('family', '')
            coauthor_name = f"{coauthor_given} {coauthor_family}".strip()

            if coauthor_name and coauthor_name != name:
                coauthor_names.append(coauthor_name)

        return {
            'mention_id': mention_id,
            'name': name,
            'orcid': orcid,
            'affiliation': affiliations,
            'journal': journal,
            'year': year,
            'doi': doi,
            'coauthors': coauthor_names,
            'sequence': author.get('sequence', ''),  # first/additional
        }

    def _clean_orcid(self, orcid: str) -> str:
        """清理ORCID格式 / Очистка формата ORCID"""
        return orcid.replace('http://orcid.org/', '').replace('https://orcid.org/', '').strip()

    def build_gold_set(self, min_mentions: int = 2) -> Dict[str, Any]:
        """
        构建金标准数据集 / Построение золотого стандарта

        Args:
            min_mentions: 最小mention数（过滤掉只有1个mention的ORCID）
                         Минимальное количество упоминаний

        Returns:
            gold_set字典 / Словарь золотого стандарта
        """
        self.logger.info(f"构建金标准 / Построение золотого стандарта (min_mentions={min_mentions})...")

        # 过滤ORCID clusters / Фильтрация кластеров ORCID
        filtered_clusters = {}
        for orcid, mentions in self.orcid_clusters.items():
            if len(mentions) >= min_mentions:
                filtered_clusters[orcid] = mentions

        self.logger.info(f"过滤后保留 {len(filtered_clusters)} 个ORCID clusters")
        self.logger.info(f"После фильтрации сохранено {len(filtered_clusters)} кластеров ORCID")

        # 构建ground truth mapping / Построение отображения ground truth
        mention_to_orcid = {}
        for orcid, mentions in filtered_clusters.items():
            for mention in mentions:
                mention_to_orcid[mention['mention_id']] = orcid

        # 构建gold set / Построение золотого стандарта
        gold_set = {
            'metadata': {
                'created_at': datetime.now().isoformat(),
                'source': self.config.get('crossref_file'),
                'min_mentions_per_orcid': min_mentions,
                'total_articles': self.stats['total_articles'],
                'total_mentions': self.stats['total_author_mentions'],
                'mentions_with_orcid': self.stats['mentions_with_orcid'],
                'orcid_coverage': self.stats['mentions_with_orcid'] / self.stats['total_author_mentions'] if self.stats['total_author_mentions'] > 0 else 0,
            },
            'statistics': self.stats,
            'gold_clusters': {
                orcid: {
                    'orcid': orcid,
                    'mention_count': len(mentions),
                    'mention_ids': [m['mention_id'] for m in mentions],
                    'names': list(set(m['name'] for m in mentions)),  # 去重的姓名变体
                    'affiliations': list(set(aff for m in mentions for aff in m['affiliation'])),
                    'journals': list(set(m['journal'] for m in mentions if m['journal'])),
                }
                for orcid, mentions in filtered_clusters.items()
            },
            'mentions': {
                m['mention_id']: m
                for orcid, mentions in filtered_clusters.items()
                for m in mentions
            },
            'ground_truth': mention_to_orcid  # mention_id -> orcid mapping
        }

        self.logger.info(f"金标准构建完成:")
        self.logger.info(f"  - ORCID clusters: {len(gold_set['gold_clusters'])}")
        self.logger.info(f"  - Total mentions in gold set: {len(gold_set['mentions'])}")

        return gold_set

    def save_gold_set(self, gold_set: Dict[str, Any], output_file: str) -> None:
        """
        保存金标准数据集 / Сохранение золотого стандарта

        Args:
            gold_set: 金标准数据集
            output_file: 输出文件路径
        """
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(gold_set, f, ensure_ascii=False, indent=2)

        self.logger.info(f"金标准已保存 / Золотой стандарт сохранён: {output_file}")

    def print_statistics(self) -> None:
        """打印统计信息 / Печать статистики"""
        print("\n" + "=" * 80)
        print("ORCID金标准统计 / Статистика золотого стандарта ORCID")
        print("=" * 80)

        print(f"\n【数据规模 / Размер данных】")
        print(f"  总文章数 / Всего статей: {self.stats['total_articles']}")
        print(f"  总作者mentions / Всего упоминаний авторов: {self.stats['total_author_mentions']}")
        print(f"  有ORCID的mentions / Упоминаний с ORCID: {self.stats['mentions_with_orcid']}")
        print(f"  ORCID覆盖率 / Покрытие ORCID: {self.stats['mentions_with_orcid']/self.stats['total_author_mentions']:.1%}")

        print(f"\n【ORCID clusters】")
        print(f"  唯一ORCID数 / Уникальных ORCID: {self.stats['unique_orcids']}")
        print(f"  平均每ORCID的mentions / Среднее упоминаний на ORCID: {self.stats['avg_mentions_per_orcid']:.2f}")
        print(f"  最多mentions的ORCID / Максимум упоминаний: {self.stats['max_mentions_per_orcid']}")

        print("\n" + "=" * 80)


def main():
    """主函数 / Главная функция"""
    parser = argparse.ArgumentParser(
        description='构建ORCID金标准数据集 / Построение золотого стандарта ORCID'
    )
    parser.add_argument(
        '--crossref-file',
        type=str,
        required=True,
        help='Crossref数据文件路径 / Путь к файлу данных Crossref'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='evaluation/gold_sets/orcid_gold_set.json',
        help='输出金标准文件路径 / Путь к выходному файлу'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='限制加载文章数 (用于测试) / Лимит статей для загрузки'
    )
    parser.add_argument(
        '--min-mentions',
        type=int,
        default=2,
        help='最小mention数（过滤单个mention的ORCID）'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='启用debug日志 / Включить отладочные логи'
    )

    args = parser.parse_args()

    # 配置 / Конфигурация
    config = {
        'crossref_file': args.crossref_file,
        'output_file': args.output,
        'limit': args.limit,
        'min_mentions': args.min_mentions,
        'debug': args.debug
    }

    # 构建金标准 / Построение золотого стандарта
    builder = ORCIDGoldSetBuilder(config)
    builder.load_crossref_data(args.crossref_file, limit=args.limit)
    gold_set = builder.build_gold_set(min_mentions=args.min_mentions)
    builder.save_gold_set(gold_set, args.output)
    builder.print_statistics()

    print(f"\n✓ 金标准构建完成 / Золотой стандарт построен")
    print(f"✓ 输出文件 / Файл вывода: {args.output}")


if __name__ == '__main__':
    main()
