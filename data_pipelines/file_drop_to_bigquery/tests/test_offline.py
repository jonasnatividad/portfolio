"""Offline tests: routing, header checks, event handling and SQL parsing.

Run: python3 -m unittest discover -s tests   (needs the loader's requirements;
sqlglot is optional and only used for the SQL parse test). No Google Cloud
credentials are needed: clients are created on first use, and none of these
paths reach BigQuery or Cloud Storage.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "loader"))

import main  # noqa: E402


class FakeBlob:
    def __init__(self, text: str):
        self.data = text.encode("utf-8")

    def download_as_bytes(self, start=0, end=None):
        return self.data[start:(end + 1) if end is not None else None]


class Routing(unittest.TestCase):
    def test_folder_decides_table(self):
        self.assertEqual(main.route("incoming/deals/deals_2026-10-01.csv"), "deals")
        self.assertEqual(main.route("incoming/companies/companies_2026-09-30.CSV"), "companies")

    def test_ignored_objects(self):
        for name in ("processed/deals/deals_2026-10-01.csv",   # the loader's own moves
                     "incoming/deals/notes.txt",
                     "incoming/invoices/x.csv",                # unknown table
                     "incoming/deals/2026/x.csv"):             # nested folders are not routed
            self.assertIsNone(main.route(name), name)


class Headers(unittest.TestCase):
    def test_parse_header_trims_and_lowercases(self):
        self.assertEqual(main.parse_header("﻿ Deal_ID ,Stage\nD1,x"), ["deal_id", "stage"])

    def test_sample_files_pass(self):
        for path in sorted((ROOT / "sample_data").glob("*.csv")):
            table = path.name.split("_")[0]
            main.check_header(FakeBlob(path.read_text()), table)  # raises on mismatch

    def test_mismatch_rejected(self):
        header = ",".join(main.EXPECTED_COLUMNS["companies"][:-1]) + "\n"
        with self.assertRaises(main.RejectedFile):
            main.check_header(FakeBlob(header), "companies")


class Events(unittest.TestCase):
    def setUp(self):
        self.client = main.app.test_client()

    def test_non_storage_event_ignored(self):
        res = self.client.post("/", json={"hello": "world"})
        self.assertEqual((res.status_code, res.get_json()["status"]), (200, "ignored"))

    def test_object_outside_incoming_ignored(self):
        res = self.client.post("/", json={"bucket": "b", "name": "processed/deals/x.csv", "generation": "1"})
        self.assertEqual(res.get_json()["status"], "ignored")

    def test_healthz(self):
        self.assertEqual(self.client.get("/healthz").status_code, 200)


class Sql(unittest.TestCase):
    def test_every_sql_file_parses(self):
        try:
            import sqlglot
        except ImportError:
            self.skipTest("sqlglot not installed")
        files = sorted((ROOT / "sql").rglob("*.sql"))
        self.assertGreater(len(files), 5)
        for path in files:
            with self.subTest(path.name):
                sqlglot.parse(path.read_text(), read="bigquery")


if __name__ == "__main__":
    unittest.main()
