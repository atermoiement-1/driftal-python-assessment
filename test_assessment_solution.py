from decimal import Decimal
from unittest import TestCase, main
from unittest.mock import patch

import requests

from assessment_solution import calculate_bonus, process_employee_data, sync_users


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else []

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status code {self.status_code}", response=self)


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, url, timeout):
        self.calls += 1
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class AssessmentSolutionTests(TestCase):
    def test_calculate_bonus_returns_percentage_of_salary(self):
        self.assertEqual(calculate_bonus(50000, 10), Decimal("5000"))

    def test_process_employee_data_splits_valid_and_invalid_records(self):
        records = [
            {"id": 1001, "email": "alex@example.com", "salary": "50000"},
            {"id": 0, "email": "bad-email", "salary": -5},
            {"id": 1003, "email": "sam@example.com", "salary": 70000},
        ]

        result = process_employee_data(records)

        self.assertEqual(len(result["valid_records"]), 2)
        self.assertEqual(len(result["invalid_records"]), 1)
        self.assertEqual(result["summary"]["salary_total"], Decimal("120000"))
        self.assertEqual(result["summary"]["salary_average"], Decimal("60000"))
        self.assertEqual(result["summary"]["error_counts"]["id"], 1)
        self.assertEqual(result["summary"]["error_counts"]["email"], 1)
        self.assertEqual(result["summary"]["error_counts"]["salary"], 1)

    @patch("assessment_solution.time.sleep", lambda seconds: None)
    def test_sync_users_retries_transient_failures_and_simplifies_payload(self):
        session = FakeSession(
            [
                FakeResponse(503),
                FakeResponse(
                    200,
                    [
                        {
                            "id": 1,
                            "name": "Leanne Graham",
                            "username": "Bret",
                            "email": "leanne@example.com",
                            "address": {"city": "Gwenborough"},
                            "company": {"name": "Romaguera-Crona"},
                        }
                    ],
                ),
            ]
        )

        users = sync_users(timeout=1, retries=3, session=session)

        self.assertEqual(session.calls, 2)
        self.assertEqual(
            users,
            [
                {
                    "external_id": 1,
                    "name": "Leanne Graham",
                    "username": "Bret",
                    "email": "leanne@example.com",
                    "city": "Gwenborough",
                    "company_name": "Romaguera-Crona",
                }
            ],
        )

    @patch("assessment_solution.time.sleep", lambda seconds: None)
    def test_sync_users_returns_empty_list_after_retries(self):
        session = FakeSession(
            [
                requests.Timeout("slow request"),
                requests.ConnectionError("network down"),
            ]
        )

        self.assertEqual(sync_users(timeout=1, retries=2, session=session), [])
        self.assertEqual(session.calls, 2)

    def test_sync_users_can_return_batches(self):
        session = FakeSession(
            [
                FakeResponse(
                    200,
                    [
                        {"id": 1, "name": "A"},
                        {"id": 2, "name": "B"},
                        {"id": 3, "name": "C"},
                    ],
                )
            ]
        )

        batches = sync_users(timeout=1, retries=1, batch_size=2, session=session)

        self.assertEqual(len(batches), 2)
        self.assertEqual([user["external_id"] for user in batches[0]], [1, 2])
        self.assertEqual([user["external_id"] for user in batches[1]], [3])


if __name__ == "__main__":
    main()
