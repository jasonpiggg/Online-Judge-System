"""Fail CI on separate line/branch thresholds, without excluding production code."""

import json
import sys
from pathlib import Path

totals = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else "coverage.json").read_text())[
    "totals"
]
line = 100 * totals["covered_lines"] / totals["num_statements"]
branch = 100 * totals["covered_branches"] / totals["num_branches"]
print(f"Backend line coverage: {line:.2f}% (>=90%); branch coverage: {branch:.2f}% (>=85%)")
if line < 90 or branch < 85:
    raise SystemExit(1)
