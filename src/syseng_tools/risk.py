from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable


RISK_SCORE = {
    "Low": 1,
    "Medium": 2,
    "High": 3,
}

DISPLAY_VALUES = {
    "Design_Constraint": "Design Constraint",
    "Flight_Software": "Flight Software",
    "Ground_Systems": "Ground Systems",
    "Mission_Success": "Mission Success",
    "N_A": "N/A",
}


def generate_risk_register(strictdoc_json: Path, output_dir: Path) -> list[dict[str, Any]]:
    if not strictdoc_json.is_file():
        raise SystemExit(f"StrictDoc JSON export not found: {strictdoc_json}")

    data = json.loads(strictdoc_json.read_text(encoding="utf-8"))
    risks = [
        _risk_record(node)
        for node in iter_nodes(data)
        if node.get("_NODE_TYPE") == "RISK"
    ]

    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "risk-register.json", risks)
    write_csv(output_dir / "risk-register.csv", risks)
    write_markdown(output_dir / "risk-register.md", risks)

    print(f"Wrote {len(risks)} risk record(s) to {output_dir}")
    return risks


def iter_nodes(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        if "_NODE_TYPE" in value:
            yield value
        for child in value.values():
            yield from iter_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_nodes(child)


def _risk_record(node: dict[str, Any]) -> dict[str, Any]:
    initial_score = _score(node, "INITIAL_LIKELIHOOD", "INITIAL_SEVERITY")
    current_score = _score(node, "CURRENT_LIKELIHOOD", "CURRENT_SEVERITY")
    return {
        "uid": node["UID"],
        "title": node["TITLE"],
        "type": display_value(node["RISK_TYPE"]),
        "subteam_owner": display_value(node["SUBTEAM_OWNER"]),
        "individual_owner": node["INDIVIDUAL_OWNER"],
        "vehicle_configuration": node["VEHICLE_CONFIGURATION"],
        "mission_phase": node["MISSION_PHASE"],
        "flight_attempt": node["FLIGHT_ATTEMPT"],
        "condition": node["CONDITION"],
        "consequence": node["CONSEQUENCE"],
        "generated_statement": generated_risk_statement(
            node["CONDITION"],
            node["CONSEQUENCE"],
        ),
        "initial_likelihood": node["INITIAL_LIKELIHOOD"],
        "initial_severity": node["INITIAL_SEVERITY"],
        "initial_score": initial_score,
        "initial_level": risk_level(initial_score),
        "current_likelihood": node["CURRENT_LIKELIHOOD"],
        "current_severity": node["CURRENT_SEVERITY"],
        "current_score": current_score,
        "current_level": risk_level(current_score),
        "risk_response": node["RISK_RESPONSE"],
        "response_plan": node.get("RESPONSE_PLAN", ""),
        "due_date": node.get("DUE_DATE", ""),
        "linked_requirements": _linked_requirements(node),
        "linked_artifacts": node.get("LINKED_ARTIFACTS", ""),
        "status": node["STATUS"],
        "disposition_notes": node.get("DISPOSITION_NOTES", ""),
    }


def _score(node: dict[str, Any], likelihood_field: str, severity_field: str) -> int:
    likelihood = _score_value(node, likelihood_field)
    severity = _score_value(node, severity_field)
    return likelihood * severity


def _score_value(node: dict[str, Any], field: str) -> int:
    value = node.get(field)
    if value in RISK_SCORE:
        return RISK_SCORE[value]
    raise SystemExit(
        f"{node.get('UID', '<unknown risk>')}: invalid or missing risk score field "
        f"{field}: {value!r}"
    )


def risk_level(score: int) -> str:
    if score >= 6:
        return "High"
    if score >= 3:
        return "Medium"
    return "Low"


def generated_risk_statement(condition: str, consequence: str) -> str:
    condition_text = condition.strip().rstrip(".")
    consequence_text = consequence.strip()
    for prefix, replacement in (("The ", "the "), ("An ", "an "), ("A ", "a ")):
        if consequence_text.startswith(prefix):
            consequence_text = replacement + consequence_text[len(prefix) :]
            break
    return f"If {condition_text}, then {consequence_text}"


def display_value(value: str) -> str:
    parts = [part.strip() for part in value.split(",")]
    return ", ".join(DISPLAY_VALUES.get(part, part) for part in parts)


def _linked_requirements(node: dict[str, Any]) -> list[str]:
    requirements: list[str] = []
    for relation in node.get("RELATIONS", []):
        if relation.get("TYPE") == "Parent" and relation.get("ROLE") == "Affects":
            value = relation.get("VALUE")
            if isinstance(value, str) and value:
                requirements.append(value)
    return requirements


def write_json(path: Path, risks: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(risks, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, risks: list[dict[str, Any]]) -> None:
    columns = [
        "uid",
        "title",
        "type",
        "subteam_owner",
        "individual_owner",
        "vehicle_configuration",
        "mission_phase",
        "flight_attempt",
        "condition",
        "consequence",
        "generated_statement",
        "initial_likelihood",
        "initial_severity",
        "initial_score",
        "initial_level",
        "current_likelihood",
        "current_severity",
        "current_score",
        "current_level",
        "risk_response",
        "response_plan",
        "due_date",
        "status",
        "linked_requirements",
        "linked_artifacts",
    ]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for risk in risks:
            row = dict(risk)
            row["linked_requirements"] = ", ".join(risk["linked_requirements"])
            writer.writerow(row)


def write_markdown(path: Path, risks: list[dict[str, Any]]) -> None:
    lines = [
        "# Risk Register",
        "",
        "| UID | Title | Type | Initial | Current | Response | Status |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for risk in risks:
        lines.append(
            "| {uid} | {title} | {type} | {initial_level} ({initial_score}) | "
            "{current_level} ({current_score}) | {risk_response} | {status} |".format(
                **risk
            )
        )
        lines.extend(
            [
                "",
                f"- Affected requirements: {', '.join(risk['linked_requirements'])}",
                f"- Claim: {risk['generated_statement']}",
                f"- Applicability: {risk['vehicle_configuration']}; "
                f"{risk['mission_phase']}; {risk['flight_attempt']}",
            ]
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
