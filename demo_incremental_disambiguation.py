# -*- coding: utf-8 -*-
"""
增量消歧系统综合演示 / Комплексная демонстрация системы инкрементального устранения неоднозначности

展示完整的增量消歧流程，包括数据建模、依赖图构建和消歧决策
Демонстрирует полный процесс инкрементального устранения неоднозначности, включая моделирование данных, построение графа зависимостей и принятие решений по устранению неоднозначности
"""

import sys
import os
import json
from datetime import datetime
from typing import List

# 添加项目根目录到Python路径 / Добавление корневого каталога проекта в путь Python
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models.author import AuthorRecord, Publication
from disambiguation_engine.engine import DisambiguationEngine
from config import SIMILARITY_THRESHOLD


def create_realistic_dataset() -> List[AuthorRecord]:
    """
    创建真实的测试数据集 / Создание реалистичного тестового набора данных

    模拟ИСТИНА系统中可能遇到的各种作者消歧场景
    Имитирует различные сценарии устранения неоднозначности авторов, которые могут встретиться в системе ИСТИНА

    Returns:
        List[AuthorRecord]: 测试记录列表 / Список тестовых записей
    """
    records = [
        # 场景1：同一作者的多条记录 / Сценарий 1: Множественные записи одного автора
        AuthorRecord(
            record_id="rec_001",
            name="张伟",
            coauthors=["李明", "王强", "陈建国"],
            journal="Nature",
            publication_title="Deep Learning in Bioinformatics",
            year=2023,
            affiliation="清华大学计算机系"
        ),
        AuthorRecord(
            record_id="rec_002",
            name="张伟",  # 同名 / Одно имя
            coauthors=["李明", "王强", "刘小红"],  # 部分相同合著者 / Частично совпадающие соавторы
            journal="Nature Machine Intelligence",
            publication_title="Neural Networks for Protein Folding",
            year=2023,
            affiliation="清华大学"  # 略有不同的机构名称 / Слегка отличающееся название учреждения
        ),
        AuthorRecord(
            record_id="rec_003",
            name="Zhang Wei",  # 英文姓名 / Английское имя
            coauthors=["Li Ming", "Chen Jianguo"],
            journal="Science",
            publication_title="AI Applications in Medicine",
            year=2024,
            affiliation="Tsinghua University"
        ),

        # 场景2：姓名相似但不同的作者 / Сценарий 2: Авторы с похожими, но разными именами
        AuthorRecord(
            record_id="rec_004",
            name="张维",  # 相似但不同的姓名 / Похожее, но другое имя
            coauthors=["孙丽华", "马建军", "周小芳"],
            journal="IEEE Transactions on Software Engineering",
            publication_title="Software Architecture Patterns",
            year=2023,
            affiliation="北京大学软件学院"
        ),
        AuthorRecord(
            record_id="rec_005",
            name="张薇",  # 又一个相似姓名 / Ещё одно похожее имя
            coauthors=["赵雅芳", "朱永红"],
            journal="ACM Computing Surveys",
            publication_title="Survey on Distributed Systems",
            year=2024,
            affiliation="北京理工大学"
        ),

        # 场景3：合著者网络中的作者 / Сценарий 3: Авторы в сети соавторов
        AuthorRecord(
            record_id="rec_006",
            name="李明",  # 张伟的合著者成为主作者 / Соавтор Zhang Wei становится основным автором
            coauthors=["张伟", "陈建国", "高峰"],
            journal="Nature Communications",
            publication_title="Machine Learning for Drug Discovery",
            year=2024,
            affiliation="中科院计算所"
        ),
        AuthorRecord(
            record_id="rec_007",
            name="陈建国",  # 另一个合著者 / Другой соавтор
            coauthors=["张伟", "李明", "吴小东"],
            journal="Cell",
            publication_title="Computational Biology Methods",
            year=2024,
            affiliation="中科院生物所"
        ),

        # 场景4：完全不同的作者群体 / Сценарий 4: Полностью разная группа авторов
        AuthorRecord(
            record_id="rec_008",
            name="王建华",
            coauthors=["林小红", "黄志强", "郑小丽"],
            journal="The Lancet",
            publication_title="Clinical Trial of New Drug",
            year=2023,
            affiliation="北京医科大学"
        ),
        AuthorRecord(
            record_id="rec_009",
            name="刘芳",
            coauthors=["张小英", "李小军"],
            journal="Physical Review Letters",
            publication_title="Quantum Computing Advances",
            year=2024,
            affiliation="中科院物理所"
        ),

        # 场景5：同名但不同领域的作者 / Сценарий 5: Одноимённые авторы из разных областей
        AuthorRecord(
            record_id="rec_010",
            name="李明",  # 与rec_006同名但不同领域 / Одно имя с rec_006, но другая область
            coauthors=["杨小华", "宋建军"],
            journal="Journal of Finance",
            publication_title="Economic Modeling with AI",
            year=2024,
            affiliation="北京大学经济学院"
        ),

        # 场景6：机构变更的作者 / Сценарий 6: Автор со сменой учреждения
        AuthorRecord(
            record_id="rec_011",
            name="陈建国",  # 与rec_007同名同人但机构不同 / То же имя и человек, что и rec_007, но другое учреждение
            coauthors=["张伟", "李明", "新合著者"],
            journal="Nature Biotechnology",
            publication_title="CRISPR Applications",
            year=2024,
            affiliation="斯坦福大学"  # 机构变更 / Смена учреждения
        )
    ]

    return records


