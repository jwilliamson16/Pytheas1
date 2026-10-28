"""Run one Pytheas 1 stage from its library classes, without Gooey.

One process per stage: two stages ship different copies of stats_tools.py,
so they cannot share an interpreter. The stage runs with cwd = --workdir,
because Pytheas 1 writes all outputs and intermediates to the current
directory.

usage: python p1_run_stage.py --code <GUI_version dir> --stage <name>
                              --workdir <dir> --args '<json>' [--seed N]
"""
import argparse
import json
import os
import random
import sys
import time
import traceback

STAGE_DIRS = {
    "digest": "in_silico_digestion",
    "match": "matching_scoring",
    "stats": "statistical_analysis",
    "report": "final_report",
    "mapping": "sequence_mapping",
    "visualize": "visualization_spectra",
}

ap = argparse.ArgumentParser()
ap.add_argument("--code", required=True)
ap.add_argument("--stage", required=True, choices=sorted(STAGE_DIRS))
ap.add_argument("--workdir", required=True)
ap.add_argument("--args", required=True, help="JSON object of constructor arguments")
ap.add_argument("--seed", type=int, help="seed Python's random (decoy shuffling)")
a = ap.parse_args()
kw = json.loads(a.args)

sys.path.insert(0, os.path.join(os.path.abspath(a.code), STAGE_DIRS[a.stage]))
os.makedirs(a.workdir, exist_ok=True)
os.chdir(a.workdir)
if a.seed is not None:
    random.seed(a.seed)
import matplotlib  # noqa: E402

matplotlib.use("Agg")

t0 = time.time()
status, err = "ok", None
try:
    if a.stage == "digest":
        from enzyme_gui import Enzyme_cleavage
        from modify_gui import Modifications
        from consolidate_gui import Consolidation
        from decoy_gui import Decoys
        from calc_mass_gui import Masses

        Enzyme_cleavage(kw["RNA_sequences"], kw["Enzyme"], kw["enzyme_missed_cleavages"],
                        kw["nonspecific_cleavage_min_length"], kw["nonspecific_cleavage_max_length"],
                        kw["cleaved_RNA_5end_chemistry"], kw["cleaved_RNA_3end_chemistry"],
                        kw["RNA_5end_chemistry"], kw["RNA_3end_chemistry"]).final_output()
        Modifications(kw["list_of_known_RNA_modifications"], kw["Nucleotides_light"]).final_output()
        Consolidation().final_output()
        if kw["decoys"]:
            Decoys().final_output()
        Masses(kw["Ion_mode"], kw["Nucleotides_light"], kw["Nucleotides_heavy"], kw["MS1_charges_table"],
               kw["MS2_charges_table"], kw["MS1_mz_min"], kw["MS1_mz_max"], kw["MS2_mz_min"], kw["MS2_mz_max"],
               kw["CID_HCD_series"], kw["SeqX_consolidation"], kw["MS1_SeqX"], kw["MS2_SeqX"],
               kw["RNA_sequences"]).final_output()
    elif a.stage == "match":
        from match_library import Match

        Match(kw["Theoretical_digest"], kw["MS_data"], kw["isotopic_species"], kw["MS1_mz_minimum"],
              kw["MS1_mz_maximum"], kw["MS2_mz_minimum"], kw["MS2_mz_maximum"], kw["MS1_ppm"], kw["MS2_ppm"],
              kw["MS1_offset"], kw["MS2_offset"], kw["MS2_absolute_peak_intensity"], kw["MS2_most_intense_peaks"],
              kw["precursor_exclusion_window"], kw["precursor_losses_exclusion_window"], kw["beta"], kw["alpha"],
              kw["MS2_relative_peak_intensity"], kw["isotopologue_precursor_matching"],
              kw["exclude_precursor_charge_matching"], kw["FDR_isotopic_species"],
              kw["targets_without_decoys"]).final_output()
    elif a.stage == "stats":
        from statistics_library import Stats

        Stats(kw["Targets"], kw["Decoys"], kw["Match_output"], kw["isotopic_species"], kw["Sp_cutoff"],
              kw["sequence_lengths"], kw["targets_without_decoys"], kw["hide_box_graphs"],
              kw["Sp_vs_dSp_plot"], kw["Sp_length_charge_plot"]).final_output()
    elif a.stage == "report":
        from final_report_library import Pytheas_Output

        Pytheas_Output(kw["Match_output"], kw["Sp_minimum"], kw["dSp_maximum"], kw["output_decoys"],
                       kw["modified_only"], kw["unique_positions_only"], kw["rank_maximum"],
                       kw["remove_redundant_SeqX_matches"], kw["dSp2_minimum"],
                       kw["MS1_ppm_cutoff"]).parse_match_file()
    elif a.stage == "mapping":
        from mapping_library import Mapping

        Mapping(kw["Nucleotides_list"], kw["Final_report"], kw["RNA_sequence"], kw["minimum_targets_length"],
                kw["Sp_cutoff"]).final_output()
    elif a.stage == "visualize":
        from visualization_library import Visualize

        Visualize(kw["Theoretical_digest"], kw["MS_data"], kw["Match_output"], kw["MS2_peaks_number"],
                  kw["spectra_mz_minimum"], kw["spectra_mz_maximum"], kw["Sp_minimum"], kw["dSp_maximum"],
                  kw["visualize_decoys"], kw["modified_only"], kw["rank_maximum"], kw["unique_positions_only"],
                  kw["remove_redundant_SeqX_matches"], kw["dSp2_minimum"], kw["MS1_ppm_cutoff"]).final_output()
except SystemExit as e:
    status, err = "exit", f"SystemExit({e.code})"
except Exception:
    status, err = "error", traceback.format_exc()

print("P1_STAGE_RESULT " + json.dumps({"stage": a.stage, "status": status, "seconds": round(time.time() - t0, 2),
                                         "error": err}), flush=True)
sys.exit(0 if status == "ok" else 1)
