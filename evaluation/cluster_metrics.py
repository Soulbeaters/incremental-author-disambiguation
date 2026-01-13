# -*- coding: utf-8 -*-
"""
Cluster-Based Evaluation Metrics
基于聚类的评估指标 / Метрики оценки на основе кластеризации

Implements B-Cubed (B³) and Pairwise metrics for author disambiguation evaluation.

Reference:
- Bagga & Baldwin (1998) for B-Cubed
- Standard pairwise precision/recall for entity resolution
"""

from typing import Dict, List, Set, Tuple, Any
from collections import defaultdict


def _build_mention_to_cluster_map(clusters: Dict[str, List[str]]) -> Dict[str, str]:
    """Build a mapping from mention_id to cluster_id."""
    mention_to_cluster = {}
    for cluster_id, mention_ids in clusters.items():
        for mid in mention_ids:
            mention_to_cluster[mid] = cluster_id
    return mention_to_cluster


def _get_all_pairs(cluster: List[str]) -> Set[Tuple[str, str]]:
    """Get all ordered pairs (a, b) where a < b from a cluster."""
    pairs = set()
    members = sorted(cluster)
    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            pairs.add((members[i], members[j]))
    return pairs


def b3_precision_recall_f1(
    gold_clusters: Dict[str, List[str]],
    pred_clusters: Dict[str, List[str]]
) -> Dict[str, float]:
    """
    Compute B-Cubed (B³) precision, recall, and F1.
    
    For each mention:
    - Precision: fraction of predicted cluster-mates that share the same gold cluster
    - Recall: fraction of gold cluster-mates that share the same predicted cluster
    
    Final scores are micro-averaged over all mentions.
    
    Args:
        gold_clusters: Dictionary mapping cluster_id -> list of mention_ids
        pred_clusters: Dictionary mapping cluster_id -> list of mention_ids
        
    Returns:
        Dictionary with 'precision', 'recall', 'f1' keys
    """
    # Build reverse mappings
    gold_map = _build_mention_to_cluster_map(gold_clusters)
    pred_map = _build_mention_to_cluster_map(pred_clusters)
    
    # Get all mentions that appear in both gold and pred
    all_mentions = set(gold_map.keys()) & set(pred_map.keys())
    
    if not all_mentions:
        return {'precision': 0.0, 'recall': 0.0, 'f1': 0.0}
    
    # Build cluster member sets for efficient lookup
    gold_members = {cid: set(mids) for cid, mids in gold_clusters.items()}
    pred_members = {cid: set(mids) for cid, mids in pred_clusters.items()}
    
    total_precision = 0.0
    total_recall = 0.0
    
    for mention in all_mentions:
        gold_cid = gold_map[mention]
        pred_cid = pred_map[mention]
        
        gold_cluster = gold_members.get(gold_cid, set())
        pred_cluster = pred_members.get(pred_cid, set())
        
        # Intersection of gold and pred cluster for this mention
        common = gold_cluster & pred_cluster
        
        # B³ precision: |common| / |pred_cluster|
        if len(pred_cluster) > 0:
            total_precision += len(common) / len(pred_cluster)
        
        # B³ recall: |common| / |gold_cluster|
        if len(gold_cluster) > 0:
            total_recall += len(common) / len(gold_cluster)
    
    n = len(all_mentions)
    precision = total_precision / n
    recall = total_recall / n
    
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    
    return {
        'precision': precision,
        'recall': recall,
        'f1': f1
    }


