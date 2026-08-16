from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from syseng_tools.cli import command_export
from syseng_tools.project import ProjectConfig, load_project_config
from syseng_tools.strictdoc_runner import export_strictdoc


class ExportTests(unittest.TestCase):
    def test_export_prepares_generated_plumbing_and_invokes_strictdoc(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = make_project(root)
            output_dir = root / "custom-output"

            with (
                patch(
                    "syseng_tools.strictdoc_runner.shutil.which",
                    return_value="/usr/bin/strictdoc",
                ),
                patch("syseng_tools.strictdoc_runner.subprocess.run") as run,
            ):
                run.return_value = subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout="exported\n",
                    stderr="",
                )

                export_strictdoc(project, output_dir)

            self.assertTrue(
                (root / "build" / "syseng" / "grammar" / "program.sgra").is_file()
            )
            config_text = (
                root / "build" / "syseng" / "strictdoc_config.py"
            ).read_text(encoding="utf-8")
            self.assertIn("project_title='Sample TVC'", config_text)
            self.assertIn("'records/*.sdoc'", config_text)
            self.assertIn("'build/syseng/grammar/*.sgra'", config_text)

            command = run.call_args.args[0]
            cwd = run.call_args.kwargs["cwd"]
            self.assertEqual(cwd, root)
            self.assertEqual(command[:3], ["/usr/bin/strictdoc", "export", str(root)])
            self.assertIn("--formats", command)
            self.assertIn("html,json,excel", command)
            self.assertIn(str(output_dir), command)

    def test_export_retries_without_parallelization_after_sandbox_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = make_project(root)

            with (
                patch(
                    "syseng_tools.strictdoc_runner.shutil.which",
                    return_value="/usr/bin/strictdoc",
                ),
                patch("syseng_tools.strictdoc_runner.subprocess.run") as run,
            ):
                run.side_effect = [
                    subprocess.CompletedProcess(
                        args=[],
                        returncode=1,
                        stdout="",
                        stderr="MultiprocessingParallelizer Operation not permitted",
                    ),
                    subprocess.CompletedProcess(
                        args=[],
                        returncode=0,
                        stdout="exported\n",
                        stderr="",
                    ),
                ]

                export_strictdoc(project, root / "build" / "strictdoc")

            self.assertEqual(run.call_count, 2)
            retry_command = run.call_args_list[1].args[0]
            self.assertEqual(retry_command[-1], "--no-parallelization")

    def test_export_retries_without_parallelization_after_process_pool_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = make_project(root)

            with (
                patch(
                    "syseng_tools.strictdoc_runner.shutil.which",
                    return_value="/usr/bin/strictdoc",
                ),
                patch("syseng_tools.strictdoc_runner.subprocess.run") as run,
            ):
                run.side_effect = [
                    subprocess.CompletedProcess(
                        args=[],
                        returncode=1,
                        stdout="",
                        stderr=(
                            "A process in the process pool was terminated "
                            "abruptly while the future was running or pending."
                        ),
                    ),
                    subprocess.CompletedProcess(
                        args=[],
                        returncode=0,
                        stdout="exported\n",
                        stderr="",
                    ),
                ]

                export_strictdoc(project, root / "build" / "strictdoc")

            self.assertEqual(run.call_count, 2)
            retry_command = run.call_args_list[1].args[0]
            self.assertEqual(retry_command[-1], "--no-parallelization")

    def test_command_export_generates_strictdoc_outputs_and_risk_reports(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "sample_project"
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "sample_project"
            shutil.copytree(
                fixture,
                project_root,
                ignore=shutil.ignore_patterns("build"),
            )
            project = load_project_config(project_root)

            result = command_export(project, None)

            self.assertEqual(result, 0)
            self.assertTrue(
                (project_root / "build" / "strictdoc" / "html" / "index.html").is_file()
            )
            self.assertTrue(
                (project_root / "build" / "strictdoc" / "json" / "index.json").is_file()
            )
            self.assertTrue(
                (project_root / "build" / "syseng" / "risk-register.json").is_file()
            )
            self.assertTrue(
                (project_root / "build" / "syseng" / "risk-register.csv").is_file()
            )
            self.assertTrue(
                (project_root / "build" / "syseng" / "risk-register.md").is_file()
            )


def make_project(root: Path) -> ProjectConfig:
    records_dir = root / "records"
    records_dir.mkdir()
    return ProjectConfig(
        root=root,
        title="Sample TVC",
        prefix="TVC",
        records_dir=records_dir,
        allowed_vehicle_configurations=("TVC-F1",),
        allowed_mission_phases=("Powered ascent",),
        allowed_flight_attempts=("Flight 1",),
    )


if __name__ == "__main__":
    unittest.main()
