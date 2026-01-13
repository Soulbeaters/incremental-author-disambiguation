# -*- coding: utf-8 -*-
"""
Make ORCID-Blind Mentions
创建ORCID盲评测数据 / Создание ORCID-слепых данных

Removes ORCID field from mentions for blind evaluation.
ORCID is only used for gold truth construction.

Usage:
    python data/make_orcid_blind_mentions.py \
        --input data/mentions.jsonl \
        --output data/mentions_orcid_blind.jsonl
"""

import argparse
import json
import sys
from pathlib import Path


def make_orcid_blind(input_path: str, output_path: str) -> dict:
    """
    Remove ORCID field from all mentions.
    
    Args:
        input_path: Path to original mentions JSONL (with ORCID)
        output_path: Path to output blind mentions JSONL
        
    Returns:
        Statistics dict
    """
    stats = {
        'total_mentions': 0,
        'had_orcid': 0,
        'no_orcid': 0
    }
    
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(input_path, 'r', encoding='utf-8') as f_in, \
         open(output_path, 'w', encoding='utf-8') as f_out:
        
        for line in f_in:
            line = line.strip()
            if not line:
                continue
            
            mention = json.loads(line)
            stats['total_mentions'] += 1
            
            # Check if has ORCID
            orcid = mention.get('orcid', '').strip()
            if orcid:
                stats['had_orcid'] += 1
            else:
                stats['no_orcid'] += 1
            
            # Remove ORCID field (set to empty string, not delete, for consistency)
            mention['orcid'] = ''
            
            # Write blind mention
            f_out.write(json.dumps(mention, ensure_ascii=False) + '\n')
    
    return stats


def main():
    parser = argparse.ArgumentParser(
        description='Make ORCID-Blind Mentions / 创建ORCID盲数据'
    )
    parser.add_argument(
        '--input', '-i',
        type=str,
        default='data/mentions.jsonl',
        help='Input mentions JSONL (with ORCID)'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='data/mentions_orcid_blind.jsonl',
        help='Output blind mentions JSONL'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Make ORCID-Blind Mentions")
    print("=" * 60)
    print(f"Input: {args.input}")
    print(f"Output: {args.output}")
    
    if not Path(args.input).exists():
        print(f"Error: Input file not found: {args.input}")
        sys.exit(1)
    
    stats = make_orcid_blind(args.input, args.output)
    
    print(f"\nStatistics:")
    print(f"  Total mentions: {stats['total_mentions']}")
    print(f"  Had ORCID: {stats['had_orcid']} ({stats['had_orcid']/stats['total_mentions']*100:.1f}%)")
    print(f"  No ORCID: {stats['no_orcid']}")
    print(f"\nORCID field removed from all mentions.")
    print(f"Output saved to: {args.output}")
    print("\nDone!")


if __name__ == '__main__':
    main()
