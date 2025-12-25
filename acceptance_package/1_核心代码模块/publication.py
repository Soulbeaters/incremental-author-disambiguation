# -*- coding: utf-8 -*-
"""
出版物数据模型 / Модель данных публикации / Publication Data Model

定义学术出版物的数据结构
Определение структуры данных научных публикаций
Define academic publication data structure

中文注释：出版物模型，包含DOI、标题、作者等信息
Русский комментарий: Модель публикации с DOI, заголовком, авторами и т.д.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid


@dataclass
class Publication:
    """
    出版物数据模型 / Модель данных публикации

    存储学术文章的完整信息
    Хранение полной информации о научной статье
    Store complete information about academic article
    """

    # 基本信息 / Основная информация / Basic Information
    doi: str
    title: str
    year: Optional[int] = None

    # 出版信息 / Информация о публикации / Publication Information
    journal: str = ""
    publisher: str = ""
    pub_type: str = ""  # article-journal, proceedings-article, etc.

    # 作者信息 / Информация об авторах / Author Information
    authors: List[Dict[str, Any]] = field(default_factory=list)

    # 引用信息 / Информация о цитировании / Citation Information
    references_count: int = 0
    cited_by_count: int = 0

    # 主题分类 / Тематическая классификация / Subject Classification
    subject: List[str] = field(default_factory=list)

    # 摘要 / Аннотация / Abstract
    abstract: str = ""

    # 元数据 / Метаданные / Metadata
    publication_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    added_date: datetime = field(default_factory=datetime.now)
    source: str = "crossref"  # crossref, manual, scopus, etc.

    def __post_init__(self):
        """
        初始化后处理 / Пост-обработка инициализации
        """
        # 确保DOI格式标准化
        # Обеспечение стандартизации формата DOI
        if self.doi:
            self.doi = self._normalize_doi(self.doi)

    def _normalize_doi(self, doi: str) -> str:
        """
        标准化DOI格式 / Нормализация формата DOI

        移除URL前缀，保留纯DOI
        Удаление URL префикса, сохранение чистого DOI
        """
        doi = doi.replace('https://doi.org/', '')
        doi = doi.replace('http://dx.doi.org/', '')
        return doi.strip()

    def get_author_names(self) -> List[str]:
        """
        获取所有作者姓名列表 / Получение списка имен авторов

        返回 / Возвращает / Returns:
            作者姓名列表 / Список имен авторов
        """
        return [author.get('full_name', '') for author in self.authors if author.get('full_name')]

    def get_first_author(self) -> Optional[Dict[str, Any]]:
        """
        获取第一作者 / Получение первого автора

        返回 / Возвращает / Returns:
            第一作者数据或None / Данные первого автора или None
        """
        return self.authors[0] if self.authors else None

    def has_orcid(self) -> bool:
        """
        检查是否有任何作者拥有ORCID / Проверка наличия ORCID у авторов

        返回 / Возвращает / Returns:
            True如果至少一个作者有ORCID / True если хотя бы один автор имеет ORCID
        """
        return any(author.get('orcid') for author in self.authors)

    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典格式 / Преобразование в формат словаря

        返回 / Возвращает / Returns:
            字典格式的出版物数据 / Данные публикации в формате словаря
        """
        return {
            'publication_id': self.publication_id,
            'doi': self.doi,
            'title': self.title,
            'year': self.year,
            'journal': self.journal,
            'publisher': self.publisher,
            'pub_type': self.pub_type,
            'authors': self.authors,
            'references_count': self.references_count,
            'cited_by_count': self.cited_by_count,
            'subject': self.subject,
            'abstract': self.abstract,
            'added_date': self.added_date.isoformat() if self.added_date else None,
            'source': self.source
        }

    @classmethod
    def from_crossref_data(cls, data: Dict[str, Any]) -> 'Publication':
        """
        从Crossref数据创建Publication对象
        Создание объекта Publication из данных Crossref

        参数 / Параметры / Parameters:
            data: Crossref返回的数据 / Данные из Crossref

        返回 / Возвращает / Returns:
            Publication对象 / Объект Publication
        """
        return cls(
            doi=data.get('doi', ''),
            title=data.get('title', ''),
            year=data.get('year'),
            journal=data.get('journal', ''),
            publisher=data.get('publisher', ''),
            pub_type=data.get('type', ''),
            authors=data.get('authors', []),
            references_count=data.get('references_count', 0),
            cited_by_count=data.get('is_referenced_by_count', 0),
            subject=data.get('subject', []),
            abstract=data.get('abstract', ''),
            source='crossref'
        )

    def __repr__(self) -> str:
        """字符串表示 / Строковое представление"""
        author_count = len(self.authors)
        return f"Publication(doi='{self.doi}', title='{self.title[:50]}...', authors={author_count})"

    def __eq__(self, other) -> bool:
        """
        相等性比较（基于DOI）/ Сравнение на равенство (по DOI)
        """
        if not isinstance(other, Publication):
            return False
        return self.doi == other.doi if self.doi and other.doi else False

    def __hash__(self) -> int:
        """
        哈希值（基于DOI）/ Хэш-значение (по DOI)
        """
        return hash(self.doi) if self.doi else hash(self.publication_id)
