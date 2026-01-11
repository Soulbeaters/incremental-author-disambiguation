# -*- coding: utf-8 -*-
"""
增量消歧系统配置 / Конфигурация системы инкрементального устранения неоднозначности

集中管理所有系统配置参数，为ИСТИНА集成做准备
Централизованное управление всеми параметрами конфигурации системы, подготовка к интеграции с ИСТИНА
"""

import logging
import os
import json
from pathlib import Path
from typing import Dict, Any, Optional


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

# ============================================================================
# Fellegi-Sunter双阈值三分决策配置 / Конфигурация двойного порога Fellegi-Sunter
# ============================================================================

# 双阈值配置（用于三分决策：MERGE/NEW/UNKNOWN）
# Конфигурация двойного порога (для тройного решения: MERGE/NEW/UNKNOWN)
# Double threshold configuration (for three-way decision: MERGE/NEW/UNKNOWN)
ACCEPT_THRESHOLD = 0.90    # 接受阈值：score >= accept -> MERGE / Порог принятия
REJECT_THRESHOLD = 0.20    # 拒绝阈值：score <= reject -> NEW / Порог отклонения
                           # accept > score > reject -> UNKNOWN (需人工审核 / требует ручной проверки)

# 特征分箱配置 / Конфигурация биннинга признаков / Feature binning configuration
# 用于Fellegi-Sunter方法的离散化比较结果
COMPARISON_BINS = {
    "name": ["exact", "high", "medium", "low", "none"],           # 姓名相似度分箱 / Бины сходства имен
    "orcid": ["match", "missing"],                                # ORCID匹配（二值）/ Совпадение ORCID
    "coauthor": ["high", "medium", "low", "none"],               # 合著者重叠分箱 / Бины пересечения соавторов
    "journal": ["high", "medium", "low", "none"],                # 期刊重叠分箱 / Бины пересечения журналов
    "affiliation": ["exact", "high", "medium", "low", "none"],   # 机构相似度分箱 / Бины сходства аффилиаций
    "chinese_name": ["high", "medium", "low", "unknown"],        # 中文姓名规范化置信度 / Уверенность нормализации китайских имен
}

# Fellegi-Sunter m/u 参数表（初始值）/ Таблица параметров m/u Fellegi-Sunter
# m: 匹配对中该特征取该值的概率 / вероятность для совпадающих пар
# u: 非匹配对中该特征取该值的概率 / вероятность для несовпадающих пар
# log(m/u) = 证据权重（正值支持匹配，负值反对匹配）/ вес доказательства
MU_TABLE = {
    "name": {
        "exact": {"m": 0.95, "u": 0.01},    # 完全匹配强烈支持 / точное совпадение сильно поддерживает
        "high": {"m": 0.80, "u": 0.05},     # 高相似度支持 / высокое сходство поддерживает
        "medium": {"m": 0.40, "u": 0.15},   # 中等相似度弱支持 / среднее сходство слабо поддерживает
        "low": {"m": 0.10, "u": 0.30},      # 低相似度反对 / низкое сходство противоречит
        "none": {"m": 0.01, "u": 0.70},     # 完全不同强烈反对 / полное несходство сильно противоречит
    },
    "orcid": {
        "match": {"m": 0.99, "u": 0.001},   # ORCID匹配几乎确定 / совпадение ORCID почти определенно
        "missing": {"m": 0.50, "u": 0.70},  # ORCID缺失，不提供信息 / отсутствие ORCID, не информативно
    },
    "coauthor": {
        "high": {"m": 0.70, "u": 0.05},     # 高重叠支持 / высокое пересечение поддерживает
        "medium": {"m": 0.40, "u": 0.15},   # 中等重叠弱支持 / среднее пересечение слабо поддерживает
        "low": {"m": 0.20, "u": 0.30},      # 低重叠弱反对 / низкое пересечение слабо противоречит
        "none": {"m": 0.10, "u": 0.60},     # 无重叠反对 / нет пересечения противоречит
    },
    "journal": {
        "high": {"m": 0.65, "u": 0.10},     # 高重叠支持 / высокое пересечение поддерживает
        "medium": {"m": 0.35, "u": 0.20},   # 中等重叠弱支持 / среднее пересечение слабо поддерживает
        "low": {"m": 0.20, "u": 0.35},      # 低重叠弱反对 / низкое пересечение слабо противоречит
        "none": {"m": 0.10, "u": 0.50},     # 无重叠反对 / нет пересечения противоречит
    },
    "affiliation": {
        "exact": {"m": 0.90, "u": 0.02},    # 完全匹配强烈支持 / точное совпадение сильно поддерживает
        "high": {"m": 0.70, "u": 0.08},     # 高相似度支持 / высокое сходство поддерживает
        "medium": {"m": 0.40, "u": 0.20},   # 中等相似度弱支持 / среднее сходство слабо поддерживает
        "low": {"m": 0.15, "u": 0.35},      # 低相似度弱反对 / низкое сходство слабо противоречит
        "none": {"m": 0.05, "u": 0.60},     # 完全不同反对 / полное несходство противоречит
    },
    "chinese_name": {
        "high": {"m": 0.85, "u": 0.10},     # 高置信度中文姓名规范化支持 / высокая уверенность поддерживает
        "medium": {"m": 0.50, "u": 0.25},   # 中等置信度弱支持 / средняя уверенность слабо поддерживает
        "low": {"m": 0.25, "u": 0.40},      # 低置信度弱反对 / низкая уверенность слабо противоречит
        "unknown": {"m": 0.50, "u": 0.50},  # 未知，不提供信息 / неизвестно, не информативно
    },
}

