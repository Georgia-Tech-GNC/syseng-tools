from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from syseng_tools.cli import command_risk
from syseng_tools.project import ProjectConfig
from syseng_tools.risk import generate_risk_register, generated_risk_statement


class RiskReportTests(unittest.TestCase):
    def test_generated_statement_uses_condition_and_consequence(self) -> None:
        statement = generated_risk_statement(
            "Actuator bandwidth is lower than assumed.",
            "The vehicle may fail to maintain commanded attitude.",
        )

        self.assertEqual(
            statement,
            "If Actuator bandwidth is lower than assumed, "
            "then the vehicle may fail to maintain commanded attitude.",
        )

    def test_generate_risk_register_extracts_risks_from_strictdoc_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            strictdoc_json = root / "index.json"
            output_dir = root / "reports"
            strictdoc_json.write_text(json.dumps(strictdoc_data()), encoding="utf-8")

            risks = generate_risk_register(strictdoc_json, output_dir)

            self.assertEqual(len(risks), 1)
            self.assertEqual(risks[0]["initial_level"], "High")
            self.assertEqual(risks[0]["initial_score"], 6)
            self.assertEqual(risks[0]["current_level"], "Medium")
            self.assertEqual(risks[0]["linked_requirements"], ["TVC-REQ-001"])
            self.assertIn(
                "If Actuator bandwidth is lower than assumed, then the vehicle "
                "may fail to maintain commanded attitude.",
                risks[0]["generated_statement"],
            )
            self.assertTrue((output_dir / "risk-register.json").is_file())
            self.assertTrue((output_dir / "risk-register.csv").is_file())
            self.assertTrue((output_dir / "risk-register.md").is_file())

            markdown = (output_dir / "risk-register.md").read_text(encoding="utf-8")
            csv_text = (output_dir / "risk-register.csv").read_text(encoding="utf-8")
            self.assertIn("TVC-RISK-003", markdown)
            self.assertIn("High (6)", markdown)
            self.assertIn("TVC-REQ-001", csv_text)

    def test_generate_risk_register_fails_when_json_export_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            strictdoc_json = Path(tmpdir) / "missing.json"

            with self.assertRaises(SystemExit) as raised:
                generate_risk_register(strictdoc_json, Path(tmpdir) / "reports")

        self.assertIn("StrictDoc JSON export not found", str(raised.exception))

    def test_generate_risk_register_ignores_non_risk_nodes(self) -> None:
        data = strictdoc_data()
        data["DOCUMENTS"][0]["NODES"].append(
            {
                "_NODE_TYPE": "REQUIREMENT",
                "UID": "TVC-REQ-001",
            }
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            strictdoc_json = root / "index.json"
            strictdoc_json.write_text(json.dumps(data), encoding="utf-8")

            risks = generate_risk_register(strictdoc_json, root / "reports")

        self.assertEqual([risk["uid"] for risk in risks], ["TVC-RISK-003"])

    def test_generate_risk_register_fails_on_invalid_score_token(self) -> None:
        data = strictdoc_data()
        data["DOCUMENTS"][0]["NODES"][0]["CURRENT_LIKELIHOOD"] = "Medium_2"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            strictdoc_json = root / "index.json"
            strictdoc_json.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                generate_risk_register(strictdoc_json, root / "reports")

        message = str(raised.exception)
        self.assertIn("TVC-RISK-003", message)
        self.assertIn("CURRENT_LIKELIHOOD", message)

    def test_command_risk_uses_default_project_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            records_dir = root / "records"
            records_dir.mkdir()
            strictdoc_json = root / "build" / "strictdoc" / "json" / "index.json"
            strictdoc_json.parent.mkdir(parents=True)
            strictdoc_json.write_text(json.dumps(strictdoc_data()), encoding="utf-8")
            project = ProjectConfig(
                root=root,
                title="Sample TVC",
                prefix="TVC",
                records_dir=records_dir,
                allowed_vehicle_configurations=("TVC-F1",),
                allowed_mission_phases=("Powered ascent",),
                allowed_flight_attempts=("Flight 1",),
            )

            result = command_risk(project, None, None)

            self.assertEqual(result, 0)
            self.assertTrue((root / "build" / "syseng" / "risk-register.json").is_file())


def strictdoc_data() -> dict[str, object]:
    return {
        "DOCUMENTS": [
            {
                "NODES": [
                    {
                        "_NODE_TYPE": "RISK",
                        "UID": "TVC-RISK-003",
                        "TITLE": "Actuator Bandwidth Shortfall",
                        "RISK_TYPE": "Technical",
                        "SUBTEAM_OWNER": "Controls",
                        "INDIVIDUAL_OWNER": "Controls Lead",
                        "VEHICLE_CONFIGURATION": "TVC-F1",
                        "MISSION_PHASE": "Powered ascent",
                        "FLIGHT_ATTEMPT": "Flight 1",
                        "CONDITION": "Actuator bandwidth is lower than assumed.",
                        "CONSEQUENCE": (
                            "The vehicle may fail to maintain commanded attitude."
                        ),
                        "INITIAL_LIKELIHOOD": "Medium",
                        "INITIAL_SEVERITY": "High",
                        "CURRENT_LIKELIHOOD": "Low",
                        "CURRENT_SEVERITY": "High",
                        "RISK_RESPONSE": "Mitigate",
                        "STATUS": "Open",
                        "RELATIONS": [
                            {
                                "TYPE": "Parent",
                                "VALUE": "TVC-REQ-001",
                                "ROLE": "Affects",
                            }
                        ],
                    }
                ]
            }
        ]
    }


if __name__ == "__main__":
    unittest.main()