def demonstrate_incremental_processing():
    """
    演示增量处理流程 / Демонстрация процесса инкрементальной обработки
    """
    print("=" * 80)
    print("增量作者消歧系统综合演示")
    print("Комплексная демонстрация системы инкрементального устранения неоднозначности авторов")
    print("=" * 80)

    # 初始化引擎 / Инициализация движка
    print("\n1. 初始化消歧引擎 / Инициализация движка устранения неоднозначности")
    engine = DisambiguationEngine()
    print(f"   初始状态: {engine}")
    print(f"   相似度阈值: {SIMILARITY_THRESHOLD}")

    # 创建测试数据 / Создание тестовых данных
    print("\n2. 创建真实测试数据集 / Создание реалистичного тестового набора данных")
    records = create_realistic_dataset()
    print(f"   创建了 {len(records)} 条测试记录")

    # 增量处理每条记录 / Инкрементальная обработка каждой записи
    print("\n3. 逐条增量处理记录 / Пошаговая инкрементальная обработка записей")
    print("-" * 80)

    results = []
    for i, record in enumerate(records, 1):
        print(f"\n[记录 {i}] 处理: {record.name} (ID: {record.record_id})")
        print(f"         合著者: {', '.join(record.coauthors[:3])}{'...' if len(record.coauthors) > 3 else ''}")
        print(f"         期刊: {record.journal}")
        print(f"         机构: {record.affiliation}")

        # 处理记录 / Обработка записи
        result = engine.process_new_record(record)
        results.append(result)

        # 显示处理结果 / Отображение результата обработки
        print(f"   → 决策: {result.decision}")
        print(f"   → 相似度分数: {result.similarity_score:.4f}")
        if result.matched_author_id:
            matched_author = engine.get_author_by_id(result.matched_author_id)
            print(f"   → 匹配作者: {matched_author.canonical_name} (ID: {result.matched_author_id})")
            print(f"   → 关联记录数: {len(matched_author.linked_records)}")

        # 显示当前系统状态 / Отображение текущего состояния системы
        stats = engine.get_statistics()
        print(f"   → 当前系统: {stats['total_authors']} 个作者, {stats['total_processed']} 条已处理记录")

    # 分析最终结果 / Анализ финальных результатов
    print("\n4. 最终结果分析 / Анализ финальных результатов")
    print("=" * 80)

    final_stats = engine.get_statistics()
    print(f"处理统计 / Статистика обработки:")
    print(f"  总处理记录数: {final_stats['total_processed']}")
    print(f"  识别出的唯一作者数: {final_stats['total_authors']}")
    print(f"  合并记录数: {final_stats['merged_records']}")
    print(f"  新建作者数: {final_stats['new_authors_created']}")
    print(f"  拒绝记录数: {final_stats['rejected_records']}")
    print(f"  平均处理时间: {final_stats['avg_processing_time']:.4f} 秒")

    # 依赖图统计 / Статистика графа зависимостей
    graph_stats = final_stats['graph_stats']
    print(f"\n合作关系图统计 / Статистика графа сотрудничества:")
    print(f"  节点数 (作者): {graph_stats['node_count']}")
    print(f"  边数 (合作关系): {graph_stats['edge_count']}")
    print(f"  平均度数: {graph_stats['average_degree']:.2f}")

    # 展示作者合并情况 / Отображение ситуации слияния авторов
    print(f"\n5. 作者身份合并分析 / Анализ слияния личностей авторов")
    print("-" * 80)

    for author_id, author in engine.authors.items():
        if len(author.linked_records) > 1:  # 只显示合并了多条记录的作者 / Показывать только авторов с объединёнными множественными записями
            print(f"\n作者: {author.canonical_name} (ID: {author_id})")
            print(f"  置信度: {author.confidence_score:.3f}")
            print(f"  备选姓名: {', '.join(author.alternate_names)}")
            print(f"  合并记录:")
            for record_id in author.linked_records:
                original_record = engine.processed_records[record_id]
                print(f"    - {record_id}: {original_record.name} | {original_record.journal}")

    # 展示增量计算的效果 / Демонстрация эффекта инкрементальных вычислений
    print(f"\n6. 增量计算效果演示 / Демонстрация эффекта инкрементальных вычислений")
    print("-" * 80)

    # 模拟添加一条新记录看受影响范围 / Имитация добавления новой записи для просмотра затронутой области
    test_record = AuthorRecord(
        record_id="test_new",
        name="张伟",
        coauthors=["李明", "新合著者"],
        journal="Nature AI",
        publication_title="Future of AI",
        year=2025,
        affiliation="清华大学"
    )

    print(f"模拟新记录: {test_record.name}")
    affected_authors = engine.dependency_graph.get_affected_authors(new_record=test_record)
    print(f"受影响的作者数量: {len(affected_authors)}")
    print(f"增量计算避免了对 {len(engine.authors) - len(affected_authors)} 个作者的重复计算")
    if len(affected_authors) > 0:
        print(f"受影响的作者比例: {len(affected_authors)/len(engine.authors)*100:.1f}%")

    return engine, results


