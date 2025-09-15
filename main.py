# -*- coding: utf-8 -*-
"""
作者姓名增量消歧系统 - 完整原型演示 / Система инкрементального устранения неоднозначности имён авторов - полная демонстрация прототипа

演示完整的增量消歧流程，包含白盒决策报告
Демонстрация полного процесса инкрементального устранения неоднозначности с отчётами о решениях белой коробки
"""

import sys
import os
from typing import List

# 添加项目根目录到Python路径 / Добавление корневого каталога проекта в путь Python
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models.author import AuthorRecord
from disambiguation_engine.engine import DisambiguationEngine
from config import SIMILARITY_THRESHOLD, SIMILARITY_WEIGHTS


def create_representative_test_cases() -> List[AuthorRecord]:
    """
    创建具有代表性的测试用例 / Создание представительных тестовых случаев

    包含四种典型场景：
    1. 明显相同的作者（微小差异，高重合度）
    2. 明显不同的作者
    3. 与现有网络有合作关系的新人
    4. 后续记录应该合并之前错误分离的作者

    Returns:
        List[AuthorRecord]: 测试记录列表 / Список тестовых записей
    """
    test_records = [
        # Case 1: 明显相同的作者 - 第一条记录 / Явно один автор - первая запись
        AuthorRecord(
            record_id="R001",
            name="John Smith",
            coauthors=["Maria Garcia", "David Chen", "Sarah Johnson"],
            journal="Nature",
            publication_title="Machine Learning in Bioinformatics",
            year=2023,
            affiliation="Stanford University"
        ),

        # Case 1: 明显相同的作者 - 第二条记录（微小差异，高重合度）/ Явно тот же автор - вторая запись (небольшие различия, высокое совпадение)
        AuthorRecord(
            record_id="R002",
            name="J. Smith",  # 姓名略有差异 / Имя слегка отличается
            coauthors=["Maria Garcia", "David Chen", "Robert Wilson"],  # 大部分合著者相同 / Большинство соавторов совпадают
            journal="Nature Biotechnology",  # 相关期刊 / Связанный журнал
            publication_title="Advanced ML Applications in Biology",
            year=2023,
            affiliation="Stanford Univ"  # 机构名称略有差异 / Название учреждения слегка отличается
        ),

        # Case 2: 明显不同的作者 / Явно другой автор
        AuthorRecord(
            record_id="R003",
            name="Li Wei",
            coauthors=["Zhang Ming", "Wang Qiang", "Liu Fang"],
            journal="IEEE Transactions on Pattern Analysis",
            publication_title="Computer Vision Algorithms",
            year=2023,
            affiliation="Tsinghua University"
        ),

        # Case 3: 与现有网络有合作关系的新人 / Новый человек с отношениями сотрудничества к существующей сети
        AuthorRecord(
            record_id="R004",
            name="Maria Garcia",  # 之前作为合著者出现 / Ранее появлялся как соавтор
            coauthors=["John Smith", "Elena Rodriguez"],  # 与已知作者合作 / Сотрудничество с известным автором
            journal="Science",
            publication_title="Collaborative Research in AI",
            year=2024,
            affiliation="MIT"
        ),

        # Case 4a: 错误分离的作者 - 第一部分 / Ошибочно разделённый автор - первая часть
        AuthorRecord(
            record_id="R005",
            name="Robert Wilson",
            coauthors=["Anna Brown", "Michael Davis"],
            journal="JAMA",
            publication_title="Medical Data Analysis",
            year=2022,
            affiliation="Harvard Medical School"
        ),

        # Case 4b: 应该与上一个是同一人的另一条记录 / Другая запись, которая должна быть тем же человеком
        AuthorRecord(
            record_id="R006",
            name="R. Wilson",  # 姓名形式不同 / Другая форма имени
            coauthors=["Anna Brown", "Jennifer Lee"],  # 部分相同合著者 / Частично совпадающие соавторы
            journal="Medical Imaging",
            publication_title="Advanced Medical Imaging Techniques",
            year=2022,
            affiliation="Harvard Med School"  # 机构缩写 / Сокращение учреждения
        ),

        # Case 4c: 后续记录应该能将之前错误分开的作者合并 / Последующая запись должна объединить ранее ошибочно разделённых авторов
        AuthorRecord(
            record_id="R007",
            name="Robert Wilson",  # 完整姓名 / Полное имя
            coauthors=["Anna Brown", "Michael Davis", "Jennifer Lee"],  # 合并了两组合著者 / Объединяет обе группы соавторов
            journal="Nature Medicine",
            publication_title="Integrated Medical Research Platform",
            year=2024,
            affiliation="Harvard Medical School"
        ),

        # Case 5: 边界测试 - 阈值边缘情况 / Граничный тест - пограничный случай с порогом
        AuthorRecord(
            record_id="R008",
            name="David Chen",  # 之前的合著者现在是主作者 / Бывший соавтор теперь основной автор
            coauthors=["John Smith", "New Collaborator"],
            journal="Nature AI",
            publication_title="AI Research Collaboration",
            year=2024,
            affiliation="Google Research"
        )
    ]

    return test_records


