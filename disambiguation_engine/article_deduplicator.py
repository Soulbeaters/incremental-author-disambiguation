# -*- coding: utf-8 -*-
"""
文章去重器 / Дедупликатор статей / Article Deduplicator

防止添加重复文章到数据库，基于DOI和标题相似度
Предотвращение добавления дубликатов статей на основе DOI и сходства заголовков
Prevent duplicate article additions based on DOI and title similarity

中文注释：文章去重模块，确保数据库中文章的唯一性
Русский комментарий: Модуль дедупликации статей, обеспечение уникальности в базе
"""

import re
import logging
from typing import Dict, Optional, Tuple, Any
try:
    from Levenshtein import ratio
except ImportError:
    # 如果没有Levenshtein库，使用简单的相似度计算
    # Если библиотека Levenshtein отсутствует, используем простое вычисление
    def ratio(s1: str, s2: str) -> float:
        """简单的字符串相似度计算 / Простое вычисление сходства строк"""
        if s1 == s2:
            return 1.0
        if not s1 or not s2:
            return 0.0
        # 基于集合交集的简单相似度
        # Простое сходство на основе пересечения множеств
        set1 = set(s1.lower().split())
        set2 = set(s2.lower().split())
        if not set1 or not set2:
            return 0.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0


class ArticleDeduplicator:
    """
    文章去重器 / Дедупликатор статей

    通过DOI和标题相似度检测重复文章
    Обнаружение дубликатов статей по DOI и сходству заголовков
    Detect duplicate articles via DOI and title similarity
    """

    def __init__(self, title_similarity_threshold: float = 0.95):
        """
        初始化去重器 / Инициализация дедупликатора

        参数 / Параметры / Parameters:
            title_similarity_threshold: 标题相似度阈值（0-1）
                                       Порог сходства заголовков (0-1)
                                       Title similarity threshold (0-1)
        """
        self.title_threshold = title_similarity_threshold

        # DOI索引：doi -> article对象
        # Индекс DOI: doi -> объект статьи
        self.doi_index: Dict[str, Any] = {}

        # 标题索引：normalized_title -> article对象
        # Индекс заголовков: нормализованный_заголовок -> объект статьи
        self.title_index: Dict[str, Any] = {}

        self.logger = logging.getLogger(__name__)

    def check_duplicate(self, article: Dict[str, Any]) -> Tuple[bool, Optional[Any]]:
        """
        检查文章是否为重复 / Проверка дубликата статьи

        检查策略 / Стратегия проверки:
        1. 优先检查DOI（最可靠）/ Приоритет DOI (наиболее надежный)
        2. 如无DOI，检查标题相似度 / Если нет DOI, проверка сходства заголовка

        参数 / Параметры / Parameters:
            article: 文章数据（字典或对象）/ Данные статьи (словарь или объект)

        返回 / Возвращает / Returns:
            (is_duplicate, existing_article) 元组
            Кортеж (является_дубликатом, существующая_статья)
            Tuple (is_duplicate, existing_article)
        """
        # 提取文章的DOI和标题
        # Извлечение DOI и заголовка статьи
        doi = self._extract_doi(article)
        title = self._extract_title(article)

        # 1. 优先检查DOI（最可靠的去重方式）
        # 1. Приоритетная проверка DOI (наиболее надежный способ)
        if doi and doi in self.doi_index:
            existing = self.doi_index[doi]
            self.logger.debug(f"Duplicate found by DOI: {doi}")
            return True, existing

        # 2. 如果没有DOI，检查标题相似度
        # 2. Если нет DOI, проверка сходства заголовка
        if title:
            normalized_title = self._normalize_title(title)

            # 精确匹配 / Точное совпадение / Exact match
            if normalized_title in self.title_index:
                existing = self.title_index[normalized_title]
                self.logger.debug(f"Duplicate found by exact title match")
                return True, existing

            # 模糊匹配（计算所有已存在标题的相似度）
            # Нечеткое совпадение (вычисление сходства со всеми заголовками)
            for existing_title, existing_article in self.title_index.items():
                similarity = ratio(normalized_title, existing_title)

                if similarity >= self.title_threshold:
                    self.logger.debug(
                        f"Duplicate found by title similarity: {similarity:.2f} "
                        f"(threshold: {self.title_threshold})"
                    )
                    return True, existing_article

        # 未发现重复 / Дубликат не обнаружен / No duplicate found
        return False, None

    def add_article(self, article: Dict[str, Any]) -> None:
        """
        将文章添加到去重索引 / Добавление статьи в индекс дедупликации

        参数 / Параметры / Parameters:
            article: 文章数据 / Данные статьи / Article data
        """
        doi = self._extract_doi(article)
        title = self._extract_title(article)

        # 添加到DOI索引 / Добавление в индекс DOI
        if doi:
            self.doi_index[doi] = article
            self.logger.debug(f"Added to DOI index: {doi}")

        # 添加到标题索引 / Добавление в индекс заголовков
        if title:
            normalized_title = self._normalize_title(title)
            self.title_index[normalized_title] = article
            self.logger.debug(f"Added to title index: {normalized_title[:50]}...")

    def remove_article(self, article: Dict[str, Any]) -> None:
        """
        从去重索引中移除文章 / Удаление статьи из индекса

        参数 / Параметры / Parameters:
            article: 文章数据 / Данные статьи / Article data
        """
        doi = self._extract_doi(article)
        title = self._extract_title(article)

        # 从DOI索引移除 / Удаление из индекса DOI
        if doi and doi in self.doi_index:
            del self.doi_index[doi]
            self.logger.debug(f"Removed from DOI index: {doi}")

        # 从标题索引移除 / Удаление из индекса заголовков
        if title:
            normalized_title = self._normalize_title(title)
            if normalized_title in self.title_index:
                del self.title_index[normalized_title]
                self.logger.debug(f"Removed from title index")

    def get_statistics(self) -> Dict[str, int]:
        """
        获取去重器统计信息 / Получение статистики дедупликатора

        返回 / Возвращает / Returns:
            统计信息字典 / Словарь статистики / Statistics dictionary
        """
        # 使用文章的id()来去重，因为文章对象不可哈希
        # Использование id() для дедупликации, так как объекты статей не хешируемы
        unique_articles = set()
        for article in self.doi_index.values():
            unique_articles.add(id(article))
        for article in self.title_index.values():
            unique_articles.add(id(article))

        return {
            'indexed_by_doi': len(self.doi_index),
            'indexed_by_title': len(self.title_index),
            'total_articles': len(unique_articles)
        }

    def _extract_doi(self, article: Dict[str, Any]) -> str:
        """
        从文章数据中提取DOI / Извлечение DOI из данных статьи

        参数 / Параметры / Parameters:
            article: 文章数据 / Данные статьи

        返回 / Возвращает / Returns:
            DOI字符串或空字符串 / Строка DOI или пустая строка
        """
        # 支持字典和对象两种形式
        # Поддержка форматов словаря и объекта
        if isinstance(article, dict):
            doi = article.get('doi', '') or article.get('DOI', '')
        else:
            doi = getattr(article, 'doi', '')

        # 清理DOI（移除URL前缀）
        # Очистка DOI (удаление URL префикса)
        if doi:
            doi = doi.replace('https://doi.org/', '')
            doi = doi.replace('http://dx.doi.org/', '')
            doi = doi.strip()

        return doi

    def _extract_title(self, article: Dict[str, Any]) -> str:
        """
        从文章数据中提取标题 / Извлечение заголовка из данных статьи

        参数 / Параметры / Parameters:
            article: 文章数据 / Данные статьи

        返回 / Возвращает / Returns:
            标题字符串或空字符串 / Строка заголовка или пустая строка
        """
        # 支持字典和对象两种形式
        # Поддержка форматов словаря и объекта
        if isinstance(article, dict):
            title = article.get('title', '')
        else:
            title = getattr(article, 'title', '')

        return title.strip() if title else ''

    def _normalize_title(self, title: str) -> str:
        """
        标准化标题用于比较 / Нормализация заголовка для сравнения

        标准化步骤 / Шаги нормализации:
        1. 转换为小写 / Перевод в нижний регистр
        2. 移除标点符号 / Удаление пунктуации
        3. 移除多余空格 / Удаление лишних пробелов
        4. 移除常见词（a, an, the等）/ Удаление стоп-слов

        参数 / Параметры / Parameters:
            title: 原始标题 / Исходный заголовок

        返回 / Возвращает / Returns:
            标准化后的标题 / Нормализованный заголовок
        """
        # 1. 转小写 / Перевод в нижний регистр
        title = title.lower()

        # 2. 移除标点符号 / Удаление пунктуации
        title = re.sub(r'[^\w\s]', '', title)

        # 3. 移除多余空格 / Удаление лишних пробелов
        title = ' '.join(title.split())

        # 4. 移除常见冠词和介词（英语）
        # Удаление артиклей и предлогов (английский)
        stop_words = {'a', 'an', 'the', 'of', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 'from'}
        words = title.split()
        words = [w for w in words if w not in stop_words]
        title = ' '.join(words)

        return title


