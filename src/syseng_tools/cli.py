from __future__ import annotations

import argparse
from pathlib import Path

from syseng_tools.project import ProjectConfig, load_project_config
from syseng_tools.risk import generate_risk_register
from syseng_tools.strictdoc_runner import export_strictdoc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="syseng",
        description="Shared systems-engineering tooling for program records.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Program repository root. Defaults to the current directory.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser(
        "export",
        help="Generate StrictDoc outputs and shared reports.",
    )
    export_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="StrictDoc output directory. Defaults to build/strictdoc.",
    )

    risk_parser = subparsers.add_parser(
        "risk",
        help="Generate the risk register from StrictDoc JSON.",
    )
    risk_parser.add_argument(
        "--strictdoc-json",
        type=Path,
        default=None,
        help="StrictDoc JSON export. Defaults to build/strictdoc/json/index.json.",
    )
    risk_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Risk report output directory. Defaults to build/syseng.",
    )

    return parser


def command_export(project: ProjectConfig, output_dir: Path | None) -> int:
    strictdoc_output_dir = output_dir or project.strictdoc_output_dir
    export_strictdoc(project, strictdoc_output_dir)
    generate_risk_register(
        strictdoc_output_dir / "json" / "index.json",
        project.syseng_build_dir,
    )
    return 0


def command_risk(
    project: ProjectConfig,
    strictdoc_json: Path | None,
    output_dir: Path | None,
) -> int:
    source_json = strictdoc_json or project.strictdoc_output_dir / "json" / "index.json"
    report_dir = output_dir or project.syseng_build_dir
    generate_risk_register(source_json, report_dir)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    project = load_project_config(args.project_root)

    if args.command == "export":
        return command_export(project, args.output_dir)
    if args.command == "risk":
        return command_risk(project, args.strictdoc_json, args.output_dir)

    parser.error(f"Unsupported command: {args.command}")
    return 2
