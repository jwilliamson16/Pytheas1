"""Run Pytheas 1 stages: defaults, input resolution and the run API.

The analysis code (the subpackages) is the published library code. It reads
and writes relative to the current directory, and stops on bad input with
sys.exit() after printing a message. Both behaviours are kept unchanged:
run_stage() switches into the job folder for the duration of a stage and
turns a SystemExit into StageError, so a caller (CLI or GUI) survives it.

DEFAULTS reproduces the argparse defaults of the six GUI_version entry
scripts exactly, including their types (argparse leaves defaults unconverted,
so e.g. enzyme_missed_cleavages is the string '0' and MS1_SeqX the int 0).
"""
import fnmatch
import glob
import os
import platform
import shutil
import time
import traceback
from importlib import resources

STAGES = ("digest", "match", "stats", "report", "mapping", "visualize")

TITLES = {
    "digest": "In silico digestion",
    "match": "Matching and scoring",
    "stats": "Statistical analysis",
    "report": "Final report",
    "mapping": "Sequence mapping",
    "visualize": "Spectra visualization",
}

ION_SERIES = ["c", "y", "a", "a-B", "w", "b", "x", "d", "z", "y-P", "z-P"]

DEFAULTS = {
    "digest": {
        "RNA_sequences": None,
        "Enzyme": None,
        "Nucleotides_light": "nts_light.xlsx",
        "Ion_mode": "-",
        "MS1_charges_table": "charges_MS1.txt",
        "MS2_charges_table": "charges_MS2.txt",
        "decoys": False,
        "list_of_known_RNA_modifications": None,
        "enzyme_missed_cleavages": "0",
        "Nucleotides_heavy": None,
        "cleaved_RNA_5end_chemistry": ["OH"],
        "cleaved_RNA_3end_chemistry": ["P"],
        "RNA_5end_chemistry": ["P"],
        "RNA_3end_chemistry": ["OH"],
        "CID_HCD_series": list(ION_SERIES),
        "SeqX_consolidation": False,
        "MS1_SeqX": 0,
        "MS2_SeqX": 0,
        "MS1_mz_min": 400,
        "MS1_mz_max": 2000,
        "MS2_mz_min": 300,
        "MS2_mz_max": 2000,
        "nonspecific_cleavage_min_length": 3,
        "nonspecific_cleavage_max_length": 10,
    },
    "match": {
        "Theoretical_digest": None,
        "MS_data": None,
        "isotopic_species": "all",
        "MS2_absolute_peak_intensity": "None",
        "MS2_most_intense_peaks": "all",
        "MS2_relative_peak_intensity": 5,
        "precursor_exclusion_window": 2.0,
        "precursor_losses_exclusion_window": 1.5,
        "MS1_ppm": 30,
        "MS2_ppm": 50,
        "MS1_offset": 0,
        "MS2_offset": 0,
        "beta": 0.075,
        "alpha": 0,
        "FDR_isotopic_species": "all",
        "MS1_mz_minimum": 400,
        "MS1_mz_maximum": 2000,
        "MS2_mz_minimum": 300,
        "MS2_mz_maximum": 2000,
        "isotopologue_precursor_matching": False,
        "exclude_precursor_charge_matching": False,
        "targets_without_decoys": False,
    },
    "stats": {
        "Targets": None,
        "Decoys": None,
        "Match_output": None,
        "isotopic_species": "all",
        "Sp_cutoff": 0,
        "sequence_lengths": "all",
        "targets_without_decoys": False,
        "hide_box_graphs": False,
        "Sp_vs_dSp_plot": False,
        "Sp_length_charge_plot": False,
    },
    "report": {
        "Match_output": None,
        "rank_maximum": 99,
        "Sp_minimum": 0,
        "dSp_maximum": 1,
        "dSp2_minimum": 0,
        "MS1_ppm_cutoff": None,
        "output_decoys": False,
        "modified_only": False,
        "unique_positions_only": False,
        "remove_redundant_SeqX_matches": False,
    },
    "mapping": {
        "Final_report": None,
        "Nucleotides_list": None,
        "RNA_sequence": None,
        "minimum_targets_length": 3,
        "Sp_cutoff": 0,
    },
    "visualize": {
        "Theoretical_digest": None,
        "MS_data": None,
        "Match_output": None,
        "visualize_decoys": False,
        "modified_only": False,
        "unique_positions_only": False,
        "remove_redundant_SeqX_matches": False,
        "rank_maximum": 99,
        "Sp_minimum": 0,
        "dSp_maximum": 1,
        "dSp2_minimum": 0,
        "MS1_ppm_cutoff": None,
        "MS2_peaks_number": "all",
        "spectra_mz_minimum": None,
        "spectra_mz_maximum": None,
    },
}

