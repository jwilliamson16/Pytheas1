"""Package plumbing: compatibility helpers, parameter files, stage runner, CLI."""
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from pytheas1._compat import merge_outer_v1, series_float
from pytheas1.params import default_params, load_params, save_params
from pytheas1.stages import DEFAULTS, STAGES, StageError, data_dir, merged_params, resolve_input


def rows(df):
    return [["nan" if pd.isna(v) else str(v) for v in r] for r in df.values.tolist()]


def test_merge_outer_v1_matches_pandas_1_4_order():
    # expected rows are pandas 1.4.1's own output for this merge
    left = pd.DataFrame({"k": ["b", "a", "c", "a", "z"], "x": [1, 2, 3, 4, 5]})
    right = pd.DataFrame({"k": ["a", "q", "b", "a", "m"], "y": [10, 20, 30, 40, 50]})
    out = merge_outer_v1(left, right, on="k")
    assert rows(out) == [["b", "1.0", "30.0"], ["a", "2.0", "10.0"], ["a", "2.0", "40.0"], ["a", "4.0", "10.0"],
                         ["a", "4.0", "40.0"], ["c", "3.0", "nan"], ["z", "5.0", "nan"], ["q", "nan", "20.0"],
                         ["m", "nan", "50.0"]]


def test_merge_outer_v1_on_common_columns():
    # pandas 1.4.1 output for the sequence-map case: merge on all shared columns
    l2 = pd.DataFrame({"1": ["A", "1", "x"], "2": ["C", "2", "y"]})
    r2 = pd.DataFrame({"1": ["1", "light"], "2": ["2", "h"]})
    assert rows(merge_outer_v1(l2, r2)) == [["A", "C"], ["1", "2"], ["x", "y"], ["light", "h"]]


def test_series_float():
    assert series_float(pd.Series([2.5])) == 2.5
    assert series_float(3.0) == 3.0
    assert isinstance(series_float(pd.Series([np.float64(1)])), float)
    with pytest.raises(TypeError):
        series_float(pd.Series([1.0, 2.0]))


def test_defaults_cover_every_stage():
    assert set(DEFAULTS) == set(STAGES)
    assert DEFAULTS["digest"]["enzyme_missed_cleavages"] == "0"      # argparse leaves defaults as given
    assert DEFAULTS["match"]["MS2_absolute_peak_intensity"] == "None"


def test_bundled_data_resolution(tmp_path):
    assert resolve_input("nts_light.xlsx", str(tmp_path)) == os.path.join(data_dir(), "nts_light.xlsx")
    local = tmp_path / "nts_light.xlsx"
    local.write_text("x")
    assert resolve_input("nts_light.xlsx", str(tmp_path)) == str(local)      # the working folder wins
    calib = "Charge_tables/QTOF_training_set_only/charges_MS1_calibration.txt"
    assert os.path.exists(resolve_input(calib, str(tmp_path)))


def test_merged_params_checks():
    with pytest.raises(StageError, match="required"):
        merged_params("match", {})
    with pytest.raises(StageError, match="unknown"):
        merged_params("report", {"Match_output": "m.txt", "nonsense": 1})
    with pytest.raises(StageError, match="not one of"):
        merged_params("digest", {"RNA_sequences": "a.fasta", "Enzyme": "T7"})
    p = merged_params("report", {"Match_output": "m.txt"})
    assert p["rank_maximum"] == 99


def test_params_round_trip(tmp_path):
    params = default_params()
    params["working_dir"] = "job"
    params["digest"]["Enzyme"] = "T1"
    path = tmp_path / "p.json"
    save_params(params, path)
    saved = json.load(open(path))
    assert saved["digest"] == {"Enzyme": "T1"}                # only non-defaults are written
    loaded = load_params(path)
    assert loaded["working_dir"] == str(tmp_path / "job")    # relative to the file
    with pytest.raises(ValueError):
        json.dump({"format": "other"}, open(path, "w"))
        load_params(path)


def test_cli_run_record_and_log(tmp_path):
    fasta = tmp_path / "one.fasta"
    fasta.write_text(">one\nGGAUCCAUGCAGUCAGG\n")
    params = default_params()
    params["working_dir"] = str(tmp_path / "job")
    params["digest"].update(RNA_sequences=str(fasta), Enzyme="T1")
    save_params(params, tmp_path / "p.json")
    p = subprocess.run([sys.executable, "-m", "pytheas1", "--nogui", "--load_vars", "--params", str(tmp_path / "p.json"),
                        "--digest"], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    runs = tmp_path / "job" / "pytheas1_runs"
    records, logs = sorted(runs.glob("*.json")), sorted(runs.glob("*.log"))
    assert len(records) == 1 and len(logs) == 1
    rec = json.load(open(records[0]))
    assert rec["log"] == str(logs[0]) and rec["stages"][0]["status"] == "ok"
    assert not any("pytheas1_runs" in f for f in rec["stages"][0]["outputs"])     # not counted as a stage output
    log = logs[0].read_text()
    assert "In silico digestion: done" in log and "=== In silico digestion ===" in p.stdout
    assert not list((tmp_path / "job").glob("pytheas1_run_*.json"))                 # nothing left in the folder itself


def test_cli_write_params_and_missing_stage(tmp_path):
    out = tmp_path / "all.json"
    p = subprocess.run([sys.executable, "-m", "pytheas1", "--write_params", str(out)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    data = json.load(open(out))
    assert set(STAGES) <= set(data) and data["match"]["MS1_ppm"] == 30
    p = subprocess.run([sys.executable, "-m", "pytheas1", "--nogui", "--load_vars", "--params", str(out)],
                       capture_output=True, text=True)
    assert p.returncode != 0 and "--all" in p.stderr
