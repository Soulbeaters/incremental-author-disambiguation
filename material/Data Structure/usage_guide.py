# -*- coding: utf-8 -*-
"""
Руководство по использованию / 使用指南

Практические примеры использования структур данных в исследовании
研究中数据结构使用的实际示例

Автор / 作者: Ма Цзясин (Ma Jiaxin)
МГУ / 莫斯科国立大学
"""

from data_structures_reference import *

# ============================
# Практические сценарии / 实际场景
# ============================

def research_scenario_1():
    """
    Сценарий 1: Сбор и структурирование данных / 场景1: 数据收集和结构化
    """
    print("=== Сценарий 1: Сбор данных / 场景1: 数据收集 ===")

    # Создаем менеджер для исследовательских данных
    # 创建研究数据管理器
    research_manager = create_data_manager()

    # Примеры данных для исследования / 研究数据示例
    research_data = [
        ("Иван", "Ivan", "Common Russian name", 85, ["Россия"]),
        ("张伟", "Zhang Wei", "Most common Chinese name", 95, ["中国"]),
        ("Maria", "Maria", "International name", 70, ["Global"]),
        ("محمد", "Muhammad", "Arabic name", 90, ["Arabic countries"]),
    ]

    print("Добавление исследовательских данных / 添加研究数据:")

    for name, transliteration, description, frequency, regions in research_data:
        info = DataInfo(
            primary_value=name,
            transliteration=transliteration,
            alternative_forms=description,
            frequency=frequency,
            region=regions
        )

        success = research_manager.add_item(name, info)
        print(f"  {name} ({transliteration}): {'✓' if success else '✗'}")

    # Получение статистики исследования / 获取研究统计
    stats = research_manager.get_statistics()
    print(f"Статистика исследования / 研究统计:")
    print(f"  Всего записей / 总记录: {stats['total_items']}")
    print(f"  Средняя частота / 平均频率: {stats['avg_frequency']:.1f}")

    return research_manager

def research_scenario_2():
    """
    Сценарий 2: Анализ и валидация данных / 场景2: 数据分析和验证
    """
    print("\n=== Сценарий 2: Анализ данных / 场景2: 数据分析 ===")

    # Создаем тестовые данные для анализа / 创建用于分析的测试数据
    test_names = [
        ("李", "明", "chinese"),
        ("Smith", "John", "english"),
        ("", "Maria", "incomplete"),  # Неполные данные / 不完整数据
        ("Иван", "", "incomplete"),   # Неполные данные / 不完整数据
    ]

    analysis_results = []

    print("Анализ валидности данных / 数据有效性分析:")

    for surname, first_name, source in test_names:
        # Создаем компоненты для анализа / 创建用于分析的组件
        components = create_name_components(
            surname=surname,
            first_name=first_name,
            source_type=source,
            confidence=0.8 if surname and first_name else 0.5
        )

        # Создаем результат обработки / 创建处理结果
        result = create_processing_result(components, components.confidence)

        # Добавляем ошибки для неполных данных / 为不完整数据添加错误
        if not components.surname:
            result.errors.append("Missing surname / 缺少姓氏")
        if not components.first_name:
            result.errors.append("Missing first name / 缺少名字")

        analysis_results.append(result)

        # Выводим результаты анализа / 输出分析结果
        status = "✓ Valid" if result.is_successful() else "✗ Invalid"
        print(f"  {surname or '[EMPTY]'} {first_name or '[EMPTY]'}: {status}")
        if result.errors:
            for error in result.errors:
                print(f"    Ошибка / 错误: {error}")

    # Сводная статистика анализа / 分析汇总统计
    valid_count = sum(1 for r in analysis_results if r.is_successful())
    total_count = len(analysis_results)

    print(f"Результаты анализа / 分析结果:")
    print(f"  Валидных записей / 有效记录: {valid_count}/{total_count}")
    print(f"  Процент успеха / 成功率: {valid_count/total_count*100:.1f}%")

    return analysis_results

