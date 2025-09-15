# -*- coding: utf-8 -*-
"""
增量消歧系统数据模型 / Модели данных системы инкрементального устранения неоднозначности

定义支持增量计算的作者、出版物和记录数据结构
Определяет структуры данных авторов, публикаций и записей, поддерживающие инкрементальные вычисления
"""

from typing import List, Set, Optional, Dict
from dataclasses import dataclass, field
import uuid
from datetime import datetime


@dataclass
class Publication:
    """
    出版物数据模型 / Модель данных публикации

    表示一篇学术出版物，包含合著者信息用于构建作者关系图
    Представляет академическую публикацию с информацией о соавторах для построения графа отношений авторов

    Attributes:
        pub_id (str): 出版物唯一标识符 / Уникальный идентификатор публикации
        title (str): 出版物标题 / Название публикации
        journal (Optional[str]): 发表期刊 / Журнал публикации
        coauthor_ids (List[str]): 合著者ID列表 / Список ID соавторов
        year (Optional[int]): 发表年份 / Год публикации
        doi (Optional[str]): 数字对象标识符 / Идентификатор цифрового объекта
        created_at (datetime): 记录创建时间 / Время создания записи

    Example:
        >>> pub = Publication(pub_id="pub_123", title="ML in Science", journal="Nature")
        >>> pub.coauthor_ids.append("author_456")
    """

    pub_id: str  # 出版物唯一标识符 / Уникальный идентификатор публикации
    title: str  # 出版物标题 / Название публикации
    journal: Optional[str] = None  # 发表期刊 / Журнал публикации
    coauthor_ids: List[str] = field(default_factory=list)  # 合著者ID列表 / Список ID соавторов
    year: Optional[int] = None  # 发表年份 / Год публикации
    doi: Optional[str] = None  # 数字对象标识符 / Идентификатор цифрового объекта

    # 元数据 / Метаданные
    created_at: datetime = field(default_factory=datetime.now)  # 记录创建时间 / Время создания записи

    def __post_init__(self):
        """
        后初始化处理 / Постинициализация

        如果未提供pub_id，自动生成唯一标识符
        Автоматически генерирует уникальный идентификатор, если pub_id не предоставлен
        """
        if not self.pub_id:
            self.pub_id = f"pub_{uuid.uuid4().hex[:8]}"


@dataclass
class AuthorRecord:
    """
    原始作者记录 / Исходная запись автора

    表示一条待处理的、从外部数据源导入的原始作者记录
    Представляет необработанную запись автора, импортированную из внешнего источника данных

    Attributes:
        record_id (str): 记录唯一标识符 / Уникальный идентификатор записи
        name (str): 作者姓名（原始形式）/ Имя автора (исходная форма)
        coauthors (List[str]): 合著者姓名列表 / Список имён соавторов
        journal (Optional[str]): 发表期刊 / Журнал публикации
        publication_title (Optional[str]): 出版物标题 / Название публикации
        year (Optional[int]): 发表年份 / Год публикации
        affiliation (Optional[str]): 所属机构 / Аффилиация
        processed (bool): 是否已处理 / Обработано ли
        matched_author_id (Optional[str]): 匹配的作者ID / ID сопоставленного автора
        source (Optional[str]): 数据源 / Источник данных
        imported_at (datetime): 导入时间 / Время импорта

    Example:
        >>> record = AuthorRecord(
        ...     record_id="R001",
        ...     name="John Smith",
        ...     coauthors=["Maria Garcia", "David Chen"],
        ...     journal="Nature"
        ... )
    """

    record_id: str  # 记录唯一标识符 / Уникальный идентификатор записи
    name: str  # 作者姓名（原始形式）/ Имя автора (исходная форма)
    coauthors: List[str] = field(default_factory=list)  # 合著者姓名列表 / Список имён соавторов
    journal: Optional[str] = None  # 发表期刊 / Журнал публикации
    publication_title: Optional[str] = None  # 出版物标题 / Название публикации
    year: Optional[int] = None  # 发表年份 / Год публикации
    affiliation: Optional[str] = None  # 所属机构 / Аффилиация

    # 处理状态 / Статус обработки
    processed: bool = False  # 是否已处理 / Обработано ли
    matched_author_id: Optional[str] = None  # 匹配的作者ID / ID сопоставленного автора

    # 元数据 / Метаданные
    source: Optional[str] = None  # 数据源 / Источник данных
    imported_at: datetime = field(default_factory=datetime.now)  # 导入时间 / Время импорта

    def __post_init__(self):
        """后初始化处理 / Постинициализация"""
        if not self.record_id:
            self.record_id = f"rec_{uuid.uuid4().hex[:8]}"


