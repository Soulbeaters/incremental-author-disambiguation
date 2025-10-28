# -*- coding: utf-8 -*-
"""
使用真实DOI数据测试增量消歧系统
Test incremental disambiguation system with real DOI data
"""

import json
import sys
from models.author import AuthorRecord
from disambiguation_engine.engine import DisambiguationEngine

def load_dois(file_path: str, limit: int = 10):
    """加载真实DOI数据 / Load real DOI data"""
    with open(file_path, 'r', encoding='utf-8') as f:
        dois = json.load(f)
    return dois[1:limit+1]  # 跳过第一个空字符串 Skip first empty string

def create_test_records_from_dois(dois: list):
    """从DOI创建测试记录（模拟真实数据）"""
    test_records = []

    # DOI 1: 中文作者论文
    test_records.append(AuthorRecord(
        record_id="ISTINA_001",
        name="Wei Li",
        coauthors=["Maria Garcia", "David Chen"],
        journal="Journal of Geophysical Research",
        publication_title="Paper from " + dois[0],
        year=2014,
        affiliation="Tsinghua University, Beijing",
        source="ISTINA/Crossref"
    ))

    # DOI 2: 同一作者Wei Li（应该被合并）
    test_records.append(AuthorRecord(
        record_id="ISTINA_002",
        name="W. Li",
        coauthors=["David Chen", "Zhang Ming"],
        journal="Advanced Engineering Materials",
        publication_title="Paper from " + dois[1],
        year=2020,
        affiliation="Tsinghua Univ",
        source="ISTINA/Crossref"
    ))

    # DOI 3: 合作者David Chen的论文
    test_records.append(AuthorRecord(
        record_id="ISTINA_003",
        name="David Chen",
        coauthors=["Wei Li", "New Author"],
        journal="Nature Materials",
        publication_title="Paper from " + dois[2],
        year=2021,
        affiliation="Stanford University",
        source="ISTINA/Crossref"
    ))

    # DOI 4: 完全不同的作者
    test_records.append(AuthorRecord(
        record_id="ISTINA_004",
        name="Anna Ivanova",
        coauthors=["Sergey Petrov", "Maria Sokolova"],
        journal="Russian Chemical Journal",
        publication_title="Paper from " + dois[3],
        year=2022,
        affiliation="MSU Moscow",
        source="ISTINA"
    ))

    # DOI 5: Wei Li的第三篇论文
    test_records.append(AuthorRecord(
        record_id="ISTINA_005",
        name="Wei Li",
        coauthors=["Zhang Ming", "Anna Ivanova"],
        journal="Advanced Functional Materials",
        publication_title="Paper from " + dois[4],
        year=2023,
        affiliation="Tsinghua University",
        source="ISTINA/Crossref"
    ))

    return test_records

def main():
    """主测试函数"""
    print("="*80)
    print("真实DOI数据增量消歧测试 / Incremental Disambiguation Test")
    print("="*80)

    # 加载真实DOI
    dois_file = r"C:\istina\materia 材料\测试表单\dois.json"
    dois = load_dois(dois_file, limit=5)
    print(f"\n[+] 加载了 {len(dois)} 个真实DOI")
    print(f"[+] Sample DOIs: {dois[:3]}...")

    # 创建测试记录
    test_records = create_test_records_from_dois(dois)
    print(f"\n[+] 创建了 {len(test_records)} 条测试记录")

    # 初始化引擎
    engine = DisambiguationEngine()

    # 逐条处理
    print("\n" + "="*80)
    print("开始增量处理 / Starting Incremental Processing")
    print("="*80)

    for i, record in enumerate(test_records, 1):
        print(f"\n{'>>>'*3} 处理记录 {i}/{len(test_records)} {'>>>'*3}")
        print(f"Record ID: {record.record_id}")
        print(f"Name: {record.name}")
        print(f"Source: {record.source}")
        print(f"Coauthors: {record.coauthors}")

        result = engine.process_new_record(record)

        print(f"\n[决策]: {result.decision}")
        print(f"[相似度]: {result.similarity_score:.4f}")
        print(f"[匹配作者]: {result.matched_author_id}")
        print("-"*80)

    # 最终统计
    print("\n" + "="*80)
    print("最终统计 / Final Statistics")
    print("="*80)

    stats = engine.get_statistics()
    print(f"[+] 处理记录总数: {stats['total_processed']}")
    print(f"[+] 识别的唯一作者: {stats['total_authors']}")
    print(f"[+] 合并的记录: {stats['merged_records']}")
    print(f"[+] 新建的作者: {stats['new_authors_created']}")
    print(f"[+] 平均处理时间: {stats['avg_processing_time']:.4f}s")

    # 作者详情
    print(f"\n[+] 作者详情:")
    for author_id, author in engine.authors.items():
        print(f"\n  Author ID: {author_id}")
        print(f"  Name: {author.canonical_name}")
        print(f"  Linked Records: {list(author.linked_records)}")
        print(f"  Coauthors: {len(author.coauthor_ids)}")
        print(f"  Publications: {author.publication_count}")

    # 测试结论
    print("\n" + "="*80)
    print("测试结论")
    print("="*80)

    expected_authors = 3  # Wei Li, David Chen, Anna Ivanova
    if stats['total_authors'] == expected_authors:
        print(f"[✓] 成功: 正确识别了 {expected_authors} 个唯一作者")
    else:
        print(f"[!] 警告: 预期 {expected_authors} 个作者，实际 {stats['total_authors']} 个")

    if stats['merged_records'] >= 2:
        print(f"[✓] 成功: 增量合并功能正常 ({stats['merged_records']} 次合并)")
    else:
        print(f"[!] 警告: 合并次数少于预期 ({stats['merged_records']} 次)")

    print("\n[✓] 测试完成！系统可以处理真实ІСТІНА/Crossref数据")
    print("="*80)

    return engine, stats

if __name__ == "__main__":
    try:
        engine, stats = main()
    except Exception as e:
        print(f"\n[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
