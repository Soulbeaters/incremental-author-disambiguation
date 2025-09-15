# -*- coding: utf-8 -*-
"""
作者姓名消歧引擎模块 / Модуль устранения неоднозначности имён авторов

该模块包含核心的相似度计算和消歧算法
Этот модуль содержит основные алгоритмы расчёта сходства и устранения неоднозначности
"""

from .similarity_scorer import SimilarityScorer
from .dependency_graph import DependencyGraph
from .engine import DisambiguationEngine, DisambiguationResult

__all__ = ['SimilarityScorer', 'DependencyGraph', 'DisambiguationEngine', 'DisambiguationResult']