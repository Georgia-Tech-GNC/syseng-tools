from __future__ import annotations

from dataclasses import dataclass
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from syseng_tools.project import ProjectConfig
from syseng_tools.strictdoc_runner import (
    _looks_like_parallelization_failure,
    _strictdoc_command,
    prepare_strictdoc_plumbing,
)


ERROR = "ERROR"
WARNING = "WARNING"

PLACEHOLDER_VALUES = {"not required", "n/a", "none", "tbd"}
FREE_TEXT_PLACEHOLDERS = ("[TBD]", "TODO", "FIXME")
OPTIONAL_PLACEHOLDER_FIELDS = {
    "RESOLUTION_OWNER",
    "RESOLUTION_PLAN",
    "RESOLUTION_DUE_DATE",
    "VERIFICATION_PLAN_LINK",
    "VERIFICATION_RESULT_LINK",
    "WAIVER_LINK",
    "RESPONSE_PLAN",
    "DUE_DATE",
    "LINKED_ARTIFACTS",
    "DISPOSITION_NOTES",
    "CONTENT",
}
FREE_TEXT_FIELDS = {
    "TITLE",
    "STATEMENT",
    "RATIONALE",
    "INDIVIDUAL_OWNER",
    "VEHICLE_CONFIGURATION",
    "MISSION_PHASE",
    "FLIGHT_ATTEMPT",
    "RESOLUTION_OWNER",
    "RESOLUTION_PLAN",
    "RESOLUTION_DUE_DATE",
    "VERIFICATION_PLAN_LINK",
    "VERIFICATION_RESULT_LINK",
    "WAIVER_LINK",
    "RESPONSE_PLAN",
    "DUE_DATE",
    "LINKED_ARTIFACTS",
    "DISPOSITION_NOTES",
    "CONDITION",
    "CONSEQUENCE",
}
ACTIVE_RISK_RESPONSES = {"Watch", "Mitigate", "Avoid"}
TERMINAL_RISK_STATUSES = {"Accepted", "Closed", "Retired"}
ALLOWED_RISK_RESPONSE_BY_STATUS = {
    "Open": {"Watch", "Mitigate", "Avoid"},
    "Accepted": {"Accept"},
    "Closed": {"Watch", "Mitigate", "Avoid"},
    "Retired": {"Watch", "Mitigate", "Avoid"},
}


@dataclass(frozen=True)
class RecordLocation:
    path: Path
    line: int
    field_lines: dict[str, int]


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    severity: str
    message: str
    uid: str | None = None
    path: Path | None = None
    line: int | None = None

    @property
    def is_error(self) -> bool:
        return self.severity == ERROR

    def format(self, project_root: Path) -> str:
        parts = [self.check_id, self.severity]
        if self.uid:
            parts.append(self.uid)
        if self.path is not None:
            path = self.path.resolve()
            try:
                path = path.relative_to(project_root.resolve())
            except ValueError:
                pass
            location = path.as_posix()
            if self.line is not None:
                location = f"{location}:{self.line}"
            parts.append(f"{location}:")
        else:
            parts.append("")
        return " ".join(part for part in parts if part) + f" {self.message}"


def run_check(project: ProjectConfig, warnings_as_errors: bool = False) -> int:
    strictdoc_output_dir = project.syseng_build_dir / "check" / "strictdoc"
    strictdoc_result = run_strictdoc_json_check(project, strictdoc_output_dir)
    if strictdoc_result.returncode != 0:
        results = classify_strictdoc_failure(strictdoc_result, project)
        print_results(project, results, warnings_as_errors)
        return 1

    strictdoc_json = strictdoc_output_dir / "json" / "index.json"
    results = check_strictdoc_json(project, strictdoc_json)
    return print_results(project, results, warnings_as_errors)