REQUIRED = {
    "digest": ["RNA_sequences", "Enzyme"],
    "match": ["Theoretical_digest", "MS_data"],
    "stats": ["Targets", "Decoys", "Match_output"],
    "report": ["Match_output"],
    "mapping": ["Final_report", "Nucleotides_list", "RNA_sequence"],
    "visualize": ["Theoretical_digest", "MS_data", "Match_output"],
}

# Parameters that name an input file. A bare name that is not found in the
# working folder falls back to the files bundled with the package
# (data/nts_light.xlsx, data/charges_MS1.txt, data/Charge_tables/...).
FILE_PARAMS = {
    "digest": ["RNA_sequences", "Nucleotides_light", "Nucleotides_heavy", "MS1_charges_table",
               "MS2_charges_table", "list_of_known_RNA_modifications"],
    "match": ["Theoretical_digest", "MS_data"],
    "stats": ["Targets", "Decoys", "Match_output"],
    "report": ["Match_output"],
    "mapping": ["Final_report", "Nucleotides_list", "RNA_sequence"],
    "visualize": ["Theoretical_digest", "MS_data", "Match_output"],
}

CHOICES = {
    ("digest", "Enzyme"): ["A", "T1", "U2", "Cus", "MC1", "MAZ", "none", "nonspecific"],
    ("digest", "Ion_mode"): ["+", "-"],
    ("digest", "enzyme_missed_cleavages"): ["0", "1", "2", "3", "4"],
    ("digest", "cleaved_RNA_5end_chemistry"): ["OH", "P"],
    ("digest", "cleaved_RNA_3end_chemistry"): ["OH", "P", "cP"],
    ("digest", "RNA_5end_chemistry"): ["OH", "P"],
    ("digest", "RNA_3end_chemistry"): ["OH", "P", "cP"],
    ("digest", "CID_HCD_series"): list(ION_SERIES),
    ("match", "isotopic_species"): ["light", "heavy", "all"],
    ("match", "FDR_isotopic_species"): ["all", "light", "heavy"],
    ("stats", "isotopic_species"): ["light", "heavy", "all"],
}


class StageError(RuntimeError):
    """A stage could not run, or stopped itself (sys.exit in the library code)."""


def data_dir():
    """Folder of the files bundled with the package."""
    return str(resources.files("pytheas1") / "data")


def resolve_input(value, workdir):
    """Absolute path for an input-file parameter: as given if it exists,
    else relative to the working folder, else a bundled data file."""
    if value in (None, "", "None"):
        return None
    if os.path.isabs(value):
        return value
    for base in (workdir, os.getcwd(), data_dir()):
        candidate = os.path.join(base, value)
        if os.path.exists(candidate):
            return os.path.abspath(candidate)
    return os.path.abspath(os.path.join(workdir, value))   # let the stage report it missing


def _fasta_arg(value, workdir):
    """RNA_sequences: one path, or several -- the library splits on ';'
    under Windows and ':' elsewhere, the way Gooey's MultiFileChooser joined them."""
    paths = value if isinstance(value, (list, tuple)) else [value]
    sep = ";" if platform.system() == "Windows" else ":"
    return sep.join(resolve_input(p, workdir) for p in paths)


def merged_params(stage, params):
    unknown = sorted(set(params) - set(DEFAULTS[stage]))
    if unknown:
        raise StageError(f"{stage}: unknown parameter(s) {', '.join(unknown)}")
    p = dict(DEFAULTS[stage])
    p.update(params)
    missing = [k for k in REQUIRED[stage] if p.get(k) in (None, "", [])]
    if missing:
        raise StageError(f"{stage}: required parameter(s) not set: {', '.join(missing)}")
    for (st, key), allowed in CHOICES.items():
        if st != stage or p.get(key) is None:
            continue
        values = p[key] if isinstance(p[key], list) else [p[key]]
        bad = [v for v in values if v not in allowed]
        if bad:
            raise StageError(f"{stage}: {key} = {bad} not one of {allowed}")
    return p


