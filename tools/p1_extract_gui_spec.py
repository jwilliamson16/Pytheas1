"""Generate src/pytheas1/gui_spec.py from the original Gooey entry scripts.

Each GUI_version stage script declares its options with GooeyParser
add_argument() calls. This reads them with `ast` (nothing is imported or
run) and writes, per stage, the program name, the description and every
option in declaration order: name, required (positional), help, type,
choices, nargs, action and Gooey widget. The GUI is built from that table,
so its options, order and help text are the published ones.

Defaults are not copied: stages.DEFAULTS is the single source, and this
checks that every option here has an entry there and vice versa.

    python tools/p1_extract_gui_spec.py            # rewrites src/pytheas1/gui_spec.py
"""
import ast
import os
import pprint
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SCRIPTS = {
    "digest": "in_silico_digestion/pytheas_insilico_digestion.py",
    "match": "matching_scoring/pytheas_matching_scoring.py",
    "stats": "statistical_analysis/pytheas_statistical_analysis.py",
    "report": "final_report/pytheas_final_report.py",
    "mapping": "sequence_mapping/pytheas_mapping.py",
    "visualize": "visualization_spectra/pytheas_visualization.py",
}
KEYS = ("help", "choices", "nargs", "action", "widget")


def literal(node):
    try:
        return ast.literal_eval(node)
    except ValueError:
        return ast.unparse(node)


def read_script(path):
    tree = ast.parse(open(path).read())
    program, description, options = None, None, []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and getattr(dec.func, "id", "") == "Gooey":
                    program = next((literal(k.value) for k in dec.keywords if k.arg == "program_name"), None)
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "description":
            description = literal(node.value)
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "add_argument":
            flag = literal(node.args[0])
            opt = {"name": flag.lstrip("-"), "required": not flag.startswith("-"), "_line": node.lineno}
            for k in node.keywords:
                if k.arg in KEYS:
                    opt[k.arg] = literal(k.value)
                elif k.arg == "type":
                    opt["type"] = ast.unparse(k.value)
            options.append(opt)
    options.sort(key=lambda o: o["_line"])          # ast.walk is breadth-first
    for o in options:
        del o["_line"]
    return program, description, options


def main():
    sys.path.insert(0, os.path.join(REPO, "src"))
    from pytheas1.stages import DEFAULTS
    spec, problems = {}, []
    for stage, rel in SCRIPTS.items():
        program, description, options = read_script(os.path.join(REPO, "GUI_version", rel))
        names = [o["name"] for o in options]
        if set(names) != set(DEFAULTS[stage]):
            problems.append(f"{stage}: script {sorted(set(names) ^ set(DEFAULTS[stage]))} differ from DEFAULTS")
        spec[stage] = {"program": program, "description": description, "options": options}
    if problems:
        sys.exit("\n".join(problems))
    out = os.path.join(REPO, "src", "pytheas1", "gui_spec.py")
    with open(out, "w") as fh:
        fh.write('"""Option table for the GUI, generated from the original Gooey entry scripts\n'
                 "(GUI_version/*/pytheas_*.py) by tools/p1_extract_gui_spec.py. Do not edit by hand.\n\n"
                 "Per stage: program name, description, and the options in declaration order.\n"
                 "Defaults live in stages.DEFAULTS.\n"
                 '"""\n\n'
                 "SPEC = " + pprint.pformat(spec, width=110, sort_dicts=False) + "\n")
    print(f"wrote {out}: " + ", ".join(f"{s} {len(v['options'])}" for s, v in spec.items()))


if __name__ == "__main__":
    main()