def print_system_state(engine: DisambiguationEngine, step: int, description: str):
    """
    打印系统当前状态 / Печать текущего состояния системы

    Args:
        engine: 消歧引擎实例 / Экземпляр движка устранения неоднозначности
        step: 步骤编号 / Номер шага
        description: 描述 / Описание
    """
    print(f"\n{'='*80}")
    print(f"SYSTEM STATE - STEP {step}: {description}")
    print(f"СОСТОЯНИЕ СИСТЕМЫ - ШАГ {step}: {description}")
    print(f"{'='*80}")

    # 基本统计 / Базовая статистика
    stats = engine.get_statistics()
    print(f"\n*** BASIC STATISTICS / БАЗОВАЯ СТАТИСТИКА:")
    print(f"   - Total Authors: {stats['total_authors']}")
    print(f"   - Total Processed Records: {stats['total_processed']}")
    print(f"   - Merged Records: {stats['merged_records']}")
    print(f"   - New Authors Created: {stats['new_authors_created']}")

    # 作者详细信息 / Подробная информация об авторах
    print(f"\n*** AUTHOR DETAILS / ДЕТАЛИ АВТОРОВ:")
    print(f"   {'-'*60}")

    for i, (author_id, author) in enumerate(engine.authors.items(), 1):
        linked_records = list(author.linked_records)
        coauthor_count = len(author.coauthor_ids)

        print(f"   [{i}] Author ID: {author_id}")
        print(f"       - Canonical Name: {author.canonical_name}")
        print(f"       - Linked Records: {linked_records} ({len(linked_records)} total)")
        print(f"       - Coauthors: {coauthor_count}")
        print(f"       - Publications: {len(author.publications)}")
        print(f"       - Journals: {list(author.journals)[:3]}{'...' if len(author.journals) > 3 else ''}")
        print(f"       - Confidence: {author.confidence_score:.3f}")
        print(f"   {'-'*60}")

    # 依赖图状态 / Состояние графа зависимостей
    graph_stats = stats.get('graph_stats', {})
    print(f"\n***  DEPENDENCY GRAPH / ГРАФ ЗАВИСИМОСТЕЙ:")
    print(f"   - Nodes (Authors): {graph_stats.get('node_count', 0)}")
    print(f"   - Edges (Collaborations): {graph_stats.get('edge_count', 0)}")
    print(f"   - Average Degree: {graph_stats.get('average_degree', 0):.2f}")

    # 性能信息 / Информация о производительности
    avg_time = stats.get('avg_processing_time', 0)
    print(f"\n*** PERFORMANCE / ПРОИЗВОДИТЕЛЬНОСТЬ:")
    print(f"   - Average Processing Time: {avg_time:.4f} seconds")
    print(f"   - Total Processing Time: {stats.get('processing_time_total', 0):.4f} seconds")


