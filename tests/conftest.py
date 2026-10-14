"""The pure-Python parts (hpcrypto, parsers) are tested on their own: put the integration's folder on the path."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "custom_components" / "appline"))   # last: its calendar.py etc. must not hide the standard library
# The apps' project, next to this repo on the PC it's built on (the parity test is skipped elsewhere)
SITE = ROOT.parent / "site"
