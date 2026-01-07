# -*- coding: utf-8 -*-
"""
Справочник структур данных для исследования / 研究用数据结构参考

Извлечено из ChineseNameProcessor v2.0.0 для использования в других исследованиях
从ChineseNameProcessor v2.0.0项目中提取，供其他研究使用

Автор / 作者: Ма Цзясин (Ma Jiaxin)
Московский государственный университет им. М.В. Ломоносова / 莫斯科国立大学
Email: majiaxing@mail.ru

Источник / 来源: https://github.com/Soulbeaters/Chinese-name
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod

# ============================
# 基础数据结构 / Basic Data Structures
# ============================

@dataclass
class NameComponents:
    """
    Компоненты имени / 姓名组件

    Базовая структура данных для хранения разобранного имени
    存储解析后姓名各个部分的基础数据结构

    Аналог старого класса Firstname, но с расширенной функциональностью
    旧版Firstname类的升级版本，具有扩展功能
    """
    surname: str                    # Фамилия / 姓氏
    first_name: str                # Имя / 名字
    middle_name: str = ""          # Отчество/среднее имя / 中间名
    confidence: float = 1.0        # Коэффициент достоверности / 置信度
    source_type: str = ""          # Тип источника данных / 数据源类型
    decision_reason: str = ""      # Объяснение решения / 决策说明

    def is_valid(self) -> bool:
        """Проверка валидности данных / 数据有效性检查"""
        return bool(self.surname or self.first_name)

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация в словарь / 序列化为字典"""
        return {
            'surname': self.surname,
            'first_name': self.first_name,
            'middle_name': self.middle_name,
            'confidence': self.confidence,
            'source_type': self.source_type,
            'decision_reason': self.decision_reason
        }

@dataclass
class ProcessingResult:
    """
    Результат обработки / 处理结果

    Содержит результат обработки и метаинформацию
    包含处理结果和元信息

    Заменяет простой возврат значений более структурированным подходом
    用结构化方法替代简单的返回值
    """
    components: NameComponents                      # Основные компоненты / 主要组件
    confidence_score: float                        # Общая оценка / 总体评分
    decision_path: List[str] = field(default_factory=list)    # Путь решений / 决策路径
    alternatives: List[NameComponents] = field(default_factory=list)  # Альтернативы / 替代方案
    errors: List[str] = field(default_factory=list)           # Ошибки / 错误列表
    processing_time: float = 0.0                  # Время обработки / 处理时间

    def is_successful(self) -> bool:
        """Проверка успешности / 成功性检查"""
        return self.components.is_valid() and len(self.errors) == 0

    def to_dict(self) -> Dict[str, Any]:
        """Полная сериализация / 完整序列化"""
        return {
            'components': self.components.to_dict(),
            'confidence_score': self.confidence_score,
            'decision_path': self.decision_path,
            'alternatives': [alt.to_dict() for alt in self.alternatives],
            'errors': self.errors,
            'processing_time': self.processing_time
        }

@dataclass
class DataInfo:
    """
    Метаинформация о данных / 数据元信息

    Расширенная информация о данных с многоязычной поддержкой
    具有多语言支持的扩展数据信息
    """
    primary_value: str             # Основное значение / 主要值
    transliteration: str           # Транслитерация / 音译
    alternative_forms: str         # Альтернативные формы / 替代形式
    frequency: int                 # Частота использования / 使用频率
    region: List[str]             # Регион распространения / 分布地区
    is_compound: bool = False      # Составное ли значение / 是否为复合值

    def get_info_dict(self) -> Dict[str, Any]:
        """Получить информационный словарь / 获取信息字典"""
        return {
            'primary': self.primary_value,
            'transliteration': self.transliteration,
            'alternatives': self.alternative_forms,
            'frequency': self.frequency,
            'region': self.region,
            'compound': self.is_compound
        }

# ============================
# управляющие классы / Management Classes
# ============================

class DataManager(ABC):
    """
    Абстрактный менеджер данных / 抽象数据管理器

    Базовый класс для управления коллекциями данных
    用于管理数据集合的基类

    Современная замена старого FirstnameManager
    旧版FirstnameManager的现代替代方案
    """

    def __init__(self):
        self._data: Dict[str, DataInfo] = {}

    @abstractmethod
    def add_item(self, key: str, info: DataInfo) -> bool:
        """Добавить элемент / 添加元素"""
        pass

    @abstractmethod
    def get_item(self, key: str) -> Optional[DataInfo]:
        """Получить элемент / 获取元素"""
        pass

    def get_all_items(self) -> Dict[str, DataInfo]:
        """Получить все элементы / 获取所有元素"""
        return self._data.copy()

    def bulk_operation(self, items: List[str]) -> Dict[str, Optional[DataInfo]]:
        """
        Массовая операция (аналог in_bulk) / 批量操作 (类似in_bulk)

        Args:
            items: Список ключей / 键列表
        Returns:
            Dict[str, DataInfo]: Словарь найденных элементов / 找到的元素字典
        """
        return {item: self.get_item(item) for item in items}