RUNS_DIR = "pytheas1_runs"      # run records and logs; not a stage output


def _snapshot(folder):
    out = {}
    for root, dirs, files in os.walk(folder):
        if root == folder and RUNS_DIR in dirs:
            dirs.remove(RUNS_DIR)
        for f in files:
            path = os.path.join(root, f)
            try:
                out[path] = os.stat(path).st_mtime_ns
            except OSError:
                pass
    return out


def _run_digest(p):
    from .in_silico_digestion.enzyme_gui import Enzyme_cleavage
    from .in_silico_digestion.modify_gui import Modifications
    from .in_silico_digestion.consolidate_gui import Consolidation
    from .in_silico_digestion.decoy_gui import Decoys
    from .in_silico_digestion.calc_mass_gui import Masses

    # the same five steps, in the same order, as pytheas_insilico_digestion.py
    Enzyme_cleavage(p["RNA_sequences"], p["Enzyme"], p["enzyme_missed_cleavages"],
                    p["nonspecific_cleavage_min_length"], p["nonspecific_cleavage_max_length"],
                    p["cleaved_RNA_5end_chemistry"], p["cleaved_RNA_3end_chemistry"],
                    p["RNA_5end_chemistry"], p["RNA_3end_chemistry"]).final_output()
    Modifications(p["list_of_known_RNA_modifications"], p["Nucleotides_light"]).final_output()
    Consolidation().final_output()
    if p["decoys"]:
        Decoys().final_output()
    Masses(p["Ion_mode"], p["Nucleotides_light"], p["Nucleotides_heavy"], p["MS1_charges_table"],
           p["MS2_charges_table"], p["MS1_mz_min"], p["MS1_mz_max"], p["MS2_mz_min"], p["MS2_mz_max"],
           p["CID_HCD_series"], p["SeqX_consolidation"], p["MS1_SeqX"], p["MS2_SeqX"],
           p["RNA_sequences"]).final_output()


def _run_match(p):
    from .matching_scoring.match_library import Match

    Match(p["Theoretical_digest"], p["MS_data"], p["isotopic_species"], p["MS1_mz_minimum"],
          p["MS1_mz_maximum"], p["MS2_mz_minimum"], p["MS2_mz_maximum"], p["MS1_ppm"], p["MS2_ppm"],
          p["MS1_offset"], p["MS2_offset"], p["MS2_absolute_peak_intensity"], p["MS2_most_intense_peaks"],
          p["precursor_exclusion_window"], p["precursor_losses_exclusion_window"], p["beta"], p["alpha"],
          p["MS2_relative_peak_intensity"], p["isotopologue_precursor_matching"],
          p["exclude_precursor_charge_matching"], p["FDR_isotopic_species"],
          p["targets_without_decoys"]).final_output()


def _run_stats(p):
    from .statistical_analysis.statistics_library import Stats

    Stats(p["Targets"], p["Decoys"], p["Match_output"], p["isotopic_species"], p["Sp_cutoff"],
          p["sequence_lengths"], p["targets_without_decoys"], p["hide_box_graphs"],
          p["Sp_vs_dSp_plot"], p["Sp_length_charge_plot"]).final_output()


def _run_report(p):
    from .final_report.final_report_library import Pytheas_Output

    Pytheas_Output(p["Match_output"], p["Sp_minimum"], p["dSp_maximum"], p["output_decoys"],
                   p["modified_only"], p["unique_positions_only"], p["rank_maximum"],
                   p["remove_redundant_SeqX_matches"], p["dSp2_minimum"], p["MS1_ppm_cutoff"]).parse_match_file()


def _run_mapping(p):
    from .sequence_mapping.mapping_library import Mapping

    Mapping(p["Nucleotides_list"], p["Final_report"], p["RNA_sequence"], p["minimum_targets_length"],
            p["Sp_cutoff"]).final_output()


def _run_visualize(p):
    from .visualization_spectra.visualization_library import Visualize

    Visualize(p["Theoretical_digest"], p["MS_data"], p["Match_output"], p["MS2_peaks_number"],
              p["spectra_mz_minimum"], p["spectra_mz_maximum"], p["Sp_minimum"], p["dSp_maximum"],
              p["visualize_decoys"], p["modified_only"], p["rank_maximum"], p["unique_positions_only"],
              p["remove_redundant_SeqX_matches"], p["dSp2_minimum"], p["MS1_ppm_cutoff"]).final_output()