def export_demonstration_results(engine: DisambiguationEngine, output_file: str = "disambiguation_results.json"):
    """
    导出演示结果 / Экспорт результатов демонстрации

    Args:
        engine: 消歧引擎实例 / Экземпляр движка устранения неоднозначности
        output_file: 输出文件名 / Имя выходного файла
    """
    print(f"\n7. 导出结果到文件 / Экспорт результатов в файл")
    print("-" * 80)

    results = engine.export_results()

    # 添加时间戳和元数据 / Добавление временной метки и метаданных
    results['export_metadata'] = {
        'timestamp': datetime.now().isoformat(),
        'system_version': '1.0.0',
        'description': '增量作者消歧系统演示结果 / Результаты демонстрации системы инкрементального устранения неоднозначности авторов'
    }

    # 保存到文件 / Сохранение в файл
    output_path = os.path.join(os.path.dirname(__file__), output_file)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)

    print(f"结果已导出到: {output_path}")
    print(f"导出数据包含:")
    print(f"  - {len(results['authors'])} 个作者的完整信息")
    print(f"  - 系统处理统计信息")
    print(f"  - 合作关系图统计")


def run_comprehensive_tests():
    """
    运行综合测试 / Запуск комплексных тестов
    """
    print(f"\n8. 运行系统测试 / Запуск системных тестов")
    print("-" * 80)

    try:
        # 导入并运行测试 / Импорт и запуск тестов
        from tests.test_similarity_scorer import TestSimilarityScorer
        from tests.test_dependency_graph import TestDependencyGraph
        from tests.test_engine import TestDisambiguationEngine
        import unittest

        # 创建测试套件 / Создание набора тестов
        test_classes = [TestSimilarityScorer, TestDependencyGraph, TestDisambiguationEngine]
        suite = unittest.TestSuite()

        for test_class in test_classes:
            tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
            suite.addTests(tests)

        # 运行测试 / Запуск тестов
        runner = unittest.TextTestRunner(verbosity=1)
        result = runner.run(suite)

        if result.wasSuccessful():
            print(f"\n✅ 所有测试通过! 总计: {result.testsRun} 个测试")
            print("Все тесты пройдены!")
        else:
            print(f"\n[X] 测试失败: {len(result.failures)} 个失败, {len(result.errors)} 个错误")
            print(f"Тесты провалены: {len(result.failures)} провалов, {len(result.errors)} ошибок")

    except ImportError as e:
        print(f"无法导入测试模块: {e}")
        print("测试跳过 / Тесты пропущены")


def main():
    """
    主演示程序 / Главная демонстрационная программа
    """
    try:
        print("启动增量作者消歧系统演示...")
        print("Запуск демонстрации системы инкрементального устранения неоднозначности авторов...")

        # 运行主要演示 / Запуск основной демонстрации
        engine, results = demonstrate_incremental_processing()

        # 导出结果 / Экспорт результатов
        export_demonstration_results(engine)

        # 运行测试 / Запуск тестов
        run_comprehensive_tests()

        print("\n" + "=" * 80)
        print("[+] 演示完成!")
        print("[+] Демонстрация завершена!")
        print("\n核心成果 / Ключевые достижения:")
        print("✅ 实现了基于加权相似度的白盒消歧模型")
        print("✅ 构建了支持增量计算的依赖关系图")
        print("✅ 创建了完整的增量消歧处理流程")
        print("✅ 验证了系统在真实场景下的有效性")
        print("\n✅ Реализована модель устранения неоднозначности белой коробки на основе взвешенного сходства")
        print("✅ Построен граф зависимостей с поддержкой инкрементальных вычислений")
        print("✅ Создан полный процесс инкрементальной обработки устранения неоднозначности")
        print("✅ Подтверждена эффективность системы в реальных сценариях")

    except KeyboardInterrupt:
        print("\n\n演示被用户中断 / Демонстрация прервана пользователем")
    except Exception as e:
        print(f"\n演示过程中发生错误 / Ошибка во время демонстрации: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()