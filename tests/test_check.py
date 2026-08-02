from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from syseng_tools.check import _strictdoc_failure_message, check_strictdoc_json
from syseng_tools.project import ProjectConfig


class CheckTests(unittest.TestCase):
    def test_clean_project_has_no_syseng_check_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = make_project(root)
            write_supporting_files(root)
            strictdoc_json = write_json(root, clean_data())

            results = check_strictdoc_json(project, strictdoc_json)

        self.assertEqual(results, [])

    def test_broken_project_reports_expected_check_ids(self) -> None:
        data = clean_data()
        requirement = data["DOCUMENTS"][1]["NODES"][0]
        requirement["UID"] = "BAD-REQ-14"
        requirement["LEVEL"] = "L2"
        requirement["STATEMENT"] = "The vehicle estimates attitude."
        requirement["APPLICABLE_SUBSYSTEM"] = "Avionics, N_A"
        requirement["STATUS"] = "Waived"
        requirement["VERIFICATION_PLAN_LINK"] = "/tmp/plan.md"

        risk = data["DOCUMENTS"][2]["NODES"][0]
        risk["CONTENT"] = "Do not render this."
        risk["CONDITION"] = "If actuator bandwidth is lower than assumed."
        risk["CONSEQUENCE"] = "then the vehicle may lose attitude control."
        risk["RISK_RESPONSE"] = "Accept"
        risk["STATUS"] = "Open"
        risk["RELATIONS"] = []

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = make_project(root)
            write_supporting_files(root)
            strictdoc_json = write_json(root, data)

            check_ids = {
                item.check_id
                for item in check_strictdoc_json(project, strictdoc_json)
            }

        self.assertTrue(
            {
                "CHK-101",
                "CHK-103",
                "CHK-105",
                "CHK-113",
                "CHK-116",
                "CHK-119",
                "CHK-121",
                "CHK-123",
                "CHK-127",
                "CHK-128",
                "CHK-129",
                "CHK-130",
                "CHK-137",
            }.issubset(check_ids)
        )

    def test_strictdoc_choice_diagnostic_uses_record_vocabulary(self) -> None:
        message = _strictdoc_failure_message(
            "\n".join(
                [
                    "error: could not parse file: records/risks.sdoc.",
                    (
                        "Semantic error: Requirement field has an invalid "
                        "SingleChoice value: Severe."
                    ),
                    "Location: records/risks.sdoc:7:1",
                    "Hint: Problematic field: CURRENT_SEVERITY.",
                ]
            )
        )

        self.assertEqual(
            message,
            "invalid SingleChoice value for CURRENT_SEVERITY: Severe.",
        )

    def test_strictdoc_field_diagnostic_uses_record_vocabulary(self) -> None:
        message = _strictdoc_failure_message(
            "\n".join(
                [
                    "error: could not parse file: records/risks.sdoc.",
                    "Semantic error: Invalid requirement field: BAD_FIELD",
                    "Location: records/risks.sdoc:7:1",
                ]
            )
        )

        self.assertEqual(message, "Invalid record field: BAD_FIELD")

    def test_strictdoc_field_order_diagnostic_is_shortened(self) -> None:
        message = _strictdoc_failure_message(
            "\n".join(
                [
                    "error: could not parse file: records/risks.sdoc.",
                    (
                        "Semantic error: Wrong field order for requirement: "
                        "[UID, STATUS, RISK_RESPONSE]."
                    ),
                    "Location: records/risks.sdoc:7:1",
                    "Hint: Problematic field: STATUS.",
                ]
            )
        )

        self.assertEqual(
            message,
            "wrong field order for record. Problematic field: STATUS.",
        )

    def test_strictdoc_missing_field_diagnostic_uses_record_vocabulary(self) -> None:
        message = _strictdoc_failure_message(
            "\n".join(
                [
                    "error: could not parse file: records/risks.sdoc.",
                    (
                        "Semantic error: Node is missing a field that is "
                        "required by grammar: CURRENT_SEVERITY."
                    ),
                    "Location: records/risks.sdoc:7:1",
                ]
            )
        )

        self.assertEqual(
            message,
            "record is missing required field: CURRENT_SEVERITY.",
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


def write_supporting_files(root: Path) -> None:
    verification_dir = root / "docs" / "verification"
    verification_dir.mkdir(parents=True)
    (verification_dir / "attitude-estimate-analysis.md").write_text(
        "# Attitude Estimate Analysis\n",
        encoding="utf-8",
    )
    (verification_dir / "actuator-frequency-response-test.md").write_text(
        "# Actuator Frequency-Response Test\n",
        encoding="utf-8",
    )


def write_json(root: Path, data: dict[str, Any]) -> Path:
    strictdoc_json = root / "index.json"
    strictdoc_json.write_text(json.dumps(data), encoding="utf-8")
    return strictdoc_json


def clean_data() -> dict[str, Any]:
    return {
        "DOCUMENTS": [
            {
                "NODES": [
                    {
                        "_NODE_TYPE": "MISSION_RECORD",
                        "UID": "TVC-MO-001",
                        "RECORD_TYPE": "Objective",
                        "TITLE": "Controlled Powered Ascent",
                        "SUBTEAM_OWNER": "Systems",
                        "INDIVIDUAL_OWNER": "Systems Lead",
                        "VEHICLE_CONFIGURATION": "TVC-F1",
                        "MISSION_PHASE": "Powered ascent",
                        "FLIGHT_ATTEMPT": "Flight 1",
                        "OPEN_ITEM_STATUS": "None",
                        "STATUS": "Approved",
                        "STATEMENT": (
                            "Demonstrate that the vehicle can maintain vertical "
                            "attitude during powered ascent."
                        ),
                        "RATIONALE": "Supports the mission.",
                    },
                    {
                        "_NODE_TYPE": "MISSION_RECORD",
                        "UID": "TVC-MC-001",
                        "RECORD_TYPE": "Constraint",
                        "TITLE": "Range Safety Compliance",
                        "SUBTEAM_OWNER": "Systems",
                        "INDIVIDUAL_OWNER": "Systems Lead",
                        "VEHICLE_CONFIGURATION": "All",
                        "MISSION_PHASE": "All",
                        "FLIGHT_ATTEMPT": "All",
                        "OPEN_ITEM_STATUS": "None",
                        "STATUS": "Approved",
                        "STATEMENT": (
                            "The vehicle shall comply with applicable range "
                            "safety rules."
                        ),
                        "RATIONALE": "Required by the launch authority.",
                    },
                ]
            },
            {
                "NODES": [
                    {
                        "_NODE_TYPE": "REQUIREMENT",
                        "UID": "TVC-REQ-001",
                        "LEVEL": "L1",
                        "REQUIREMENT_TYPE": "Functional",
                        "TITLE": "Powered Ascent Attitude",
                        "APPLICABLE_SUBSYSTEM": "Avionics, Flight_Software",
                        "SUBTEAM_OWNER": "Electrical, Software, Controls",
                        "INDIVIDUAL_OWNER": "Systems Lead",
                        "VEHICLE_CONFIGURATION": "TVC-F1",
                        "MISSION_PHASE": "Powered ascent",
                        "FLIGHT_ATTEMPT": "Flight 1",
                        "OPEN_ITEM_STATUS": "None",
                        "VERIFICATION_METHOD": "Analysis",
                        "VERIFICATION_PLAN_LINK": (
                            "docs/verification/attitude-estimate-analysis.md"
                        ),
                        "STATUS": "Approved",
                        "STATEMENT": (
                            "The vehicle shall estimate attitude during powered "
                            "ascent."
                        ),
                        "RATIONALE": "Supports TVC-MO-001.",
                        "RELATIONS": [
                            {
                                "TYPE": "Parent",
                                "VALUE": "TVC-MO-001",
                            }
                        ],
                    },
                    {
                        "_NODE_TYPE": "REQUIREMENT",
                        "UID": "TVC-REQ-002",
                        "LEVEL": "L1",
                        "REQUIREMENT_TYPE": "Safety",
                        "TITLE": "Range Safety Compliance",
                        "APPLICABLE_SUBSYSTEM": "N_A",
                        "SUBTEAM_OWNER": "Systems",
                        "INDIVIDUAL_OWNER": "Systems Lead",
                        "VEHICLE_CONFIGURATION": "All",
                        "MISSION_PHASE": "All",
                        "FLIGHT_ATTEMPT": "All",
                        "OPEN_ITEM_STATUS": "None",
                        "VERIFICATION_METHOD": "Inspection",
                        "STATUS": "Approved",
                        "STATEMENT": (
                            "The vehicle shall comply with applicable range "
                            "safety rules."
                        ),
                        "RATIONALE": "Supports TVC-MC-001.",
                        "RELATIONS": [
                            {
                                "TYPE": "Parent",
                                "VALUE": "TVC-MC-001",
                            }
                        ],
                    },
                ]
            },
            {
                "NODES": [
                    {
                        "_NODE_TYPE": "RISK",
                        "UID": "TVC-RISK-003",
                        "RISK_TYPE": "Technical",
                        "TITLE": "Actuator Bandwidth Shortfall",
                        "SUBTEAM_OWNER": "Controls",
                        "INDIVIDUAL_OWNER": "Controls Lead",
                        "VEHICLE_CONFIGURATION": "TVC-F1",
                        "MISSION_PHASE": "Powered ascent",
                        "FLIGHT_ATTEMPT": "Flight 1",
                        "INITIAL_LIKELIHOOD": "Medium",
                        "INITIAL_SEVERITY": "High",
                        "CURRENT_LIKELIHOOD": "Medium",
                        "CURRENT_SEVERITY": "High",
                        "RISK_RESPONSE": "Mitigate",
                        "RESPONSE_PLAN": "Measure actuator bandwidth.",
                        "DUE_DATE": "Before CDR",
                        "LINKED_ARTIFACTS": (
                            "docs/verification/actuator-frequency-response-test.md"
                        ),
                        "STATUS": "Open",
                        "CONDITION": "Actuator bandwidth is lower than assumed.",
                        "CONSEQUENCE": (
                            "The vehicle may fail to maintain commanded attitude."
                        ),
                        "RELATIONS": [
                            {
                                "TYPE": "Parent",
                                "VALUE": "TVC-REQ-001",
                                "ROLE": "Affects",
                            }
                        ],
                    }
                ]
            },
        ]
    }


if __name__ == "__main__":
    unittest.main()
