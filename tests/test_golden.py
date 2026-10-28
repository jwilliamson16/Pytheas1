"""The package against golden outputs of the original code (tests/golden).

The golden folders were made with tools/p1_make_golden.py: the published
GUI_version library code, run on its original stack (Python 3.9, pandas
1.4.1, numpy 1.23.1, matplotlib 3.5.0), one stage at a time. Each test runs
the package's version of a stage on the same inputs and compares every file
it writes (rules in tools/p1_golden_check.py). FutureWarnings are errors, so
a deprecation that will break with the next library release fails here first.
"""
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = os.path.join(REPO, "tools", "p1_golden_check.py")
GOLDEN = os.path.join(REPO, "tests", "golden", "training_set")


def run_check(out, stages):
    p = subprocess.run([sys.executable, "-W", "error::FutureWarning", CHECK, GOLDEN, str(out), *stages],
                       capture_output=True, text=True, env=dict(os.environ, PYTHONHASHSEED="0"))
    report = p.stdout[-6000:] + p.stderr[-3000:]
    assert p.returncode == 0, report
    assert "0 difference(s)" in p.stdout, report


def test_training_set_fast_stages(tmp_path):
    run_check(tmp_path, ["digest", "report", "mapping", "stats"])


@pytest.mark.slow
def test_training_set_match(tmp_path):
    run_check(tmp_path, ["match"])


@pytest.mark.slow
def test_training_set_visualize(tmp_path):
    run_check(tmp_path, ["visualize"])
