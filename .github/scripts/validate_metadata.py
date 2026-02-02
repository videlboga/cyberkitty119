#!/usr/bin/env python3
"""
Validate markdown files under a docs directory have YAML front-matter with required keys.

Usage: ./validate_metadata.py <docs_dir>
Exits non-zero if missing metadata found.
"""
import sys
import os
import yaml

def find_md_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        for fn in filenames:
            if fn.lower().endswith('.md'):
                yield os.path.join(dirpath, fn)

def read_front_matter(path):
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    if not lines:
        return None
    if not lines[0].strip().startswith('---'):
        return None
    # find end '---'
    for i in range(1, min(len(lines), 2000)):
        if lines[i].strip().startswith('---'):
            fm = ''.join(lines[1:i])
            try:
                data = yaml.safe_load(fm)
                return data or {}
            except Exception:
                return None
    return None

REQUIRED_KEYS = ['title', 'author', 'date', 'status', 'tags']
VALID_STATUSES = ['Draft', 'Proposed', 'Accepted', 'Deprecated']

import re
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:?\d{2})?)?$")

def main():
    if len(sys.argv) < 2:
        print('Usage: validate_metadata.py <docs_dir>')
        return 2
    root = sys.argv[1]
    if not os.path.isdir(root):
        print(f'Path not found: {root}')
        return 2
    failures = 0
    for md in find_md_files(root):
        fm = read_front_matter(md)
        if fm is None:
            print(f'ERROR: Missing or invalid front-matter in {md}')
            failures += 1
            continue
        missing = [k for k in REQUIRED_KEYS if k not in fm or fm.get(k) is None]
        if missing:
            print(f'ERROR: {md} missing keys: {missing}')
            failures += 1
            continue

        # validate status
        status = fm.get('status')
        if status not in VALID_STATUSES:
            print(f'ERROR: {md} has invalid status: {status}. Expected one of: {VALID_STATUSES}')
            failures += 1

        # validate date format (YYYY-MM-DD or ISO datetime)
        date_val = str(fm.get('date'))
        if not DATE_RE.match(date_val):
            print(f'ERROR: {md} has invalid date format: {date_val}. Expected YYYY-MM-DD or ISO datetime.')
            failures += 1

        # validate tags: should be list or comma-separated string
        tags = fm.get('tags')
        if tags is None:
            print(f'ERROR: {md} missing tags')
            failures += 1
        else:
            if not (isinstance(tags, list) or isinstance(tags, str)):
                print(f'ERROR: {md} tags must be a list or string. Found: {type(tags)}')
                failures += 1

        # validate related if present: should be list or string
        related = fm.get('related')
        if related is not None and not (isinstance(related, list) or isinstance(related, str)):
            print(f'ERROR: {md} related must be a list or string if present. Found: {type(related)}')
            failures += 1
    if failures:
        print(f'Found {failures} files with missing/invalid metadata')
        return 1
    print('All docs have required front-matter')
    return 0

if __name__ == '__main__':
    sys.exit(main())
