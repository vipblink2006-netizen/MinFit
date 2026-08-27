import sys
import time
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database import load_persona_weights_from_database, load_projects_from_database
from loan_dti import FinancialProfile, LoanScenario
from project_engine import rank_projects


class FullRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.projects = load_projects_from_database()
        cls.weights = load_persona_weights_from_database()
        cls.profile = FinancialProfile(Decimal("100000000"), Decimal("2000000000"), Decimal("0"), Decimal("25000000"))

    def test_all_persona_repayment_grace_combinations(self):
        for persona in ("single", "young_couple", "family_with_children", "retired"):
            for method in ("equal_principal", "annuity"):
                for grace_type, grace_months in (("none", 0), ("interest_only", 6), ("capitalized", 6)):
                    with self.subTest(persona=persona, method=method, grace_type=grace_type):
                        scenario = LoanScenario(Decimal("70"), 20, Decimal("7.5"), 24, Decimal("13.5"), method, grace_type, grace_months)
                        started = time.perf_counter()
                        eligible, rejected = rank_projects(
                            self.projects,
                            self.profile,
                            scenario,
                            persona,
                            10.8106,
                            106.7091,
                            ("school", "park", "parking"),
                            self.weights,
                        )
                        elapsed = time.perf_counter() - started
                        self.assertEqual(len(eligible) + len(rejected), len(self.projects))
                        self.assertTrue(all(len(item.analysis.timeline) == 240 for item in eligible + rejected))
                        self.assertLess(elapsed, 2)

    def test_timeline_lengths_120_240_360(self):
        for years in (5, 10, 20, 30, 35):
            with self.subTest(years=years):
                scenario = LoanScenario(Decimal("70"), years, Decimal("7.5"), 24, Decimal("13.5"), "annuity", "capitalized", 6)
                eligible, rejected = rank_projects(
                    self.projects,
                    self.profile,
                    scenario,
                    "family_with_children",
                    10.8106,
                    106.7091,
                    ("school", "park", "parking"),
                    self.weights,
                )
                self.assertTrue(all(len(item.analysis.timeline) == years * 12 for item in eligible + rejected))


if __name__ == "__main__":
    unittest.main()
