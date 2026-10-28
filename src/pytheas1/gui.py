"""Pytheas 1 GUI: one window with a working-folder bar, a tab per stage and a log.

The options, their order and their help text come from gui_spec (generated
from the original Gooey scripts); defaults come from stages.DEFAULTS. Values
are returned in the types argparse would have produced, so a setting made
here behaves exactly as the same setting given to the original script.

A Run button saves the settings to <working folder>/pytheas1_parameters.json
and runs

    python -m pytheas1 --nogui --load_vars --workdir <folder> --<stage> ...

in a QProcess. A GUI run and a command-line run are therefore the same run,
with the same run record; the log streams into the window and Stop ends the
process. Inputs left blank chain from the stages before them.
"""
import datetime
import glob
import json
import os
import sys
import time

from PyQt5.QtCore import QProcess, QProcessEnvironment, Qt, QUrl
from PyQt5.QtGui import QDesktopServices, QFont, QFontDatabase, QTextCursor
from PyQt5.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QFileDialog, QGridLayout, QGroupBox,
                             QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
                             QPushButton, QRadioButton, QScrollArea, QSplitter, QTabWidget, QVBoxLayout, QWidget)

from . import __version__
from .gui_spec import SPEC
from .params import FORMAT, VERSION, load_params, save_params
from .stages import DEFAULTS, REQUIRED, RUNS_DIR, STAGES, TITLES, chain_inputs

PARAMS_FILE = "pytheas1_parameters.json"        # the file --load_vars reads by default
TAB_NAMES = {"digest": "Digest", "match": "Match", "stats": "Statistics", "report": "Report",
             "mapping": "Mapping", "visualize": "Visualize"}
MARK = {"ok": "  ✓", "failed": "  ✗", "running": "  …", None: ""}
# inputs that may be left blank: the stage they chain from
CHAINED = {("match", "Theoretical_digest"): "digest", ("stats", "Targets"): "match",
           ("stats", "Decoys"): "match", ("stats", "Match_output"): "match", ("report", "Match_output"): "match",
           ("mapping", "Final_report"): "report", ("mapping", "Nucleotides_list"): "digest",
           ("mapping", "RNA_sequence"): "digest", ("visualize", "Theoretical_digest"): "digest",
           ("visualize", "MS_data"): "match", ("visualize", "Match_output"): "match"}


def _show(value):
    return "" if value is None else str(value)


class Option:
    """One option: its widget, and get/set in the types argparse produces."""

    def __init__(self, stage, spec):
        self.stage, self.spec, self.name = stage, spec, spec["name"]
        self.default = DEFAULTS[stage][self.name]
        self.error = None
        self.widget = self.build()
        self.set(self.default)

    def reset(self):
        self.set(self.default)


class Flag(Option):
    def build(self):
        self.box = QCheckBox()
        return self.box

    def get(self):
        self.error = None
        return self.box.isChecked()

    def set(self, value):
        self.box.setChecked(bool(value))


