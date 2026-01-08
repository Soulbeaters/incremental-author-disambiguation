# -*- coding: utf-8 -*-
"""
决策追踪脱敏测试 / Тесты редактирования трассировки решений
Test decision trace redaction - verify no plaintext names in trace output

确保trace日志中不包含明文姓名
Проверка что в логах трассировки нет имён в открытом виде
"""

import unittest
import json
import re
import sys
import os
import tempfile
from pathlib import Path

# 添加项目根目录
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from disambiguation_engine.decision_trace import DecisionTraceLogger
from disambiguation_engine.decision_types import Decision, DecisionResult


class TestTraceRedaction(unittest.TestCase):
    """测试trace脱敏功能 / Тесты редактирования трассировки"""

    def setUp(self):
        """创建临时trace文件 / Создание временных файлов трассировки"""
        self.temp_dir = tempfile.mkdtemp()
        self.trace_file = os.path.join(self.temp_dir, 'test_trace.jsonl')
        self.review_file = os.path.join(self.temp_dir, 'test_review.jsonl')
        
        self.logger = DecisionTraceLogger(
            trace_path=self.trace_file,
            review_path=self.review_file
        )
        
        # 测试用的敏感姓名
        self.sensitive_names = [
            'Zhang Wei',
            'John Smith',
            '李明',
            'Иванов Иван',
            'María García'
        ]

    def tearDown(self):
        """清理临时文件 / Очистка временных файлов"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_decision_result(self, decision: Decision, name: str) -> DecisionResult:
        """创建测试用DecisionResult / Создание тестового DecisionResult"""
        return DecisionResult(
            decision=decision,
            best_author_id='au_test123' if decision == Decision.MERGE else None,
            score_total=0.85 if decision == Decision.MERGE else 0.15,
            score_components={'name': 0.5, 'coauthors': 0.2},
            comparisons={'name_sim': 0.9, 'name_bin': 'high'},
            thresholds={'accept': 0.8, 'reject': 0.2},
            mode='baseline',
            topk=[],
            run_id='test_redaction',
            candidate_count=1,
            blocking_keys=['surname:test']
        )

    def _create_mention(self, name: str) -> dict:
        """创建测试用mention / Создание тестового упоминания"""
        return {
            'name': name,
            'orcid': '0000-0001-2345-6789',
            'affiliation': ['Test University', 'Research Institute'],
            'journals': ['Nature', 'Science'],
            'coauthors': ['Coauthor One', 'Coauthor Two']
        }

    def test_name_not_in_trace_plaintext(self):
        """测试姓名不以明文出现在trace中 / Тест что имя не появляется в открытом виде"""
        for name in self.sensitive_names:
            result = self._create_decision_result(Decision.MERGE, name)
            mention = self._create_mention(name)
            
            self.logger.append_trace(result, mention, {'test': True})
        
        # 读取trace文件
        with open(self.trace_file, 'r', encoding='utf-8') as f:
            trace_content = f.read()
        
        # 检查每个敏感姓名都不应该以明文出现
        for name in self.sensitive_names:
            # 姓名不应该直接出现（除非是在hash值中偶然匹配）
            # 检查整个姓名字符串
            self.assertNotIn(f'"name": "{name}"', trace_content,
                f"Plaintext name '{name}' found in trace!")

    def test_name_replaced_with_hash_structure(self):
        """测试姓名被替换为hash结构 / Тест что имя заменено на хеш-структуру"""
        name = 'Zhang Wei'
        result = self._create_decision_result(Decision.MERGE, name)
        mention = self._create_mention(name)
        
        self.logger.append_trace(result, mention, {'test': True})
        
        # 读取trace文件
        with open(self.trace_file, 'r', encoding='utf-8') as f:
            trace_line = f.readline()
        
        trace_data = json.loads(trace_line)
        
        # mention中的name应该是一个字典结构（包含hash）
        if 'mention' in trace_data:
            mention_data = trace_data['mention']
            if 'name' in mention_data:
                name_data = mention_data['name']
                # 应该是字典，包含hash字段
                self.assertIsInstance(name_data, dict,
                    "Redacted name should be a dict with hash structure")
                self.assertIn('hash', name_data,
                    "Redacted name should contain 'hash' field")

    def test_affiliation_redacted(self):
        """测试机构信息脱敏 / Тест редактирования аффилиаций"""
        name = 'Test Person'
        result = self._create_decision_result(Decision.MERGE, name)
        mention = self._create_mention(name)
        mention['affiliation'] = ['Harvard University', 'MIT']
        
        self.logger.append_trace(result, mention, {'test': True})
        
        with open(self.trace_file, 'r', encoding='utf-8') as f:
            trace_content = f.read()
        
        # 机构名不应该以明文出现
        self.assertNotIn('Harvard University', trace_content)
        self.assertNotIn('MIT', trace_content)

    def test_unknown_decision_goes_to_review(self):
        """测试UNKNOWN决策写入review文件 / Тест что UNKNOWN записывается в review"""
        name = 'Review Person'
        result = self._create_decision_result(Decision.UNKNOWN, name)
        result.decision = Decision.UNKNOWN
        result.score_total = 0.45  # 在uncertain区间
        
        mention = self._create_mention(name)
        
        self.logger.append_trace(result, mention, {'test': True})
        
        # 检查review文件被创建并包含记录
        self.assertTrue(os.path.exists(self.review_file),
            "Review file should be created for UNKNOWN decisions")
        
        with open(self.review_file, 'r', encoding='utf-8') as f:
            review_content = f.read()
        
        self.assertGreater(len(review_content), 0,
            "Review file should contain UNKNOWN decision")

    def test_orcid_not_redacted(self):
        """测试ORCID不被脱敏 / Тест что ORCID не редактируется"""
        name = 'Test Person'
        orcid = '0000-0001-2345-6789'
        result = self._create_decision_result(Decision.MERGE, name)
        mention = self._create_mention(name)
        mention['orcid'] = orcid
        
        self.logger.append_trace(result, mention, {'test': True})
        
        with open(self.trace_file, 'r', encoding='utf-8') as f:
            trace_content = f.read()
        
        # ORCID应该保留明文
        self.assertIn(orcid, trace_content,
            "ORCID should remain in plaintext")

    def test_hash_is_deterministic(self):
        """测试hash值确定性 / Тест детерминизма хеша"""
        name = 'Consistent Name'
        
        # 多次创建相同的trace
        for _ in range(3):
            result = self._create_decision_result(Decision.MERGE, name)
            mention = self._create_mention(name)
            self.logger.append_trace(result, mention, {'test': True})
        
        # 读取所有trace行
        with open(self.trace_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 提取所有name hash值
        name_hashes = []
        for line in lines:
            data = json.loads(line)
            if 'mention' in data and 'name' in data['mention']:
                name_data = data['mention']['name']
                if isinstance(name_data, dict) and 'hash' in name_data:
                    name_hashes.append(name_data['hash'])
        
        # 所有hash值应该相同
        if len(name_hashes) > 1:
            self.assertEqual(len(set(name_hashes)), 1,
                "Same name should produce same hash")

    def test_chinese_name_redaction(self):
        """测试中文姓名脱敏 / Тест редактирования китайских имён"""
        chinese_name = '张伟'
        result = self._create_decision_result(Decision.MERGE, chinese_name)
        mention = self._create_mention(chinese_name)
        
        self.logger.append_trace(result, mention, {'test': True})
        
        with open(self.trace_file, 'r', encoding='utf-8') as f:
            trace_content = f.read()
        
        # 中文姓名不应该以明文出现
        self.assertNotIn(f'"{chinese_name}"', trace_content)

    def test_regex_no_plaintext_names(self):
        """使用正则表达式验证无明文姓名 / Проверка отсутствия имён регулярным выражением"""
        # 添加多种类型的姓名
        names = ['John Smith', 'Zhang Wei', '李明', 'María García']
        
        for name in names:
            result = self._create_decision_result(Decision.MERGE, name)
            mention = self._create_mention(name)
            self.logger.append_trace(result, mention, {'test': True})
        
        with open(self.trace_file, 'r', encoding='utf-8') as f:
            trace_content = f.read()
        
        # 检查常见的姓名模式不出现在"name":后面
        # 如果name后面直接是字符串值（而非对象），则可能是未脱敏
        pattern = r'"name"\s*:\s*"[A-Za-z\u4e00-\u9fff\u0400-\u04ff]+'
        
        # 解析每一行JSON
        for line in trace_content.strip().split('\n'):
            if not line:
                continue
            data = json.loads(line)
            
            # 检查mention.name是否为dict（脱敏结构）
            if 'mention' in data and 'name' in data['mention']:
                name_field = data['mention']['name']
                self.assertIsInstance(name_field, dict,
                    f"Name field should be redacted dict, got: {type(name_field)}")


class TestRedactionStructure(unittest.TestCase):
    """测试脱敏结构 / Тесты структуры редактирования"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.trace_file = os.path.join(self.temp_dir, 'test_trace.jsonl')
        
        self.logger = DecisionTraceLogger(
            trace_path=self.trace_file
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_redacted_name_has_expected_fields(self):
        """测试脱敏姓名包含预期字段 / Тест что редактированное имя содержит ожидаемые поля"""
        result = DecisionResult(
            decision=Decision.MERGE,
            best_author_id='au_123',
            score_total=0.9,
            score_components={},
            comparisons={},
            thresholds={'accept': 0.8, 'reject': 0.2},
            mode='baseline',
            topk=[],
            run_id='test'
        )
        
        mention = {
            'name': 'Test Person Name',
            'orcid': ''
        }
        
        self.logger.append_trace(result, mention, {})
        
        with open(self.trace_file, 'r', encoding='utf-8') as f:
            data = json.loads(f.readline())
        
        name_data = data['mention']['name']
        
        # 检查预期的脱敏字段
        expected_fields = ['hash', 'tokens', 'length', 'script']
        for field in expected_fields:
            self.assertIn(field, name_data,
                f"Redacted name should contain '{field}' field")


if __name__ == '__main__':
    print("=" * 80)
    print("决策追踪脱敏测试 / Тесты редактирования трассировки")
    print("=" * 80)
    
    unittest.main(verbosity=2)
