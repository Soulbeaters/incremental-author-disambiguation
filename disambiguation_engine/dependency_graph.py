# -*- coding: utf-8 -*-
"""
依赖关系图 / Граф зависимостей

实现增量计算的核心组件，用于追踪作者间的关联关系并确定受影响的范围
Реализует ключевой компонент инкрементальных вычислений для отслеживания связей между авторами и определения затронутых областей
"""

from typing import Dict, Set, List, Optional, Tuple
from collections import defaultdict, deque
import logging

from models.author import Publication, AuthorRecord


class DependencyGraph:
    """
    作者依赖关系图 / Граф зависимостей авторов

    使用邻接表表示作者间的合作关系，支持增量计算中的影响范围分析
    Использует список смежности для представления отношений сотрудничества между авторами,
    поддерживает анализ области влияния в инкрементальных вычислениях
    """

    def __init__(self, full_scan_threshold: int = 0):
        """
        初始化依赖关系图 / Инициализация графа зависимостей
        
        Args:
            full_scan_threshold: 全扫描阈值。当作者数<=此值时返回全体作者。
                               设为0则禁用全扫描（默认）。
                               Порог полного сканирования. При количестве авторов <= 
                               этого значения возвращаются все авторы. 0 = отключено.
        """
        # P1-1修复：可配置的全扫描阈值 / P1-1 fix: configurable full scan threshold
        self.full_scan_threshold = full_scan_threshold
        
        # 邻接表：author_id -> set of connected author_ids / Список смежности: author_id -> множество связанных author_ids
        self.graph: Dict[str, Set[str]] = defaultdict(set)

        # 作者ID集合，用于快速检查节点存在性 / Множество ID авторов для быстрой проверки существования узлов
        self.authors: Set[str] = set()

        # 合作关系强度统计 / Статистика интенсивности сотрудничества
        self.collaboration_strength: Dict[Tuple[str, str], int] = defaultdict(int)

        # 缓存最近的影响分析结果 / Кэширование недавних результатов анализа влияния
        self.influence_cache: Dict[str, Set[str]] = {}
        self.cache_max_size = 1000

        # 日志记录器 / Логгер
        self.logger = logging.getLogger(__name__)

    def add_author(self, author_id: str) -> None:
        """
        添加作者节点 / Добавить узел автора

        Args:
            author_id: 作者唯一标识符 / Уникальный идентификатор автора
        """
        if author_id and author_id not in self.authors:
            self.authors.add(author_id)
            # 确保在邻接表中存在该节点 / Обеспечение существования узла в списке смежности
            if author_id not in self.graph:
                self.graph[author_id] = set()

            self.logger.debug(f"添加作者节点: {author_id}")

    def add_coauthor_relationship(self, author_id_1: str, author_id_2: str, weight: int = 1) -> None:
        """
        添加合著者关系边 / Добавить ребро отношения соавторства

        Args:
            author_id_1: 第一个作者ID / ID первого автора
            author_id_2: 第二个作者ID / ID второго автора
            weight: 关系权重（合作次数）/ Вес отношения (количество сотрудничеств)
        """
        if not author_id_1 or not author_id_2 or author_id_1 == author_id_2:
            return

        # 确保两个作者都在图中 / Обеспечение присутствия обоих авторов в графе
        self.add_author(author_id_1)
        self.add_author(author_id_2)

        # 添加无向边 / Добавление неориентированного ребра
        self.graph[author_id_1].add(author_id_2)
        self.graph[author_id_2].add(author_id_1)

        # 更新合作强度 / Обновление интенсивности сотрудничества
        edge_key = tuple(sorted([author_id_1, author_id_2]))
        self.collaboration_strength[edge_key] += weight

        # 清除相关的缓存 / Очистка соответствующего кэша
        self._clear_influence_cache([author_id_1, author_id_2])

        self.logger.debug(f"添加合著者关系: {author_id_1} <-> {author_id_2}, 权重: {weight}")

    def remove_author(self, author_id: str) -> None:
        """
        移除作者节点及其所有关系 / Удалить узел автора и все его отношения

        Args:
            author_id: 作者ID / ID автора
        """
        if author_id not in self.authors:
            return

        # 获取所有相邻作者 / Получение всех смежных авторов
        neighbors = self.graph[author_id].copy()

        # 移除与该作者相关的所有边 / Удаление всех рёбер, связанных с автором
        for neighbor_id in neighbors:
            self.graph[neighbor_id].discard(author_id)
            # 清理合作强度记录 / Очистка записей интенсивности сотрудничества
            edge_key = tuple(sorted([author_id, neighbor_id]))
            if edge_key in self.collaboration_strength:
                del self.collaboration_strength[edge_key]

        # 移除作者节点 / Удаление узла автора
        del self.graph[author_id]
        self.authors.discard(author_id)

        # 清除相关缓存 / Очистка соответствующего кэша
        self._clear_influence_cache([author_id] + list(neighbors))

        self.logger.debug(f"移除作者节点: {author_id}")

    def get_neighbors(self, author_id: str) -> Set[str]:
        """
        获取作者的直接合著者 / Получить непосредственных соавторов автора

        Args:
            author_id: 作者ID / ID автора

        Returns:
            Set[str]: 合著者ID集合 / Множество ID соавторов
        """
        return self.graph.get(author_id, set()).copy()

    def get_collaboration_strength(self, author_id_1: str, author_id_2: str) -> int:
        """
        获取两位作者间的合作强度 / Получить интенсивность сотрудничества между двумя авторами

        Args:
            author_id_1: 第一个作者ID / ID первого автора
            author_id_2: 第二个作者ID / ID второго автора

        Returns:
            int: 合作强度（合作次数）/ Интенсивность сотрудничества (количество сотрудничеств)
        """
        edge_key = tuple(sorted([author_id_1, author_id_2]))
        return self.collaboration_strength.get(edge_key, 0)

    def get_affected_authors(self, new_publication: Optional[Publication] = None,
                           new_record: Optional[AuthorRecord] = None,
                           max_depth: int = 2) -> Set[str]:
        """
        获取受影响的作者集合（增量计算的核心）/ Получить множество затронутых авторов (ядро инкрементальных вычислений)

        当新的出版物或记录被添加时，确定需要重新评估的作者范围
        При добавлении новой публикации или записи определяет область авторов, требующих переоценки

        Args:
            new_publication: 新出版物 / Новая публикация
            new_record: 新作者记录 / Новая запись автора
            max_depth: 最大搜索深度 / Максимальная глубина поиска

        Returns:
            Set[str]: 受影响的作者ID集合 / Множество ID затронутых авторов
        """
        affected_authors = set()

        # 情况1：处理新出版物 / Случай 1: Обработка новой публикации
        if new_publication:
            # 直接影响：出版物中的所有合著者 / Прямое влияние: все соавторы в публикации
            directly_affected = set(new_publication.coauthor_ids)
            affected_authors.update(directly_affected)

            # 间接影响：合著者的邻居们 / Косвенное влияние: соседи соавторов
            for author_id in directly_affected:
                affected_authors.update(self._get_authors_within_depth(author_id, max_depth))

        # 情况2：处理新作者记录 / Случай 2: Обработка новой записи автора
        elif new_record:
            # 基于合著者姓名查找可能相关的作者 / Поиск потенциально связанных авторов по именам соавторов
            potential_matches = self._find_potential_author_matches(new_record)
            affected_authors.update(potential_matches)

            # 扩展到邻居 / Расширение до соседей
            for author_id in list(potential_matches):
                affected_authors.update(self._get_authors_within_depth(author_id, max_depth))

        # 限制结果大小以控制计算复杂度 / Ограничение размера результата для управления вычислительной сложностью
        if len(affected_authors) > 1000:
            self.logger.warning(f"受影响作者数量过多: {len(affected_authors)}, 将进行截断")
            # 优先保留高合作强度的作者 / Приоритет авторам с высокой интенсивностью сотрудничества
            affected_authors = self._prioritize_high_collaboration_authors(affected_authors, 1000)

        self.logger.debug(f"识别出受影响的作者数量: {len(affected_authors)}")
        return affected_authors

    def _get_authors_within_depth(self, start_author_id: str, max_depth: int) -> Set[str]:
        """
        获取指定深度内的所有作者 / Получить всех авторов в пределах указанной глубины

        使用BFS算法遍历图 / Использует алгоритм BFS для обхода графа

        Args:
            start_author_id: 起始作者ID / ID начального автора
            max_depth: 最大深度 / Максимальная глубина

        Returns:
            Set[str]: 指定深度内的作者ID集合 / Множество ID авторов в пределах глубины
        """
        if start_author_id not in self.authors or max_depth <= 0:
            return set()

        # 检查缓存 / Проверка кэша
        cache_key = f"{start_author_id}_{max_depth}"
        if cache_key in self.influence_cache:
            return self.influence_cache[cache_key].copy()

        visited = set()
        queue = deque([(start_author_id, 0)])  # (author_id, depth)

        while queue:
            current_author, current_depth = queue.popleft()

            if current_author in visited or current_depth > max_depth:
                continue

            visited.add(current_author)

            # 添加邻居到队列 / Добавление соседей в очередь
            if current_depth < max_depth:
                for neighbor in self.graph.get(current_author, set()):
                    if neighbor not in visited:
                        queue.append((neighbor, current_depth + 1))

        # 缓存结果 / Кэширование результата
        self._cache_influence_result(cache_key, visited)

        return visited.copy()

    def _find_potential_author_matches(self, record: AuthorRecord) -> Set[str]:
        """
        基于记录信息查找可能匹配的作者 / Поиск потенциально соответствующих авторов на основе информации записи

        Args:
            record: 作者记录 / Запись автора

        Returns:
            Set[str]: 可能匹配的作者ID集合 / Множество ID потенциально соответствующих авторов
        """
        potential_matches = set()

        # P1-1修复：使用可配置的全扫描阈值 / P1-1 fix: use configurable full_scan_threshold
        # 默认为0时禁用全扫描 / По умолчанию 0 = отключено
        if self.full_scan_threshold > 0 and len(self.authors) <= self.full_scan_threshold:
            # 小规模图且显式启用全扫描时返回所有作者
            # При небольшом графе и явно включённом полном сканировании возвращаем всех авторов
            potential_matches = self.authors.copy()
            self.logger.debug(f"Full scan: returning all {len(self.authors)} authors (threshold={self.full_scan_threshold})")
        else:
            # 使用blocking策略：返回空集（由外层blocking机制提供候选）
            # Использование blocking стратегии: возврат пустого множества (кандидаты предоставляются внешним механизмом blocking)
            self.logger.debug(f"Using blocking strategy (authors={len(self.authors)}, threshold={self.full_scan_threshold})")

        return potential_matches

    def _prioritize_high_collaboration_authors(self, authors: Set[str], limit: int) -> Set[str]:
        """
        优先选择高合作强度的作者 / Приоритет авторам с высокой интенсивностью сотрудничества

        Args:
            authors: 作者集合 / Множество авторов
            limit: 限制数量 / Лимит количества

        Returns:
            Set[str]: 优先选择的作者集合 / Множество приоритетных авторов
        """
        # 计算每个作者的总合作强度 / Расчёт общей интенсивности сотрудничества для каждого автора
        author_scores = {}
        for author_id in authors:
            total_strength = 0
            for neighbor_id in self.graph.get(author_id, set()):
                total_strength += self.get_collaboration_strength(author_id, neighbor_id)
            author_scores[author_id] = total_strength

        # 按合作强度排序并取前limit个 / Сортировка по интенсивности сотрудничества и взятие первых limit
        sorted_authors = sorted(author_scores.keys(), key=lambda x: author_scores[x], reverse=True)
        return set(sorted_authors[:limit])

    def _cache_influence_result(self, cache_key: str, result: Set[str]) -> None:
        """
        缓存影响分析结果 / Кэширование результата анализа влияния

        Args:
            cache_key: 缓存键 / Ключ кэша
            result: 结果集合 / Множество результатов
        """
        if len(self.influence_cache) >= self.cache_max_size:
            # 简单的LRU：删除一半的缓存 / Простой LRU: удаление половины кэша
            keys_to_remove = list(self.influence_cache.keys())[:self.cache_max_size // 2]
            for key in keys_to_remove:
                del self.influence_cache[key]

        self.influence_cache[cache_key] = result.copy()

    def _clear_influence_cache(self, author_ids: List[str]) -> None:
        """
        清除相关作者的影响缓存 / Очистка кэша влияния для соответствующих авторов

        Args:
            author_ids: 需要清除缓存的作者ID列表 / Список ID авторов для очистки кэша
        """
        keys_to_remove = []
        for cache_key in self.influence_cache:
            # 如果缓存键包含任何相关作者，则删除 / Удаление, если ключ кэша содержит любого соответствующего автора
            for author_id in author_ids:
                if author_id in cache_key:
                    keys_to_remove.append(cache_key)
                    break

        for key in keys_to_remove:
            del self.influence_cache[key]

    def get_graph_stats(self) -> Dict:
        """
        获取图的统计信息 / Получить статистику графа

        Returns:
            Dict: 统计信息字典 / Словарь статистической информации
        """
        total_edges = sum(len(neighbors) for neighbors in self.graph.values()) // 2  # 无向图边数 / Количество рёбер неориентированного графа
        avg_degree = total_edges * 2 / len(self.authors) if self.authors else 0

        return {
            'node_count': len(self.authors),  # 节点数 / Количество узлов
            'edge_count': total_edges,  # 边数 / Количество рёбер
            'average_degree': avg_degree,  # 平均度数 / Средняя степень
            'collaboration_relationships': len(self.collaboration_strength),  # 合作关系数 / Количество отношений сотрудничества
            'cache_size': len(self.influence_cache)  # 缓存大小 / Размер кэша
        }

    def __str__(self) -> str:
        """字符串表示 / Строковое представление"""
        stats = self.get_graph_stats()
        return f"DependencyGraph(nodes={stats['node_count']}, edges={stats['edge_count']}, avg_degree={stats['average_degree']:.2f})"