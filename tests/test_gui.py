"""GUI: option widgets give argparse's types, settings round-trip, and a run
from the window is a real --nogui run (headless, Qt offscreen)."""
import json
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PyQt5.QtWidgets")

from pytheas1 import gui                                     # noqa: E402
from pytheas1.params import save_params                       # noqa: E402
from pytheas1.stages import DEFAULTS, STAGES, data_dir        # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def app():
    a = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    a.setStyle("Fusion")
    return a


@pytest.fixture
def window(app, monkeypatch):
    # a message box would block a headless test; record it instead
    shown = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a: shown.append(a[2]))
    w = gui.MainWindow()
    w.shown = shown
    yield w
    w.close()


def training_params(workdir):
    ds = json.load(open(os.path.join(REPO, "tools", "datasets", "training_set.json")))

    def ex(v):
        if isinstance(v, str):
            return v.replace("@PAPER", os.path.join(REPO, "paper_data")).replace("@DATA", data_dir())
        return v
    out = {"format": "pytheas1-parameters", "version": 1, "working_dir": str(workdir)}
    for s, sec in ds["stages"].items():
        out[s] = {k: ex(v) for k, v in sec.items()}
    return out


def test_every_option_has_a_widget(window):
    for s in STAGES:
        assert set(window.stage_tabs[s].options) == set(DEFAULTS[s])


def test_defaults_round_trip(window):
    params, errors = window.collect()
    assert errors == []
    for s in STAGES:
        assert params[s] == DEFAULTS[s], s


def test_load_round_trip(window, tmp_path):
    p = training_params(tmp_path / "job")
    save_params(p, tmp_path / "t.json")
    assert window.load(str(tmp_path / "t.json"))
    got, errors = window.collect()
    assert errors == []
    for s in STAGES:
        want = {**DEFAULTS[s], **{k: (None if v == "auto" else v) for k, v in p[s].items()}}
        assert got[s] == want, s
    assert window.workdir() == str(tmp_path / "job")


def test_save_then_load_round_trip(app, window, tmp_path, monkeypatch):
    # change something on every tab, save, and load it into a fresh window
    t = window.stage_tabs
    window.folder.setText(str(tmp_path / "job"))
    t["digest"].options["RNA_sequences"].set(["a.fasta", "b.fasta"])
    t["digest"].options["Enzyme"].set("T1")
    t["digest"].options["CID_HCD_series"].set(["c", "y", "w"])
    t["digest"].options["decoys"].set(True)
    t["match"].options["MS1_ppm"].set("12.5")
    t["match"].options["MS_data"].set("run.mgf")
    t["stats"].options["Sp_cutoff"].set("0.2")
    t["report"].options["rank_maximum"].set("3")
    t["mapping"].options["minimum_targets_length"].set("5")
    t["visualize"].options["MS2_peaks_number"].set("50")
    before, errors = window.collect()
    assert errors == []
    path = tmp_path / "settings.json"
    assert window.save(str(path)) == str(path)
    saved = json.load(open(path))
    assert saved["digest"]["Enzyme"] == "T1" and "Ion_mode" not in saved["digest"]      # only non-defaults
    assert saved["working_dir"] == str(tmp_path / "job")
    other = gui.MainWindow()
    try:
        assert other.load(str(path))
        after, errors = other.collect()
        assert errors == [] and after == before
    finally:
        other.close()


def test_choosing_a_folder_loads_its_settings(app, window, tmp_path):
    p = training_params(tmp_path)
    p["match"]["MS1_ppm"] = 7.0
    save_params(p, tmp_path / gui.PARAMS_FILE)
    window.set_folder(str(tmp_path))
    assert window.stage_tabs["match"].options["MS1_ppm"].get() == 7.0
    assert window.params_path == str(tmp_path / gui.PARAMS_FILE)


def test_text_values_follow_argparse(window):
    m = window.stage_tabs["match"].options
    m["MS1_ppm"].set("30")
    assert m["MS1_ppm"].get() == 30 and type(m["MS1_ppm"].get()) is int     # unchanged: the default, as is
    m["MS1_ppm"].set("12.5")
    assert m["MS1_ppm"].get() == 12.5
    m["MS1_ppm"].set("ten")
    m["MS1_ppm"].get()
    assert "not a float" in m["MS1_ppm"].error
    r = window.stage_tabs["report"].options
    r["MS1_ppm_cutoff"].set("")
    assert r["MS1_ppm_cutoff"].get() is None
    r["rank_maximum"].set("3")
    assert r["rank_maximum"].get() == 3
    m["MS2_most_intense_peaks"].set("50")
    assert m["MS2_most_intense_peaks"].get() == "50"     # untyped in the original: stays a string


def test_choices_and_lists(window):
    d = window.stage_tabs["digest"].options
    d["Enzyme"].set("T1")
    assert d["Enzyme"].get() == "T1"
    d["CID_HCD_series"].set(["y", "c", "w"])
    assert d["CID_HCD_series"].get() == ["c", "y", "w"]   # the original's list order
    d["CID_HCD_series"].set([])
    d["CID_HCD_series"].get()
    assert d["CID_HCD_series"].error


def test_run_refuses_missing_required(window, tmp_path):
    window.set_folder(str(tmp_path))
    window.run(["digest"])                         # no FASTA, no enzyme
    assert window.proc is None
    assert "RNA_sequences" in window.shown[-1] and "Enzyme" in window.shown[-1]


def wait_for(app, window, timeout):
    t0 = time.time()
    while window.proc is not None and time.time() - t0 < timeout:
        app.processEvents()
        time.sleep(0.05)
    assert window.proc is None, "run did not finish"


def test_run_digest_from_window(app, window, tmp_path):
    p = training_params(tmp_path / "job")
    save_params(p, tmp_path / "t.json")
    window.load(str(tmp_path / "t.json"))
    window.run(["digest"])
    assert window.proc is not None
    wait_for(app, window, 300)
    assert window.status["digest"] == "ok"
    digest = tmp_path / "job" / "Digest_calibration_set_sequences.txt"
    assert digest.exists()
    assert (tmp_path / "job" / gui.PARAMS_FILE).exists()
    # Match's blank digest input now names the file it will use
    hint = window.stage_tabs["match"].options["Theoretical_digest"].edit.placeholderText()
    assert hint == "auto: Digest_calibration_set_sequences.txt"
    assert "In silico digestion: done" in window.log.toPlainText()


@pytest.mark.slow
def test_run_match_to_mapping_from_window(app, window, tmp_path):
    p = training_params(tmp_path / "job")
    save_params(p, tmp_path / "t.json")
    window.load(str(tmp_path / "t.json"))
    window.run(["digest", "match", "stats", "report", "mapping"])
    wait_for(app, window, 1200)
    assert [window.status[s] for s in ("digest", "match", "stats", "report", "mapping")] == ["ok"] * 5
    job = tmp_path / "job"
    assert (job / "mapping_output.csv").exists()
    # Mapping run alone takes its nucleotides sheet and FASTA from the Digest settings
    window.run(["mapping"])
    wait_for(app, window, 300)
    assert window.status["mapping"] == "ok"
