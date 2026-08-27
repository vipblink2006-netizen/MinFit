import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database import (
    database_status, ensure_database, load_persona_weights_from_database, load_projects_from_database,
    save_user_to_db, list_users_from_db, toggle_user_status_in_db
)
from workflow_api import create_client, list_clients, delete_client


class LocalDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_database()

    def test_database_contains_seed_data(self):
        status = database_status()
        self.assertEqual(status.database, "MinFitLocal")
        self.assertGreaterEqual(status.project_count, 27)
        self.assertEqual(status.persona_count, 4)

    def test_projects_load_with_amenities(self):
        projects = load_projects_from_database()
        self.assertGreaterEqual(len(projects), 27)
        self.assertTrue(all(project.amenities for project in projects))

    def test_persona_weights_sum_to_one(self):
        weights = load_persona_weights_from_database()
        self.assertEqual(len(weights), 4)
        for item in weights.values():
            self.assertEqual(item["price"] + item["distance"] + item["amenities"], 1)

    def test_user_and_client_lifecycle(self):
        test_broker_id = "test_broker_999"
        save_user_to_db({
            "id": test_broker_id,
            "name": "Môi Giới Test",
            "email": "test_broker@minfit.vn",
            "phone": "0988776655",
            "role": "broker",
            "agency": "Sàn BĐS Hà Nội",
            "status": "active"
        })

        # Create client for this broker
        client_res = create_client({
            "broker_id": test_broker_id,
            "name": "Khách hàng Test",
            "phone": "0912345678",
            "units_sold": 1,
            "profile": {"monthly_income": 80000000, "available_cash": 2000000000}
        })
        self.assertIn("id", client_res)
        client_id = client_res["id"]

        # List clients for broker
        clients = list_clients(test_broker_id)
        self.assertTrue(any(c["id"] == client_id for c in clients))

        # Check Admin view of users reflects clients count and units sold
        users = list_users_from_db()
        test_user = next((u for u in users if u["id"] == test_broker_id), None)
        self.assertIsNotNone(test_user)
        self.assertGreaterEqual(test_user["clients_count"], 1)
        self.assertGreaterEqual(test_user["units_sold"], 1)
        self.assertTrue(any(c["id"] == client_id for c in test_user["clients_list"]))

        # Delete client
        del_res = delete_client(client_id)
        self.assertTrue(del_res["success"])

        # Toggle user status
        toggled = toggle_user_status_in_db(test_broker_id)
        self.assertEqual(toggled["status"], "locked")


if __name__ == "__main__":
    unittest.main()
