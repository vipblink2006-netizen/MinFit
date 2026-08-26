import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database import database_status, ensure_database, load_persona_weights_from_database, load_projects_from_database


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


if __name__ == "__main__":
    unittest.main()