class Choice(Option):
    """One of several values: a row of radio buttons."""

    def build(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self.group = QButtonGroup(w)
        self.buttons = {}
        for c in self.spec["choices"]:
            b = QRadioButton(c)
            self.group.addButton(b)
            self.buttons[c] = b
            lay.addWidget(b)
        lay.addStretch(1)
        return w

    def get(self):
        self.error = None
        b = self.group.checkedButton()
        return b.text() if b else None

    def set(self, value):
        self.group.setExclusive(False)
        for c, b in self.buttons.items():
            b.setChecked(c == _show(value))
        self.group.setExclusive(True)


class MultiChoice(Option):
    """Any of several values (a Gooey Listbox): a row of check boxes, returned in list order."""

    def build(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self.boxes = {c: QCheckBox(c) for c in self.spec["choices"]}
        for b in self.boxes.values():
            lay.addWidget(b)
        lay.addStretch(1)
        return w

    def get(self):
        chosen = [c for c, b in self.boxes.items() if b.isChecked()]
        self.error = None if chosen else f"{self.name}: choose at least one"
        return chosen

    def set(self, value):
        value = [] if value is None else ([value] if isinstance(value, str) else list(value))
        for c, b in self.boxes.items():
            b.setChecked(c in value)


class Text(Option):
    """A typed value. Blank or unchanged means the default, as an omitted flag does."""

    def build(self):
        self.edit = QLineEdit()
        self.edit.setMaximumWidth(160)
        self.edit.textChanged.connect(lambda _: self._mark())
        return self.edit

    def get(self):
        self.error = None
        t = self.edit.text().strip()
        if t in ("", _show(self.default)):
            return self.default
        typ = self.spec.get("type")
        try:
            return {"int": int, "float": float}.get(typ, str)(t)
        except ValueError:
            self.error = f"{self.name}: {t!r} is not {'an' if typ == 'int' else 'a'} {typ}"
            return self.default

    def set(self, value):
        self.edit.setText(_show(value))

    def _mark(self):
        self.get()
        self.edit.setStyleSheet("QLineEdit { background: #ffd6d6; }" if self.error else "")


class FileInput(Option):
    """An input file: a path field and Browse. Blank chains from an earlier stage."""

    def __init__(self, stage, spec, window):
        self.window = window
        self.multi = spec.get("widget") == "MultiFileChooser"
        super().__init__(stage, spec)

    def build(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.browse)
        lay.addWidget(self.edit, 1)
        lay.addWidget(browse)
        if self.default and not os.path.isabs(str(self.default)):
            self.edit.setToolTip(f"'{self.default}' is the copy bundled with Pytheas 1, "
                                 "unless the working folder has a file of that name")
        return w

    def browse(self):
        start = self.window.workdir() or os.getcwd()
        if self.multi:
            paths, _ = QFileDialog.getOpenFileNames(self.widget, self.name, start)
        else:
            path, _ = QFileDialog.getOpenFileName(self.widget, self.name, start)
            paths = [path] if path else []
        if paths:
            self.edit.setText("; ".join(self.window.relative(p) for p in paths))

    def get(self):
        self.error = None
        parts = [p.strip() for p in self.edit.text().split(";") if p.strip()]
        if not parts:
            return None if (self.stage, self.name) in CHAINED else self.default
        if self.multi and len(parts) > 1:
            return parts
        return parts[0]

    def set(self, value):
        if isinstance(value, (list, tuple)):
            value = "; ".join(value)
        self.edit.setText("" if value in (None, "auto") else str(value))

    def set_placeholder(self, text):
        self.edit.setPlaceholderText(text)


def make_option(stage, spec, window):
    if spec.get("action") == "store_true":
        return Flag(stage, spec)
    if spec.get("choices") and spec.get("nargs") == "*":
        return MultiChoice(stage, spec)
    if spec.get("choices"):
        return Choice(stage, spec)
    if spec.get("widget") in ("FileChooser", "MultiFileChooser"):
        return FileInput(stage, spec, window)
    return Text(stage, spec)


class StageTab(QWidget):
    def __init__(self, window, stage):
        super().__init__()
        self.stage = stage
        self.options = {}
        spec = SPEC[stage]
        outer = QVBoxLayout(self)
        title = QLabel(f"<b>{spec['program']}</b> &nbsp; {spec['description']}")
        outer.addWidget(title)
        inner = QWidget()
        col = QVBoxLayout(inner)
        small = QFont()
        small.setPointSizeF(max(9.0, small.pointSizeF() - 1.0))
        for heading, required in (("Required", True), ("Optional", False)):
            box = QGroupBox(heading)
            grid = QGridLayout(box)
            grid.setColumnStretch(1, 1)
            row = 0
            for o in spec["options"]:
                if o["required"] != required:
                    continue
                opt = make_option(stage, o, window)
                self.options[o["name"]] = opt
                label = QLabel(o["name"])
                label.setToolTip(o.get("help", ""))
                grid.addWidget(label, row, 0, Qt.AlignTop | Qt.AlignLeft)
                grid.addWidget(opt.widget, row, 1)
                helptext = QLabel(o.get("help", ""))
                helptext.setWordWrap(True)
                helptext.setFont(small)
                grid.addWidget(helptext, row + 1, 1)
                row += 2
            col.addWidget(box)
        col.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)
        bar = QHBoxLayout()
        self.run_button = QPushButton(f"Run {TITLES[stage]}")
        self.run_button.clicked.connect(lambda: window.run([stage]))
        defaults = QPushButton("Defaults")
        defaults.setToolTip(f"Reset every {TAB_NAMES[stage]} option to its default")
        defaults.clicked.connect(self.reset)
        bar.addWidget(defaults)
        bar.addStretch(1)
        bar.addWidget(self.run_button)
        outer.addLayout(bar)

    def get(self):
        values = {name: opt.get() for name, opt in self.options.items()}
        errors = [opt.error for opt in self.options.values() if opt.error]
        return values, errors

    def set(self, section):
        for name, opt in self.options.items():
            opt.set(section.get(name, opt.default))

    def reset(self):
        for opt in self.options.values():
            opt.reset()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Pytheas 1  ({__version__})")
        self.proc = None
        self.running = []
        self.started = 0.0
        self.params_path = None
        self.status = {s: None for s in STAGES}

        central = QWidget()
        main = QVBoxLayout(central)

        folder_bar = QHBoxLayout()
        folder_bar.addWidget(QLabel("<b>Working folder</b>"))
        self.folder = QLineEdit()
        self.folder.setPlaceholderText("folder for inputs and outputs")
        self.folder.editingFinished.connect(self.folder_changed)
        folder_bar.addWidget(self.folder, 1)
        for text, slot in (("Browse…", self.browse_folder), ("Open", self.open_folder)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            folder_bar.addWidget(b)
        folder_bar.addSpacing(16)
        folder_bar.addWidget(QLabel("<b>Settings</b>"))
        for text, slot in (("Load…", self.load_dialog), ("Save", self.save), ("Save as…", self.save_as)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            folder_bar.addWidget(b)
        main.addLayout(folder_bar)

        self.tabs = QTabWidget()
        self.stage_tabs = {}
        for s in STAGES:
            tab = StageTab(self, s)
            self.stage_tabs[s] = tab
            self.tabs.addTab(tab, TAB_NAMES[s])

        log_panel = QWidget()
        lv = QVBoxLayout(log_panel)
        lv.setContentsMargins(0, 0, 0, 0)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(20000)
        self.log.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        lv.addWidget(self.log)
        run_bar = QHBoxLayout()
        self.run_all_button = QPushButton("Run all")
        self.run_all_button.setToolTip("Run the six stages in order, each feeding the next")
        self.run_all_button.clicked.connect(lambda: self.run(list(STAGES)))
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop)
        clear = QPushButton("Clear log")
        clear.clicked.connect(self.log.clear)
        self.state = QLabel("")
        run_bar.addWidget(self.run_all_button)
        run_bar.addWidget(self.stop_button)
        run_bar.addWidget(self.state, 1)
        run_bar.addWidget(clear)
        lv.addLayout(run_bar)

        split = QSplitter(Qt.Vertical)
        split.addWidget(self.tabs)
        split.addWidget(log_panel)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        main.addWidget(split, 1)
        self.setCentralWidget(central)
        self.resize(1100, 900)
        self.refresh_chained()

    # -- working folder and settings -------------------------------------
    def workdir(self):
        t = self.folder.text().strip()
        return os.path.abspath(os.path.expanduser(t)) if t else None

    def relative(self, path):
        wd = self.workdir()
        if wd and os.path.abspath(path).startswith(wd + os.sep):
            return os.path.relpath(path, wd)
        return path

    def set_folder(self, path, load=True):
        self.folder.setText(path)
        self.folder_changed(load)

    def folder_changed(self, load=True):
        wd = self.workdir()
        f = os.path.join(wd, PARAMS_FILE) if wd else None
        if load and f and os.path.exists(f) and f != self.params_path:
            self.load(f, keep_folder=True)
        self.refresh_chained()

    def browse_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Working folder", self.workdir() or os.getcwd())
        if path:
            self.set_folder(path)

    def open_folder(self):
        if self.workdir() and os.path.isdir(self.workdir()):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.workdir()))

    def collect(self):
        """-> (parameter dict, list of errors)"""
        params = {"format": FORMAT, "version": VERSION, "working_dir": self.workdir()}
        errors = []
        for s, tab in self.stage_tabs.items():
            params[s], errs = tab.get()
            errors += errs
        return params, errors

    def apply(self, params):
        for s, tab in self.stage_tabs.items():
            tab.set(params.get(s, {}))
        self.refresh_chained()

    def load(self, path, keep_folder=False):
        try:
            params = load_params(path)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Pytheas 1", str(e))
            return False
        self.params_path = path
        if not keep_folder:
            self.folder.setText(params.get("working_dir") or os.path.dirname(os.path.abspath(path)))
        self.apply(params)
        self.say(f"settings loaded from {path}")
        return True

    def load_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load settings", self.workdir() or os.getcwd(),
                                              "Pytheas 1 settings (*.json)")
        if path:
            self.load(path)

    def save(self, path=None):
        params, errors = self.collect()
        if errors:
            QMessageBox.warning(self, "Pytheas 1", "Fix these first:\n" + "\n".join(errors))
            return None
        path = path or self.params_path or (os.path.join(self.workdir(), PARAMS_FILE) if self.workdir() else None)
        if not path:
            return self.save_as()
        save_params(params, path)
        self.params_path = path
        self.say(f"settings saved to {path}")
        return path

    def save_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save settings", self.workdir() or os.getcwd(),
                                              "Pytheas 1 settings (*.json)")
        return self.save(path) if path else None

    def refresh_chained(self, records=()):
        """Show in each blank chained input what it will use."""
        params, _ = self.collect()
        wd = self.workdir()
        for (stage, key), src in CHAINED.items():
            hint = f"auto: from {TAB_NAMES[src]}"
            if wd and os.path.isdir(wd):
                got = chain_inputs(stage, {}, wd, list(records), settings=params).get(key)
                if isinstance(got, (list, tuple)):
                    got = got[0] if got else None
                if got:
                    hint = f"auto: {self.relative(got) if os.path.isabs(str(got)) else got}"
            self.stage_tabs[stage].options[key].set_placeholder(hint)

    # -- running ----------------------------------------------------------
    def run(self, stages):
        if self.proc is not None:
            return
        wd = self.workdir()
        if not wd:
            QMessageBox.warning(self, "Pytheas 1", "Choose a working folder first.")
            return
        params, _ = self.collect()
        missing = [f"{TAB_NAMES[s]}: {k}" for s in stages for k in REQUIRED[s]
                   if params[s].get(k) in (None, "", []) and (s, k) not in CHAINED]
        if missing:
            QMessageBox.warning(self, "Pytheas 1", "Required settings are not set:\n" + "\n".join(missing))
            return
        os.makedirs(wd, exist_ok=True)
        if not self.save(os.path.join(wd, PARAMS_FILE)):
            return
        self.running = list(stages)
        self.started = time.time()
        for s in stages:
            self.set_status(s, "running")
        self.say(f"running {', '.join(TAB_NAMES[s] for s in stages)} in {wd}")
        self.proc = QProcess(self)
        self.proc.setWorkingDirectory(wd)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")
        env.insert("MPLBACKEND", "Agg")
        self.proc.setProcessEnvironment(env)
        self.proc.readyReadStandardOutput.connect(self.read_output)
        self.proc.finished.connect(self.finished)
        self.proc.errorOccurred.connect(self.process_error)
        self.set_busy(True)
        self.proc.start(sys.executable, ["-u", "-m", "pytheas1", "--nogui", "--load_vars", "--workdir", wd]
                        + [f"--{s}" for s in stages])

    def read_output(self):
        text = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        self.log.moveCursor(QTextCursor.End)
        self.log.insertPlainText(text)
        self.log.moveCursor(QTextCursor.End)

    def process_error(self, err):
        if err == QProcess.FailedToStart:
            self.say("could not start the Pytheas 1 process")
            self.finished(-1, None)

    def stop(self):
        if self.proc is not None:
            self.say("stopping")
            self.proc.kill()

    def finished(self, code, _status):
        if self.proc is None:
            return
        self.read_output()
        records = self.run_record()
        done = {r["stage"]: r.get("status") for r in records}
        for s in self.running:
            self.set_status(s, done.get(s))
        secs = time.time() - self.started
        self.say(f"finished in {secs:.0f} s" + ("" if code == 0 else f" (exit code {code})"))
        self.proc.deleteLater()
        self.proc = None
        self.running = []
        self.set_busy(False)
        self.refresh_chained(records)

    def run_record(self):
        """Stage records of the run just finished (the newest run record written since it started)."""
        wd = self.workdir()
        recs = [f for f in glob.glob(os.path.join(wd, RUNS_DIR, "*.json")) if os.path.getmtime(f) >= self.started - 1]
        if not recs:
            return []
        try:
            return json.load(open(max(recs, key=os.path.getmtime)))["stages"]
        except (OSError, ValueError, KeyError):
            return []

    def set_status(self, stage, status):
        self.status[stage] = status
        self.tabs.setTabText(STAGES.index(stage), TAB_NAMES[stage] + MARK[status])

    def set_busy(self, busy):
        for tab in self.stage_tabs.values():
            tab.run_button.setEnabled(not busy)
        self.run_all_button.setEnabled(not busy)
        self.stop_button.setEnabled(busy)
        self.state.setText("running…" if busy else "")

    def say(self, text):
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log.appendPlainText(f"[{stamp}] {text}")

    def closeEvent(self, event):
        if self.proc is not None:
            if QMessageBox.question(self, "Pytheas 1", "A run is in progress. Stop it and quit?") != QMessageBox.Yes:
                event.ignore()
                return
            self.proc.kill()
            self.proc.waitForFinished(3000)
        event.accept()


def main(args=None):
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    win = MainWindow()
    if args is not None and getattr(args, "params", None):
        win.load(args.params)
    if args is not None and getattr(args, "workdir", None):
        win.set_folder(os.path.abspath(args.workdir), load=not getattr(args, "params", None))
    win.show()
    return app.exec_()
