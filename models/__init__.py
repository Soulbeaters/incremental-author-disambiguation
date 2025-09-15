# -*- coding: utf-8 -*-
"""
数据模型定义模块 / Модуль определения моделей данных

包含作者和相关实体的数据结构定义
Содержит определения структур данных для авторов и связанных сущностей
"""

from .author import Author, AuthorRecord, Publication, create_author_from_record, create_publication_from_record

__all__ = ['Author', 'AuthorRecord', 'Publication', 'create_author_from_record', 'create_publication_from_record']