@dataclass
class Author:
    """
    消歧后的作者实体 / Сущность автора после устранения неоднозначности

    表示系统中一个独立的、唯一的作者身份，聚合多个原始记录的信息
    Представляет независимую, уникальную личность автора в системе, агрегирующую информацию из множественных исходных записей

    Attributes:
        author_id (str): 作者唯一标识符 / Уникальный идентификатор автора
        canonical_name (str): 规范化姓名 / Каноническое имя
        publications (Set[str]): 出版物ID集合 / Множество ID публикаций
        linked_records (Set[str]): 关联的原始记录ID集合 / Множество ID связанных исходных записей
        alternate_names (Set[str]): 备选姓名集合 / Множество альтернативных имён
        coauthor_ids (Set[str]): 合著者ID集合 / Множество ID соавторов
        journals (Set[str]): 发表期刊集合 / Множество журналов публикаций
        affiliations (Set[str]): 机构集合 / Множество аффилиаций
        publication_count (int): 出版物数量 / Количество публикаций
        collaboration_count (int): 合作关系数量 / Количество сотрудничеств
        confidence_score (float): 消歧置信度 [0.0-1.0] / Уверенность в устранении неоднозначности [0.0-1.0]
        last_updated (datetime): 最后更新时间 / Время последнего обновления

    Example:
        >>> author = Author(author_id="au_123", canonical_name="John Smith")
        >>> author.add_linked_record("R001")
        >>> author.merge_with_record(record)
    """

    author_id: str  # 作者唯一标识符 / Уникальный идентификатор автора
    canonical_name: str  # 规范化姓名 / Каноническое имя
    publications: Set[str] = field(default_factory=set)  # 出版物ID集合 / Множество ID публикаций
    linked_records: Set[str] = field(default_factory=set)  # 关联的原始记录ID集合 / Множество ID связанных исходных записей

    # 合并的属性信息（从关联记录中聚合）/ Агрегированная информация атрибутов (из связанных записей)
    alternate_names: Set[str] = field(default_factory=set)  # 备选姓名集合 / Множество альтернативных имён
    coauthor_ids: Set[str] = field(default_factory=set)  # 合著者ID集合 / Множество ID соавторов
    journals: Set[str] = field(default_factory=set)  # 发表期刊集合 / Множество журналов публикаций
    affiliations: Set[str] = field(default_factory=set)  # 机构集合 / Множество аффилиаций

    # 统计信息 / Статистическая информация
    publication_count: int = 0  # 出版物数量 / Количество публикаций
    collaboration_count: int = 0  # 合作关系数量 / Количество сотрудничеств

    # 质量评分 / Оценка качества
    confidence_score: float = 1.0  # 消歧置信度 / Уверенность в устранении неоднозначности
    last_updated: datetime = field(default_factory=datetime.now)  # 最后更新时间 / Время последнего обновления

    def __post_init__(self):
        """后初始化处理 / Постинициализация"""
        if not self.author_id:
            self.author_id = f"au_{uuid.uuid4().hex[:8]}"

        # 将规范姓名添加到备选姓名中 / Добавление канонического имени к альтернативным
        if self.canonical_name:
            self.alternate_names.add(self.canonical_name)

    def add_publication(self, publication_id: str) -> None:
        """
        添加出版物 / Добавить публикацию

        Args:
            publication_id: 出版物ID / ID публикации
        """
        self.publications.add(publication_id)
        self.publication_count = len(self.publications)
        self.last_updated = datetime.now()

    def add_linked_record(self, record_id: str) -> None:
        """
        添加关联记录 / Добавить связанную запись

        Args:
            record_id: 记录ID / ID записи
        """
        self.linked_records.add(record_id)
        self.last_updated = datetime.now()

    def add_coauthor(self, coauthor_id: str) -> None:
        """
        添加合著者 / Добавить соавтора

        Args:
            coauthor_id: 合著者ID / ID соавтора
        """
        self.coauthor_ids.add(coauthor_id)
        self.collaboration_count = len(self.coauthor_ids)
        self.last_updated = datetime.now()

    def add_journal(self, journal_name: str) -> None:
        """
        添加期刊 / Добавить журнал

        Args:
            journal_name: 期刊名称 / Название журнала
        """
        if journal_name:
            self.journals.add(journal_name)
            self.last_updated = datetime.now()

    def add_affiliation(self, affiliation: str) -> None:
        """
        添加机构 / Добавить аффилиацию

        Args:
            affiliation: 机构名称 / Название учреждения
        """
        if affiliation:
            self.affiliations.add(affiliation)
            self.last_updated = datetime.now()

    def add_alternate_name(self, name: str) -> None:
        """
        添加备选姓名 / Добавить альтернативное имя

        Args:
            name: 姓名 / Имя
        """
        if name and name.strip():
            self.alternate_names.add(name.strip())
            self.last_updated = datetime.now()

    def merge_with_record(self, record: 'AuthorRecord') -> None:
        """
        与原始记录合并信息 / Слияние информации с исходной записью

        Args:
            record: 原始作者记录 / Исходная запись автора
        """
        # 添加记录ID到关联记录集合 / Добавление ID записи к связанным записям
        self.add_linked_record(record.record_id)

        # 添加备选姓名 / Добавление альтернативного имени
        self.add_alternate_name(record.name)

        # 添加期刊信息 / Добавление информации о журнале
        if record.journal:
            self.add_journal(record.journal)

        # 添加机构信息 / Добавление информации об аффилиации
        if record.affiliation:
            self.add_affiliation(record.affiliation)

        # 更新置信度（简单平均）/ Обновление уверенности (простое усреднение)
        record_count = len(self.linked_records)
        if record_count > 1:
            # 多记录合并时降低置信度 / Снижение уверенности при слиянии множественных записей
            self.confidence_score = min(self.confidence_score, 0.95)

        # 标记记录为已处理 / Отметка записи как обработанной
        record.processed = True
        record.matched_author_id = self.author_id

    def get_similarity_features(self) -> Dict:
        """
        获取用于相似度计算的特征 / Получение признаков для расчёта сходства

        Returns:
            Dict: 特征字典 / Словарь признаков
        """
        return {
            'name': self.canonical_name,
            'alternate_names': self.alternate_names,
            'coauthors': self.coauthor_ids,
            'journals': self.journals,
            'affiliations': self.affiliations,
            'publication_count': self.publication_count,
            'collaboration_count': self.collaboration_count
        }

    def __str__(self) -> str:
        """字符串表示 / Строковое представление"""
        return f"Author(id={self.author_id}, name='{self.canonical_name}', pubs={len(self.publications)}, records={len(self.linked_records)})"

    def __repr__(self) -> str:
        """详细字符串表示 / Подробное строковое представление"""
        return self.__str__()


# 工具函数 / Вспомогательные функции

def create_author_from_record(record: AuthorRecord) -> Author:
    """
    从原始记录创建新的作者实体 / Создание новой сущности автора из исходной записи

    Args:
        record: 原始作者记录 / Исходная запись автора

    Returns:
        Author: 新的作者实体 / Новая сущность автора
    """
    author = Author(
        author_id=f"au_{uuid.uuid4().hex[:8]}",
        canonical_name=record.name.strip() if record.name else "Unknown"
    )

    # 合并记录信息 / Слияние информации записи
    author.merge_with_record(record)

    return author


def create_publication_from_record(record: AuthorRecord, author_id: str) -> Publication:
    """
    从原始记录创建出版物 / Создание публикации из исходной записи

    Args:
        record: 原始作者记录 / Исходная запись автора
        author_id: 主作者ID / ID основного автора

    Returns:
        Publication: 出版物实体 / Сущность публикации
    """
    pub = Publication(
        pub_id=f"pub_{uuid.uuid4().hex[:8]}",
        title=record.publication_title or f"Publication from {record.record_id}",
        journal=record.journal,
        year=record.year,
        coauthor_ids=[author_id]  # 主作者 / Основной автор
    )

    return pub