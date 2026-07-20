# -*- coding: utf-8 -*-
"""
集成模块 / Модуль интеграций / Integrations Module

外部API集成，包括Crossref等服务
Интеграция с внешними API, включая Crossref и другие сервисы
External API integrations including Crossref and other services
"""

try:
    from .crossref_client import CrossrefClient
except ModuleNotFoundError:
    CrossrefClient = None

from .istina_disambiguation_client import (
    IstinaDisambiguationClient,
    IstinaServiceAuthor,
    IstinaServiceCandidate,
    IstinaServiceDecision,
    istina_author_record_from_export,
    iter_istina_author_records,
)
from .istina_pipeline import (
    IstinaDisambiguationPipeline,
    IstinaHistoryState,
    IstinaPipelineConfig,
    IstinaPipelineDecision,
    article_mentions,
    build_istina_history_state,
)
from .istina_production_runtime import (
    CircuitBreaker,
    CircuitBreakerConfig,
    DecisionDriftMonitor,
    DriftBaseline,
    DriftThresholds,
    IstinaProductionRuntime,
    ReleaseAuthorization,
    RuntimeMode,
)

__all__ = [
    'CrossrefClient',
    'IstinaDisambiguationClient',
    'IstinaServiceAuthor',
    'IstinaServiceCandidate',
    'IstinaServiceDecision',
    'istina_author_record_from_export',
    'iter_istina_author_records',
    'IstinaDisambiguationPipeline',
    'IstinaHistoryState',
    'IstinaPipelineConfig',
    'IstinaPipelineDecision',
    'article_mentions',
    'build_istina_history_state',
    'CircuitBreaker',
    'CircuitBreakerConfig',
    'DecisionDriftMonitor',
    'DriftBaseline',
    'DriftThresholds',
    'IstinaProductionRuntime',
    'ReleaseAuthorization',
    'RuntimeMode',
]