def run_strictdoc_json_check(
    project: ProjectConfig,
    output_dir: Path,
) -> subprocess.CompletedProcess[str]:
    prepare_strictdoc_plumbing(project)
    command = [
        *_strictdoc_command(),
        "export",
        str(project.root),
        "--config",
        str(project.syseng_build_dir / "strictdoc_config.py"),
        "--formats",
        "json",
        "--output-dir",
        str(output_dir),
    ]
    result = subprocess.run(
        command,
        cwd=project.root,
        text=True,
        capture_output=True,
    )
    if result.returncode == 0 or not _looks_like_parallelization_failure(
        result.stdout + result.stderr
    ):
        return result

    return subprocess.run(
        [*command, "--no-parallelization"],
        cwd=project.root,
        text=True,
        capture_output=True,
    )


def classify_strictdoc_failure(
    result: subprocess.CompletedProcess[str],
    project: ProjectConfig,
) -> list[CheckResult]:
    output = result.stdout + result.stderr
    message = _strictdoc_failure_message(output)
    check_id = "CHK-001"
    if "imports a grammar from a file that does not exist" in output:
        check_id = "CHK-002"
    elif "invalid requirement type" in output.lower():
        check_id = "CHK-003"
    elif "invalid requirement field" in output.lower():
        check_id = "CHK-004"
    elif "field" in output.lower() and "required" in output.lower():
        check_id = "CHK-005"
    elif "invalid" in output.lower() and "choice" in output.lower():
        check_id = "CHK-006"
    elif "relation" in output.lower() and "does not exist" in output.lower():
        check_id = "CHK-008"
    elif "duplicate" in output.lower() and "uid" in output.lower():
        check_id = "CHK-009"

    path, line = _strictdoc_location(output)
    uid = None
    if path is not None and line is not None:
        uid = uid_for_line(scan_record_locations(project.records_dir), path, line)
        field = _strictdoc_problematic_field(output) or _strictdoc_invalid_field(
            output
        )
        if uid is not None and field is not None:
            location = scan_record_locations(project.records_dir).get(uid)
            if location is not None and field in location.field_lines:
                line = location.field_lines[field]
    return [CheckResult(check_id, ERROR, message, uid, path, line)]


def check_strictdoc_json(
    project: ProjectConfig,
    strictdoc_json: Path,
) -> list[CheckResult]:
    if not strictdoc_json.is_file():
        raise SystemExit(f"StrictDoc JSON export not found: {strictdoc_json}")

    data = json.loads(strictdoc_json.read_text(encoding="utf-8"))
    nodes = [
        node
        for node in iter_nodes(data)
        if node.get("_NODE_TYPE") in {"MISSION_RECORD", "REQUIREMENT", "RISK"}
    ]
    index = RecordIndex(nodes)
    locations = scan_record_locations(project.records_dir)
    results: list[CheckResult] = []

    for node in nodes:
        results.extend(check_common(project, node, locations))
        node_type = node["_NODE_TYPE"]
        if node_type == "MISSION_RECORD":
            results.extend(check_mission_record(node, index, locations))
        elif node_type == "REQUIREMENT":
            results.extend(check_requirement(project, node, index, locations))
        elif node_type == "RISK":
            results.extend(check_risk(project, node, index, locations))

    results.sort(key=_result_sort_key)
    return results


def check_common(
    project: ProjectConfig,
    node: dict[str, Any],
    locations: dict[str, RecordLocation],
) -> list[CheckResult]:
    uid = node["UID"]
    results: list[CheckResult] = []
    if not uid.startswith(f"{project.prefix}-"):
        results.append(
            result(
                "CHK-101",
                ERROR,
                node,
                locations,
                "UID uses the wrong project prefix.",
            )
        )

    uid_match = re.fullmatch(rf"{re.escape(project.prefix)}-[A-Z]+-(\d{{3}})", uid)
    if uid_match is None:
        results.append(
            result(
                "CHK-105",
                ERROR,
                node,
                locations,
                "UID number must be exactly three digits.",
            )
        )

    title_words = re.findall(r"[A-Za-z0-9]+", text_value(node, "TITLE"))
    if len(title_words) < 3 or len(title_words) > 6:
        results.append(
            result(
                "CHK-106",
                WARNING,
                node,
                locations,
                "title should contain three to six words.",
            )
        )

    results.extend(
        check_allowed_value(
            project,
            node,
            locations,
            "VEHICLE_CONFIGURATION",
            project.allowed_vehicle_configurations,
            "CHK-107",
            "vehicle configuration",
        )
    )
    results.extend(
        check_allowed_value(
            project,
            node,
            locations,
            "MISSION_PHASE",
            project.allowed_mission_phases,
            "CHK-108",
            "mission phase",
        )
    )
    results.extend(
        check_allowed_value(
            project,
            node,
            locations,
            "FLIGHT_ATTEMPT",
            project.allowed_flight_attempts,
            "CHK-109",
            "flight attempt",
        )
    )
    for field in ("VEHICLE_CONFIGURATION", "MISSION_PHASE", "FLIGHT_ATTEMPT"):
        if text_value(node, field).casefold() == "n/a":
            results.append(
                result(
                    "CHK-110",
                    ERROR,
                    node,
                    locations,
                    f"{field} must not use N/A.",
                    field,
                )
            )

    results.extend(check_open_item_fields(node, locations))
    results.extend(check_placeholders(node, locations))
    return results