def pairwise_precision_recall_f1(
    gold_clusters: Dict[str, List[str]],
    pred_clusters: Dict[str, List[str]]
) -> Dict[str, float]:
    """
    Compute Pairwise precision, recall, and F1.
    
    - True Positive: pair is in same cluster in both gold and pred
    - False Positive: pair is in same cluster in pred but not in gold
    - False Negative: pair is in same cluster in gold but not in pred
    
    Args:
        gold_clusters: Dictionary mapping cluster_id -> list of mention_ids
        pred_clusters: Dictionary mapping cluster_id -> list of mention_ids
        
    Returns:
        Dictionary with 'precision', 'recall', 'f1', 'tp', 'fp', 'fn' keys
    """
    # Get all pairs from gold and pred
    gold_pairs = set()
    for cid, members in gold_clusters.items():
        gold_pairs.update(_get_all_pairs(members))
    
    pred_pairs = set()
    for cid, members in pred_clusters.items():
        pred_pairs.update(_get_all_pairs(members))
    
    # Compute TP, FP, FN
    tp = len(gold_pairs & pred_pairs)
    fp = len(pred_pairs - gold_pairs)
    fn = len(gold_pairs - pred_pairs)
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    
    return {
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'tp': tp,
        'fp': fp,
        'fn': fn
    }


def orcid_conflict_merge_rate(
    gold_clusters: Dict[str, List[str]],
    pred_clusters: Dict[str, List[str]]
) -> Dict[str, Any]:
    """
    Compute the ORCID conflict merge rate.
    
    An ORCID conflict occurs when mentions from different ORCIDs (gold clusters)
    are merged into the same predicted cluster.
    
    Args:
        gold_clusters: Dictionary mapping ORCID -> list of mention_ids
        pred_clusters: Dictionary mapping cluster_id -> list of mention_ids
        
    Returns:
        Dictionary with conflict statistics
    """
    gold_map = _build_mention_to_cluster_map(gold_clusters)
    
    conflicts = 0
    conflict_pairs = []
    
    for pred_cid, members in pred_clusters.items():
        if len(members) < 2:
            continue
        
        # Get ORCIDs for each member
        member_orcids = {}
        for mid in members:
            if mid in gold_map:
                member_orcids[mid] = gold_map[mid]
        
        # Check for ORCID conflicts within this predicted cluster
        unique_orcids = set(member_orcids.values())
        if len(unique_orcids) > 1:
            conflicts += 1
            conflict_pairs.append({
                'pred_cluster': pred_cid,
                'orcids': list(unique_orcids),
                'mention_count': len(members)
            })
    
    total_pred_clusters = len([c for c in pred_clusters.values() if len(c) >= 2])
    conflict_rate = conflicts / total_pred_clusters if total_pred_clusters > 0 else 0.0
    
    return {
        'conflict_clusters': conflicts,
        'total_pred_clusters_with_pairs': total_pred_clusters,
        'conflict_rate': conflict_rate,
        'conflicts_detail': conflict_pairs[:10]  # Limit to first 10 for brevity
    }


def evaluate_all_metrics(
    gold_clusters: Dict[str, List[str]],
    pred_clusters: Dict[str, List[str]]
) -> Dict[str, Any]:
    """
    Run all evaluation metrics.
    
    Args:
        gold_clusters: Dictionary mapping cluster_id -> list of mention_ids
        pred_clusters: Dictionary mapping cluster_id -> list of mention_ids
        
    Returns:
        Dictionary with all metrics results
    """
    b3 = b3_precision_recall_f1(gold_clusters, pred_clusters)
    pairwise = pairwise_precision_recall_f1(gold_clusters, pred_clusters)
    conflicts = orcid_conflict_merge_rate(gold_clusters, pred_clusters)
    
    return {
        'b3': b3,
        'pairwise': pairwise,
        'orcid_conflicts': conflicts,
        'summary': {
            'b3_f1': b3['f1'],
            'pairwise_f1': pairwise['f1'],
            'conflict_rate': conflicts['conflict_rate']
        }
    }


# Utility functions for filtering clusters by subset

def filter_clusters_by_mentions(
    clusters: Dict[str, List[str]],
    mention_subset: Set[str]
) -> Dict[str, List[str]]:
    """
    Filter clusters to only include mentions in the given subset.
    
    Args:
        clusters: Dictionary mapping cluster_id -> list of mention_ids
        mention_subset: Set of mention_ids to keep
        
    Returns:
        Filtered clusters (clusters with no remaining members are removed)
    """
    filtered = {}
    for cid, members in clusters.items():
        filtered_members = [m for m in members if m in mention_subset]
        if filtered_members:
            filtered[cid] = filtered_members
    return filtered
