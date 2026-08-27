import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workflow_api import authenticate_user, parse_raw_project_text, analyze


class WorkflowSecurityAndParsingTests(unittest.TestCase):
    def test_admin_auth_success_and_failure(self):
        # Successful admin login
        admin_res = authenticate_user({"role": "admin", "pin": "admin888"})
        self.assertTrue(admin_res["success"])
        self.assertEqual(admin_res["role"], "admin")
        self.assertTrue(admin_res["token"].startswith("adm_"))

        # Failed admin login with wrong PIN
        with self.assertRaises(ValueError):
            authenticate_user({"role": "admin", "pin": "incorrect_pin"})

        # Failed admin login with empty PIN
        with self.assertRaises(ValueError):
            authenticate_user({"role": "admin", "pin": ""})

    def test_broker_auth_validation(self):
        # Valid broker login
        broker_res = authenticate_user({
            "role": "broker",
            "email": "moigioi@minfit.vn",
            "password": "strong_password_123"
        })
        self.assertTrue(broker_res["success"])
        self.assertEqual(broker_res["role"], "broker")
        self.assertTrue(broker_res["token"].startswith("brk_"))

        # Invalid email format
        with self.assertRaises(ValueError):
            authenticate_user({
                "role": "broker",
                "email": "not-an-email",
                "password": "valid_password"
            })

        # Password too short (< 6 chars)
        with self.assertRaises(ValueError):
            authenticate_user({
                "role": "broker",
                "email": "broker@test.com",
                "password": "123"
            })

    def test_regex_parser_preserves_characters_and_extracts_clean_fields(self):
        # Broker text containing names with 'l' and 'i' (previously corrupted by [/-li])
        sample = """DỰ ÁN: LUMI HANOI
Chủ đầu tư: CapitaLand
Vị trí: Đại lộ Thăng Long, Tây Mỗ, Nam Từ Liêm
Giá bán: 75 - 95 tr/m2
Diện tích: 65 - 85m2
Link bảng hàng: https://docs.google.com/spreadsheets/d/123456
Link 360: https://kuula.co/post/abcxyz"""

        res = parse_raw_project_text(sample)
        self.assertTrue(res["success"])
        p = res["project"]
        # Must NOT contain newline in name, must preserve 'L' and 'i'
        self.assertEqual(p["name"], "LUMI HANOI")
        self.assertEqual(p["developer"], "CapitaLand")
        self.assertEqual(p["area"], "Nam Từ Liêm")
        self.assertEqual(p["price_avg_mil_m2"], 85.0)
        self.assertEqual(p["area_m2"], 75.0)
        self.assertEqual(p["links"]["sheets"], "https://docs.google.com/spreadsheets/d/123456")
        self.assertEqual(p["links"]["kuula_360"], "https://kuula.co/post/abcxyz")

    def test_regex_parser_handles_billion_and_m2_prices(self):
        sample = """Bán căn 2PN Masteri West Heights
Diện tích 62.5 m2, giá 4.8 tỷ (khoảng 77 tr/m2)
Căn tầng trung view hồ điều hòa
Bảng hàng cập nhật: https://docs.google.com/spreadsheets/d/789"""

        res = parse_raw_project_text(sample)
        self.assertTrue(res["success"])
        p = res["project"]
        self.assertEqual(p["name"], "Masteri West Heights")
        self.assertEqual(p["price_min_vnd"], 4800000000)
        self.assertEqual(p["area_m2"], 62.5)

    def test_dynamic_payment_shock_detection(self):
        # 12-month intro with high shock (> 1.8) -> shock at month 13
        r12 = analyze({
            "intro_months": 12,
            "phase1_rate_percent": 0.0,
            "grace_months": 12,
            "grace_type": "interest_only",
            "floating_rate_percent": 12.0,
            "term_years": 15,
            "project_ids": ["prj_06"]
        })
        shock12 = r12["results"][0]["payment_shock"]
        self.assertEqual(shock12["shock_month"], 13)
        self.assertGreater(shock12["ratio"], 1.8)
        self.assertIn("tháng 13", shock12["suggestion"])

        # 36-month intro test -> shock at month 37
        r36 = analyze({
            "intro_months": 36,
            "phase1_rate_percent": 6.0,
            "floating_rate_percent": 12.0,
            "term_years": 20,
            "project_ids": ["prj_06"]
        })
        shock36 = r36["results"][0]["payment_shock"]
        self.assertEqual(shock36["shock_month"], 37)


if __name__ == "__main__":
    unittest.main()