def check_allowed_value(
    project: ProjectConfig,
    node: dict[str, Any],
    locations: dict[str, RecordLocation],
    field: str,
    allowed_values: tuple[str, ...],
    check_id: str,
    label: str,
) -> list[CheckResult]:
    if not allowed_values:
        return [
            result(
                check_id,
                ERROR,
                node,
                locations,
                f"{label} vocabulary is not configured in syseng.toml.",
                field,
            )
        ]
    value = text_value(node, field)
    if value != "All" and value not in allowed_values:
        return [
            result(
                check_id,
                ERROR,
                node,
                locations,
                f"{field} is not an allowed value: {value}.",
                field,
            )
        ]
    return []


def check_open_item_fields(
    node: dict[str, Any],
    locations: dict[str, RecordLocation],
) -> list[CheckResult]:
    if "OPEN_ITEM_STATUS" not in node:
        return []
    uid_results: list[CheckResult] = []
    fields = ("RESOLUTION_OWNER", "RESOLUTION_PLAN", "RESOLUTION_DUE_DATE")
    if node["OPEN_ITEM_STATUS"] in {"TBD", "TBR", "TBS"}:
        for field in fields:
            if not has_value(node, field):
                uid_results.append(
                    result(
                        "CHK-111",
                        ERROR,
                        node,
                        locations,
                        f"open item status is {node['OPEN_ITEM_STATUS']}, but {field} is missing.",
                        "OPEN_ITEM_STATUS",
                    )
                )
    elif node["OPEN_ITEM_STATUS"] == "None":
        for field in fields:
            if has_value(node, field):
                uid_results.append(
                    result(
                        "CHK-112",
                        ERROR,
                        node,
                        locations,
                        f"{field} must be absent when OPEN_ITEM_STATUS is None.",
                        field,
                    )
                )
    return uid_results


