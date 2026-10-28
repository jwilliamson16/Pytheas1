"""Run the Pytheas 1 Training_set demo (README settings) through all six
stages with a given Python, into a fresh job folder.

usage: python p1_training_set.py <python executable> <job dir> [--seed N]
"""
import glob
import json
import os
import shutil
import subprocess
import sys

P1 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the repository
CODE = os.environ.get("P1_CODE", os.path.join(P1, "GUI_version"))
TS = os.path.join(P1, "paper_data", "Training_set")
DRIVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "p1_run_stage.py")

py, job = sys.argv[1], os.path.abspath(sys.argv[2])
seed = sys.argv[sys.argv.index("--seed") + 1] if "--seed" in sys.argv else "0"
# fixes set/dict-of-str iteration order, which decides e.g. ion order in digest lines
hashseed = sys.argv[sys.argv.index("--hashseed") + 1] if "--hashseed" in sys.argv else "0"
os.makedirs(job, exist_ok=False)
for d in ("sequence_mapping", "visualization_spectra"):   # HTML outputs load js/ relative to themselves
    if not os.path.exists(os.path.join(job, "js")):
        shutil.copytree(os.path.join(CODE, d, "js"), os.path.join(job, "js"))

dig = os.path.join(CODE, "in_silico_digestion")
fasta = os.path.join(TS, "calibration_set_sequences.fasta")
mgf = os.path.join(TS, "calibration_set.mgf")
if "--calib_charges" in sys.argv:      # the charge tables shipped with paper_data/Training_set
    MS1_CHARGES = os.path.join(TS, "charges_MS1_calibration.txt")
    MS2_CHARGES = os.path.join(TS, "charges_MS2_calibration.txt")
else:                                  # the stage folder's defaults, as in the README demo
    MS1_CHARGES = os.path.join(dig, "charges_MS1.txt")
    MS2_CHARGES = os.path.join(dig, "charges_MS2.txt")


def run(stage, args):
    cmd = [py, DRIVER, "--code", CODE, "--stage", stage, "--workdir", job, "--args", json.dumps(args), "--seed", seed]
    p = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ, PYTHONHASHSEED=hashseed))
    with open(os.path.join(job, f"_{stage}.log"), "w") as fh:
        fh.write(p.stdout + "\n--- stderr ---\n" + p.stderr)
    line = [l for l in p.stdout.splitlines() if l.startswith("P1_STAGE_RESULT ")]
    res = json.loads(line[-1][len("P1_STAGE_RESULT "):]) if line else {
        "stage": stage, "status": "crash", "seconds": None, "error": p.stderr[-2000:]}
    err = (res["error"] or "").strip().splitlines()
    print(f"{stage:10s} {res['status']:6s} {res['seconds']}s  {err[-1] if err else ''}", flush=True)
    return res


results = [run("digest", dict(
    RNA_sequences=fasta, Enzyme="none", enzyme_missed_cleavages="0",
    nonspecific_cleavage_min_length=3, nonspecific_cleavage_max_length=10,
    cleaved_RNA_5end_chemistry=["OH"], cleaved_RNA_3end_chemistry=["P"],
    RNA_5end_chemistry=["OH"], RNA_3end_chemistry=["P"],
    list_of_known_RNA_modifications=os.path.join(TS, "modfile_calibration_set.txt"),
    Nucleotides_light=os.path.join(dig, "nts_light.xlsx"), Nucleotides_heavy=None, decoys=True,
    Ion_mode="-", MS1_charges_table=MS1_CHARGES, MS2_charges_table=MS2_CHARGES,
    MS1_mz_min=400, MS1_mz_max=2000, MS2_mz_min=300, MS2_mz_max=2000,
    CID_HCD_series=["c", "y", "a", "a-B", "w", "b", "x", "d", "z", "y-P", "z-P"],
    SeqX_consolidation=False, MS1_SeqX=0, MS2_SeqX=0))]
digest = (glob.glob(os.path.join(job, "Digest_*.txt")) or [None])[0]
results.append(run("match", dict(
    Theoretical_digest=digest, MS_data=mgf, isotopic_species="light",
    MS1_mz_minimum=400, MS1_mz_maximum=2000, MS2_mz_minimum=300, MS2_mz_maximum=2000,
    MS1_ppm=30, MS2_ppm=50, MS1_offset=0, MS2_offset=0, MS2_absolute_peak_intensity="None",
    MS2_most_intense_peaks="all", precursor_exclusion_window=2.0, precursor_losses_exclusion_window=1.5,
    beta=0.075, alpha=0, MS2_relative_peak_intensity=5, isotopologue_precursor_matching=False,
    exclude_precursor_charge_matching=False, FDR_isotopic_species="all", targets_without_decoys=False)))
match_out = (glob.glob(os.path.join(job, "match_output_*.txt")) or [None])[0]
targets = (glob.glob(os.path.join(job, "targets_*.csv")) or [None])[0]
decoys = (glob.glob(os.path.join(job, "decoys_*.csv")) or [None])[0]
results.append(run("stats", dict(
    Targets=targets, Decoys=decoys, Match_output=match_out, isotopic_species="all", Sp_cutoff=0,
    sequence_lengths="all", targets_without_decoys=False, hide_box_graphs=False, Sp_vs_dSp_plot=False,
    Sp_length_charge_plot=False)))
results.append(run("report", dict(
    Match_output=match_out, Sp_minimum=0, dSp_maximum=1, output_decoys=False, modified_only=False,
    unique_positions_only=False, rank_maximum=99, remove_redundant_SeqX_matches=False, dSp2_minimum=0,
    MS1_ppm_cutoff=None)))
report = (glob.glob(os.path.join(job, "final_report_*.csv")) or [None])[0]
results.append(run("mapping", dict(
    Nucleotides_list=os.path.join(dig, "nts_light.xlsx"), Final_report=report, RNA_sequence=fasta,
    minimum_targets_length=3, Sp_cutoff=0)))
results.append(run("visualize", dict(
    Theoretical_digest=digest, MS_data=mgf, Match_output=match_out, MS2_peaks_number="all",
    spectra_mz_minimum=None, spectra_mz_maximum=None, Sp_minimum=0, dSp_maximum=1, visualize_decoys=False,
    modified_only=False, rank_maximum=99, unique_positions_only=False, remove_redundant_SeqX_matches=False,
    dSp2_minimum=0, MS1_ppm_cutoff=None)))
json.dump(results, open(os.path.join(job, "_results.json"), "w"), indent=1)
