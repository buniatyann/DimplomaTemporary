"""YosysRunner subprocess handler for invoking the Yosys synthesis tool."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from backend.core.exceptions import SynthesisError

logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent / "scripts"


def _to_short_path(p: str | Path) -> str:
    """Convert a path to Windows 8.3 short form to avoid Unicode issues."""
    if sys.platform != "win32":
        return str(p)
    import ctypes
    buf = ctypes.create_unicode_buffer(260)
    ret = ctypes.windll.kernel32.GetShortPathNameW(str(p), buf, 260)
    return buf.value if ret else str(p)


class YosysRunner:
    """Manages subprocess communication with the Yosys synthesis tool."""

    def __init__(self, timeout: int = 1800) -> None:
        self._timeout = timeout
        self._yosys_path = shutil.which("yosys")

    @property
    def is_available(self) -> bool:
        return self._yosys_path is not None

    def elaborate(self, source_paths: list[Path]) -> tuple[dict, str, str]:
        """Run elaboration-only flow on source files.

        Returns:
            Tuple of (json_netlist_dict, stdout, stderr).
        """
        return self._run_script("elaborate.ys", source_paths)

    def synthesize(self, source_paths: list[Path]) -> tuple[dict, str, str]:
        """Run full synthesis flow on source files.

        Returns:
            Tuple of (json_netlist_dict, stdout, stderr).
        """
        return self._run_script("synthesize.ys", source_paths)

    def preprocess(self, source_paths: list[Path]) -> tuple[dict, str, str]:
        """Run preprocessing flow (elaborate + flatten) for training data.

        Returns:
            Tuple of (json_netlist_dict, stdout, stderr).
        """
        return self._run_script("preprocess.ys", source_paths)

    def _run_script(
        self, script_name: str, source_paths: list[Path]
    ) -> tuple[dict, str, str]:
        """Execute a Yosys script template with the given source files."""
        if not self.is_available:
            raise SynthesisError(
                "Yosys is not installed or not found in PATH. "
                "Install Yosys: https://yosyshq.net/yosys/"
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Build the Yosys script
            script_template = SCRIPT_DIR / script_name
            if not script_template.exists():
                raise SynthesisError(f"Yosys script template not found: {script_template}")

            template_content = script_template.read_text()

            # Copy source files to temp dir, applying compatibility fixes
            local_paths = []
            for i, p in enumerate(source_paths):
                local_name = f"input_{i}_{Path(p).name}"
                local_copy = tmpdir_path / local_name
                content = Path(p).read_text(encoding="utf-8", errors="replace")
                # Yosys doesn't support 'trireg' — substitute with 'wire'
                content = content.replace("trireg ", "wire    ")
                local_copy.write_text(content, encoding="utf-8")
                local_paths.append(local_name)

            read_commands = "\n".join(f"read_verilog {lp}" for lp in local_paths)
            script_content = template_content.replace("{{READ_FILES}}", read_commands)
            # Use relative path for JSON output since cwd=tmpdir
            script_content = script_content.replace("{{JSON_OUTPUT}}", "netlist.json")

            script_path = tmpdir_path / "run.ys"
            script_path.write_text(script_content, encoding="utf-8")

            # Use Windows short paths to avoid Unicode issues with Yosys
            yosys_exe = _to_short_path(self._yosys_path)
            script_arg = _to_short_path(script_path)

            try:
                result = subprocess.run(
                    [yosys_exe, "-s", script_arg],
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                    cwd=tmpdir,
                )
            except subprocess.TimeoutExpired as e:
                raise SynthesisError(
                    f"Yosys timed out after {self._timeout} seconds",
                    yosys_output=str(e),
                ) from e
            except FileNotFoundError as e:
                raise SynthesisError(
                    "Yosys executable not found",
                    yosys_output=str(e),
                ) from e

            stdout = result.stdout
            stderr = result.stderr

            if result.returncode != 0:
                raise SynthesisError(
                    f"Yosys exited with code {result.returncode}",
                    yosys_output=stderr or stdout,
                )

            # Parse JSON output
            json_output = tmpdir_path / "netlist.json"
            json_netlist: dict = {}
            if json_output.exists():
                try:
                    json_netlist = json.loads(json_output.read_text())
                except json.JSONDecodeError as e:
                    raise SynthesisError(
                        f"Failed to parse Yosys JSON output: {e}",
                        yosys_output=str(e),
                    ) from e

            return json_netlist, stdout, stderr