def check_requirement(
    project: ProjectConfig,
    node: dict[str, Any],
    index: "RecordIndex",
    locations: dict[str, RecordLocation],
) -> list[CheckResult]:
    results: list[CheckResult] = []
    uid = node["UID"]
    if not re.fullmatch(rf"{re.escape(project.prefix)}-REQ-\d{{3}}", uid):
        results.append(
            result(
                "CHK-103",
                ERROR,
                node,
                locations,
                "requirement UID must use [PROJECT]-REQ-[NNN].",
            )
        )

    statement = text_value(node, "STATEMENT")
    if not re.search(r"\bshall\b", statement, flags=re.IGNORECASE):
        results.append(
            result(
                "CHK-113",
                ERROR,
                node,
                locations,
                "requirement statement must contain shall.",
                "STATEMENT",
            )
        )
    if (
        re.search(r"\bshall\s+not\b", statement, flags=re.IGNORECASE)
        and node["REQUIREMENT_TYPE"] not in {"Design Constraint", "Safety"}
    ):
        results.append(
            result(
                "CHK-114",
                WARNING,
                node,
                locations,
                "shall not is expected only for Design Constraint or Safety "
                "requirements.",
                "STATEMENT",
            )
        )

    parent_values = parent_relation_values(node)
    if len(parent_values) != 1:
        results.append(
            result(
                "CHK-117",
                ERROR,
                node,
                locations,
                "requirement must have exactly one parent relation.",
            )
        )
    elif node["LEVEL"] == "L1":
        parent = index.by_uid.get(parent_values[0])
        if parent is None or parent.get("_NODE_TYPE") != "MISSION_RECORD":
            results.append(
                result(
                    "CHK-115",
                    ERROR,
                    node,
                    locations,
                    f"L1 parent must be a mission record: {parent_values[0]}.",
                )
            )
    elif node["LEVEL"] == "L2":
        parent = index.by_uid.get(parent_values[0])
        if (
            parent is None
            or parent.get("_NODE_TYPE") != "REQUIREMENT"
            or parent.get("LEVEL") != "L1"
        ):
            results.append(
                result(
                    "CHK-116",
                    ERROR,
                    node,
                    locations,
                    f"L2 parent must be an L1 requirement: {parent_values[0]}.",
                )
            )

    if node["STATUS"] in {"Verified", "Failed"} and not has_value(
        node, "VERIFICATION_RESULT_LINK"
    ):
        results.append(
            result(
                "CHK-118",
                ERROR,
                node,
                locations,
                f"{node['STATUS']} requirement must include "
                "VERIFICATION_RESULT_LINK.",
            )
        )
    if node["STATUS"] == "Waived" and not has_value(node, "WAIVER_LINK"):
        results.append(
            result(
                "CHK-119",
                ERROR,
                node,
                locations,
                "waived requirement must include WAIVER_LINK.",
            )
        )
    if node["STATUS"] != "Waived" and has_value(node, "WAIVER_LINK"):
        results.append(
            result(
                "CHK-120",
                ERROR,
                node,
                locations,
                "WAIVER_LINK must be absent unless status is Waived.",
                "WAIVER_LINK",
            )
        )

    for field in ("VERIFICATION_PLAN_LINK", "VERIFICATION_RESULT_LINK", "WAIVER_LINK"):
        results.extend(
            check_path_field(
                project,
                node,
                locations,
                field,
                "CHK-121",
                "CHK-122",
            )
        )

    subsystems = split_values(text_value(node, "APPLICABLE_SUBSYSTEM"))
    if "N_A" in subsystems and len(subsystems) > 1:
        results.append(
            result(
                "CHK-123",
                ERROR,
                node,
                locations,
                "Applicable subsystem must not combine N/A with other values.",
                "APPLICABLE_SUBSYSTEM",
            )
        )

    return results


def check_mission_record(
    node: dict[str, Any],
    index: "RecordIndex",
    locations: dict[str, RecordLocation],
) -> list[CheckResult]:
    results: list[CheckResult] = []
    uid = node["UID"]
    record_type = node["RECORD_TYPE"]
    if record_type == "Objective":
        if "-MO-" not in uid:
            results.append(
                result(
                    "CHK-102",
                    ERROR,
                    node,
                    locations,
                    "objective UID must use [PROJECT]-MO-[NNN].",
                )
            )
        if not text_value(node, "STATEMENT").startswith(
            ("Demonstrate that ", "Achieve ", "Determine whether ")
        ):
            results.append(
                result(
                    "CHK-124",
                    WARNING,
                    node,
                    locations,
                    "mission objective should start with an accepted pattern.",
                    "STATEMENT",
                )
            )
    elif record_type == "Constraint":
        if "-MC-" not in uid:
            results.append(
                result(
                    "CHK-102",
                    ERROR,
                    node,
                    locations,
                    "constraint UID must use [PROJECT]-MC-[NNN].",
                )
            )
        if not re.match(
            r"^The (mission|vehicle) shall (comply with|remain within|use)\b",
            text_value(node, "STATEMENT"),
        ):
            results.append(
                result(
                    "CHK-125",
                    WARNING,
                    node,
                    locations,
                    "mission constraint should start with an accepted pattern.",
                    "STATEMENT",
                )
            )
        if not index.requirements_by_parent.get(uid):
            results.append(
                result(
                    "CHK-126",
                    WARNING,
                    node,
                    locations,
                    "mission constraint has no child requirement relation.",
                )
            )
    return results


