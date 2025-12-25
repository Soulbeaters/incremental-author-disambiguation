# -*- coding: utf-8 -*-
"""
作者数据库管理 / Управление базой данных авторов / Author Database Management

内存数据库用于存储和查询作者信息
База данных в памяти для хранения и запросов авторов
In-memory database for storing and querying author information

中文注释：作者数据库，支持快速查找和更新
Русский комментарий: База данных авторов с быстрым поиском и обновлением
"""

import logging
from typing import List, Dict, Optional, Any
from collections import defaultdict
from models.author import Author
from models.publication import Publication


class AuthorDatabase:
    """
    作者数据库 / База данных авторов

    内存数据库，支持按姓氏索引的快速查找
    База данных в памяти с быстрым поиском по фамилии
    In-memory database with fast surname-based lookup
    """

    def __init__(self):
        """
        初始化数据库 / Инициализация базы данных
        """
        # 所有作者列表 / Список всех авторов
        self.authors: List[Author] = []

        # 姓氏索引：surname -> List[Author]
        # Индекс по фамилии: surname -> List[Author]
        self.surname_index: Dict[str, List[Author]] = defaultdict(list)

        # 姓氏+首字母索引：surname_initial -> List[Author]
        # Индекс фамилия+инициал: surname_initial -> List[Author]
        # 例如 "smith_j" -> [Author(...), ...]
        self.surname_initial_index: Dict[str, List[Author]] = defaultdict(list)

        # ORCID索引：orcid -> Author
        # Индекс ORCID: orcid -> Author
        self.orcid_index: Dict[str, Author] = {}

        # 作者ID索引：author_id -> Author
        # Индекс ID автора: author_id -> Author
        self.id_index: Dict[str, Author] = {}

        # 通用blocking键索引：blocking_key -> List[Author]
        # Универсальный индекс ключей блокировки
        # 支持多种键类型（中文姓氏、机构、期刊等）
        self.blocking_key_index: Dict[str, List[Author]] = defaultdict(list)

        self.logger = logging.getLogger(__name__)

    def add_author(self, author_data: Dict[str, Any]) -> Author:
        """
        添加新作者到数据库 / Добавление нового автора в базу

        参数 / Параметры / Parameters:
            author_data: 作者数据字典 / Словарь данных автора

        返回 / Возвращает / Returns:
            创建的Author对象 / Созданный объект Author
        """
        import uuid

        # 创建Author对象 / Создание объекта Author
        # Author构造函数只需要author_id和canonical_name
        author = Author(
            author_id=f"au_{uuid.uuid4().hex[:8]}",
            canonical_name=author_data.get('name', author_data.get('full_name', '')),
            orcid=author_data.get('orcid')
        )

        # 设置其他属性 / Установка других атрибутов
        # 机构信息 / Информация об аффилиации
        affiliations = author_data.get('affiliation', [])
        if isinstance(affiliations, list):
            author.affiliations = set(affiliations)
        elif isinstance(affiliations, str):
            author.affiliations = {affiliations}

        # 合著者信息 / Информация о соавторах
        coauthors = author_data.get('coauthors', [])
        if coauthors:
            author.coauthor_ids = set(coauthors)
            author.collaboration_count = len(author.coauthor_ids)

        # 期刊信息 / Информация о журналах
        journals = author_data.get('journals', [])
        if journals:
            author.journals = set(journals)

        # 添加到主列表 / Добавление в основной список
        self.authors.append(author)

        # 更新姓氏索引 / Обновление индекса по фамилии
        surname = self._extract_surname(author.canonical_name)
        if surname:
            self.surname_index[surname.lower()].append(author)

        # 更新姓氏+首字母索引 / Обновление индекса фамилия+инициал
        surname_initial_key = self._extract_surname_initial(author.canonical_name)
        if surname_initial_key:
            self.surname_initial_index[surname_initial_key].append(author)

        # 更新ORCID索引 / Обновление индекса ORCID
        if author.orcid:
            self.orcid_index[author.orcid] = author

        # 更新ID索引 / Обновление индекса ID
        self.id_index[author.author_id] = author

        # 更新blocking键索引 / Обновление индекса ключей блокировки
        blocking_keys = self._generate_blocking_keys(author)
        for key in blocking_keys:
            self.blocking_key_index[key].append(author)

        self.logger.debug(f"Added author: {author.canonical_name} (ID: {author.author_id})")
        return author

    def search_authors(self, surname: str) -> List[Author]:
        """
        按姓氏搜索作者 / Поиск авторов по фамилии

        参数 / Параметры / Parameters:
            surname: 姓氏 / Фамилия

        返回 / Возвращает / Returns:
            匹配的作者列表 / Список совпадающих авторов
        """
        return self.surname_index.get(surname.lower(), [])

    def find_by_orcid(self, orcid: str) -> Optional[Author]:
        """
        通过ORCID查找作者 / Поиск автора по ORCID

        参数 / Параметры / Parameters:
            orcid: ORCID标识符 / Идентификатор ORCID

        返回 / Возвращает / Returns:
            Author对象或None / Объект Author или None
        """
        return self.orcid_index.get(orcid)

    def find_by_id(self, author_id: str) -> Optional[Author]:
        """
        通过ID查找作者 / Поиск автора по ID

        参数 / Параметры / Parameters:
            author_id: 作者ID / ID автора

        返回 / Возвращает / Returns:
            Author对象或None / Объект Author или None
        """
        return self.id_index.get(author_id)

    def get_author(self, author_id: str) -> Optional[Author]:
        """
        获取作者对象（find_by_id的别名）/ Получить объект автора (псевдоним find_by_id)

        参数 / Параметры / Parameters:
            author_id: 作者ID / ID автора

        返回 / Возвращает / Returns:
            Author对象或None / Объект Author или None
        """
        return self.find_by_id(author_id)

    def update_author(self, author: Author) -> None:
        """
        更新作者信息 / Обновление информации об авторе

        参数 / Параметры / Parameters:
            author: 更新后的Author对象 / Обновленный объект Author
        """
        # 更新索引
        # Обновление индексов
        surname = self._extract_surname(author.canonical_name)
        if surname:
            # 移除旧索引
            # Удаление старого индекса
            old_authors = self.surname_index.get(surname.lower(), [])
            self.surname_index[surname.lower()] = [a for a in old_authors if a.author_id != author.author_id]

            # 添加新索引
            # Добавление нового индекса
            self.surname_index[surname.lower()].append(author)

        # 更新ORCID索引
        # Обновление индекса ORCID
        if author.orcid:
            self.orcid_index[author.orcid] = author

        self.logger.debug(f"Updated author: {author.canonical_name}")

    def remove_author(self, author_id: str) -> bool:
        """
        从数据库移除作者 / Удаление автора из базы

        参数 / Параметры / Parameters:
            author_id: 作者ID / ID автора

        返回 / Возвращает / Returns:
            True如果成功移除 / True если успешно удален
        """
        author = self.id_index.get(author_id)
        if not author:
            return False

        # 从主列表移除
        # Удаление из основного списка
        self.authors = [a for a in self.authors if a.author_id != author_id]

        # 从姓氏索引移除
        # Удаление из индекса по фамилии
        surname = self._extract_surname(author.name)
        if surname:
            self.surname_index[surname.lower()] = [
                a for a in self.surname_index[surname.lower()]
                if a.author_id != author_id
            ]

        # 从ORCID索引移除
        # Удаление из индекса ORCID
        if author.orcid in self.orcid_index:
            del self.orcid_index[author.orcid]

        # 从ID索引移除
        # Удаление из индекса ID
        del self.id_index[author_id]

        self.logger.debug(f"Removed author: {author.canonical_name}")
        return True

    def get_author_count(self) -> int:
        """
        获取数据库中的作者总数 / Получение общего количества авторов

        返回 / Возвращает / Returns:
            作者数量 / Количество авторов
        """
        return len(self.authors)

    def get_all_authors(self) -> List[Author]:
        """
        获取所有作者 / Получение всех авторов

        返回 / Возвращает / Returns:
            所有作者列表 / Список всех авторов
        """
        return self.authors.copy()

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取数据库统计信息 / Получение статистики базы данных

        返回 / Возвращает / Returns:
            统计信息字典 / Словарь статистики
        """
        total_publications = sum(len(author.publications) for author in self.authors)
        authors_with_orcid = sum(1 for author in self.authors if author.orcid)

        return {
            'total_authors': len(self.authors),
            'total_publications': total_publications,
            'authors_with_orcid': authors_with_orcid,
            'unique_surnames': len(self.surname_index),
            'avg_publications_per_author': total_publications / len(self.authors) if self.authors else 0
        }

    def _extract_surname(self, full_name: str) -> str:
        """
        从全名中提取姓氏 / Извлечение фамилии из полного имени

        简单实现：假设姓氏是最后一个词
        Простая реализация: фамилия - последнее слово

        参数 / Параметры / Parameters:
            full_name: 全名 / Полное имя

        返回 / Возвращает / Returns:
            姓氏 / Фамилия
        """
        if not full_name:
            return ''

        parts = full_name.strip().split()
        if not parts:
            return ''

        # 返回最后一个部分作为姓氏
        # Возврат последней части как фамилии
        return parts[-1]

    def _extract_surname_initial(self, full_name: str) -> str:
        """
        提取姓氏+首字母 / Извлечение фамилии+инициал / Extract surname + first initial

        例如 "John Smith" -> "smith_j"
        Например "John Smith" -> "smith_j"

        Args:
            full_name: 全名 / Полное имя / Full name

        Returns:
            str: 姓氏+首字母（小写）/ Фамилия+инициал / surname_initial
        """
        if not full_name:
            return ''

        parts = full_name.strip().split()
        if not parts:
            return ''

        if len(parts) == 1:
            # 只有一个词，可能是单名或姓氏
            # Только одно слово
            return parts[0].lower()

        # 提取姓氏（最后一个词）和名字首字母（第一个词的首字母）
        # Фамилия (последнее слово) + первый инициал (первая буква первого слова)
        surname = parts[-1].lower()
        first_initial = parts[0][0].lower() if parts[0] else ''

        if first_initial:
            return f"{surname}_{first_initial}"
        else:
            return surname

    def _generate_blocking_keys(self, author: Author) -> List[str]:
        """
        生成作者的blocking键 / Генерация ключей блокировки для автора

        生成多种类型的blocking键以支持多策略候选检索
        Генерирует несколько типов ключей для мультистратегического поиска кандидатов

        Args:
            author: 作者对象 / Объект автора

        Returns:
            List[str]: blocking键列表 / Список ключей блокировки
        """
        keys = []

        # 1. ORCID键（最可靠）/ Ключ ORCID (самый надёжный)
        if author.orcid:
            keys.append(f"orcid:{author.orcid}")

        # 2. 姓氏键 / Ключ фамилии
        surname = self._extract_surname(author.canonical_name)
        if surname:
            keys.append(f"surname:{surname.lower()}")

        # 3. 姓氏+首字母键 / Ключ фамилия+инициал
        surname_initial = self._extract_surname_initial(author.canonical_name)
        if surname_initial:
            keys.append(f"surname_init:{surname_initial}")

        # 4. 机构键（如果有）/ Ключи аффилиаций
        for affiliation in list(author.affiliations)[:2]:  # 限制前2个机构 / первые 2
            if affiliation:
                # 简化机构名称 / Упрощение названия
                aff_normalized = affiliation.lower().replace(' ', '_')[:30]
                keys.append(f"affil:{aff_normalized}")

        # 5. 期刊键（如果有）/ Ключи журналов
        for journal in list(author.journals)[:3]:  # 限制前3个期刊 / первые 3
            if journal:
                journal_normalized = journal.lower().replace(' ', '_')[:30]
                keys.append(f"journal:{journal_normalized}")

        # TODO: 6. 中文姓氏键（待一号项目集成）/ Ключи китайских фамилий

        return keys

    def get_candidates(
        self,
        mention: Dict[str, Any],
        max_candidates: int = 100
    ) -> List[Author]:
        """
        获取候选作者（blocking策略）/ Получение кандидатов (стратегия блокировки)

        使用多键blocking策略检索候选作者，避免全库扫描
        Использует мультиключевую блокировку для избежания полного сканирования

        Args:
            mention: 作者mention数据（包含name, orcid, affiliation等）
                    Данные упоминания автора
            max_candidates: 最大候选数量限制 / Максимальное количество кандидатов

        Returns:
            List[Author]: 候选作者列表（去重且稳定排序）
                         Список кандидатов (дедупликация и стабильная сортировка)
        """
        # 使用字典去重（author_id -> Author）/ Используем словарь для дедупликации
        candidates_dict = {}
        blocking_keys_used = []

        # 策略1：ORCID精确匹配（优先级最高）/ Стратегия 1: точное совпадение ORCID
        mention_orcid = mention.get('orcid', '')
        if mention_orcid:
            orcid_key = f"orcid:{mention_orcid}"
            blocking_keys_used.append(orcid_key)
            candidates_from_orcid = self.blocking_key_index.get(orcid_key, [])
            for author in candidates_from_orcid:
                candidates_dict[author.author_id] = author

            # 如果通过ORCID找到了，同时获取同姓候选作为容错
            # Если найдено по ORCID, также получить кандидатов с той же фамилией

        # 策略2：姓氏匹配 / Стратегия 2: совпадение фамилии
        mention_name = mention.get('name', '')
        if mention_name:
            surname = self._extract_surname(mention_name)
            if surname:
                surname_key = f"surname:{surname.lower()}"
                blocking_keys_used.append(surname_key)
                candidates_from_surname = self.blocking_key_index.get(surname_key, [])
                for author in candidates_from_surname:
                    candidates_dict[author.author_id] = author

        # 策略3：姓氏+首字母匹配（更精确）/ Стратегия 3: фамилия+инициал
        if mention_name:
            surname_initial = self._extract_surname_initial(mention_name)
            if surname_initial:
                surname_init_key = f"surname_init:{surname_initial}"
                blocking_keys_used.append(surname_init_key)
                candidates_from_init = self.blocking_key_index.get(surname_init_key, [])
                for author in candidates_from_init:
                    candidates_dict[author.author_id] = author

        # 策略4：机构匹配（弱信号）/ Стратегия 4: совпадение аффилиации
        mention_affiliation = mention.get('affiliation', [])
        if isinstance(mention_affiliation, str):
            mention_affiliation = [mention_affiliation]
        for affiliation in mention_affiliation[:1]:  # 只用第一个机构 / только первая
            if affiliation:
                aff_normalized = affiliation.lower().replace(' ', '_')[:30]
                aff_key = f"affil:{aff_normalized}"
                candidates_from_aff = self.blocking_key_index.get(aff_key, [])
                for author in candidates_from_aff[:20]:  # 限制机构候选数 / лимит
                    candidates_dict[author.author_id] = author

        # 转换为列表并按author_id排序（确保确定性）/ Преобразование в список
        candidates_list = list(candidates_dict.values())
        candidates_list.sort(key=lambda a: a.author_id)  # 稳定排序 / стабильная сортировка

        # 限制候选数量 / Ограничение количества
        if len(candidates_list) > max_candidates:
            self.logger.warning(
                f"Candidate set size ({len(candidates_list)}) exceeds max_candidates "
                f"({max_candidates}), truncating"
            )
            candidates_list = candidates_list[:max_candidates]

        self.logger.debug(
            f"Retrieved {len(candidates_list)} candidates using keys: {blocking_keys_used}"
        )

        return candidates_list

    def clear(self) -> None:
        """
        清空数据库 / Очистка базы данных
        """
        self.authors.clear()
        self.surname_index.clear()
        self.surname_initial_index.clear()
        self.orcid_index.clear()
        self.id_index.clear()
        self.blocking_key_index.clear()
        self.logger.info("Database cleared")


# 测试代码 / Тестовый код / Test Code
if __name__ == '__main__':
    # 配置日志 / Настройка логирования
    logging.basicConfig(level=logging.DEBUG)

    print("=" * 80)
    print("作者数据库测试 / Тест базы данных авторов")
    print("=" * 80)

    # 创建数据库 / Создание базы данных
    db = AuthorDatabase()

    # 添加测试作者 / Добавление тестовых авторов
    author1_data = {
        'name': 'Zhang Wei',
        'orcid': '0000-0001-2345-6789',
        'affiliation': ['Tsinghua University'],
        'coauthors': ['Li Ming', 'Wang Qiang'],
        'journals': ['Nature', 'Science']
    }

    author2_data = {
        'name': 'Zhang Li',
        'orcid': '0000-0002-3456-7890',
        'affiliation': ['Peking University'],
        'coauthors': ['Chen Jing'],
        'journals': ['Cell']
    }

    author3_data = {
        'name': 'John Smith',
        'affiliation': ['MIT'],
        'coauthors': ['Jane Doe'],
        'journals': ['Nature']
    }

    # 添加作者 / Добавление авторов
    print("\n[Test 1] 添加作者 / Добавление авторов")
    a1 = db.add_author(author1_data)
    a2 = db.add_author(author2_data)
    a3 = db.add_author(author3_data)
    print(f"  添加了 / Добавлено: {db.get_author_count()} 位作者")

    # 按姓氏搜索 / Поиск по фамилии
    print("\n[Test 2] 按姓氏搜索 / Поиск по фамилии")
    zhang_authors = db.search_authors('Zhang')
    print(f"  姓 'Zhang' 的作者数 / Авторы с фамилией 'Zhang': {len(zhang_authors)}")
    for author in zhang_authors:
        print(f"    - {author.canonical_name}")

    # ORCID查找 / Поиск по ORCID
    print("\n[Test 3] ORCID查找 / Поиск по ORCID")
    author = db.find_by_orcid('0000-0001-2345-6789')
    if author:
        print(f"  找到作者 / Найден автор: {author.canonical_name}")

    # 统计信息 / Статистика
    print("\n[Test 4] 统计信息 / Статистика")
    stats = db.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")
