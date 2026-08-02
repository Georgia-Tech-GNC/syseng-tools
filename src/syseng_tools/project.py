from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class ProjectConfig:
    root: Path
    title: str
    prefix: str
    records_dir: Path
    allowed_vehicle_configurations: tuple[str, ...]
    allowed_mission_phases: tuple[str, ...]
    allowed_flight_attempts: tuple[str, ...]

    @property
    def syseng_build_dir(self) -> Path:
        return self.root / "build" / "syseng"

    @property
    def strictdoc_output_dir(self) -> Path:
        return self.root / "build" / "strictdoc"


def load_project_config(project_root: Path) -> ProjectConfig:
    root = project_root.resolve()
    config_path = root / "syseng.toml"
    if not config_path.is_file():
        raise SystemExit(
            f"Missing syseng.toml in {root}. "
            "Create one with project_title, project_prefix, and records_dir."
        )

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    title = _required_string(data, "project_title", config_path)
    prefix = _required_string(data, "project_prefix", config_path)
    records_dir_value = data.get("records_dir", "records")
    if not isinstance(records_dir_value, str) or not records_dir_value:
        raise SystemExit(f"{config_path}: records_dir must be a non-empty string.")

    records_dir = root / records_dir_value
    if not records_dir.is_dir():
        raise SystemExit(f"{config_path}: records_dir does not exist: {records_dir}.")

    return ProjectConfig(
        root=root,
        title=title,
        prefix=prefix,
        records_dir=records_dir,
        allowed_vehicle_configurations=_optional_string_list(
            data,
            "allowed_vehicle_configurations",
            config_path,
        ),
        allowed_mission_phases=_optional_string_list(
            data,
            "allowed_mission_phases",
            config_path,
        ),
        allowed_flight_attempts=_optional_string_list(
            data,
            "allowed_flight_attempts",
            config_path,
        ),
    )


def _required_string(data: dict[str, object], key: str, config_path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise SystemExit(f"{config_path}: {key} must be a non-empty string.")
    return value


def _optional_string_list(
    data: dict[str, object],
    key: str,
    config_path: Path,
) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise SystemExit(f"{config_path}: {key} must be a list of non-empty strings.")
    return tuple(value)
