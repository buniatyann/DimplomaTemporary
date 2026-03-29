"""Main application window wiring all GUI components together."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QSplitter,
    QStatusBar,
    QWidget,
)

from gui.config import GUIConfig
from gui.file_explorer import FileExplorer
from gui.reports_dir_dialog import ReportsDirDialog
from gui.tabbed_log_panel import TabbedLogPanel
from gui.state import AppState, AppStateManager, FileStatus
from gui.toolbar import Toolbar
from gui.workers import DesignWorker, DetectionWorker

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Top-level window: toolbar + splitter(file_explorer | log_viewer) + status bar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Hardware Trojan Detector")

        self._config = GUIConfig.load()
        self._state_mgr = AppStateManager(self)
        self._worker: DetectionWorker | DesignWorker | None = None
        self._last_results: dict[str, dict[str, Any]] = {}

        # ── Load stylesheet ──
        self._apply_stylesheet()

        # ── Widgets ──
        self._toolbar = Toolbar(self)
        self.addToolBar(self._toolbar)

        self._file_explorer = FileExplorer(self._state_mgr, self)
        self._log_panel = TabbedLogPanel(max_lines=self._config.max_log_lines, parent=self)
        self._log_panel.auto_scroll = self._config.auto_scroll

        # ── Layout ──
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self._file_explorer)
        splitter.addWidget(self._log_panel)
        splitter.setSizes(self._config.splitter_sizes)
        self._splitter = splitter
        self.setCentralWidget(splitter)

        # ── Status bar ──
        self._status_bar = QStatusBar(self)
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready")

        # ── Restore geometry ──
        self.resize(self._config.window_width, self._config.window_height)

        # ── Connect signals ──
        self._connect_signals()

        # ── Reports directory ──
        self._reports_dir: str = self._config.reports_directory
        self._ask_reports_dir()

        self._log_panel.log_info("Hardware Trojan Detector ready.")

    # ------------------------------------------------------------------
    # Stylesheet
    # ------------------------------------------------------------------
    def _apply_stylesheet(self, theme: str = "dark") -> None:
        qss_path = Path(__file__).parent / "styles" / f"{theme}_theme.qss"
        if qss_path.exists():
            self.setStyleSheet(qss_path.read_text(encoding="utf-8"))
        else:
            logger.warning("Theme stylesheet not found at %s", qss_path)
        if hasattr(self, "_log_panel"):
            self._log_panel.set_theme(theme)

    # ------------------------------------------------------------------
    # Reports directory
    # ------------------------------------------------------------------
    def _ask_reports_dir(self) -> None:
        """Show the reports-directory dialog on startup."""
        dlg = ReportsDirDialog(last_reports_dir=self._reports_dir, parent=self)
        if dlg.exec() == ReportsDirDialog.DialogCode.Accepted:
            self._reports_dir = dlg.chosen_directory
            self._config.reports_directory = self._reports_dir
            self._config.save()
            self._log_panel.log_info(f"Reports directory: {self._reports_dir}")
        else:
            # User cancelled — keep previous or fall back to cwd
            if not self._reports_dir:
                self._reports_dir = str(Path.cwd())

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------
    def _connect_signals(self) -> None:
        tb = self._toolbar

        # Toolbar → actions
        tb.upload_file_clicked.connect(self._file_explorer.add_files_dialog)
        tb.upload_folder_clicked.connect(self._file_explorer.add_folder_dialog)
        tb.run_all_clicked.connect(self._start_detection_all)
        tb.run_detection_clicked.connect(self._start_detection)
        tb.run_as_design_clicked.connect(self._start_detection_as_design)
        tb.stop_clicked.connect(self._stop_detection)
        tb.remove_checked_clicked.connect(self._remove_checked)
        tb.clear_log_clicked.connect(self._log_panel.clear)
        tb.export_results_clicked.connect(self._export_results)
        tb.toggle_paths_clicked.connect(self._file_explorer.toggle_absolute_paths)
        tb.theme_toggled.connect(self._apply_stylesheet)

        # File explorer → log feedback
        self._file_explorer.files_added.connect(self._on_files_added)
        self._file_explorer.file_removed.connect(self._on_file_removed)
        self._file_explorer.selection_changed.connect(self._toolbar.update_selection_state)
        self._file_explorer.file_double_clicked.connect(self._on_file_double_clicked)

        # App state → toolbar
        self._state_mgr.state_changed.connect(self._on_state_changed)

    # ------------------------------------------------------------------
    # File events
    # ------------------------------------------------------------------
    def _on_files_added(self, paths: list[str]) -> None:
        for p in paths:
            self._log_panel.log_info(f"Added: {Path(p).name}")
        self._status_bar.showMessage(f"{len(self._file_explorer.all_paths())} file(s) loaded")

    def _on_file_removed(self, path: str) -> None:
        self._log_panel.log_info(f"Removed: {Path(path).name}")
        self._last_results.pop(path, None)

    def _remove_checked(self) -> None:
        checked = self._file_explorer.checked_paths()
        if not checked:
            self._log_panel.log_warning("No checked files to remove.")
            return
        self._file_explorer.remove_checked()
        self._status_bar.showMessage(f"{len(self._file_explorer.all_paths())} file(s) loaded")

    # ------------------------------------------------------------------
    # Detection lifecycle
    # ------------------------------------------------------------------
    def _start_detection_all(self) -> None:
        paths = self._file_explorer.all_paths()
        if not paths:
            self._log_panel.log_warning("No files loaded.")
            return
        self._run_detection(paths)

    def _start_detection(self) -> None:
        paths = self._file_explorer.checked_paths()
        if not paths:
            self._log_panel.log_warning("No checked files to analyse.")
            return
        self._run_detection(paths)

    def _run_detection(self, paths: list[str]) -> None:
        # Reset statuses for target files
        for p in paths:
            self._state_mgr.set_file_status(p, FileStatus.PENDING)

        self._state_mgr.set_state(AppState.PROCESSING)
        selected = self._toolbar.selected_models
        model_desc = ", ".join(m.upper() for m in selected)
        self._log_panel.log_info(
            f"Starting detection on {len(paths)} file(s) using {model_desc}..."
        )

        self._worker = DetectionWorker(
            paths, selected_models=selected, parent=self,
        )
        self._worker.file_started.connect(self._on_file_started)
        self._worker.file_completed.connect(self._on_file_completed)
        self._worker.file_error.connect(self._on_file_error)
        self._worker.progress_updated.connect(self._on_progress)
        self._worker.all_completed.connect(self._on_all_completed)
        self._worker.start()

    def _start_detection_as_design(self) -> None:
        paths = self._file_explorer.checked_paths()
        if not paths:
            self._log_panel.log_warning("No checked files to analyse as design.")
            return

        for p in paths:
            self._state_mgr.set_file_status(p, FileStatus.PROCESSING)

        self._state_mgr.set_state(AppState.PROCESSING)
        selected = self._toolbar.selected_models
        model_desc = ", ".join(m.upper() for m in selected)
        self._log_panel.log_info(
            f"Analyzing {len(paths)} file(s) as a single design using {model_desc}..."
        )

        self._worker = DesignWorker(paths, selected_models=selected, parent=self)
        self._worker.started_signal.connect(lambda: self._status_bar.showMessage("Analyzing design..."))
        self._worker.completed.connect(self._on_design_completed)
        self._worker.error.connect(self._on_design_error)
        self._worker.finished.connect(lambda: self._state_mgr.set_state(AppState.IDLE))
        self._worker.start()

    def _on_design_completed(self, result: dict) -> None:
        verdict = result.get("verdict", "N/A")
        confidence = result.get("confidence", 0.0)
        is_trojan = result.get("is_trojan", False)

        status = FileStatus.INFECTED if is_trojan else FileStatus.CLEAN
        for p in self._file_explorer.checked_paths():
            self._state_mgr.set_file_status(p, status)

        log_fn = self._log_panel.log_alert if is_trojan else self._log_panel.log_ok
        log_fn(f"Design verdict: {verdict} (confidence {confidence:.1%})")

        report_text = result.get("report_text", "")
        if report_text:
            self._log_panel.open_report("__design__", report_text)

        self._status_bar.showMessage(f"Design: {verdict} ({confidence:.1%})")

    def _on_design_error(self, error_msg: str) -> None:
        self._log_panel.log_alert(f"Design analysis error: {error_msg}")
        self._status_bar.showMessage("Design analysis failed")

    def _stop_detection(self) -> None:
        if self._worker:
            self._state_mgr.set_state(AppState.CANCELLING)
            self._log_panel.log_warning("Cancelling detection...")
            self._worker.cancel()

    # ------------------------------------------------------------------
    # Worker callbacks (run on main thread via signals)
    # ------------------------------------------------------------------
    def _on_file_started(self, path: str) -> None:
        self._state_mgr.set_file_status(path, FileStatus.PROCESSING)
        self._log_panel.log_info(f"Processing: {Path(path).name}")

    def _on_file_completed(self, path: str, result: dict[str, Any]) -> None:
        is_trojan = result.get("is_trojan", False)
        confidence = result.get("confidence", 0.0)
        verdict = result.get("verdict", "N/A")

        # Check if pipeline had errors (earlier stage failed)
        raw_report = result.get("raw", {}).get("report", {})
        errors = raw_report.get("errors", [])

        if errors and verdict == "N/A":
            self._state_mgr.set_file_status(path, FileStatus.ERROR)
            self._log_panel.log_alert(
                f"{Path(path).name}: Pipeline error — {errors[0]}"
            )
        elif is_trojan:
            self._state_mgr.set_file_status(path, FileStatus.INFECTED)
            self._log_panel.log_alert(
                f"{Path(path).name}: {verdict} (confidence {confidence:.1%})"
            )
        else:
            self._state_mgr.set_file_status(path, FileStatus.CLEAN)
            self._log_panel.log_ok(
                f"{Path(path).name}: {verdict} (confidence {confidence:.1%})"
            )

        self._last_results[path] = result

        # Update report path in file explorer
        export_paths = result.get("export_paths", [])
        if export_paths:
            self._file_explorer.set_report_path(path, export_paths[0])
        else:
            # Show where report would be saved
            stem = Path(path).stem
            fmt = self._toolbar.export_format
            ext = {"json": ".json", "text": ".txt", "pdf": ".pdf"}.get(fmt, ".json")
            reports_dir = self._reports_dir or str(Path.cwd())
            self._file_explorer.set_report_path(
                path, str(Path(reports_dir) / f"{stem}_report{ext}")
            )

    def _on_file_error(self, path: str, error_msg: str) -> None:
        self._state_mgr.set_file_status(path, FileStatus.ERROR)
        self._log_panel.log_alert(f"Error on {Path(path).name}: {error_msg}")
        self._last_results[path] = {
            "is_trojan": False,
            "confidence": 0.0,
            "verdict": "ERROR",
            "export_paths": [],
            "report_text": f"Detection failed for {Path(path).name}:\n\n{error_msg}",
        }

    def _on_progress(self, current: int, total: int) -> None:
        self._status_bar.showMessage(f"Processing {current}/{total}...")

    def _on_all_completed(self) -> None:
        self._state_mgr.set_state(AppState.IDLE)
        total = len(self._last_results)
        infected = sum(
            1 for r in self._last_results.values() if r.get("is_trojan")
        )
        self._log_panel.log_info(
            f"Detection complete. {infected}/{total} file(s) flagged."
        )
        self._status_bar.showMessage(
            f"Done — {infected} infected / {total} total"
        )

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------
    def _on_state_changed(self, state: AppState) -> None:
        processing = state in (AppState.PROCESSING, AppState.CANCELLING)
        self._toolbar.set_processing(processing)

    # ------------------------------------------------------------------
    # Double-click → show report in log viewer
    # ------------------------------------------------------------------
    def _on_file_double_clicked(self, path: str) -> None:
        result = self._last_results.get(path)
        if result is None:
            self._log_panel.log_warning(
                f"No report for {Path(path).name}. Run detection first."
            )
            return

        report_text = result.get("report_text", "")
        if not report_text:
            self._log_panel.log_warning(
                f"No report text available for {Path(path).name}."
            )
            return

        self._log_panel.open_report(path, report_text)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    def _export_results(self) -> None:
        if not self._last_results:
            self._log_panel.log_warning("No results to export. Run detection first.")
            return

        folder = QFileDialog.getExistingDirectory(
            self, "Export Directory", self._reports_dir or str(Path.cwd())
        )
        if not folder:
            return

        fmt = self._toolbar.export_format
        ext = {"json": ".json", "text": ".txt", "pdf": ".pdf"}.get(fmt, ".json")
        export_path = Path(folder) / f"trojan_detection_results{ext}"

        try:
            import json

            serialisable = {}
            for path, result in self._last_results.items():
                serialisable[path] = {
                    "is_trojan": result.get("is_trojan"),
                    "confidence": result.get("confidence"),
                    "verdict": result.get("verdict"),
                    "export_paths": result.get("export_paths", []),
                }

            if fmt == "json":
                export_path.write_text(
                    json.dumps(serialisable, indent=2), encoding="utf-8"
                )
            else:
                # Text / PDF fallback — write as plain text summary
                lines = [f"Hardware Trojan Detection Results", "=" * 40, ""]
                for path, info in serialisable.items():
                    verdict = info.get("verdict", "N/A")
                    conf = info.get("confidence", 0.0)
                    lines.append(f"File: {path}")
                    lines.append(f"  Verdict:    {verdict}")
                    lines.append(f"  Confidence: {conf:.1%}")
                    lines.append("")
                export_path.write_text("\n".join(lines), encoding="utf-8")

            self._log_panel.log_ok(f"Results exported to {export_path}")
        except Exception as exc:
            self._log_panel.log_alert(f"Export failed: {exc}")

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: ANN001
        self._config.window_width = self.width()
        self._config.window_height = self.height()
        self._config.splitter_sizes = self._splitter.sizes()
        self._config.auto_scroll = self._log_panel.main_log.auto_scroll
        self._config.save()

        # Ensure worker shuts down
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)

        super().closeEvent(event)