def research_scenario_3():
    """
    Сценарий 3: Создание отчета исследования / 场景3: 创建研究报告
    """
    print("\n=== Сценарий 3: Отчет исследования / 场景3: 研究报告 ===")

    # Создаем комплексный результат исследования / 创建综合研究结果
    main_component = create_name_components(
        surname="Research",
        first_name="Data",
        confidence=0.95,
        source_type="research",
        decision_reason="Comprehensive analysis of multilingual name data"
    )

    research_result = create_processing_result(main_component, 0.95)

    # Добавляем детальный путь исследования / 添加详细研究路径
    research_result.decision_path.extend([
        "Step 1: Data collection from multiple sources",
        "Step 2: Validation and cleaning of collected data",
        "Step 3: Statistical analysis of name patterns",
        "Step 4: Cross-cultural comparison",
        "Step 5: Results compilation and reporting"
    ])

    # Создаем альтернативные интерпретации / 创建替代解释
    alternative1 = create_name_components(
        surname="Alternative",
        first_name="Analysis",
        confidence=0.85,
        source_type="secondary",
        decision_reason="Alternative interpretation of the same data"
    )

    research_result.alternatives.append(alternative1)

    print("Отчет о исследовании / 研究报告:")
    print(f"  Основной результат / 主要结果: {research_result.components.surname} {research_result.components.first_name}")
    print(f"  Достоверность / 可信度: {research_result.confidence_score}")
    print(f"  Этапов исследования / 研究阶段: {len(research_result.decision_path)}")
    print(f"  Альтернативных интерпретаций / 替代解释: {len(research_result.alternatives)}")

    # Экспорт результатов в JSON / 将结果导出为JSON
    export_data = research_result.to_dict()
    print(f"  Экспортируемых данных / 可导出数据: {len(str(export_data))} символов")

    # Детальный путь исследования / 详细研究路径
    print("Путь исследования / 研究路径:")
    for i, step in enumerate(research_result.decision_path, 1):
        print(f"  {i}. {step}")

    return research_result

def integration_example():
    """
    Пример интеграции всех компонентов / 综合所有组件的示例
    """
    print("\n=== Интеграционный пример / 综合示例 ===")

    print("Объединение всех компонентов для комплексного исследования")
    print("整合所有组件进行综合研究")

    # Получаем результаты всех сценариев / 获取所有场景的结果
    manager = research_scenario_1()
    analysis = research_scenario_2()
    report = research_scenario_3()

    print(f"Интеграция завершена / 集成完成:")
    print(f"  Данных в менеджере / 管理器中数据: {len(manager.get_all_items())}")
    print(f"  Результатов анализа / 分析结果: {len(analysis)}")
    print(f"  Этапов в отчете / 报告阶段: {len(report.decision_path)}")

    # Создаем финальный интегрированный результат / 创建最终集成结果
    final_result = {
        'data_manager': manager.get_statistics(),
        'analysis_summary': {
            'total_analyzed': len(analysis),
            'successful': sum(1 for a in analysis if a.is_successful()),
            'average_confidence': sum(a.confidence_score for a in analysis) / len(analysis)
        },
        'report_metadata': {
            'main_confidence': report.confidence_score,
            'steps_count': len(report.decision_path),
            'alternatives_count': len(report.alternatives)
        }
    }

    print("Финальная интеграция / 最终集成:")
    for section, data in final_result.items():
        print(f"  {section}: {data}")

    return final_result

def main():
    """
    Главная функция демонстрации / 主要演示功能
    """
    print("Руководство по использованию структур данных")
    print("数据结构使用指南")
    print("=" * 60)

    # Запускаем все сценарии использования / 运行所有使用场景
    final_integration = integration_example()

    print("\n" + "=" * 60)
    print("Руководство завершено / 指南完成")
    print("Структуры данных готовы для использования в ваших исследованиях")
    print("数据结构已准备好在您的研究中使用")

    return final_integration

if __name__ == "__main__":
    result = main()