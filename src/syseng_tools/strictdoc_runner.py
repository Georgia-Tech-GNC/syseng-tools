from __future__ import annotations

from importlib.resources import files
from pathlib import Path
import shutil
import subprocess
import sys
import os

from syseng_tools.project import ProjectConfig


def export_strictdoc(project: ProjectConfig, output_dir: Path) -> None:
    prepare_strictdoc_plumbing(project)

    command = [
        *_strictdoc_command(),
        "export",
        str(project.root),
        "--config",
        str(project.syseng_build_dir / "strictdoc_config.py"),
        "--formats",
        "html,json,excel",
        "--output-dir",
        str(output_dir),
    ]
    _run_strictdoc_export(command, project.root)


def prepare_strictdoc_plumbing(project: ProjectConfig) -> None:
    grammar_dir = project.syseng_build_dir / "grammar"
    grammar_dir.mkdir(parents=True, exist_ok=True)

    grammar_source = files("syseng_tools").joinpath("strictdoc/program.sgra")
    shutil.copyfile(grammar_source, grammar_dir / "program.sgra")

    config_path = project.syseng_build_dir / "strictdoc_config.py"
    config_path.write_text(_strictdoc_config_text(project), encoding="utf-8")


def _strictdoc_config_text(project: ProjectConfig) -> str:
    records_pattern = f"{_posix_relpath(project.records_dir, project.root)}/*.sdoc"
    grammar_path = project.syseng_build_dir / "grammar" / "program.sgra"
    grammar_rel_path = _posix_relpath(grammar_path, project.root)
    grammar_pattern = f"{_posix_relpath(grammar_path.parent, project.root)}/*.sgra"
    return f'''from strictdoc.core.project_config import ProjectConfig


class SysengProjectConfig(ProjectConfig):
    def validate_and_finalize(self) -> None:
        super().validate_and_finalize()
        self.exclude_doc_paths = [
            path
            for path in self.exclude_doc_paths
            if path not in {{"build/", "/build/", "build/**", "/build/**"}}
        ]


def create_config() -> SysengProjectConfig:
    return SysengProjectConfig(
        project_title={project.title!r},
        include_doc_paths=[
            {records_pattern!r},
            {grammar_pattern!r},
        ],
        exclude_doc_paths=[
            ".git/**",
            ".venv/**",
            "build/strictdoc/**",
        ],
        grammars={{
            "@program": {grammar_rel_path!r},
        }},
    )
'''


def _strictdoc_command() -> list[str]:
    executable = shutil.which("strictdoc")
    if executable is not None:
        return [executable]
    return [
        sys.executable,
        "-c",
        "from strictdoc.cli.main import main; main()",
    ]


def _run_strictdoc_export(command: list[str], cwd: Path) -> None:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if result.returncode == 0:
        _print_completed_process(result)
        return

    combined_output = result.stdout + result.stderr
    if _looks_like_parallelization_failure(combined_output):
        retry_command = [*command, "--no-parallelization"]
        retry_result = subprocess.run(
            retry_command,
            cwd=cwd,
            text=True,
            capture_output=True,
        )
        _print_completed_process(retry_result)
        retry_result.check_returncode()
        return

    _print_completed_process(result)
    result.check_returncode()


def _looks_like_parallelization_failure(output: str) -> bool:
    return (
        "SC_SEM_NSEMS_MAX" in output
        or "MultiprocessingParallelizer" in output
        or "Operation not permitted" in output
        or "process in the process pool was terminated abruptly" in output
    )


def _print_completed_process(result: subprocess.CompletedProcess[str]) -> None:
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)


def _posix_relpath(path: Path, start: Path) -> str:
    return Path(os.path.relpath(path, start)).as_posix()
