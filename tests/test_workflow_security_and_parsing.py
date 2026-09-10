import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workflow_api import (
    analyze,
    authenticate_user,
    create_admin_request,
    delete_admin_request,
    list_admin_requests,
    parse_raw_project_text,
    update_admin_request,
    update_admin_request_status,
)


class WorkflowSecurityAndParsingTests(unittest.TestCase):
    def test_admin_auth_success_and_failure(self):
        # The account's role is read from the database; the client sends no role.
        admin_res = authenticate_user({
            "email": "admin@minfit.vn",
            "password": "admin888",
        })
        self.assertTrue(admin_res["success"])
        self.assertEqual(admin_res["role"], "admin")
        self.assertTrue(admin_res["token"].startswith("adm_"))
        self.assertGreaterEqual(len(admin_res["token"]), 36)

        # A client-provided role cannot change the database-derived role.
        forced_broker = authenticate_user({
            "role": "broker",
            "email": "admin@minfit.vn",
            "password": "admin888",
        })
        self.assertEqual(forced_broker["role"], "admin")

        # Failed admin login with wrong password
        with self.assertRaises(ValueError):
            authenticate_user({
                "email": "admin@minfit.vn",
                "password": "incorrect_password",
            })

        with self.assertRaises(ValueError):
            authenticate_user({"role": "admin", "pin": "admin888"})

        # Failed admin login with missing account
        with self.assertRaises(ValueError):
            authenticate_user({"email": "", "password": ""})

    def test_broker_auth_password_verification(self):
        # Default broker login with correct password '123456'
        broker_res = authenticate_user({
            "email": "moigioi@minfit.vn",
            "password": "123456"
        })
        self.assertTrue(broker_res["success"])
        self.assertEqual(broker_res["role"], "broker")
        self.assertTrue(broker_res["token"].startswith("brk_"))
        self.assertGreaterEqual(len(broker_res["token"]), 36)

        # Rejection of wrong password for existing broker
        with self.assertRaises(ValueError):
            authenticate_user({
                "email": "moigioi@minfit.vn",
                "password": "wrong_password_xyz"
            })

        # Invalid email format
        with self.assertRaises(ValueError):
            authenticate_user({
                "email": "not-an-email",
                "password": "valid_password"
            })

        # Password too short (< 6 chars)
        with self.assertRaises(ValueError):
            authenticate_user({
                "email": "broker@test.com",
                "password": "123"
            })

        with self.assertRaises(ValueError):
            authenticate_user({
                "email": "missing@minfit.vn",
                "password": "123456"
            })

    def test_session_lifecycle_and_revocation(self):
        from database import create_session, revoke_session, verify_session

        # Create session
        token = create_session("usr_test_01", "broker", "test_user@minfit.vn", ttl_hours=2)
        self.assertIsNotNone(token)

        # Verify active session
        session = verify_session(token)
        self.assertIsNotNone(session)
        self.assertEqual(session["user_id"], "usr_test_01")
        self.assertEqual(session["role"], "broker")

        # Revoke session (logout)
        revoked = revoke_session(token)
        self.assertTrue(revoked)

        # Verify session is now None
        self.assertIsNone(verify_session(token))

    def test_broker_cannot_delete_another_brokers_client_or_keep_locked_session(self):
        from database import create_session, save_user_to_db, toggle_user_status_in_db, verify_session
        from workflow_api import create_client, delete_client

        owner_id = "security_owner_01"
        other_id = "security_other_01"
        for user_id, email in (
            (owner_id, "security_owner@minfit.vn"),
            (other_id, "security_other@minfit.vn"),
        ):
            save_user_to_db({
                "id": user_id,
                "name": user_id,
                "email": email,
                "role": "broker",
                "status": "active",
            })

        client = create_client({"broker_id": owner_id, "name": "Khách hàng riêng"})
        with self.assertRaises(PermissionError):
            delete_client(client["id"], broker_id=other_id)

        token = create_session(owner_id, "broker", "security_owner@minfit.vn", ttl_hours=2)
        self.assertIsNotNone(verify_session(token))
        self.assertEqual(toggle_user_status_in_db(owner_id)["status"], "locked")
        self.assertIsNone(verify_session(token))
        self.assertEqual(toggle_user_status_in_db(owner_id)["status"], "active")
        self.assertTrue(delete_client(client["id"], broker_id=owner_id)["success"])

    def test_admin_request_crud_and_validation(self):
        request = create_admin_request({
            "text": "Kiểm tra hồ sơ khách hàng.",
            "priority": True,
        })
        self.assertTrue(request["id"].startswith("req_"))
        self.assertEqual(request["text"], "Kiểm tra hồ sơ khách hàng.")
        self.assertTrue(request["priority"])
        self.assertFalse(request["completed"])
        self.assertIn(request["id"], {item["id"] for item in list_admin_requests()})

        updated = update_admin_request({
            "id": request["id"],
            "text": "Đã cập nhật nội dung.",
            "priority": False,
        })
        self.assertEqual(updated["text"], "Đã cập nhật nội dung.")
        self.assertFalse(updated["priority"])

        completed = update_admin_request_status(request["id"], True)
        self.assertTrue(completed["completed"])
        self.assertIsNotNone(completed["completedAt"])
        reopened = update_admin_request_status(request["id"], False)
        self.assertFalse(reopened["completed"])
        self.assertIsNone(reopened["completedAt"])

        with self.assertRaises(ValueError):
            create_admin_request({"text": "x", "images": [{"dataUrl": "not-an-image"}]})
        self.assertTrue(delete_admin_request(request["id"])["deleted"])
        with self.assertRaises(ValueError):
            delete_admin_request(request["id"])

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
