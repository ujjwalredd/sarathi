from __future__ import annotations

import unittest

import render_repo_chart


class RepoChartTests(unittest.TestCase):
    def test_chart_contains_every_arm_and_metric(self):
        arms = {}
        for index, (arm, label) in enumerate(
            [("A", "control"), ("F", "Caveman"), ("G", "Ponytail"), ("H", "Sarathi")],
            1,
        ):
            arms[arm] = {
                "label": label,
                "passed": index,
                "valid": 4,
                "infrastructure_invalid": 0,
                "pass_rate": index / 4,
                "estimated_api_cost_per_verified_pass_usd": 1 / index,
                "raw_tokens_per_verified_pass": 1000 / index,
                "mean_duration_ms": 100 * index,
            }
        rendered = render_repo_chart.chart(
            {"arms": arms},
            {"model": "test-model", "effort": "medium"},
        )
        self.assertIn("Executable repository benchmark", rendered)
        self.assertIn("Correctness is higher-better", rendered)
        for label in ("control", "Caveman", "Ponytail", "Sarathi"):
            self.assertIn(label, rendered)
        for title in (
            "Verified pass rate",
            "API-equivalent cost per verified pass",
            "Raw tokens per verified pass",
            "Mean agent time",
        ):
            self.assertIn(title, rendered)
        self.assertNotIn("nan", rendered.lower())


if __name__ == "__main__":
    unittest.main()
