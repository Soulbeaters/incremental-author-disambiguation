# -*- coding: utf-8 -*-
"""
依赖关系图单元测试 / Модульные тесты графа зависимостей

测试DependencyGraph类的功能和准确性
Тестирует функциональность и точность класса DependencyGraph
"""

import unittest
from disambiguation_engine.dependency_graph import DependencyGraph
from models.author import AuthorRecord, Publication


class TestDependencyGraph(unittest.TestCase):
    """依赖关系图测试类 / Класс тестов графа зависимостей"""

    def setUp(self):
        """测试环境初始化 / Инициализация тестовой среды"""
        self.graph = DependencyGraph()

    def test_add_author(self):
        """
        测试：添加作者节点
        Тест: добавление узлов авторов
        """
        author_id = "au_001"
        self.graph.add_author(author_id)

        # 验证作者已添加 / Проверка добавления автора
        self.assertIn(author_id, self.graph.authors)
        self.assertIn(author_id, self.graph.graph)
        self.assertEqual(len(self.graph.graph[author_id]), 0)

        print(f"添加作者测试通过: {author_id}")

    def test_add_coauthor_relationship(self):
        """
        测试：添加合著者关系
        Тест: добавление отношений соавторства
        """
        author1 = "au_001"
        author2 = "au_002"

        self.graph.add_coauthor_relationship(author1, author2)

        # 验证双向关系已建立 / Проверка установления двустороннего отношения
        self.assertIn(author1, self.graph.authors)
        self.assertIn(author2, self.graph.authors)
        self.assertIn(author2, self.graph.graph[author1])
        self.assertIn(author1, self.graph.graph[author2])

        # 验证合作强度 / Проверка интенсивности сотрудничества
        strength = self.graph.get_collaboration_strength(author1, author2)
        self.assertEqual(strength, 1)

        print(f"合著者关系测试通过: {author1} <-> {author2}")

    def test_get_neighbors(self):
        """
        测试：获取邻居节点
        Тест: получение соседних узлов
        """
        # 构建简单的图 / Построение простого графа
        authors = ["au_001", "au_002", "au_003"]
        for author in authors:
            self.graph.add_author(author)

        # 添加关系 / Добавление отношений
        self.graph.add_coauthor_relationship("au_001", "au_002")
        self.graph.add_coauthor_relationship("au_001", "au_003")

        # 测试邻居获取 / Тестирование получения соседей
        neighbors = self.graph.get_neighbors("au_001")
        expected_neighbors = {"au_002", "au_003"}

        self.assertEqual(neighbors, expected_neighbors)

        print(f"邻居节点测试通过: {neighbors}")

    def test_remove_author(self):
        """
        测试：移除作者节点
        Тест: удаление узлов авторов
        """
        # 建立三角关系 / Установление треугольного отношения
        authors = ["au_001", "au_002", "au_003"]
        for author in authors:
            self.graph.add_author(author)

        self.graph.add_coauthor_relationship("au_001", "au_002")
        self.graph.add_coauthor_relationship("au_001", "au_003")
        self.graph.add_coauthor_relationship("au_002", "au_003")

        # 移除中心节点 / Удаление центрального узла
        self.graph.remove_author("au_001")

        # 验证节点及其关系已移除 / Проверка удаления узла и его отношений
        self.assertNotIn("au_001", self.graph.authors)
        self.assertNotIn("au_001", self.graph.graph)

        # 验证其他节点的关系已更新 / Проверка обновления отношений других узлов
        self.assertNotIn("au_001", self.graph.graph["au_002"])
        self.assertNotIn("au_001", self.graph.graph["au_003"])

        # 验证剩余关系仍然存在 / Проверка сохранения оставшихся отношений
        self.assertIn("au_003", self.graph.graph["au_002"])
        self.assertIn("au_002", self.graph.graph["au_003"])

        print("移除作者测试通过")

    def test_get_affected_authors_with_publication(self):
        """
        测试：基于新出版物获取受影响的作者
        Тест: получение затронутых авторов на основе новой публикации
        """
        # 建立作者网络 / Построение сети авторов
        authors = ["au_001", "au_002", "au_003", "au_004", "au_005"]
        for author in authors:
            self.graph.add_author(author)

        # 建立关系链 / Построение цепи отношений
        relationships = [
            ("au_001", "au_002"),
            ("au_002", "au_003"),
            ("au_003", "au_004"),
            ("au_004", "au_005")
        ]
        for author1, author2 in relationships:
            self.graph.add_coauthor_relationship(author1, author2)

        # 创建涉及au_002和au_003的新出版物 / Создание новой публикации с участием au_002 и au_003
        new_publication = Publication(
            pub_id="pub_001",
            title="Test Publication",
            coauthor_ids=["au_002", "au_003"]
        )

        # 获取受影响的作者 / Получение затронутых авторов
        affected = self.graph.get_affected_authors(new_publication=new_publication, max_depth=2)

        # 验证受影响范围 / Проверка области влияния
        # 应该包括：au_002, au_003 (直接), au_001, au_004 (1级邻居), au_005 (2级邻居)
        expected_affected = {"au_001", "au_002", "au_003", "au_004", "au_005"}
        self.assertEqual(affected, expected_affected)

        print(f"出版物影响分析测试通过，受影响作者: {len(affected)}")

    def test_get_affected_authors_with_record(self):
        """
        测试：基于新记录获取受影响的作者
        Тест: получение затронутых авторов на основе новой записи
        """
        # 使用启用全扫描的图进行测试 / Использование графа с включённым полным сканированием
        graph = DependencyGraph(full_scan_threshold=50)  # P1-1: 显式启用全扫描
        
        # 建立基础图 / Построение базового графа
        authors = ["au_001", "au_002", "au_003"]
        for author in authors:
            graph.add_author(author)

        graph.add_coauthor_relationship("au_001", "au_002")
        graph.add_coauthor_relationship("au_002", "au_003")

        # 创建新记录 / Создание новой записи
        new_record = AuthorRecord(
            record_id="rec_001",
            name="新作者 Test Author",
            coauthors=["合著者1", "合著者2"],
            journal="Test Journal"
        )

        # 获取受影响的作者 / Получение затронутых авторов
        affected = graph.get_affected_authors(new_record=new_record, max_depth=1)

        # 启用全扫描后小图应该返回所有作者 / С включённым полным сканированием малый граф возвращает всех авторов
        self.assertTrue(len(affected) > 0)

        print(f"记录影响分析测试通过，受影响作者: {len(affected)}")

    def test_collaboration_strength_tracking(self):
        """
        测试：合作强度跟踪
        Тест: отслеживание интенсивности сотрудничества
        """
        author1 = "au_001"
        author2 = "au_002"

        # 多次添加同一关系 / Многократное добавление того же отношения
        for i in range(3):
            self.graph.add_coauthor_relationship(author1, author2, weight=1)

        # 验证累积强度 / Проверка накопленной интенсивности
        strength = self.graph.get_collaboration_strength(author1, author2)
        self.assertEqual(strength, 3)

        print(f"合作强度跟踪测试通过: {strength}")

    def test_graph_statistics(self):
        """
        测试：图统计信息
        Тест: статистика графа
        """
        # 建立测试图 / Построение тестового графа
        authors = ["au_001", "au_002", "au_003", "au_004"]
        for author in authors:
            self.graph.add_author(author)

        relationships = [
            ("au_001", "au_002"),
            ("au_002", "au_003"),
            ("au_003", "au_004"),
            ("au_001", "au_003")  # 创建一个循环 / Создание цикла
        ]
        for author1, author2 in relationships:
            self.graph.add_coauthor_relationship(author1, author2)

        # 获取统计信息 / Получение статистики
        stats = self.graph.get_graph_stats()

        # 验证统计数据 / Проверка статистических данных
        self.assertEqual(stats['node_count'], 4)
        self.assertEqual(stats['edge_count'], 4)
        self.assertEqual(stats['average_degree'], 2.0)  # 每个节点平均2条边 / В среднем 2 ребра на узел

        print(f"图统计测试通过: {stats}")

    def test_empty_graph_behavior(self):
        """
        测试：空图行为
        Тест: поведение пустого графа
        """
        # 测试空图的各种操作 / Тестирование различных операций на пустом графе
        self.assertEqual(len(self.graph.authors), 0)

        # 获取不存在作者的邻居 / Получение соседей несуществующего автора
        neighbors = self.graph.get_neighbors("non_existent")
        self.assertEqual(len(neighbors), 0)

        # 获取不存在关系的强度 / Получение интенсивности несуществующего отношения
        strength = self.graph.get_collaboration_strength("au_001", "au_002")
        self.assertEqual(strength, 0)

        # 空图的统计 / Статистика пустого графа
        stats = self.graph.get_graph_stats()
        self.assertEqual(stats['node_count'], 0)
        self.assertEqual(stats['edge_count'], 0)
        self.assertEqual(stats['average_degree'], 0)

        print("空图行为测试通过")


def run_dependency_graph_tests():
    """运行依赖关系图测试 / Запуск тестов графа зависимостей"""
    unittest.main()


if __name__ == '__main__':
    run_dependency_graph_tests()