def check_risk(
    project: ProjectConfig,
    node: dict[str, Any],
    index: "RecordIndex",
    locations: dict[str, RecordLocation],
) -> list[CheckResult]:
    results: list[CheckResult] = []
    uid = node["UID"]
    if not re.fullmatch(rf"{re.escape(project.prefix)}-RISK-\d{{3}}", uid):
        results.append(
            result(
                "CHK-104",
                ERROR,
                node,
                locations,
                "risk UID must use [PROJECT]-RISK-[NNN].",
            )
        )
    if has_value(node, "CONTENT"):
        results.append(
            result(
                "CHK-127",
                ERROR,
                node,
                locations,
                "CONTENT must be absent for risk records.",
                "CONTENT",
            )
        )
    if text_value(node, "CONDITION").casefold().startswith("if"):
        results.append(
            result(
                "CHK-128",
                ERROR,
                node,
                locations,
                "condition must not start with If.",
                "CONDITION",
            )
        )
    if text_value(node, "CONSEQUENCE").casefold().startswith("then"):
        results.append(
            result(
                "CHK-129",
                ERROR,
                node,
                locations,
                "consequence must not start with then.",
                "CONSEQUENCE",
            )
        )

    affects_values = affects_relation_values(node)
    if not affects_values:
        results.append(
            result(
                "CHK-130",
                ERROR,
                node,
                locations,
                "risk must have at least one Affects relation to a requirement.",
            )
        )
    for affected_uid in affects_values:
        affected = index.by_uid.get(affected_uid)
        if affected is None or affected.get("_NODE_TYPE") != "REQUIREMENT":
            results.append(
                result(
                    "CHK-131",
                    ERROR,
                    node,
                    locations,
                    f"Affects relation must point to a requirement: {affected_uid}.",
                )
            )

    if node["RISK_RESPONSE"] in ACTIVE_RISK_RESPONSES:
        if not has_value(node, "RESPONSE_PLAN"):
            results.append(
                result(
                    "CHK-132",
                    ERROR,
                    node,
                    locations,
                    f"{node['RISK_RESPONSE']} risk must include RESPONSE_PLAN.",
                )
            )
        if not has_value(node, "DUE_DATE"):
            results.append(
                result(
                    "CHK-133",
                    ERROR,
                    node,
                    locations,
                    f"{node['RISK_RESPONSE']} risk must include DUE_DATE.",
                )
            )

    if node["STATUS"] in TERMINAL_RISK_STATUSES and not has_value(
        node, "DISPOSITION_NOTES"
    ):
        results.append(
            result(
                "CHK-134",
                ERROR,
                node,
                locations,
                f"{node['STATUS']} risk must include DISPOSITION_NOTES.",
            )
        )

    results.extend(
        check_path_field(
            project,
            node,
            locations,
            "LINKED_ARTIFACTS",
            "CHK-135",
            "CHK-136",
            allow_multiple=True,
        )
    )

    allowed_responses = ALLOWED_RISK_RESPONSE_BY_STATUS[node["STATUS"]]
    if node["RISK_RESPONSE"] not in allowed_responses:
        allowed_text = ", ".join(sorted(allowed_responses))
        results.append(
            result(
                "CHK-137",
                ERROR,
                node,
                locations,
                f"status {node['STATUS']} allows only these responses: "
                f"{allowed_text}.",
                "STATUS",
            )
        )

    return results


def check_path_field(
    project: ProjectConfig,
    node: dict[str, Any],
    locations: dict[str, RecordLocation],
    field: str,
    path_check_id: str,
    exists_check_id: str,
    allow_multiple: bool = False,
) -> list[CheckResult]:
    if not has_value(node, field):
        return []
    results: list[CheckResult] = []
    values = split_values(node[field]) if allow_multiple else [node[field].strip()]
    for value in values:
        if not is_repository_relative_path(value):
            results.append(
                result(
                    path_check_id,
                    ERROR,
                    node,
                    locations,
                    f"{field} must be a repository-relative path: {value}.",
                    field,
                )
            )
            continue
        if not (project.root / value).is_file():
            results.append(
                result(
                    exists_check_id,
                    WARNING,
                    node,
                    locations,
                    f"{field} does not resolve to a file: {value}.",
                    field,
                )
            )
    return results


