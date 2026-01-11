# -*- coding: utf-8 -*-
"""
Crossref API客户端 / Клиент Crossref API / Crossref API Client

通过DOI获取学术文章元数据
Получение метаданных научных статей по DOI
Retrieve academic article metadata via DOI

中文注释：Crossref API集成，用于获取文章和作者信息
Русский комментарий: Интеграция Crossref API для получения информации о статьях и авторах
"""

import os
import logging
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from crossref.restful import Works, Etiquette


class CrossrefClient:
    """
    Crossref API客户端 / Клиент Crossref API

    用于通过DOI获取文章元数据，支持批量查询
    Получение метаданных статьи по DOI с поддержкой пакетных запросов
    Fetch article metadata by DOI with batch query support
    """

    def __init__(self, email: Optional[str] = None):
        """
        初始化Crossref客户端 / Инициализация клиента Crossref

        参数 / Параметры / Parameters:
            email: 联系邮箱（如不提供，从环境变量CROSSREF_EMAIL读取）
                   Email контакт (если не указан, читается из CROSSREF_EMAIL)
                   Contact email (if not provided, reads from CROSSREF_EMAIL)
        
        Raises:
            ValueError: 如果没有提供email / если email не указан
        """
        # 从参数或环境变量获取email
        self.email = email or os.environ.get('CROSSREF_EMAIL')
        if not self.email:
            raise ValueError(
                "CROSSREF_EMAIL is required. "
                "Set via 'email' parameter or CROSSREF_EMAIL environment variable. "
                "See .env.example for configuration."
            )
        
        # 设置礼仪信息以提高API请求优先级
        # Установка этикета для повышения приоритета запросов API
        self.etiquette = Etiquette(
            application_name='ISTINA-Author-Disambiguation',
            application_version='2.0',
            application_url='https://github.com/Soulbeaters/incremental-author-disambiguation',
            contact_email=self.email
        )

        self.works = Works(etiquette=self.etiquette)
        self.logger = logging.getLogger(__name__)
        
        # P1-2: 重试配置 / Retry configuration
        self.max_retries = 3
        self.base_delay = 0.5  # 初始延迟（秒）/ Initial delay (seconds)

    def get_work_by_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        """
        通过DOI获取单篇文章信息（带重试）/ Получение информации о статье по DOI (с повтором)

        参数 / Параметры / Parameters:
            doi: 数字对象标识符 / Цифровой идентификатор объекта / Digital Object Identifier

        返回 / Возвращает / Returns:
            文章元数据字典或None（如果失败）
            Словарь метаданных статьи или None (при ошибке)
            Article metadata dictionary or None (on failure)
        """
        import time
        
        # 清理DOI格式（移除可能的URL前缀）
        # Очистка формата DOI (удаление возможного URL префикса)
        clean_doi = doi.replace('https://doi.org/', '').replace('http://dx.doi.org/', '').strip()
        
        # P1-2: 带指数退避的重试逻辑 / Retry with exponential backoff
        for attempt in range(self.max_retries):
            try:
                # 查询Crossref API
                # Запрос к Crossref API
                work = self.works.doi(clean_doi)

                if work:
                    return self._parse_work(work)
                else:
                    self.logger.warning(f"DOI not found: {clean_doi}")
                    return None

            except Exception as e:
                error_str = str(e).lower()
                # 检查是否是可重试的错误（429, 503, 504）
                # Проверка, является ли ошибка повторяемой (429, 503, 504)
                is_retryable = any(code in error_str for code in ['429', '503', '504', 'rate limit', 'temporarily'])
                
                if is_retryable and attempt < self.max_retries - 1:
                    delay = self.base_delay * (2 ** attempt)  # 指数退避 / Exponential backoff
                    self.logger.warning(f"Retryable error for {clean_doi}: {e}. Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    self.logger.error(f"Error fetching DOI {doi}: {e}")
            return None

    def _parse_work(self, work: Dict) -> Dict[str, Any]:
        """
        解析Crossref返回的原始数据为标准格式
        Парсинг исходных данных Crossref в стандартный формат
        Parse raw Crossref data into standardized format

        参数 / Параметры / Parameters:
            work: Crossref原始数据 / Исходные данные Crossref / Raw Crossref data

        返回 / Возвращает / Returns:
            标准化的文章数据 / Нормализованные данные статьи / Standardized article data
        """
        parsed = {
            'doi': work.get('DOI', ''),
            'title': '',
            'authors': [],
            'journal': '',
            'year': None,
            'type': work.get('type', ''),
            'publisher': work.get('publisher', ''),
            'abstract': work.get('abstract', ''),
            'subject': work.get('subject', []),
            'references_count': work.get('references-count', 0),
            'is_referenced_by_count': work.get('is-referenced-by-count', 0)
        }

        # 解析标题 / Парсинг заголовка / Parse title
        if 'title' in work and work['title']:
            parsed['title'] = work['title'][0] if isinstance(work['title'], list) else work['title']

        # 解析期刊名 / Парсинг названия журнала / Parse journal name
        if 'container-title' in work and work['container-title']:
            parsed['journal'] = work['container-title'][0] if isinstance(work['container-title'], list) else work['container-title']

        # 解析作者列表 / Парсинг списка авторов / Parse author list
        if 'author' in work:
            for author in work['author']:
                parsed_author = {
                    'given_name': author.get('given', ''),
                    'family_name': author.get('family', ''),
                    'full_name': self._construct_full_name(author),
                    'orcid': self._extract_orcid(author.get('ORCID', '')),
                    'affiliation': [aff.get('name', '') for aff in author.get('affiliation', [])]
                }
                parsed['authors'].append(parsed_author)

        # 解析发表年份 / Парсинг года публикации / Parse publication year
        year = None
        if 'published-print' in work and 'date-parts' in work['published-print']:
            year = work['published-print']['date-parts'][0][0]
        elif 'published-online' in work and 'date-parts' in work['published-online']:
            year = work['published-online']['date-parts'][0][0]
        elif 'issued' in work and 'date-parts' in work['issued']:
            year = work['issued']['date-parts'][0][0]

        parsed['year'] = year

        return parsed

    def _construct_full_name(self, author: Dict) -> str:
        """
        构建作者全名 / Построение полного имени автора / Construct author full name

        参数 / Параметры / Parameters:
            author: 作者原始数据 / Исходные данные автора / Raw author data

        返回 / Возвращает / Returns:
            作者全名 / Полное имя автора / Author full name
        """
        given = author.get('given', '').strip()
        family = author.get('family', '').strip()

        if given and family:
            return f"{given} {family}"
        elif family:
            return family
        elif given:
            return given
        else:
            return "Unknown Author"

    def _extract_orcid(self, orcid_url: str) -> str:
        """
        从ORCID URL提取纯ORCID标识符
        Извлечение чистого идентификатора ORCID из URL
        Extract clean ORCID identifier from URL

        参数 / Параметры / Parameters:
            orcid_url: ORCID URL或标识符 / ORCID URL или идентификатор

        返回 / Возвращает / Returns:
            纯ORCID标识符 / Чистый идентификатор ORCID
        """
        if not orcid_url:
            return ''

        # 移除URL前缀，仅保留ORCID号
        # Удаление URL префикса, сохранение только номера ORCID
        orcid = orcid_url.replace('http://orcid.org/', '')
        orcid = orcid.replace('https://orcid.org/', '')

        return orcid.strip()

    def batch_get_works(self, dois: List[str], max_workers: int = 5) -> List[Dict[str, Any]]:
        """
        批量获取多篇文章信息（并发处理）
        Пакетное получение информации о статьях (параллельная обработка)
        Batch fetch multiple articles (concurrent processing)

        参数 / Параметры / Parameters:
            dois: DOI列表 / Список DOI / List of DOIs
            max_workers: 最大并发线程数 / Максимальное количество потоков

        返回 / Возвращает / Returns:
            文章数据列表 / Список данных статей / List of article data
        """
        results = []
        total = len(dois)

        self.logger.info(f"Starting batch fetch for {total} DOIs with {max_workers} workers")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务 / Отправка всех задач / Submit all tasks
            future_to_doi = {
                executor.submit(self.get_work_by_doi, doi): doi
                for doi in dois
            }

            # 收集结果 / Сбор результатов / Collect results
            completed = 0
            for future in as_completed(future_to_doi):
                doi = future_to_doi[future]
                completed += 1

                try:
                    result = future.result()
                    if result:
                        results.append(result)
                        self.logger.debug(f"[{completed}/{total}] Successfully fetched: {doi}")
                    else:
                        self.logger.warning(f"[{completed}/{total}] Failed to fetch: {doi}")

                except Exception as e:
                    self.logger.error(f"[{completed}/{total}] Error processing DOI {doi}: {e}")

        self.logger.info(f"Batch fetch completed: {len(results)}/{total} successful")
        return results


# 使用示例 / Пример использования / Usage Example
if __name__ == '__main__':
    # 配置日志 / Настройка логирования / Configure logging
    logging.basicConfig(level=logging.INFO)

    # 创建客户端 / Создание клиента / Create client
    client = CrossrefClient()

    # 测试单个DOI查询 / Тест одиночного запроса DOI / Test single DOI query
    print("=" * 80)
    print("测试单个DOI查询 / Тестирование одиночного запроса")
    print("=" * 80)

    test_doi = "10.1038/nature12373"
    work = client.get_work_by_doi(test_doi)

    if work:
        print(f"\nDOI: {work['doi']}")
        print(f"Title: {work['title']}")
        print(f"Journal: {work['journal']}")
        print(f"Year: {work['year']}")
        print(f"Authors: {len(work['authors'])}")
        for i, author in enumerate(work['authors'][:3], 1):
            print(f"  {i}. {author['full_name']} (ORCID: {author['orcid'] or 'N/A'})")

    # 测试批量查询 / Тест пакетного запроса / Test batch query
    print("\n" + "=" * 80)
    print("测试批量DOI查询 / Тестирование пакетного запроса")
    print("=" * 80)

    test_dois = [
        "10.1038/nature12373",
        "10.1126/science.1248506",
        "10.1016/j.cell.2014.05.010"
    ]

    results = client.batch_get_works(test_dois, max_workers=3)
    print(f"\n成功获取 / Успешно получено: {len(results)}/{len(test_dois)} 篇文章")

    for result in results:
        print(f"  - {result['title'][:50]}... ({result['year']})")