def demonstrate_incremental_disambiguation():
    """
    演示增量消歧的完整流程 / Демонстрация полного процесса инкрементального устранения неоднозначности
    """
    print(">>> 启动增量作者消歧系统完整原型演示")
    print(">>> Запуск полной демонстрации прототипа системы инкрементального устранения неоднозначности авторов")
    print(f"\n当前配置 / Текущая конфигурация:")
    print(f"* 相似度阈值 / Порог сходства: {SIMILARITY_THRESHOLD}")
    print(f"* 权重配置 / Конфигурация весов: {SIMILARITY_WEIGHTS}")

    # 初始化引擎 / Инициализация движка
    engine = DisambiguationEngine()

    # 创建测试数据 / Создание тестовых данных
    test_records = create_representative_test_cases()

    print(f"\n>>> 创建了 {len(test_records)} 条代表性测试记录")
    print(f">>> Создано {len(test_records)} представительных тестовых записей")

    # 显示初始状态 / Отображение начального состояния
    print_system_state(engine, 0, "INITIAL STATE / НАЧАЛЬНОЕ СОСТОЯНИЕ")

    # 逐条处理记录 / Пошаговая обработка записей
    for i, record in enumerate(test_records, 1):
        print(f"\n{'>>>'*3} PROCESSING RECORD {i}/{len(test_records)} {'>>>'*3}")
        print(f"Record ID: {record.record_id}")
        print(f"Name: {record.name}")
        print(f"Coauthors: {record.coauthors}")
        print(f"Journal: {record.journal}")
        print(f"Affiliation: {record.affiliation}")

        # 处理记录 / Обработка записи
        result = engine.process_new_record(record)

        # 生成并显示白盒决策报告 / Генерация и отображение отчёта о решении белой коробки
        matched_author_name = None
        if result.matched_author_id and result.matched_author_id in engine.authors:
            matched_author_name = engine.authors[result.matched_author_id].canonical_name

        result.print_decision_report(record.name, matched_author_name)

        # 显示系统状态变化 / Отображение изменений состояния системы
        step_description = f"After processing {record.record_id} ({record.name})"
        print_system_state(engine, i, step_description)

        # 在关键步骤后暂停 / Пауза после ключевых шагов
        if i in [2, 4, 7]:  # 在重要决策点暂停 / Пауза в важных точках принятия решений
            input(f"\n>>>  按Enter继续到下一步... / Нажмите Enter для продолжения...")

    # 最终总结 / Финальное резюме
    print(f"\n{'***'*5} FINAL SUMMARY / ИТОГОВОЕ РЕЗЮМЕ {'***'*5}")
    final_stats = engine.get_statistics()

    print(f"\n*** PROCESSING RESULTS / РЕЗУЛЬТАТЫ ОБРАБОТКИ:")
    print(f"- 处理记录总数 / Всего обработано записей: {final_stats['total_processed']}")
    print(f"- 识别出的唯一作者 / Выявлено уникальных авторов: {final_stats['total_authors']}")
    print(f"- 成功合并的记录 / Успешно объединено записей: {final_stats['merged_records']}")
    print(f"- 创建的新作者 / Создано новых авторов: {final_stats['new_authors_created']}")

    print(f"\n*** KEY ACHIEVEMENTS / КЛЮЧЕВЫЕ ДОСТИЖЕНИЯ:")
    print(f"[+] 白盒决策：每个决策都有完整的透明报告")
    print(f"[+] 增量计算：只处理受影响的作者子集")
    print(f"[+] 动态图构建：自动建立和更新合作关系网络")
    print(f"[+] 性能优化：平均处理时间 {final_stats['avg_processing_time']:.4f} 秒")

    print(f"\n[+] Решения белой коробки: каждое решение имеет полный прозрачный отчёт")
    print(f"[+] Инкрементальные вычисления: обработка только затронутого подмножества авторов")
    print(f"[+] Динамическое построение графа: автоматическое создание и обновление сети сотрудничества")
    print(f"[+] Оптимизация производительности: среднее время обработки {final_stats['avg_processing_time']:.4f} секунд")

    return engine, final_stats


def main():
    """
    主函数 / Главная функция
    """
    try:
        # 运行完整演示 / Запуск полной демонстрации
        engine, stats = demonstrate_incremental_disambiguation()

        print(f"\n{'='*80}")
        print("*** 增量消歧系统原型演示完成！")
        print("*** Демонстрация прототипа системы инкрементального устранения неоднозначности завершена!")
        print(f"{'='*80}")

        # 可选：导出结果 / Опционально: экспорт результатов
        export_choice = input("\n是否导出结果到文件? (y/N) / Экспортировать результаты в файл? (y/N): ").strip().lower()
        if export_choice in ['y', 'yes', 'д', 'да']:
            results = engine.export_results()
            import json
            output_file = "incremental_disambiguation_results.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2, default=str)
            print(f"[+] 结果已导出到: {output_file}")
            print(f"[+] Результаты экспортированы в: {output_file}")

    except KeyboardInterrupt:
        print("\n\n[!]  演示被用户中断")
        print("[!]  Демонстрация прервана пользователем")
    except Exception as e:
        print(f"\n[ERROR] 演示过程中发生错误: {e}")
        print(f"[ERROR] Ошибка во время демонстрации: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()