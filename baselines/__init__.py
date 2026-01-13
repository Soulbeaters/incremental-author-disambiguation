# -*- coding: utf-8 -*-
"""
Baseline Clustering Methods (ORCID-Blind)
基线聚类方法 / Базовые методы кластеризации

This package provides simple baseline clustering methods for author disambiguation:
- FINI: Surname + First Initial
- AINI: Surname + All Initials
- OldHeuristic: FINI + Affiliation Gate (ORCID-blind, no ORCID features)
"""

from .fini import cluster_by_fini, extract_surname_and_initial, load_mentions_jsonl
from .aini import cluster_by_aini, extract_surname_and_all_initials
from .old_heuristic import cluster_by_old_heuristic_orcid_blind

# Alias for backward compatibility
cluster_by_old_heuristic = cluster_by_old_heuristic_orcid_blind

__all__ = [
    'cluster_by_fini',
    'cluster_by_aini',
    'cluster_by_old_heuristic',
    'cluster_by_old_heuristic_orcid_blind',
    'extract_surname_and_initial',
    'extract_surname_and_all_initials',
    'load_mentions_jsonl'
]
