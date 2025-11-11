# -*- coding: utf-8 -*-
"""
集成模块 / Модуль интеграций / Integrations Module

外部API集成，包括Crossref等服务
Интеграция с внешними API, включая Crossref и другие сервисы
External API integrations including Crossref and other services
"""

from .crossref_client import CrossrefClient

__all__ = ['CrossrefClient']
