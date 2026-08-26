import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from loan_dti import FinancialProfile, LoanScenario, annuity_payment, simulate_loan
from project_engine import load_projects, rank_projects


class LoanSimulationTests(unittest.TestCase):
    def setUp(self):
        self.profile = FinancialProfile(
            monthly_income=Decimal("100000000"),
            available_cash=Decimal("2000000000"),
            existing_debt_payment=Decimal("0"),
            essential_expenses=Decimal("20000000"),
        )

    def scenario(self, **overrides):
        values = {
            "loan_ratio_percent": Decimal("70"),
            "term_years": 20,
            "phase1_rate_percent": Decimal("7.5"),
            "phase1_months": 24,
            "phase2_rate_percent": Decimal("13.5"),
            "repayment_method": "equal_principal",
            "grace_type": "none",
            "grace_months": 0,
        }
        values.update(overrides)
        return LoanScenario(**values)

    def test_equal_principal_first_month_is_exact(self):
        scenario = self.scenario(
            loan_ratio_percent=Decimal("100"),
            term_years=10,
            phase1_rate_percent=Decimal("12"),
            phase1_months=119,
            phase2_rate_percent=Decimal("12"),
        )
        analysis = simulate_loan(self.profile, scenario, Decimal("1200000000"), Decimal("0"), Decimal("0"))
        first = analysis.timeline[0]
        self.assertEqual(first.principal, Decimal("10000000"))
        self.assertEqual(first.interest, Decimal("12000000.00"))
        self.assertEqual(first.payment, Decimal("22000000.00"))
        self.assertEqual(first.closing_balance, Decimal("1190000000"))

    def test_annuity_uses_formula_and_recalculates_at_phase_two(self):
        scenario = self.scenario(repayment_method="annuity")
        analysis = simulate_loan(self.profile, scenario, Decimal("4000000000"), Decimal("1000000"), Decimal("500000000"))
        expected = annuity_payment(Decimal("2800000000"), Decimal("7.5"), 240)
        self.assertAlmostEqual(float(analysis.timeline[0].payment), float(expected), places=4)
        self.assertGreater(analysis.timeline[24].payment, analysis.timeline[23].payment)

    def test_interest_only_grace_pays_no_principal(self):
        scenario = self.scenario(grace_type="interest_only", grace_months=6)
        analysis = simulate_loan(self.profile, scenario, Decimal("4000000000"), Decimal("0"), Decimal("500000000"))
        self.assertEqual(analysis.timeline[0].principal, Decimal("0"))
        self.assertEqual(analysis.timeline[0].payment, analysis.timeline[0].interest)
        self.assertGreater(analysis.timeline[6].principal, Decimal("0"))

    def test_capitalized_grace_increases_balance(self):
        scenario = self.scenario(grace_type="capitalized", grace_months=6, repayment_method="annuity")
        analysis = simulate_loan(self.profile, scenario, Decimal("4000000000"), Decimal("0"), Decimal("500000000"))
        first = analysis.timeline[0]
        self.assertEqual(first.payment, Decimal("0"))
        self.assertGreater(first.closing_balance, first.opening_balance)
        self.assertGreater(analysis.timeline[6].payment, Decimal("0"))

    def test_timeline_has_full_360_months(self):
        scenario = self.scenario(term_years=30)
        analysis = simulate_loan(self.profile, scenario, Decimal("4000000000"), Decimal("0"), Decimal("500000000"))
        self.assertEqual(len(analysis.timeline), 360)

    def test_hard_filter_flags_ltv_dti_and_negative_fcf(self):
        tight_profile = FinancialProfile(
            monthly_income=Decimal("30000000"),
            available_cash=Decimal("100000000"),
            existing_debt_payment=Decimal("5000000"),
            essential_expenses=Decimal("20000000"),
        )
        scenario = self.scenario(loan_ratio_percent=Decimal("85"), phase2_rate_percent=Decimal("15"))
        analysis = simulate_loan(tight_profile, scenario, Decimal("5000000000"), Decimal("2000000"), Decimal("0"))
        reasons = " ".join(analysis.hard_filter_reasons)
        self.assertIn("LTV", reasons)
        self.assertIn("DTI", reasons)
        self.assertIn("Dòng tiền", reasons)


class ProjectRankingTests(unittest.TestCase):
    def test_ranking_processes_all_projects(self):
        projects = load_projects(ROOT / "data" / "projects.json")
        profile = FinancialProfile(Decimal("100000000"), Decimal("2000000000"), Decimal("0"), Decimal("25000000"))
        scenario = LoanScenario(Decimal("70"), 20, Decimal("7.5"), 24, Decimal("13.5"), "equal_principal", "none", 0)
        eligible, rejected = rank_projects(projects, profile, scenario, "family_with_children", 10.8106, 106.7091, ("school", "park", "parking"))
        self.assertGreaterEqual(len(eligible) + len(rejected), 27)
        self.assertTrue(all(item.is_eligible for item in eligible))


if __name__ == "__main__":
    unittest.main()
