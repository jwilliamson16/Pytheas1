"""Pytheas 1 parameter files: one JSON file holding every stage's settings.

    {
      "format": "pytheas1-parameters", "version": 1,
      "working_dir": "/path/to/job",         (optional)
      "digest": {"RNA_sequences": "my.fasta", "Enzyme": "T1", ...},
      "match":  {"MS_data": "run.mgf", ...},
      ...
    }

A stage section lists only the settings that differ from the defaults (any
omitted key takes the Pytheas 1 default). Input files that chain from an
earlier stage -- the digest for Match, the match output for the report --
can be left out or set to "auto". Relative paths are looked up in the
working folder, then among the files bundled with the package.
"""
import copy
import json
import os

from .stages import DEFAULTS, STAGES

FORMAT = "pytheas1-parameters"
VERSION = 1


def default_params():
    out = {"format": FORMAT, "version": VERSION, "working_dir": None}
    out.update(copy.deepcopy(DEFAULTS))
    return out


def load_params(path):
    with open(path) as fh:
        data = json.load(fh)
    if data.get("format") != FORMAT:
        raise ValueError(f"{path}: not a Pytheas 1 parameter file (format = {data.get('format')!r})")
    unknown = sorted(set(data) - {"format", "version", "working_dir", *STAGES})
    if unknown:
        raise ValueError(f"{path}: unknown section(s) {', '.join(unknown)}")
    wd = data.get("working_dir")
    if wd and not os.path.isabs(wd):
        data["working_dir"] = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(path)), wd))
    for stage in STAGES:
        data.setdefault(stage, {})
    return data


def save_params(params, path, only_changed=True):
    """Write params; by default each stage keeps only its non-default settings."""
    out = {"format": FORMAT, "version": VERSION, "working_dir": params.get("working_dir")}
    for stage in STAGES:
        section = params.get(stage, {})
        if only_changed:
            section = {k: v for k, v in section.items() if DEFAULTS[stage].get(k) != v}
        out[stage] = section
    with open(path, "w") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")
