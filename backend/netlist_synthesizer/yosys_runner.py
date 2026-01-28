"""YosysRunner subprocess handler for invoking the Yosys synthesis tool."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from backend.core.exceptions import SynthesisError

logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent / "scripts"


class YosysRunner:
    """Manages subprocess communication with the Yosys synthesis tool."""

    def __init__(self, timeout: int = 300) -> None:
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
            json_output = tmpdir_path / "netlist.json"

            # Build the Yosys script
            script_template = SCRIPT_DIR / script_name
            if not script_template.exists():
                raise SynthesisError(f"Yosys script template not found: {script_template}")

            template_content = script_template.read_text()
            read_commands = "\n".join(f"read_verilog {p}" for p in source_paths)
            script_content = template_content.replace("{{READ_FILES}}", read_commands)
            script_content = script_content.replace("{{JSON_OUTPUT}}", str(json_output))

            script_path = tmpdir_path / "run.ys"
            script_path.write_text(script_content)

            try:
                result = subprocess.run(
                    [self._yosys_path, "-s", str(script_path)],  # type: ignore[arg-type]
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
