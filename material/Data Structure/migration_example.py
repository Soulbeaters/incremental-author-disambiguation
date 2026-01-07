# -*- coding: utf-8 -*-
"""
Пример миграции со старой структуры на новую / 从旧结构迁移到新结构的示例

Показывает, как заменить старый код новыми структурами данных
演示如何用新数据结构替换旧代码

Автор / 作者: Ма Цзясин (Ma Jiaxin)
МГУ / 莫斯科国立大学
"""

from data_structures_reference import (
    create_name_components,
    create_data_manager,
    create_processing_result,
    DataInfo
)

# ============================
# Старая версия / 旧版本
# ============================

class OldFirstname:
    """Имитация старого класса Firstname / 模拟旧的Firstname类"""

    def __init__(self, name, people_count=100):
        self.name = name
        self.people_count = people_count

class OldFirstnameManager:
    """Имитация старого класса FirstnameManager / 模拟旧的FirstnameManager类"""

    def in_bulk(self, names):
        """Старый метод массовой обработки / 旧的批量处理方法"""
        return {name: OldFirstname(name) for name in names}

# ============================
# Примеры миграции / 迁移示例
# ============================

def migration_example_1():
    """
    Пример 1: Миграция простого создания объектов
    示例1: 简单对象创建的迁移
    """
    print("=== Пример 1: Создание объектов / 示例1: 对象创建 ===")

    # Старый способ / 旧方式
    print("Старый способ / 旧方式:")
    old_name = OldFirstname("李小明", 150)
    print(f"  Имя: {old_name.name}, Количество: {old_name.people_count}")

    # Новый способ / 新方式
    print("Новый способ / 新方式:")
    new_name = create_name_components(
        surname="李",
        first_name="小明",
        confidence=0.95,
        source_type="migrated"
    )
    print(f"  Фамилия: {new_name.surname}, Имя: {new_name.first_name}")
    print(f"  Достоверность: {new_name.confidence}, Тип: {new_name.source_type}")
    print(f"  Валидность: {new_name.is_valid()}")
    print(f"  JSON: {new_name.to_dict()}")
    print()

def migration_example_2():
    """
    Пример 2: Миграция массовых операций
    示例2: 批量操作的迁移
    """
    print("=== Пример 2: Массовые операции / 示例2: 批量操作 ===")

    names_list = ["李明", "王红", "张伟"]

    # Старый способ / 旧方式
    print("Старый способ / 旧方式:")
    old_manager = OldFirstnameManager()
    old_result = old_manager.in_bulk(names_list)

    for name, obj in old_result.items():
        print(f"  {name}: {obj.name} (count: {obj.people_count})")

    # Новый способ / 新方式
    print("Новый способ / 新方式:")
    new_manager = create_data_manager()

    # Сначала заполняем менеджер данными / 先填充管理器数据
    for name in names_list:
        if len(name) >= 2:
            surname = name[0]
            first_name = name[1:]
        else:
            surname = name
            first_name = ""

        info = DataInfo(
            primary_value=name,
            transliteration=f"transliterated_{name}",
            alternative_forms="",
            frequency=100,
            region=["全国"]
        )
        new_manager.add_item(name, info)

    # Массовое получение / 批量获取
    new_result = new_manager.bulk_operation(names_list)

    for name, info in new_result.items():
        if info:
            print(f"  {name}: {info.primary_value} (frequency: {info.frequency})")
            print(f"    Transliteration: {info.transliteration}")

    # Статистика / 统计
    stats = new_manager.get_statistics()
    print(f"  Статистика / 统计: {stats}")
    print()

def migration_example_3():
    """
    Пример 3: Расширенная функциональность
    示例3: 扩展功能
    """
    print("=== Пример 3: Расширенная функциональность / 示例3: 扩展功能 ===")

    # Создание компонентов имени с проверкой / 创建带验证的姓名组件
    name_comp = create_name_components(
        surname="司马",
        first_name="光",
        confidence=0.98,
        source_type="compound_surname",
        decision_reason="Recognized as compound surname from classical Chinese"
    )

    # Создание результата обработки / 创建处理结果
    result = create_processing_result(name_comp, 0.98)

    # Добавление пути решений / 添加决策路径
    result.decision_path.extend([
        "Input received: 司马光",
        "Detected compound surname: 司马",
        "Extracted given name: 光",
        "Validation: successful",
        "Confidence calculated: 0.98"
    ])

    print("Результат обработки / 处理结果:")
    print(f"  Успешность: {result.is_successful()}")
    print(f"  Компоненты: {result.components.surname} | {result.components.first_name}")
    print(f"  Достоверность: {result.confidence_score}")
    print(f"  Шагов обработки: {len(result.decision_path)}")

    # Полная сериализация / 完整序列化
    full_dict = result.to_dict()
    print(f"  Полный JSON доступен ({len(str(full_dict))} символов)")
    print()

def comparison_summary():
    """
    Сравнительная сводка / 对比总结
    """
    print("=== Сравнительная сводка / 对比总结 ===")

    improvements = {
        "Типизация / 类型化": {
            "Старое / 旧": "Нет типов / 无类型",
            "Новое / 新": "Полная типизация / 完整类型化"
        },
        "Валидация / 验证": {
            "Старое / 旧": "Нет проверок / 无验证",
            "Новое / 新": "is_valid() метод / is_valid()方法"
        },
        "Сериализация / 序列化": {
            "Старое / 旧": "Ручная / 手动",
            "Новое / 新": "to_dict() метод / to_dict()方法"
        },
        "Функциональность / 功能": {
            "Старое / 旧": "Базовая / 基础",
            "Новое / 新": "Расширенная / 扩展"
        },
        "Документация / 文档": {
            "Старое / 旧": "Минимальная / 最少",
            "Новое / 新": "Двуязычная / 双语"
        }
    }

    for aspect, comparison in improvements.items():
        print(f"{aspect}:")
        print(f"  {comparison['Старое / 旧']} → {comparison['Новое / 新']}")

    print()
    print("Рекомендация / 建议:")
    print("Используйте новые структуры для будущих исследований")
    print("建议在未来的研究中使用新结构")

def main():
    """
    Главная демонстрационная функция / 主演示函数
    """
    print("Пример миграции структур данных")
    print("数据结构迁移示例")
    print("=" * 60)

    migration_example_1()
    migration_example_2()
    migration_example_3()
    comparison_summary()

    print("Миграция завершена! Новые структуры готовы к использованию.")
    print("迁移完成！新结构已准备好使用。")

if __name__ == "__main__":
    main()