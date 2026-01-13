# -*- coding: utf-8 -*-
"""
YAML Config Loader for Similarity Scorer
YAML配置加载器 / Загрузчик конфигурации YAML

Helper functions to load scorer configuration from YAML files.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional


def load_mu_table_from_yaml(path: str) -> Dict[str, Any]:
    """
    Load m/u probability table from YAML file.
    
    Args:
        path: Path to mu_table.yaml
        
    Returns:
        Dictionary with m/u probabilities per feature/bin
    """
    yaml_path = Path(path)
    if not yaml_path.exists():
        raise FileNotFoundError(f"m/u table file not found: {path}")
    
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    
    # Extract features section
    if 'features' in data:
        return data['features']
    return data


def load_scorer_config_from_yaml(
    mu_table_path: str = None,
    bins_path: str = None,
    enable_chinese_name: bool = False
) -> Dict[str, Any]:
    """
    Load a complete scorer configuration from YAML files.
    
    This can be passed directly to SimilarityScorer(config=...).
    
    Args:
        mu_table_path: Path to mu_table.yaml (m/u probabilities)
        bins_path: Path to bins.yaml (feature binning rules)
        enable_chinese_name: Whether to enable Chinese name module
        
    Returns:
        Configuration dictionary for SimilarityScorer
    """
    config = {}
    
    if mu_table_path and Path(mu_table_path).exists():
        with open(mu_table_path, 'r', encoding='utf-8') as f:
            mu_data = yaml.safe_load(f)
        # Extract features section as mu_table
        if 'features' in mu_data:
            config['mu_table'] = mu_data['features']
        # Also store thresholds if present
        if 'thresholds' in mu_data:
            config['thresholds'] = mu_data['thresholds']
    
    if bins_path and Path(bins_path).exists():
        with open(bins_path, 'r', encoding='utf-8') as f:
            bins_data = yaml.safe_load(f)
        # Convert bins to comparison_bins format
        config['comparison_bins'] = {}
        for feature_name, feature_config in bins_data.items():
            if isinstance(feature_config, dict) and 'bins' in feature_config:
                config['comparison_bins'][feature_name] = feature_config['bins']
    
    config['enable_chinese_name'] = enable_chinese_name
    
    return config


def create_scorer_from_yaml(
    mu_table_path: str = 'config/mu_table.yaml',
    bins_path: str = 'config/bins.yaml',
    enable_chinese_name: bool = False
):
    """
    Create a SimilarityScorer instance from YAML configuration.
    
    Args:
        mu_table_path: Path to mu_table.yaml
        bins_path: Path to bins.yaml
        enable_chinese_name: Whether to enable Chinese name module
        
    Returns:
        Configured SimilarityScorer instance
    """
    from disambiguation_engine.similarity_scorer import SimilarityScorer
    
    config = load_scorer_config_from_yaml(
        mu_table_path=mu_table_path,
        bins_path=bins_path,
        enable_chinese_name=enable_chinese_name
    )
    
    return SimilarityScorer(config=config)


if __name__ == '__main__':
    # Test loading
    config = load_scorer_config_from_yaml(
        mu_table_path='config/mu_table.calibrated.yaml',
        bins_path='config/bins.yaml'
    )
    print("Loaded config:")
    for key, value in config.items():
        if isinstance(value, dict):
            print(f"  {key}: {len(value)} items")
        else:
            print(f"  {key}: {value}")
