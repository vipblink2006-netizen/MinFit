from decimal import Decimal
import unittest

from workflow_api import analyze
from loan_dti import FinancialProfile, LoanScenario, simulate_loan


class TestPaymentSchemes(unittest.TestCase):
    def test_primary_htls_scheme(self):
        payload = {
            "monthly_income": 65000000,
            "available_cash": 1500000000,
            "market_segment": "primary",
            "payment_scheme": "loan_htls",
            "ltv_percent": 70,
            "grace_months": 24,
            "intro_rate_percent": 0.0,
            "floating_rate_percent": 11.5,
            "term_years": 20,
        }
        res = analyze(payload)
        self.assertEqual(res["market_segment"], "primary")
        self.assertEqual(res["payment_scheme"], "loan_htls")
        self.assertTrue(len(res["results"]) > 0)
        top = res["results"][0]
        eval_data = top.get("payment_scheme_evaluation")
        self.assertIsNotNone(eval_data)
        self.assertEqual(eval_data["scheme_key"], "loan_htls")
        self.assertIn("HTLS 0%", eval_data["scheme_name"])
        self.assertIn("Giai đoạn 1", eval_data["phase_1_summary"])
        self.assertIn("Giai đoạn 2", eval_data["phase_2_summary"])

    def test_primary_standard_progress_scheme(self):
        payload = {
            "monthly_income": 80000000,
            "available_cash": 3000000000,
            "market_segment": "primary",
            "payment_scheme": "standard_progress",
        }
        res = analyze(payload)
        self.assertEqual(res["payment_scheme"], "standard_progress")
        top = res["results"][0]
        eval_data = top.get("payment_scheme_evaluation")
        self.assertIsNotNone(eval_data)
        self.assertEqual(eval_data["scheme_key"], "standard_progress")
        self.assertTrue(len(eval_data["progress_schedule"]) >= 7)
        self.assertEqual(eval_data["progress_schedule"][0]["percentage"], 15)

    def test_primary_early_payment_scheme(self):
        payload = {
            "monthly_income": 100000000,
            "available_cash": 6000000000,
            "market_segment": "primary",
            "payment_scheme": "early_payment",
            "discount_percent": 12,
        }
        res = analyze(payload)
        self.assertEqual(res["payment_scheme"], "early_payment")
        top = res["results"][0]
        eval_data = top.get("payment_scheme_evaluation")
        self.assertIsNotNone(eval_data)
        self.assertEqual(eval_data["scheme_key"], "early_payment")
        self.assertIn("95%", eval_data["scheme_name"])

    def test_secondary_bank_vcb_scheme(self):
        payload = {
            "monthly_income": 70000000,
            "available_cash": 2000000000,
            "market_segment": "secondary",
            "payment_scheme": "bank_vcb",
            "ltv_percent": 70,
            "term_years": 20,
        }
        res = analyze(payload)
        self.assertEqual(res["market_segment"], "secondary")
        self.assertEqual(res["payment_scheme"], "bank_vcb")
        top = res["results"][0]
        eval_data = top.get("payment_scheme_evaluation")
        self.assertIsNotNone(eval_data)
        self.assertEqual(eval_data["scheme_key"], "bank_vcb")
        self.assertIn("Vietcombank", eval_data["scheme_name"])

    def test_secondary_equity_100_scheme(self):
        payload = {
            "monthly_income": 90000000,
            "available_cash": 5000000000,
            "market_segment": "secondary",
            "payment_scheme": "equity_100",
        }
        res = analyze(payload)
        self.assertEqual(res["payment_scheme"], "equity_100")
        top = res["results"][0]
        eval_data = top.get("payment_scheme_evaluation")
        self.assertIsNotNone(eval_data)
        self.assertEqual(eval_data["scheme_key"], "equity_100")
        self.assertIn("100%", eval_data["scheme_name"])


if __name__ == "__main__":
    unittest.main()