_RUNNERS = {"digest": _run_digest, "match": _run_match, "stats": _run_stats,
            "report": _run_report, "mapping": _run_mapping, "visualize": _run_visualize}


def run_stage(stage, params, workdir):
    """Run one stage with cwd = workdir. Returns a dict with the parameters
    used, the run time and the files the stage created or rewrote."""
    if stage not in _RUNNERS:
        raise StageError(f"unknown stage {stage!r}; stages are {', '.join(STAGES)}")
    workdir = os.path.abspath(workdir)
    os.makedirs(workdir, exist_ok=True)
    p = merged_params(stage, params)
    for key in FILE_PARAMS[stage]:
        if key == "RNA_sequences":
            p[key] = _fasta_arg(p[key], workdir)
        else:
            p[key] = resolve_input(p[key], workdir)
    # the HTML outputs load js/... relative to themselves
    if stage in ("mapping", "visualize") and not os.path.isdir(os.path.join(workdir, "js")):
        shutil.copytree(os.path.join(data_dir(), "js"), os.path.join(workdir, "js"))

    import matplotlib
    matplotlib.use("Agg")       # every plot is saved to a file; no window

    before = _snapshot(workdir)
    old_cwd = os.getcwd()
    t0 = time.time()
    os.chdir(workdir)
    try:
        _RUNNERS[stage](p)
    except SystemExit as e:
        raise StageError(f"{TITLES[stage]} stopped (exit code {e.code}); see the messages above") from None
    except Exception as e:
        raise StageError(f"{TITLES[stage]} failed: {type(e).__name__}: {e}\n{traceback.format_exc()}") from None
    finally:
        os.chdir(old_cwd)
    after = _snapshot(workdir)
    outputs = sorted(path for path, mtime in after.items() if before.get(path) != mtime)
    return {"stage": stage, "seconds": round(time.time() - t0, 2), "params": p, "outputs": outputs}


def latest(workdir, pattern, exclude=()):
    """Newest file in workdir matching pattern (None if there is none)."""
    hits = [f for f in glob.glob(os.path.join(workdir, pattern)) if os.path.basename(f) not in exclude]
    return max(hits, key=os.path.getmtime) if hits else None


def chain_inputs(stage, params, workdir, previous, settings=None):
    """Fill a stage's unset input files from earlier stages of the same run
    (or, failing that, the newest matching file in the working folder). An
    input that is set explicitly is never replaced.

    `settings` is the whole parameter file. Inputs that are an earlier
    stage's setting rather than its output (the nucleotides sheet and FASTA
    for Mapping, the MS data for Visualization) fall back to that stage's
    section when the stage was not run in this process."""
    p = dict(params)
    produced = [f for r in previous for f in r["outputs"]]
    used = {k: v for r in previous for k, v in r["params"].items()}
    for st in STAGES[:STAGES.index(stage)] if settings else ():
        for k, v in {**DEFAULTS[st], **settings.get(st, {})}.items():
            used.setdefault(k, v)

    def pick(pattern, exclude=()):
        mine = [f for f in produced if fnmatch.fnmatch(os.path.basename(f), pattern)
                and os.path.basename(f) not in exclude]
        return mine[-1] if mine else latest(workdir, pattern, exclude)

    def fill(key, value):
        if p.get(key) in (None, "", "auto") and value:
            p[key] = value

    if stage in ("match", "visualize"):
        # Digest_<fasta>.txt is the MS2 digest; Digest_MS1.txt is an MS1-only side output
        fill("Theoretical_digest", pick("Digest_*.txt", exclude=("Digest_MS1.txt",)))
    if stage == "visualize":
        fill("MS_data", used.get("MS_data"))
    if stage in ("stats", "report", "visualize"):
        fill("Match_output", pick("match_output_*.txt"))
    if stage == "stats":
        fill("Targets", pick("targets_*.csv"))
        fill("Decoys", pick("decoys_*.csv"))
    if stage == "mapping":
        fill("Final_report", pick("final_report_*.csv"))
        fill("Nucleotides_list", used.get("Nucleotides_light"))
        seqs = used.get("RNA_sequences")
        if isinstance(seqs, (list, tuple)):
            seqs = seqs[0] if seqs else None
        if seqs:
            fill("RNA_sequence", seqs.split(";" if platform.system() == "Windows" else ":")[0])
    return p