def check_placeholders(
    node: dict[str, Any],
    locations: dict[str, RecordLocation],
) -> list[CheckResult]:
    results: list[CheckResult] = []
    for field in OPTIONAL_PLACEHOLDER_FIELDS:
        if field in node and text_value(node, field).casefold() in PLACEHOLDER_VALUES:
            results.append(
                result(
                    "CHK-138",
                    ERROR,
                    node,
                    locations,
                    f"{field} contains a placeholder value.",
                    field,
                )
            )
    for field in FREE_TEXT_FIELDS:
        if any(placeholder in text_value(node, field) for placeholder in FREE_TEXT_PLACEHOLDERS):
            results.append(
                result(
                    "CHK-139",
                    WARNING,
                    node,
                    locations,
                    f"{field} contains an unresolved placeholder.",
                    field,
                )
            )
    return results


class RecordIndex:
    def __init__(self, nodes: list[dict[str, Any]]) -> None:
        self.by_uid = {node["UID"]: node for node in nodes}
        self.requirements_by_parent: dict[str, list[dict[str, Any]]] = {}
        for node in nodes:
            if node.get("_NODE_TYPE") != "REQUIREMENT":
                continue
            for parent_uid in parent_relation_values(node):
                self.requirements_by_parent.setdefault(parent_uid, []).append(node)


def iter_nodes(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        if "_NODE_TYPE" in value:
            yield value
        for child in value.values():
            yield from iter_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_nodes(child)


def scan_record_locations(records_dir: Path) -> dict[str, RecordLocation]:
    locations: dict[str, RecordLocation] = {}
    for path in sorted(records_dir.glob("*.sdoc")):
        current_tag: str | None = None
        current_line = 0
        current_fields: dict[str, int] = {}
        current_uid: str | None = None
        for line_number, raw_line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            1,
        ):
            tag_match = re.fullmatch(r"\[([A-Z_]+)\]", raw_line.strip())
            if tag_match is not None:
                if current_uid is not None:
                    locations[current_uid] = RecordLocation(
                        path,
                        current_line,
                        dict(current_fields),
                    )
                current_tag = tag_match.group(1)
                current_line = line_number
                current_fields = {}
                current_uid = None
                continue
            if current_tag not in {"MISSION_RECORD", "REQUIREMENT", "RISK"}:
                continue
            field_match = re.match(r"^([A-Z][A-Z0-9_]*):\s*(.*)$", raw_line)
            if field_match is None:
                continue
            field_name = field_match.group(1)
            current_fields.setdefault(field_name, line_number)
            if field_name == "UID":
                current_uid = field_match.group(2).strip()
        if current_uid is not None:
            locations[current_uid] = RecordLocation(path, current_line, dict(current_fields))
    return locations


