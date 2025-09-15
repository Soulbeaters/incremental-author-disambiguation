# -*- coding: utf-8 -*-
"""
增量消歧系统配置 / Конфигурация системы инкрементального устранения неоднозначности

集中管理所有系统配置参数，为ИСТИНА集成做准备
Централизованное управление всеми параметрами конфигурации системы, подготовка к интеграции с ИСТИНА
"""

import logging
from typing import Dict, Any


# ============================================================================
# 核心消歧配置 / Основная конфигурация устранения неоднозначности
# ============================================================================

# 相似度计算权重配置 / Конфигурация весов расчёта сходства
# 各维度权重之和必须等于1.0 / Сумма весов всех измерений должна равняться 1.0
SIMILARITY_WEIGHTS = {
    "name": 0.5,           # 姓名相似度权重 / Вес сходства имён
    "coauthors": 0.3,      # 合著者相似度权重 / Вес сходства соавторов
    "journals": 0.2,       # 期刊相似度权重 / Вес сходства журналов
    # 可扩展的其他维度 / Расширяемые другие измерения
    # "research_fields": 0.0,  # 研究领域相似度权重 / Вес сходства областей исследований
    # "affiliations": 0.0,     # 机构相似度权重 / Вес сходства аффилиаций
    # "keywords": 0.0,         # 关键词相似度权重 / Вес сходства ключевых слов
}

# 消歧判断阈值 / Пороговые значения для устранения неоднозначности
SIMILARITY_THRESHOLD = 0.85    # 判断为同一作者的相似度阈值 / Порог сходства для идентификации как одного автора
LOW_SIMILARITY_THRESHOLD = 0.3  # 明显不同作者的相似度阈值 / Порог сходства для явно разных авторов

# 姓名相似度计算参数 / Параметры расчёта сходства имён
NAME_SIMILARITY_CONFIG = {
    "case_sensitive": False,          # 是否区分大小写 / Чувствительность к регистру
    "normalize_spaces": True,         # 是否标准化空格 / Нормализация пробелов
    "remove_punctuation": True,       # 是否移除标点符号 / Удаление знаков препинания
    "levenshtein_threshold": 0.8,     # 莱文斯坦距离阈值 / Порог расстояния Левенштейна
}

# 集合相似度计算参数 / Параметры расчёта сходства множеств
SET_SIMILARITY_CONFIG = {
    "jaccard_threshold": 0.1,         # Jaccard相似度阈值 / Порог сходства Жаккара
    "min_overlap_ratio": 0.2,         # 最小重叠比例 / Минимальное отношение пересечения
}

# ============================================================================
# 性能与资源配置 / Конфигурация производительности и ресурсов
# ============================================================================

# 引擎性能配置 / Конфигурация производительности движка
ENGINE_CONFIG = {
    "max_affected_authors": 100,        # 最大受影响作者数 / Максимальное количество затронутых авторов
    "similarity_calculation_timeout": 30,  # 相似度计算超时(秒) / Таймаут расчёта сходства (сек)
    "dependency_graph_max_depth": 2,    # 依赖图最大搜索深度 / Максимальная глубина поиска графа зависимостей
    "enable_performance_warnings": True,  # 启用性能警告 / Включить предупреждения о производительности
}

# 系统性能配置 / Конфигурация производительности системы
PERFORMANCE_CONFIG = {
    "max_batch_size": 1000,           # 最大批处理大小 / Максимальный размер пакета
    "enable_caching": True,           # 是否启用缓存 / Включение кэширования
    "cache_size_limit": 10000,        # 缓存大小限制 / Лимит размера кэша
}

# 缓存配置 / Конфигурация кэширования
CACHE_CONFIG = {
    "enable_similarity_cache": True,   # 启用相似度缓存 / Включить кэш сходства
    "cache_max_size": 1000,           # 缓存最大条目数 / Максимальное количество записей в кэше
    "cache_ttl_seconds": 3600,        # 缓存生存时间(秒) / Время жизни кэша (сек)
}


# ============================================================================
# 日志配置 / Конфигурация логирования
# ============================================================================

# 日志配置 / Конфигурация логирования
LOGGING_CONFIG = {
    "level": logging.INFO,              # 默认日志级别 / Уровень логирования по умолчанию
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "date_format": "%Y-%m-%d %H:%M:%S",
    "enable_console": True,             # 启用控制台输出 / Включить вывод в консоль
    "enable_file": False,               # 启用文件输出 / Включить вывод в файл
    "file_path": "disambiguation.log",  # 日志文件路径 / Путь к файлу логов
    "max_file_size": 10 * 1024 * 1024,  # 最大文件大小(bytes) / Максимальный размер файла (байты)
    "backup_count": 5,                  # 备份文件数量 / Количество резервных файлов
}


