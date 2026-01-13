# -*- coding: utf-8 -*-
"""
Build Mentions JSONL from Crossref Data
从Crossref数据构建Mentions数据集 / Создание датасета упоминаний из Crossref

This script extracts author mentions from the raw Crossref JSON file
and outputs them in a standardized JSONL format for evaluation.

Usage:
    python data/build_mentions.py --input <crossref.json> --output <mentions.jsonl>
"""

import argparse
import json
import hashlib
import sys
from pathlib import Path
from typing import List, Dict, Any


def generate_mention_id(doi: str, author_index: int, name: str) -> str:
    """Generate a unique mention ID from DOI, author position, and name."""
    raw = f"{doi}_{author_index}_{name}"
    return hashlib.md5(raw.encode('utf-8')).hexdigest()[:12]


def extract_mentions(
    data: Dict[str, Any],
    limit: int = None
) -> List[Dict[str, Any]]:
    """
    Extract author mentions from Crossref data.
    
    Args:
        data: Raw Crossref JSON data containing 'authors' list
        limit: Optional limit on number of authors to process
        
    Returns:
        List of mention dictionaries
    """
    authors = data.get('authors', [])
    if limit:
        authors = authors[:limit]
    
    mentions = []
    
    for idx, author in enumerate(authors):
        # Extract basic fields
        original_name = author.get('original_name', '').strip()
        if not original_name:
            continue
            
        doi = author.get('doi', '')
        orcid = author.get('orcid', '').strip()
        
        # Generate unique mention ID
        mention_id = generate_mention_id(doi, idx, original_name)
        
        # Build mention record
        mention = {
            'mention_id': mention_id,
            'doi': doi,
            'raw_name': original_name,
            'lastname': author.get('lastname', '').strip(),
            'firstname': author.get('firstname', '').strip(),
            'orcid': orcid,
            'affiliation': author.get('affiliation', '').strip(),
            'venue': author.get('journal', '').strip(),
            'year': author.get('year', ''),
            # Raw coauthors if available
            'coauthors': author.get('coauthors', []),
            # Original index for traceability
            '_original_index': idx
        }
        
        mentions.append(mention)
    
    return mentions


def main():
    parser = argparse.ArgumentParser(
        description='Build Mentions JSONL from Crossref Data / 从Crossref构建Mentions数据集'
    )
    parser.add_argument(
        '--input', '-i',
        type=str,
        default=r'C:\istina\materia 材料\测试表单\crossref.json',
        help='Input Crossref JSON file path'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='data/mentions.jsonl',
        help='Output JSONL file path'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit number of author records to process'
    )
    parser.add_argument(
        '--pretty',
        action='store_true',
        help='Output as pretty-printed JSON array instead of JSONL'
    )
    
    args = parser.parse_args()
    
    # Load input data
    print(f"Loading Crossref data from: {args.input}")
    input_path = Path(args.input)
    
    if not input_path.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Extract mentions
    print("Extracting mentions...")
    mentions = extract_mentions(data, limit=args.limit)
    
    print(f"Extracted {len(mentions)} mentions")
    
    # Count ORCID annotations
    orcid_count = sum(1 for m in mentions if m['orcid'])
    unique_orcids = len(set(m['orcid'] for m in mentions if m['orcid']))
    
    print(f"  - With ORCID: {orcid_count} ({100*orcid_count/len(mentions):.1f}%)")
    print(f"  - Unique ORCIDs: {unique_orcids}")
    
    # Create output directory if needed
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write output
    print(f"Writing to: {args.output}")
    
    if args.pretty:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(mentions, f, ensure_ascii=False, indent=2)
    else:
        # JSONL format - one JSON object per line
        with open(output_path, 'w', encoding='utf-8') as f:
            for mention in mentions:
                f.write(json.dumps(mention, ensure_ascii=False) + '\n')
    
    print("Done!")
    
    # Output summary
    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Total mentions: {len(mentions)}")
    print(f"  With ORCID: {orcid_count}")
    print(f"  Unique ORCIDs: {unique_orcids}")
    print(f"  Output: {output_path.absolute()}")
    print("=" * 60)


if __name__ == '__main__':
    main()