def parent_relation_values(node: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for relation in node.get("RELATIONS", []):
        if relation.get("TYPE") == "Parent" and "ROLE" not in relation:
            values.append(relation["VALUE"])
    return values


def affects_relation_values(node: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for relation in node.get("RELATIONS", []):
        if relation.get("TYPE") == "Parent" and relation.get("ROLE") == "Affects":
            values.append(relation["VALUE"])
    return values


def result(
    check_id: str,
    severity: str,
    node: dict[str, Any],
    locations: dict[str, RecordLocation],
    message: str,
    field: str | None = None,
) -> CheckResult:
    uid = node.get("UID")
    location = locations.get(uid)
    line = None
    path = None
    if location is not None:
        path = location.path
        line = location.field_lines.get(field, location.line) if field else location.line
    return CheckResult(check_id, severity, message, uid, path, line)


def print_results(
    project: ProjectConfig,
    results: list[CheckResult],
    warnings_as_errors: bool,
) -> int:
    error_count = sum(1 for item in results if item.severity == ERROR)
    warning_count = sum(1 for item in results if item.severity == WARNING)
    for item in results:
        print(item.format(project.root))
    print(f"syseng check: {error_count} error(s), {warning_count} warning(s)")
    if error_count or (warnings_as_errors and warning_count):
        return 1
    return 0


def has_value(node: dict[str, Any], field: str) -> bool:
    return bool(text_value(node, field))


def text_value(node: dict[str, Any], field: str) -> str:
    value = node.get(field, "")
    return value.strip() if isinstance(value, str) else ""


def split_values(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def is_repository_relative_path(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def uid_for_line(
    locations: dict[str, RecordLocation],
    path: Path,
    line: int,
) -> str | None:
    path = path.resolve()
    best_uid = None
    best_line = 0
    for uid, location in locations.items():
        if location.path.resolve() != path:
            continue
        if best_line <= location.line <= line:
            best_uid = uid
            best_line = location.line
    return best_uid


def _strictdoc_failure_message(output: str) -> str:
    semantic_error = None
    field = None
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("Semantic error:"):
            semantic_error = _normalize_strictdoc_semantic_error(
                stripped.removeprefix("Semantic error:").strip()
            )
        elif stripped.startswith("Hint: Problematic field:"):
            field = _strictdoc_problematic_field(stripped)
    if semantic_error is not None and field is not None:
        choice_error = _strictdoc_choice_error(semantic_error, field)
        if choice_error is not None:
            return choice_error
        if semantic_error.startswith("Wrong field order for record:"):
            return f"wrong field order for record. Problematic field: {field}."
        return f"{semantic_error} Problematic field: {field}."
    if semantic_error is not None:
        return semantic_error
    return _first_error_line(output)


def _normalize_strictdoc_semantic_error(message: str) -> str:
    message = re.sub(
        r"^Invalid requirement field:",
        "Invalid record field:",
        message,
    )
    message = re.sub(
        r"^Wrong field order for requirement:",
        "Wrong field order for record:",
        message,
    )
    message = re.sub(
        r"^Requirement field\b",
        "Record field",
        message,
    )
    message = re.sub(
        r"^Requirement fields:",
        "Record fields:",
        message,
    )
    message = re.sub(
        r"^Node is missing a field that is required by grammar:",
        "record is missing required field:",
        message,
    )
    message = re.sub(
        r"^Node fields:",
        "Record fields:",
        message,
    )
    return message


def _strictdoc_choice_error(message: str, field: str) -> str | None:
    match = re.fullmatch(
        r"Record field has an invalid (SingleChoice|MultipleChoice) value: (.*)\.",
        message,
    )
    if match is not None:
        return f"invalid {match.group(1)} value for {field}: {match.group(2)}."

    match = re.fullmatch(
        r"Record field of type (MultipleChoice|Tag) is invalid: (.*)\.",
        message,
    )
    if match is not None:
        return f"invalid {match.group(1)} value for {field}: {match.group(2)}."

    return None


def _strictdoc_location(output: str) -> tuple[Path | None, int | None]:
    for line in output.splitlines():
        match = re.match(r"Location: (.*):(\d+):\d+$", line.strip())
        if match is not None:
            return Path(match.group(1)), int(match.group(2))
    return None, None


def _strictdoc_problematic_field(output: str) -> str | None:
    for line in output.splitlines():
        match = re.search(r"Problematic field: ([A-Z][A-Z0-9_]*)", line)
        if match is not None:
            return match.group(1)
    return None


def _strictdoc_invalid_field(output: str) -> str | None:
    for line in output.splitlines():
        match = re.search(r"Invalid requirement field: ([A-Z][A-Z0-9_]*)", line)
        if match is not None:
            return match.group(1)
    return None


def _first_error_line(output: str) -> str:
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("error:"):
            return stripped.removeprefix("error:").strip()
    return "StrictDoc failed before syseng checks could run."


def _result_sort_key(item: CheckResult) -> tuple[str, str, int, str]:
    path = item.path.as_posix() if item.path else ""
    line = item.line or 0
    return (path, item.uid or "", line, item.check_id)
