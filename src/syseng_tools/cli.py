from __future__ import annotations

import argparse
from pathlib import Path

from syseng_tools.project import load_project_config


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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    load_project_config(args.project_root)
    parser.print_help()
    return 0