class SimpleDataManager(DataManager):
    """
    Простой менеджер данных / 简单数据管理器

    Конкретная реализация для базовых операций
    基本操作的具体实现
    """

    def add_item(self, key: str, info: DataInfo) -> bool:
        """Добавить элемент в коллекцию / 向集合添加元素"""
        try:
            self._data[key] = info
            return True
        except Exception:
            return False

    def get_item(self, key: str) -> Optional[DataInfo]:
        """Получить элемент по ключу / 通过键获取元素"""
        return self._data.get(key)

    def search_by_pattern(self, pattern: str) -> List[str]:
        """Поиск по шаблону / 按模式搜索"""
        return [key for key in self._data.keys() if pattern in key]

    def get_statistics(self) -> Dict[str, Any]:
        """Получить статистику / 获取统计信息"""
        return {
            'total_items': len(self._data),
            'compound_items': sum(1 for info in self._data.values() if info.is_compound),
            'avg_frequency': sum(info.frequency for info in self._data.values()) / len(self._data) if self._data else 0
        }

# ============================
# Фабричные функции / Factory Functions
# ============================

def create_name_components(surname: str = "", first_name: str = "", **kwargs) -> NameComponents:
    """
    Фабричная функция для создания компонентов имени / 创建姓名组件的工厂函数

    Упрощенный способ создания объектов NameComponents
    创建NameComponents对象的简化方式
    """
    return NameComponents(
        surname=surname,
        first_name=first_name,
        middle_name=kwargs.get('middle_name', ''),
        confidence=kwargs.get('confidence', 1.0),
        source_type=kwargs.get('source_type', ''),
        decision_reason=kwargs.get('decision_reason', '')
    )

def create_data_manager() -> SimpleDataManager:
    """
    Создать менеджер данных по умолчанию / 创建默认数据管理器

    Аналог создания FirstnameManager в старой версии
    类似于旧版本中创建FirstnameManager
    """
    return SimpleDataManager()

def create_processing_result(components: NameComponents, confidence: float = 1.0) -> ProcessingResult:
    """
    Создать результат обработки / 创建处理结果

    Удобный способ создания объекта результата
    创建结果对象的便捷方式
    """
    return ProcessingResult(
        components=components,
        confidence_score=confidence
    )

# ============================
# Примеры использования / Usage Examples
# ============================

def example_basic_usage():
    """
    Базовые примеры использования / 基本使用示例

    Демонстрирует основные паттерны работы с данными
    演示数据处理的基本模式
    """
    print("=== Базовое использование / Basic Usage ===")

    # Создание компонентов имени / 创建姓名组件
    name = create_name_components(
        surname="李",
        first_name="小明",
        confidence=0.95,
        source_type="chinese"
    )

    print(f"Имя создано / 姓名创建: {name.surname} {name.first_name}")
    print(f"Валидность / 有效性: {name.is_valid()}")
    print(f"JSON: {name.to_dict()}")

    # Создание менеджера данных / 创建数据管理器
    manager = create_data_manager()

    # Добавление данных / 添加数据
    info = DataInfo(
        primary_value="李",
        transliteration="Li",
        alternative_forms="Lee, Li",
        frequency=95,
        region=["全国"]
    )

    success = manager.add_item("李", info)
    print(f"Данные добавлены / 数据已添加: {success}")

    # Массовое получение / 批量获取
    bulk_result = manager.bulk_operation(["李", "王", "张"])
    print(f"Массовый результат / 批量结果: {len(bulk_result)} элементов")

    return name, manager

def example_advanced_usage():
    """
    Продвинутые примеры / 高级示例

    Показывает сложные сценарии использования
    展示复杂的使用场景
    """
    print("=== Продвинутое использование / Advanced Usage ===")

    # Создание результата обработки / 创建处理结果
    name_comp = create_name_components("张", "三丰", confidence=0.98)
    result = create_processing_result(name_comp, 0.98)

    # Добавление пути решений / 添加决策路径
    result.decision_path.extend([
        "Анализ входных данных",
        "Распознавание китайского имени",
        "Разделение на фамилию и имя"
    ])

    print(f"Результат обработки / 处理结果: {result.is_successful()}")
    print(f"Путь решений / 决策路径: {len(result.decision_path)} шагов")

    return result

if __name__ == "__main__":
    """
    Демонстрационный запуск / 演示运行
    """
    print("Справочник структур данных для исследования")
    print("研究用数据结构参考")
    print("=" * 50)

    # Базовые примеры / 基础示例
    name, manager = example_basic_usage()
    print()

    # Продвинутые примеры / 高级示例
    result = example_advanced_usage()
    print()

    # Статистика / 统计信息
    print("=== Статистика менеджера / 管理器统计 ===")
    stats = manager.get_statistics()
    for key, value in stats.items():
        print(f"{key}: {value}")