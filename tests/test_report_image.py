import sys
import unittest
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from loan_dti import FinancialProfile, LoanScenario
from project_engine import load_projects, rank_projects
from report_image import H, W, build_a4_report_png


class ReportImageTests(unittest.TestCase):
    def test_a4_report_is_valid_png(self):
        projects = load_projects(ROOT / "data" / "projects.json")
        profile = FinancialProfile(
            Decimal("100000000"),
            Decimal("2000000000"),
            Decimal("0"),
            Decimal("25000000"),
        )
        scenario = LoanScenario(
            Decimal("70"),
            20,
            Decimal("7.5"),
            24,
            Decimal("13.5"),
            "annuity",
            "none",
            0,
        )
        eligible, _ = rank_projects(
            projects,
            profile,
            scenario,
            "family_with_children",
            10.8106,
            106.7091,
            ("school", "park", "parking"),
        )

        report = build_a4_report_png(eligible[0], "family_with_children", profile, scenario)

        with Image.open(BytesIO(report)) as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.size, (W, H))


if __name__ == "__main__":
    unittest.main()
