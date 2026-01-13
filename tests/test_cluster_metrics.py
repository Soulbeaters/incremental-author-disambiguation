# -*- coding: utf-8 -*-
"""
Unit Tests for Cluster Metrics
聚类指标单元测试 / Модульные тесты метрик кластеризации

Tests for B-Cubed, Pairwise, and ORCID conflict metrics.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from evaluation.cluster_metrics import (
    b3_precision_recall_f1,
    pairwise_precision_recall_f1,
    orcid_conflict_merge_rate,
    evaluate_all_metrics,
    filter_clusters_by_mentions
)


class TestB3Metrics:
    """Tests for B-Cubed (B³) metrics."""
    
    def test_perfect_clustering(self):
        """Perfect clustering should have P=R=F1=1.0."""
        gold = {
            'A': ['m1', 'm2', 'm3'],
            'B': ['m4', 'm5']
        }
        pred = {
            'C1': ['m1', 'm2', 'm3'],
            'C2': ['m4', 'm5']
        }
        result = b3_precision_recall_f1(gold, pred)
        
        assert abs(result['precision'] - 1.0) < 1e-6
        assert abs(result['recall'] - 1.0) < 1e-6
        assert abs(result['f1'] - 1.0) < 1e-6
    
    def test_all_singletons(self):
        """All singletons should have P=1.0, R varies."""
        gold = {
            'A': ['m1', 'm2', 'm3']
        }
        pred = {
            'C1': ['m1'],
            'C2': ['m2'],
            'C3': ['m3']
        }
        result = b3_precision_recall_f1(gold, pred)
        
        # Each mention's pred cluster contains only itself, so precision = 1
        assert abs(result['precision'] - 1.0) < 1e-6
        # Recall should be 1/3 for each (only 1 of 3 cluster-mates in same pred cluster)
        assert abs(result['recall'] - 1/3) < 1e-6
    
    def test_single_cluster_all(self):
        """Putting all in one cluster should have R=1.0, P varies."""
        gold = {
            'A': ['m1', 'm2'],
            'B': ['m3', 'm4']
        }
        pred = {
            'C1': ['m1', 'm2', 'm3', 'm4']
        }
        result = b3_precision_recall_f1(gold, pred)
        
        # Recall = 1 (all gold cluster-mates are in same pred cluster)
        assert abs(result['recall'] - 1.0) < 1e-6
        # Precision = 2/4 = 0.5 for each mention (2 true, 2 false cluster-mates)
        assert abs(result['precision'] - 0.5) < 1e-6


class TestPairwiseMetrics:
    """Tests for Pairwise metrics."""
    
    def test_perfect_clustering(self):
        """Perfect clustering should have P=R=F1=1.0."""
        gold = {
            'A': ['m1', 'm2', 'm3'],
            'B': ['m4', 'm5']
        }
        pred = {
            'C1': ['m1', 'm2', 'm3'],
            'C2': ['m4', 'm5']
        }
        result = pairwise_precision_recall_f1(gold, pred)
        
        assert abs(result['precision'] - 1.0) < 1e-6
        assert abs(result['recall'] - 1.0) < 1e-6
        assert abs(result['f1'] - 1.0) < 1e-6
        assert result['tp'] == 4  # 3 pairs in A, 1 pair in B
        assert result['fp'] == 0
        assert result['fn'] == 0
    
    def test_all_singletons(self):
        """All singletons should have P=1.0 (no pairs), R=0."""
        gold = {
            'A': ['m1', 'm2', 'm3']  # 3 pairs: (m1,m2), (m1,m3), (m2,m3)
        }
        pred = {
            'C1': ['m1'],
            'C2': ['m2'],
            'C3': ['m3']
        }
        result = pairwise_precision_recall_f1(gold, pred)
        
        assert result['tp'] == 0
        assert result['fp'] == 0
        assert result['fn'] == 3
        # Precision is 0/0 -> 0 by convention
        assert result['recall'] == 0.0
    
    def test_partial_overlap(self):
        """Test partial overlap between gold and pred."""
        gold = {
            'A': ['m1', 'm2', 'm3']  # pairs: (m1,m2), (m1,m3), (m2,m3)
        }
        pred = {
            'C1': ['m1', 'm2'],       # pair: (m1,m2)
            'C2': ['m3']
        }
        result = pairwise_precision_recall_f1(gold, pred)
        
        assert result['tp'] == 1    # (m1,m2)
        assert result['fp'] == 0    # no false pairs
        assert result['fn'] == 2    # (m1,m3), (m2,m3) missed
        
        assert abs(result['precision'] - 1.0) < 1e-6
        assert abs(result['recall'] - 1/3) < 1e-6


class TestORCIDConflict:
    """Tests for ORCID conflict detection."""
    
    def test_no_conflicts(self):
        """No conflicts when pred clusters respect gold clusters."""
        gold = {
            'orcid1': ['m1', 'm2'],
            'orcid2': ['m3', 'm4']
        }
        pred = {
            'C1': ['m1', 'm2'],
            'C2': ['m3', 'm4']
        }
        result = orcid_conflict_merge_rate(gold, pred)
        
        assert result['conflict_clusters'] == 0
        assert result['conflict_rate'] == 0.0
    
    def test_one_conflict(self):
        """One conflict when mentions from different ORCIDs are merged."""
        gold = {
            'orcid1': ['m1', 'm2'],
            'orcid2': ['m3', 'm4']
        }
        pred = {
            'C1': ['m1', 'm2', 'm3']  # m3 is from orcid2, conflict!
        }
        result = orcid_conflict_merge_rate(gold, pred)
        
        assert result['conflict_clusters'] == 1
    
    def test_singleton_clusters_ignored(self):
        """Singleton pred clusters should not count as conflicts."""
        gold = {
            'orcid1': ['m1'],
            'orcid2': ['m2']
        }
        pred = {
            'C1': ['m1'],
            'C2': ['m2']
        }
        result = orcid_conflict_merge_rate(gold, pred)
        
        # No clusters with 2+ members
        assert result['total_pred_clusters_with_pairs'] == 0


class TestFilterClusters:
    """Tests for cluster filtering."""
    
    def test_filter_by_subset(self):
        """Filter clusters to only include specified mentions."""
        clusters = {
            'A': ['m1', 'm2', 'm3'],
            'B': ['m4', 'm5']
        }
        subset = {'m1', 'm2', 'm5'}
        
        filtered = filter_clusters_by_mentions(clusters, subset)
        
        assert 'A' in filtered
        assert set(filtered['A']) == {'m1', 'm2'}
        assert 'B' in filtered
        assert filtered['B'] == ['m5']
    
    def test_filter_removes_empty_clusters(self):
        """Clusters with no remaining members should be removed."""
        clusters = {
            'A': ['m1', 'm2'],
            'B': ['m3', 'm4']
        }
        subset = {'m1', 'm2'}  # Only mentions from cluster A
        
        filtered = filter_clusters_by_mentions(clusters, subset)
        
        assert 'A' in filtered
        assert 'B' not in filtered


class TestEvaluateAll:
    """Integration tests for evaluate_all_metrics."""
    
    def test_returns_all_metrics(self):
        """All metrics should be returned."""
        gold = {'A': ['m1', 'm2']}
        pred = {'C1': ['m1', 'm2']}
        
        result = evaluate_all_metrics(gold, pred)
        
        assert 'b3' in result
        assert 'pairwise' in result
        assert 'orcid_conflicts' in result
        assert 'summary' in result
        
        assert 'f1' in result['b3']
        assert 'f1' in result['pairwise']
        assert 'conflict_rate' in result['orcid_conflicts']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
