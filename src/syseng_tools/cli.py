from __future__ import annotations

import argparse
from pathlib import Path

from syseng_tools.check import run_check
from syseng_tools.project import ProjectConfig, load_project_config
from syseng_tools.risk import generate_risk_register
from syseng_tools.serve import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    generated_html_dir,
    serve_static_site,
)
from syseng_tools.strictdoc_runner import export_strictdoc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="syseng",
        description="Systems-engineering tooling for program records.",
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
        help="Generate StrictDoc outputs and reports.",
    )
    export_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="StrictDoc output directory. Defaults to build/strictdoc.",
    )

    check_parser = subparsers.add_parser(
        "check",
        help="Run StrictDoc parsing and automated checks.",
    )
    check_parser.add_argument(
        "--warnings-as-errors",
        action="store_true",
        help="Return a failing exit code when warnings are reported.",
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

    serve_parser = subparsers.add_parser(
        "serve",
        help="Serve the generated StrictDoc HTML.",
    )
    serve_parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Host interface to bind. Defaults to {DEFAULT_HOST}.",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port to bind. Defaults to {DEFAULT_PORT}.",
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


def command_serve(project: ProjectConfig, host: str, port: int) -> int:
    serve_static_site(generated_html_dir(project), host, port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    project = load_project_config(args.project_root)

    if args.command == "export":
        return command_export(project, args.output_dir)
    if args.command == "check":
        return run_check(project, args.warnings_as_errors)
    if args.command == "risk":
        return command_risk(project, args.strictdoc_json, args.output_dir)
    if args.command == "serve":
        return command_serve(project, args.host, args.port)

    parser.error(f"Unsupported command: {args.command}")
    return 2
