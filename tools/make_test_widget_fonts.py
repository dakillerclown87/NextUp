"""Generate browser-test fixtures from caller-provided fonts (test-only deps).

Install fonttools and brotli, then run:
  python tools/make_test_widget_fonts.py --ttf path/font.ttf --otf path/font.otf
Fixtures live under build/ and are never included in releases.
"""
import argparse
from pathlib import Path
from fontTools.ttLib import TTFont


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ttf',required=True,type=Path)
    parser.add_argument('--otf',required=True,type=Path)
    args=parser.parse_args()
    folder=Path(__file__).resolve().parents[1]/'build/font-fixtures'
    folder.mkdir(parents=True,exist_ok=True)
    (folder/'Serif.ttf').write_bytes(args.ttf.read_bytes())
    (folder/'Gothic.otf').write_bytes(args.otf.read_bytes())
    for fmt in ('woff','woff2'):
        font=TTFont(args.ttf);font.flavor=fmt;font.save(folder/('Mono.'+fmt));font.close()

if __name__=='__main__':main()
