#!/usr/bin/env python3
import sys
import json
from pathlib import Path

def usage():
    print("Usage: extract_segments.py <result_json> [outdir]")
    sys.exit(2)


def main():
    if len(sys.argv) < 2:
        usage()
    src = Path(sys.argv[1])
    outdir = Path(sys.argv[2]) if len(sys.argv) > 2 else src.parent
    if not src.exists():
        print(f"File not found: {src}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(src.read_text(encoding='utf-8'))
    segments = data.get('segments') or []
    # write CSV using csv module to avoid quoting issues
    import csv as _csv
    csv_path = outdir / (src.stem + "_segments.csv")
    txt_path = outdir / (src.stem + "_transcript_with_timestamps.txt")
    with csv_path.open('w', encoding='utf-8', newline='') as fcsv, txt_path.open('w', encoding='utf-8') as ftxt:
        writer = _csv.writer(fcsv)
        writer.writerow(['start_s', 'end_s', 'text'])
        for s in segments:
            start = s.get('start')
            end = s.get('end')
            text = s.get('text','').replace('\n',' ').strip()
            writer.writerow([start, end, text])
            # pretty text line with timestamp
            ftxt.write(f'[{float(start):.3f} - {float(end):.3f}] {text}\n')
    print(f'Wrote: {csv_path}\nWrote: {txt_path}')

if __name__ == '__main__':
    main()
