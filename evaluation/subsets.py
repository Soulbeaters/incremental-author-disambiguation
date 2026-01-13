# -*- coding: utf-8 -*-
"""
Subset Detection Utilities
子集检测工具 / Утилиты определения подмножеств

Utilities for identifying subsets of mentions, particularly for Chinese name detection.
"""

from typing import List, Set, Dict, Any
import re


# Common Chinese surnames in pinyin (romanized)
CHINESE_SURNAMES = {
    # Top 100 most common surnames
    'wang', 'li', 'zhang', 'liu', 'chen', 'yang', 'huang', 'zhao', 'wu', 'zhou',
    'xu', 'sun', 'ma', 'zhu', 'hu', 'guo', 'he', 'lin', 'luo', 'gao',
    'liang', 'zheng', 'xie', 'song', 'tang', 'feng', 'han', 'deng', 'cao', 'peng',
    'zeng', 'xiao', 'tian', 'dong', 'pan', 'yuan', 'cai', 'jiang', 'du', 'ye',
    'cheng', 'wei', 'su', 'lu', 'ding', 'ren', 'shen', 'yao', 'xue',
    'shi', 'qian', 'dai', 'hou', 'meng', 'shao', 'qiu', 'bai', 'yin', 'chang',
    'lei', 'tan', 'fang', 'wan', 'jin', 'zou', 'jia', 'yan', 'hao', 'long',
    'kong', 'qin', 'xia', 'jing', 'ning', 'wen', 'fu', 'xi', 'kang', 'zou',
    'dou', 'zhong', 'gan', 'ai', 'lan', 'ning', 'ji', 'fan', 'yu', 'liao',
    'cui', 'gu', 'mao', 'kong', 'gong', 'xing', 'du', 'mu', 'xiang'
}

# Common non-Chinese surnames that might look like Chinese
NON_CHINESE_CONFUSABLES = {
    'lee', 'chan', 'wong', 'cheng', 'ho', 'ng', 'lam', 'fung', 'tsang',
    'yeung', 'kwok', 'leung', 'hui', 'tam', 'lo', 'chan', 'chow', 'ng'
}


def is_romanized_chinese(name: str, strict: bool = False) -> bool:
    """
    Check if a name appears to be romanized Chinese.
    
    Uses heuristics based on:
    1. Common Chinese surnames (pinyin)
    2. Name structure patterns (Chinese authors often have surname in special positions)
    3. Given name patterns (pinyin-style multi-syllable names)
    
    Args:
        name: The name string to check
        strict: If True, require stronger evidence for Chinese name detection
        
    Returns:
        True if the name appears to be romanized Chinese
    """
    if not name:
        return False
    
    # Clean and normalize name
    name_clean = name.lower().strip()
    # Remove common punctuation
    name_clean = re.sub(r'[,.\-\'\"()]', ' ', name_clean)
    parts = [p for p in name_clean.split() if p]
    
    if not parts:
        return False
    
    # Pattern 1: "Surname Givenname" format (common in academic papers)
    # Check if first or last part is a common Chinese surname
    first_is_chinese = parts[0] in CHINESE_SURNAMES
    last_is_chinese = parts[-1] in CHINESE_SURNAMES if len(parts) > 1 else False
    
    # Pattern 2: Check for hyphenated pinyin given names (e.g., "Xiao-Ming")
    hyphen_pattern = bool(re.search(r'\w+-\w+', name, re.IGNORECASE))
    
    # Pattern 3: Name ends with initial that could be Chinese given name initial
    ends_with_initial = len(parts) > 1 and len(parts[-1]) == 1
    
    # Pattern 4: Two-part name where both parts look like pinyin
    two_part_pinyin = len(parts) == 2 and all(len(p) >= 2 and len(p) <= 8 for p in parts)
    
    if strict:
        # Strict mode: require surname AND additional evidence
        return (first_is_chinese or last_is_chinese) and (hyphen_pattern or two_part_pinyin)
    else:
        # Normal mode: surname match is usually sufficient
        return first_is_chinese or last_is_chinese


def get_chinese_subset_ids(mentions: List[Dict[str, Any]]) -> Set[str]:
    """
    Get mention IDs for mentions with romanized Chinese names.
    
    Args:
        mentions: List of mention dictionaries with 'mention_id' and name fields
        
    Returns:
        Set of mention IDs where the name appears to be Chinese
    """
    chinese_ids = set()
    
    for m in mentions:
        # Try various name fields
        name = (
            m.get('raw_name', '') or 
            m.get('original_name', '') or
            f"{m.get('firstname', '')} {m.get('lastname', '')}".strip()
        )
        
        if is_romanized_chinese(name):
            mention_id = m.get('mention_id', '')
            if mention_id:
                chinese_ids.add(mention_id)
    
    return chinese_ids


def get_non_chinese_subset_ids(mentions: List[Dict[str, Any]]) -> Set[str]:
    """
    Get mention IDs for mentions with non-Chinese names.
    
    This is the complement of get_chinese_subset_ids().
    """
    all_ids = {m.get('mention_id', '') for m in mentions if m.get('mention_id')}
    chinese_ids = get_chinese_subset_ids(mentions)
    return all_ids - chinese_ids


def compute_subset_statistics(
    mentions: List[Dict[str, Any]],
    label: str = 'chinese'
) -> Dict[str, Any]:
    """
    Compute statistics about a subset of mentions.
    
    Args:
        mentions: List of mention dictionaries
        label: Subset type ('chinese' or 'non_chinese')
        
    Returns:
        Dictionary with subset statistics
    """
    total = len(mentions)
    
    if label == 'chinese':
        subset_ids = get_chinese_subset_ids(mentions)
    elif label == 'non_chinese':
        subset_ids = get_non_chinese_subset_ids(mentions)
    else:
        raise ValueError(f"Unknown subset label: {label}")
    
    subset_count = len(subset_ids)
    
    # Count ORCIDs in subset
    subset_orcids = set()
    for m in mentions:
        if m.get('mention_id') in subset_ids:
            orcid = m.get('orcid', '')
            if orcid:
                subset_orcids.add(orcid)
    
    return {
        'subset_label': label,
        'total_mentions': total,
        'subset_mentions': subset_count,
        'subset_ratio': subset_count / total if total > 0 else 0,
        'subset_orcids': len(subset_orcids)
    }


if __name__ == '__main__':
    # Quick test
    test_names = [
        "Wang Xiaoming",    # Chinese
        "Zhang Wei",        # Chinese
        "Liu Y.",           # Chinese
        "John Smith",       # Not Chinese
        "Maria Garcia",     # Not Chinese
        "Chen Hui",         # Chinese
        "Yang Jian-Ming",   # Chinese (hyphenated)
        "Xiao-Hong Li",     # Chinese (hyphenated)
        "Michael Brown",    # Not Chinese
        "Lin M.",           # Chinese
    ]
    
    print("Testing is_romanized_chinese():")
    for name in test_names:
        result = is_romanized_chinese(name)
        print(f"  {name:20} -> {result}")