# ============================================================================
# 数据库配置（占位符，为ИСТИНА集成做准备）/ Конфигурация БД (заглушка, подготовка к интеграции с ИСТИНА)
# ============================================================================

# 数据库配置占位符 / Заглушка конфигурации базы данных
DATABASE_CONFIG = {
    "enabled": False,                   # 是否启用数据库 / Включена ли база данных
    "connection_string": "",            # 连接字符串 / Строка подключения
    "connection_pool_size": 10,         # 连接池大小 / Размер пула соединений
    "query_timeout": 30,                # 查询超时(秒) / Таймаут запроса (сек)
    "batch_size": 100,                  # 批处理大小 / Размер пакета
    "enable_transactions": True,        # 启用事务 / Включить транзакции
}

# ИСТИНА系统集成配置 / Конфигурация интеграции системы ИСТИНА
ISTINA_CONFIG = {
    "api_base_url": "",                 # ИСТИНА API基础URL / Базовый URL API ИСТИНА
    "api_timeout": 60,                  # API超时(秒) / Таймаут API (сек)
    "api_retry_count": 3,              # API重试次数 / Количество повторов API
    "data_sync_interval": 3600,        # 数据同步间隔(秒) / Интервал синхронизации данных (сек)
    "enable_real_time_sync": False,    # 启用实时同步 / Включить синхронизацию в реальном времени
}

# ============================================================================
# 配置验证和工具函数 / Функции валидации конфигурации и утилиты
# ============================================================================

def validate_similarity_weights(weights: Dict[str, float]) -> bool:
    """
    验证相似度权重配置 / Валидация конфигурации весов сходства

    Args:
        weights: 权重字典 / Словарь весов

    Returns:
        bool: 是否有效 / Валидна ли конфигурация

    Raises:
        ValueError: 权重配置无效时 / При недействительной конфигурации весов
    """
    if not isinstance(weights, dict):
        raise ValueError("权重必须是字典类型 / Веса должны быть типа dict")

    total = sum(weights.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"权重总和必须等于1.0，当前为: {total} / Сумма весов должна равняться 1.0, текущая: {total}")

    for key, value in weights.items():
        if not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"权重值必须是非负数，{key}={value} / Значение веса должно быть неотрицательным, {key}={value}")

    return True


def get_default_config() -> Dict[str, Any]:
    """
    获取默认配置字典 / Получение словаря конфигурации по умолчанию

    Returns:
        Dict[str, Any]: 完整的默认配置 / Полная конфигурация по умолчанию
    """
    return {
        "similarity_threshold": SIMILARITY_THRESHOLD,
        "similarity_weights": SIMILARITY_WEIGHTS.copy(),
        "name_similarity_config": NAME_SIMILARITY_CONFIG.copy(),
        "set_similarity_config": SET_SIMILARITY_CONFIG.copy(),
        "engine_config": ENGINE_CONFIG.copy(),
        "cache_config": CACHE_CONFIG.copy(),
        "logging_config": LOGGING_CONFIG.copy(),
        "database_config": DATABASE_CONFIG.copy(),
        "istina_config": ISTINA_CONFIG.copy(),
    }


def create_engine_config(**overrides) -> Dict[str, Any]:
    """
    创建引擎配置，支持参数覆盖 / Создание конфигурации движка с поддержкой переопределения параметров

    Args:
        **overrides: 要覆盖的配置参数 / Параметры конфигурации для переопределения

    Returns:
        Dict[str, Any]: 配置字典 / Словарь конфигурации

    Example:
        >>> config = create_engine_config(similarity_threshold=0.9, log_level=logging.DEBUG)
    """
    config = get_default_config()

    # 应用覆盖参数 / Применение переопределяющих параметров
    for key, value in overrides.items():
        if key in config:
            if isinstance(config[key], dict) and isinstance(value, dict):
                config[key].update(value)
            else:
                config[key] = value
        else:
            config[key] = value

    # 验证关键配置 / Валидация ключевой конфигурации
    if "similarity_weights" in config:
        validate_similarity_weights(config["similarity_weights"])

    return config


# 验证权重配置的有效性 / Проверка валидности конфигурации весов
def validate_weights() -> bool:
    """
    验证相似度权重配置是否有效 / Проверяет валидность конфигурации весов сходства

    Returns:
        bool: 权重配置是否有效 / Валидна ли конфигурация весов
    """
    return validate_similarity_weights(SIMILARITY_WEIGHTS)


# 在模块导入时验证配置 / Проверка конфигурации при импорте модуля
validate_weights()