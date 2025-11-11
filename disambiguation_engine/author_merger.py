# -*- coding: utf-8 -*-
"""
作者合并引擎 / Движок слияния авторов / Author Merger Engine

防止创建重复作者，通过多维相似度计算识别同一作者
Предотвращение создания дубликатов авторов через многомерный расчёт сходства
Prevent duplicate author creation through multi-dimensional similarity calculation

中文注释：作者合并模块，实现多维相似度匹配
Русский комментарий: Модуль слияния авторов с многомерным сопоставлением сходства
"""

import logging
from typing import List, Optional, Tuple, Set, Dict, Any
try:
    from Levenshtein import ratio
except ImportError:
    # 如果没有Levenshtein库，使用简单的相似度计算
    # Если библиотека Levenshtein отсутствует, используем простое вычисление
    def ratio(s1: str, s2: str) -> float:
        """简单的字符串相似度计算 / Простое вычисление сходства строк"""
        if s1 == s2:
            return 1.0
        if not s1 or not s2:
            return 0.0
        set1 = set(s1.lower().split())
        set2 = set(s2.lower().split())
        if not set1 or not set2:
            return 0.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0


from models.author import Author


class AuthorMerger:
    """
    作者合并引擎 / Движок слияния авторов

    通过多维相似度计算防止重复作者创建
    Предотвращение дубликатов через многомерный расчёт сходства
    Prevent duplicate authors through multi-dimensional similarity

    相似度权重配置 / Конфигурация весов сходства / Similarity weight configuration:
    - 姓名相似度 / Сходство имён / Name similarity: 40%
    - ORCID匹配 / Совпадение ORCID / ORCID match: 30%
    - 合著者重叠 / Пересечение соавторов / Coauthor overlap: 15%
    - 期刊重叠 / Пересечение журналов / Journal overlap: 10%
    - 机构相似度 / Сходство аффилиаций / Affiliation similarity: 5%
    """

    def __init__(
        self,
        similarity_threshold: float = 0.85,
        name_weight: float = 0.40,
        orcid_weight: float = 0.30,
        coauthor_weight: float = 0.15,
        journal_weight: float = 0.10,
        affiliation_weight: float = 0.05
    ):
        """
        初始化作者合并引擎 / Инициализация движка слияния

        参数 / Параметры / Parameters:
            similarity_threshold: 判定为同一作者的相似度阈值 [0-1]
                                 Порог сходства для определения того же автора
            name_weight: 姓名相似度权重 / Вес сходства имён
            orcid_weight: ORCID匹配权重 / Вес совпадения ORCID
            coauthor_weight: 合著者重叠权重 / Вес пересечения соавторов
            journal_weight: 期刊重叠权重 / Вес пересечения журналов
            affiliation_weight: 机构相似度权重 / Вес сходства аффилиаций
        """
        self.similarity_threshold = similarity_threshold

        # 权重配置 / Конфигурация весов / Weight configuration
        self.weights = {
            'name': name_weight,
            'orcid': orcid_weight,
            'coauthor': coauthor_weight,
            'journal': journal_weight,
            'affiliation': affiliation_weight
        }

        # 验证权重和为1 / Проверка суммы весов / Validate weights sum to 1
        total_weight = sum(self.weights.values())
        if abs(total_weight - 1.0) > 0.01:
            raise ValueError(
                f"权重和必须为1.0，当前为{total_weight} / "
                f"Сумма весов должна быть 1.0, текущая: {total_weight}"
            )

        self.logger = logging.getLogger(__name__)

    def find_matching_author(
        self,
        candidate: Dict[str, Any],
        existing_authors: List[Author]
    ) -> Tuple[Optional[Author], float]:
        """
        在现有作者中查找匹配的作者 / Поиск совпадающего автора среди существующих

        参数 / Параметры / Parameters:
            candidate: 候选作者数据（字典格式）/ Данные кандидата (формат словаря)
            existing_authors: 现有作者列表 / Список существующих авторов

        返回 / Возвращает / Returns:
            (matched_author, similarity_score) 元组
            如果没有找到匹配，返回 (None, 0.0)
            Кортеж (совпадающий_автор, оценка_сходства)
            Если не найдено, возвращает (None, 0.0)
        """
        if not existing_authors:
            return None, 0.0

        best_match = None
        best_similarity = 0.0

        candidate_name = candidate.get('name', '')
        candidate_orcid = candidate.get('orcid', '')

        for author in existing_authors:
            # 计算综合相似度 / Расчёт комплексного сходства
            similarity = self._calculate_comprehensive_similarity(
                candidate,
                author
            )

            # 记录详细信息 / Логирование деталей
            self.logger.debug(
                f"Comparing '{candidate_name}' with '{author.canonical_name}': "
                f"similarity={similarity:.3f}"
            )

            # 更新最佳匹配 / Обновление лучшего совпадения
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = author

        # 检查是否超过阈值 / Проверка порога
        if best_similarity >= self.similarity_threshold:
            self.logger.info(
                f"找到匹配作者 / Найдено совпадение: '{candidate_name}' -> "
                f"'{best_match.canonical_name}' (similarity={best_similarity:.3f})"
            )
            return best_match, best_similarity
        else:
            self.logger.debug(
                f"未找到匹配 / Совпадение не найдено: '{candidate_name}' "
                f"(best_similarity={best_similarity:.3f} < threshold={self.similarity_threshold})"
            )
            return None, 0.0

    def _calculate_comprehensive_similarity(
        self,
        candidate: Dict[str, Any],
        author: Author
    ) -> float:
        """
        计算综合相似度 / Расчёт комплексного сходства

        使用多维特征的加权组合 / Взвешенная комбинация многомерных признаков

        参数 / Параметры / Parameters:
            candidate: 候选作者数据 / Данные кандидата
            author: 现有作者对象 / Существующий объект автора

        返回 / Возвращает / Returns:
            综合相似度分数 [0.0-1.0] / Комплексная оценка сходства
        """
        scores = {}

        # 1. 姓名相似度 (40%) / Сходство имён
        scores['name'] = self._calculate_name_similarity(
            candidate.get('name', ''),
            author
        )

        # 2. ORCID匹配 (30%) / Совпадение ORCID
        scores['orcid'] = self._calculate_orcid_similarity(
            candidate.get('orcid', ''),
            author
        )

        # 3. 合著者重叠 (15%) / Пересечение соавторов
        scores['coauthor'] = self._calculate_coauthor_overlap(
            set(candidate.get('coauthors', [])),
            author.coauthor_ids
        )

        # 4. 期刊重叠 (10%) / Пересечение журналов
        scores['journal'] = self._calculate_journal_overlap(
            set(candidate.get('journals', [])),
            author.journals
        )

        # 5. 机构相似度 (5%) / Сходство аффилиаций
        scores['affiliation'] = self._calculate_affiliation_similarity(
            candidate.get('affiliation', []),
            author.affiliations
        )

        # 计算加权总分 / Расчёт взвешенной суммы
        total_score = sum(
            scores[key] * self.weights[key]
            for key in scores.keys()
        )

        # 详细日志 / Детальное логирование
        self.logger.debug(
            f"Similarity breakdown: name={scores['name']:.2f}, "
            f"orcid={scores['orcid']:.2f}, coauthor={scores['coauthor']:.2f}, "
            f"journal={scores['journal']:.2f}, affiliation={scores['affiliation']:.2f} "
            f"-> total={total_score:.3f}"
        )

        return total_score

    def _calculate_name_similarity(self, candidate_name: str, author: Author) -> float:
        """
        计算姓名相似度 / Расчёт сходства имён

        检查候选姓名与作者的规范姓名和所有备选姓名的相似度
        Проверка сходства имени кандидата с каноническим именем автора и всеми альтернативными

        参数 / Параметры / Parameters:
            candidate_name: 候选作者姓名 / Имя кандидата
            author: 现有作者对象 / Существующий объект автора

        返回 / Возвращает / Returns:
            最高的姓名相似度 [0.0-1.0] / Максимальное сходство имён
        """
        if not candidate_name:
            return 0.0

        # 标准化姓名 / Нормализация имён
        candidate_normalized = self._normalize_name(candidate_name)

        # 检查所有备选姓名 / Проверка всех альтернативных имён
        max_similarity = 0.0

        for author_name in author.alternate_names:
            author_normalized = self._normalize_name(author_name)

            # 精确匹配 / Точное совпадение
            if candidate_normalized == author_normalized:
                return 1.0

            # 模糊匹配 / Нечёткое совпадение
            similarity = ratio(candidate_normalized, author_normalized)
            max_similarity = max(max_similarity, similarity)

        return max_similarity

    def _normalize_name(self, name: str) -> str:
        """
        标准化姓名 / Нормализация имени

        参数 / Параметры / Parameters:
            name: 原始姓名 / Исходное имя

        返回 / Возвращает / Returns:
            标准化后的姓名 / Нормализованное имя
        """
        import re

        if not name:
            return ''

        # 转小写 / Нижний регистр
        name = name.lower().strip()

        # 移除标点符号 / Удаление пунктуации
        name = re.sub(r'[^\w\s]', '', name)

        # 移除多余空格 / Удаление лишних пробелов
        name = ' '.join(name.split())

        return name

    def _calculate_orcid_similarity(self, candidate_orcid: str, author: Author) -> float:
        """
        计算ORCID相似度 / Расчёт сходства ORCID

        ORCID是唯一标识符，要么完全匹配(1.0)，要么不匹配(0.0)
        ORCID - уникальный идентификатор, либо полное совпадение (1.0), либо нет (0.0)

        参数 / Параметры / Parameters:
            candidate_orcid: 候选作者的ORCID / ORCID кандидата
            author: 现有作者对象 / Существующий объект автора

        返回 / Возвращает / Returns:
            1.0 如果匹配，0.0 如果不匹配或缺失 / 1.0 если совпадает, 0.0 иначе
        """
        # 如果候选者没有ORCID，不能判定 / Если у кандидата нет ORCID, не определяется
        if not candidate_orcid:
            return 0.0

        # 如果现有作者没有ORCID，不能判定 / Если у автора нет ORCID, не определяется
        if not author.orcid:
            return 0.0

        # 清理ORCID格式 / Очистка формата ORCID
        candidate_orcid_clean = self._clean_orcid(candidate_orcid)
        author_orcid_clean = self._clean_orcid(author.orcid)

        # ORCID完全匹配 / Полное совпадение ORCID
        if candidate_orcid_clean == author_orcid_clean:
            return 1.0

        return 0.0

    def _clean_orcid(self, orcid: str) -> str:
        """
        清理ORCID格式 / Очистка формата ORCID

        参数 / Параметры / Parameters:
            orcid: 原始ORCID / Исходный ORCID

        返回 / Возвращает / Returns:
            清理后的ORCID / Очищенный ORCID
        """
        if not orcid:
            return ''

        # 移除URL前缀 / Удаление URL префикса
        orcid = orcid.replace('http://orcid.org/', '')
        orcid = orcid.replace('https://orcid.org/', '')

        return orcid.strip()

    def _calculate_coauthor_overlap(
        self,
        candidate_coauthors: Set[str],
        author_coauthors: Set[str]
    ) -> float:
        """
        计算合著者重叠度 / Расчёт пересечения соавторов

        使用Jaccard相似度 / Использование сходства Жаккара

        参数 / Параметры / Parameters:
            candidate_coauthors: 候选作者的合著者集合 / Множество соавторов кандидата
            author_coauthors: 现有作者的合著者集合 / Множество соавторов автора

        返回 / Возвращает / Returns:
            Jaccard相似度 [0.0-1.0] / Сходство Жаккара
        """
        if not candidate_coauthors or not author_coauthors:
            return 0.0

        # Jaccard相似度：交集/并集 / Сходство Жаккара: пересечение/объединение
        intersection = len(candidate_coauthors & author_coauthors)
        union = len(candidate_coauthors | author_coauthors)

        return intersection / union if union > 0 else 0.0

    def _calculate_journal_overlap(
        self,
        candidate_journals: Set[str],
        author_journals: Set[str]
    ) -> float:
        """
        计算期刊重叠度 / Расчёт пересечения журналов

        使用Jaccard相似度 / Использование сходства Жаккара

        参数 / Параметры / Parameters:
            candidate_journals: 候选作者的期刊集合 / Множество журналов кандидата
            author_journals: 现有作者的期刊集合 / Множество журналов автора

        返回 / Возвращает / Returns:
            Jaccard相似度 [0.0-1.0] / Сходство Жаккара
        """
        if not candidate_journals or not author_journals:
            return 0.0

        # 标准化期刊名称 / Нормализация названий журналов
        candidate_normalized = {self._normalize_journal(j) for j in candidate_journals}
        author_normalized = {self._normalize_journal(j) for j in author_journals}

        # Jaccard相似度 / Сходство Жаккара
        intersection = len(candidate_normalized & author_normalized)
        union = len(candidate_normalized | author_normalized)

        return intersection / union if union > 0 else 0.0

    def _normalize_journal(self, journal_name: str) -> str:
        """
        标准化期刊名称 / Нормализация названия журнала

        参数 / Параметры / Parameters:
            journal_name: 原始期刊名 / Исходное название журнала

        返回 / Возвращает / Returns:
            标准化后的期刊名 / Нормализованное название
        """
        import re

        if not journal_name:
            return ''

        # 转小写 / Нижний регистр
        name = journal_name.lower().strip()

        # 移除"journal of", "the"等常见词 / Удаление распространённых слов
        name = re.sub(r'\bthe\b', '', name)
        name = re.sub(r'\bjournal of\b', '', name)
        name = re.sub(r'\bjournal\b', '', name)

        # 移除标点和多余空格 / Удаление пунктуации и лишних пробелов
        name = re.sub(r'[^\w\s]', '', name)
        name = ' '.join(name.split())

        return name

    def _calculate_affiliation_similarity(
        self,
        candidate_affiliations: List[str],
        author_affiliations: Set[str]
    ) -> float:
        """
        计算机构相似度 / Расчёт сходства аффилиаций

        参数 / Параметры / Parameters:
            candidate_affiliations: 候选作者的机构列表 / Список аффилиаций кандидата
            author_affiliations: 现有作者的机构集合 / Множество аффилиаций автора

        返回 / Возвращает / Returns:
            最高的机构相似度 [0.0-1.0] / Максимальное сходство аффилиаций
        """
        if not candidate_affiliations or not author_affiliations:
            return 0.0

        max_similarity = 0.0

        for candidate_aff in candidate_affiliations:
            candidate_normalized = self._normalize_affiliation(candidate_aff)

            for author_aff in author_affiliations:
                author_normalized = self._normalize_affiliation(author_aff)

                # 精确匹配 / Точное совпадение
                if candidate_normalized == author_normalized:
                    return 1.0

                # 模糊匹配 / Нечёткое совпадение
                similarity = ratio(candidate_normalized, author_normalized)
                max_similarity = max(max_similarity, similarity)

        return max_similarity

    def _normalize_affiliation(self, affiliation: str) -> str:
        """
        标准化机构名称 / Нормализация названия учреждения

        参数 / Параметры / Parameters:
            affiliation: 原始机构名 / Исходное название

        返回 / Возвращает / Returns:
            标准化后的机构名 / Нормализованное название
        """
        import re

        if not affiliation:
            return ''

        # 转小写 / Нижний регистр
        aff = affiliation.lower().strip()

        # 移除常见后缀 / Удаление распространённых суффиксов
        aff = re.sub(r'\buniversity\b', 'univ', aff)
        aff = re.sub(r'\binstitute\b', 'inst', aff)
        aff = re.sub(r'\bdepartment\b', 'dept', aff)

        # 移除标点和多余空格 / Удаление пунктуации и лишних пробелов
        aff = re.sub(r'[^\w\s]', '', aff)
        aff = ' '.join(aff.split())

        return aff

    def merge_authors(
        self,
        target_author: Author,
        source_author: Author
    ) -> Author:
        """
        合并两个作者实体 / Слияние двух сущностей автора

        将source_author的所有信息合并到target_author中
        Слияние всей информации из source_author в target_author

        参数 / Параметры / Parameters:
            target_author: 目标作者（保留）/ Целевой автор (сохраняется)
            source_author: 源作者（将被合并）/ Исходный автор (будет объединён)

        返回 / Возвращает / Returns:
            合并后的作者对象 / Объединённый объект автора
        """
        self.logger.info(
            f"合并作者 / Слияние авторов: "
            f"'{source_author.canonical_name}' -> '{target_author.canonical_name}'"
        )

        # 合并备选姓名 / Слияние альтернативных имён
        target_author.alternate_names.update(source_author.alternate_names)

        # 合并出版物 / Слияние публикаций
        target_author.publications.update(source_author.publications)
        target_author.publication_count = len(target_author.publications)

        # 合并关联记录 / Слияние связанных записей
        target_author.linked_records.update(source_author.linked_records)

        # 合并合著者 / Слияние соавторов
        target_author.coauthor_ids.update(source_author.coauthor_ids)
        target_author.collaboration_count = len(target_author.coauthor_ids)

        # 合并期刊 / Слияние журналов
        target_author.journals.update(source_author.journals)

        # 合并机构 / Слияние аффилиаций
        target_author.affiliations.update(source_author.affiliations)

        # 更新置信度（合并会降低置信度）/ Обновление уверенности (слияние снижает уверенность)
        target_author.confidence_score = min(
            target_author.confidence_score,
            source_author.confidence_score * 0.95
        )

        self.logger.info(
            f"合并完成 / Слияние завершено: "
            f"pubs={target_author.publication_count}, "
            f"records={len(target_author.linked_records)}, "
            f"confidence={target_author.confidence_score:.3f}"
        )

        return target_author

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取合并引擎统计信息 / Получение статистики движка слияния

        返回 / Возвращает / Returns:
            统计信息字典 / Словарь статистики
        """
        return {
            'similarity_threshold': self.similarity_threshold,
            'weights': self.weights.copy()
        }


# 测试代码 / Тестовый код / Test Code
if __name__ == '__main__':
    # 配置日志 / Настройка логирования
    logging.basicConfig(level=logging.DEBUG)

    print("=" * 80)
    print("作者合并引擎测试 / Тест движка слияния авторов")
    print("=" * 80)

    # 创建合并引擎 / Создание движка слияния
    merger = AuthorMerger(similarity_threshold=0.85)

    # 创建测试作者 / Создание тестовых авторов
    author1 = Author(
        author_id="au_001",
        canonical_name="Zhang Wei",
        coauthor_ids={"au_100", "au_101", "au_102"},
        journals={"Nature", "Science", "Cell"},
        affiliations={"Tsinghua University"}
    )

    author2 = Author(
        author_id="au_002",
        canonical_name="Li Ming",
        coauthor_ids={"au_200", "au_201"},
        journals={"PLOS ONE", "BMC Biology"},
        affiliations={"Peking University"}
    )

    # 测试候选者 / Тестовые кандидаты

    # 候选者1：应该匹配author1（姓名相似，合著者重叠）
    # Кандидат 1: должен совпадать с author1 (сходство имён, пересечение соавторов)
    candidate1 = {
        'name': 'Zhang Wei',
        'orcid': '',
        'coauthors': ['au_100', 'au_103'],
        'journals': ['Nature', 'PNAS'],
        'affiliation': ['Tsinghua University']
    }

    # 候选者2：应该匹配author1（姓名稍有不同，但合著者和期刊重叠）
    # Кандидат 2: должен совпадать с author1 (имя слегка отличается, но пересечение соавторов и журналов)
    candidate2 = {
        'name': 'Wei Zhang',
        'orcid': '',
        'coauthors': ['au_101', 'au_102'],
        'journals': ['Science', 'Cell'],
        'affiliation': ['Tsinghua Univ']
    }

    # 候选者3：不应该匹配任何人（完全不同）
    # Кандидат 3: не должен совпадать ни с кем (полностью отличается)
    candidate3 = {
        'name': 'John Smith',
        'orcid': '',
        'coauthors': ['au_500', 'au_501'],
        'journals': ['IEEE Transactions'],
        'affiliation': ['MIT']
    }

    existing_authors = [author1, author2]

    # 测试1：精确匹配
    # Тест 1: Точное совпадение
    print("\n[Test 1] 精确姓名匹配 / Точное совпадение имени")
    match, score = merger.find_matching_author(candidate1, existing_authors)
    print(f"  匹配结果 / Результат: {match.canonical_name if match else 'None'}")
    print(f"  相似度 / Сходство: {score:.3f} (期望 / ожидается: > 0.85)")

    # 测试2：姓名顺序不同但应该匹配
    # Тест 2: Порядок имени отличается, но должно совпадать
    print("\n[Test 2] 姓名顺序不同 / Другой порядок имени")
    match, score = merger.find_matching_author(candidate2, existing_authors)
    print(f"  匹配结果 / Результат: {match.canonical_name if match else 'None'}")
    print(f"  相似度 / Сходство: {score:.3f}")

    # 测试3：完全不同的作者
    # Тест 3: Полностью другой автор
    print("\n[Test 3] 完全不同的作者 / Полностью другой автор")
    match, score = merger.find_matching_author(candidate3, existing_authors)
    print(f"  匹配结果 / Результат: {match.canonical_name if match else 'None'}")
    print(f"  相似度 / Сходство: {score:.3f} (期望 / ожидается: < 0.85)")

    # 测试4：作者合并
    # Тест 4: Слияние авторов
    print("\n[Test 4] 作者合并测试 / Тест слияния авторов")
    author_a = Author(
        author_id="au_A",
        canonical_name="Alice Johnson",
        publications={"pub_1", "pub_2"},
        coauthor_ids={"au_100"},
        journals={"Nature"}
    )

    author_b = Author(
        author_id="au_B",
        canonical_name="A. Johnson",
        publications={"pub_3", "pub_4"},
        coauthor_ids={"au_200"},
        journals={"Science"}
    )

    print(f"  合并前 / До слияния:")
    print(f"    author_a: pubs={len(author_a.publications)}, coauthors={len(author_a.coauthor_ids)}")
    print(f"    author_b: pubs={len(author_b.publications)}, coauthors={len(author_b.coauthor_ids)}")

    merged = merger.merge_authors(author_a, author_b)

    print(f"  合并后 / После слияния:")
    print(f"    merged: pubs={len(merged.publications)}, coauthors={len(merged.coauthor_ids)}")
    print(f"    置信度 / Уверенность: {merged.confidence_score:.3f}")

    # 统计信息 / Статистика
    print("\n" + "=" * 80)
    print("合并引擎配置 / Конфигурация движка")
    print("=" * 80)
    stats = merger.get_statistics()
    print(f"  相似度阈值 / Порог сходства: {stats['similarity_threshold']}")
    print(f"  权重配置 / Конфигурация весов:")
    for key, value in stats['weights'].items():
        print(f"    {key}: {value:.2%}")
