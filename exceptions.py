# -*- coding: utf-8 -*-
"""
增量消歧系统异常定义 / Определения исключений системы инкрементального устранения неоднозначности

定义系统专用的异常类，提供更精确的错误处理和调试信息
Определяет специализированные классы исключений для более точной обработки ошибок и отладки
"""


class DisambiguationError(Exception):
    """
    消歧系统基础异常 / Базовое исключение системы устранения неоднозначности

    所有消歧相关异常的基类
    Базовый класс для всех исключений, связанных с устранением неоднозначности
    """
    pass


class InvalidRecordError(DisambiguationError):
    """
    无效记录异常 / Исключение недействительной записи

    当输入的AuthorRecord格式不正确或缺少必要字段时抛出
    Выбрасывается, когда входная AuthorRecord имеет неправильный формат или отсутствуют необходимые поля

    Attributes:
        record_id (str): 问题记录的ID / ID проблемной записи
        message (str): 错误详情 / Детали ошибки
    """

    def __init__(self, record_id: str, message: str):
        self.record_id = record_id
        self.message = message
        super().__init__(f"记录 {record_id} 无效: {message} / Запись {record_id} недействительна: {message}")


class SimilarityCalculationError(DisambiguationError):
    """
    相似度计算异常 / Исключение расчёта сходства

    在相似度计算过程中发生错误时抛出
    Выбрасывается при ошибках в процессе расчёта сходства

    Attributes:
        author_id_a (str): 第一个作者ID / ID первого автора
        author_id_b (str): 第二个作者ID / ID второго автора
        stage (str): 错误发生的阶段 / Стадия, на которой произошла ошибка
    """

    def __init__(self, author_id_a: str, author_id_b: str, stage: str, message: str):
        self.author_id_a = author_id_a
        self.author_id_b = author_id_b
        self.stage = stage
        self.message = message
        super().__init__(f"相似度计算错误 ({stage}): {author_id_a} vs {author_id_b} - {message}")


class GraphUpdateError(DisambiguationError):
    """
    依赖图更新异常 / Исключение обновления графа зависимостей

    在更新作者依赖图时发生错误时抛出
    Выбрасывается при ошибках обновления графа зависимостей авторов

    Attributes:
        operation (str): 失败的操作类型 / Тип неудавшейся операции
        author_id (str): 相关作者ID / ID связанного автора
    """

    def __init__(self, operation: str, author_id: str, message: str):
        self.operation = operation
        self.author_id = author_id
        self.message = message
        super().__init__(f"图更新错误 ({operation}): 作者 {author_id} - {message}")


class ConfigurationError(DisambiguationError):
    """
    配置错误异常 / Исключение ошибки конфигурации

    当系统配置无效或不一致时抛出
    Выбрасывается при недействительной или несогласованной конфигурации системы

    Attributes:
        config_key (str): 问题配置项 / Проблемный элемент конфигурации
        expected (str): 期望值说明 / Описание ожидаемого значения
        actual (str): 实际值说明 / Описание фактического значения
    """

    def __init__(self, config_key: str, expected: str, actual: str):
        self.config_key = config_key
        self.expected = expected
        self.actual = actual
        super().__init__(f"配置错误 {config_key}: 期望 {expected}, 实际 {actual}")


class DataIntegrityError(DisambiguationError):
    """
    数据完整性异常 / Исключение целостности данных

    当检测到数据不一致或损坏时抛出
    Выбрасывается при обнаружении несогласованности или повреждения данных

    Attributes:
        entity_type (str): 实体类型 (author, publication, record) / Тип сущности
        entity_id (str): 实体ID / ID сущности
        inconsistency (str): 不一致描述 / Описание несогласованности
    """

    def __init__(self, entity_type: str, entity_id: str, inconsistency: str):
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.inconsistency = inconsistency
        super().__init__(f"数据完整性错误: {entity_type} {entity_id} - {inconsistency}")


class PerformanceWarning(UserWarning):
    """
    性能警告 / Предупреждение о производительности

    当操作可能影响性能时发出的警告
    Предупреждение, выдаваемое при операциях, которые могут повлиять на производительность
    """
    pass