# 测试代码 / Тестовый код / Test Code
if __name__ == '__main__':
    # 配置日志 / Настройка логирования
    logging.basicConfig(level=logging.DEBUG)

    print("=" * 80)
    print("文章去重器测试 / Тест дедупликатора статей")
    print("=" * 80)

    # 创建去重器 / Создание дедупликатора
    deduplicator = ArticleDeduplicator(title_similarity_threshold=0.95)

    # 测试文章数据 / Тестовые данные статей
    article1 = {
        'doi': '10.1038/nature12373',
        'title': 'The Genome of the Sea Urchin'
    }

    article2 = {
        'doi': '10.1038/nature12373',  # 相同DOI / Тот же DOI
        'title': 'Different Title'
    }

    article3 = {
        'doi': '10.1126/science.123456',
        'title': 'The Genome of the Sea Urchin'  # 相同标题 / Тот же заголовок
    }

    article4 = {
        'doi': '10.1016/j.cell.789',
        'title': 'The genome of sea urchin'  # 非常相似的标题 / Очень похожий заголовок
    }

    article5 = {
        'doi': '10.1093/nar/gkz999',
        'title': 'Completely Different Research Topic'
    }

    # 测试1：添加第一篇文章
    # Тест 1: Добавление первой статьи
    print("\n[Test 1] 添加第一篇文章 / Добавление первой статьи")
    is_dup, existing = deduplicator.check_duplicate(article1)
    print(f"  是否重复 / Дубликат: {is_dup}")
    if not is_dup:
        deduplicator.add_article(article1)
        print("  ✓ 文章已添加 / Статья добавлена")

    # 测试2：相同DOI检测
    # Тест 2: Обнаружение по DOI
    print("\n[Test 2] 相同DOI检测 / Обнаружение по DOI")
    is_dup, existing = deduplicator.check_duplicate(article2)
    print(f"  是否重复 / Дубликат: {is_dup} (期望 / ожидается: True)")

    # 测试3：相同标题检测
    # Тест 3: Обнаружение по заголовку
    print("\n[Test 3] 相同标题检测 / Обнаружение по заголовку")
    is_dup, existing = deduplicator.check_duplicate(article3)
    print(f"  是否重复 / Дубликат: {is_dup} (期望 / ожидается: True)")

    # 测试4：相似标题检测
    # Тест 4: Обнаружение по сходству
    print("\n[Test 4] 相似标题检测 / Обнаружение по сходству")
    is_dup, existing = deduplicator.check_duplicate(article4)
    print(f"  是否重复 / Дубликат: {is_dup} (期望 / ожидается: True)")

    # 测试5：不同文章
    # Тест 5: Другая статья
    print("\n[Test 5] 完全不同的文章 / Совершенно другая статья")
    is_dup, existing = deduplicator.check_duplicate(article5)
    print(f"  是否重复 / Дубликат: {is_dup} (期望 / ожидается: False)")

    # 统计信息 / Статистика
    print("\n" + "=" * 80)
    print("统计信息 / Статистика")
    print("=" * 80)
    stats = deduplicator.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")