# 中文姓名规范化模块配置 / Конфигурация модуля нормализации китайских имен
# 默认关闭，需显式启用 / По умолчанию выключено, требует явного включения
ENABLE_CHINESE_NAME_NORMALIZATION = os.environ.get('ENABLE_CHINESE_NAME', 'false').lower() == 'true'
CHINESE_NAME_MODULE_PATH = os.environ.get('CHINESE_NAME_MODULE_PATH')  # 从环境变量读取 / из переменной окружения

# Decision trace 脱敏配置 / Конфигурация редакции трейса решений
# 用于生成可审计但保护隐私的决策日志 / для генерации аудируемых, но приватных логов решений
TRACE_REDACTION_SALT = os.environ.get(
    'ISTINA_LOG_SALT',
    'default_salt_change_in_production'    # 生产环境必须从环境变量读取 / в продакшене обязательно из переменной окружения
)

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


def load_mu_table(path: Optional[str] = None) -> Dict[str, Dict[str, Dict[str, float]]]:
    """
    加载Fellegi-Sunter m/u参数表 / Загрузка таблицы параметров m/u Fellegi-Sunter
    Load Fellegi-Sunter m/u parameter table

    如果提供了路径，从JSON文件加载；否则使用内置默认值
    Если указан путь, загружает из JSON; иначе использует встроенные значения
    If path provided, loads from JSON file; otherwise uses built-in defaults

    Args:
        path: JSON文件路径（可选）/ Путь к JSON файлу (опционально)

    Returns:
        Dict: m/u参数表 / Таблица параметров m/u

    Raises:
        FileNotFoundError: 指定的文件不存在 / Файл не найден
        json.JSONDecodeError: JSON格式错误 / Ошибка формата JSON

    Example:
        >>> mu_table = load_mu_table('custom_mu_table.json')
        >>> mu_table = load_mu_table()  # 使用默认值 / использовать значения по умолчанию
    """
    if path is None:
        # 返回内置默认值的深拷贝 / Возврат глубокой копии встроенных значений
        import copy
        return copy.deepcopy(MU_TABLE)

    # 从文件加载 / Загрузка из файла
    path_obj = Path(path)
    if not path_obj.exists():
        raise FileNotFoundError(f"MU table file not found: {path}")

    with open(path_obj, 'r', encoding='utf-8') as f:
        loaded_table = json.load(f)

    # 验证加载的表结构 / Проверка структуры загруженной таблицы
    for feature, bins in loaded_table.items():
        if not isinstance(bins, dict):
            raise ValueError(f"Invalid MU table structure for feature: {feature}")
        for bin_name, params in bins.items():
            if 'm' not in params or 'u' not in params:
                raise ValueError(f"Missing m/u parameters for {feature}.{bin_name}")
            if not (0 <= params['m'] <= 1 and 0 <= params['u'] <= 1):
                raise ValueError(f"m/u must be in [0,1] for {feature}.{bin_name}")

    logging.info(f"Loaded custom MU table from: {path}")
    return loaded_table


# 在模块导入时验证配置 / Проверка конфигурации при импорте модуля
validate_weights()