import logging
import re
import time
from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any

import requests


logger = logging.getLogger(__name__)

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def calculate_bonus(salary: Any, percentage: Any) -> Decimal:
    """Return the bonus amount for a salary and percentage."""
    try:
        salary_value = Decimal(str(salary))
        percentage_value = Decimal(str(percentage))
    except (InvalidOperation, TypeError):
        raise ValueError("salary and percentage must be numeric")

    if salary_value <= 0:
        raise ValueError("salary must be greater than zero")
    if percentage_value < 0:
        raise ValueError("percentage cannot be negative")

    return salary_value * percentage_value / Decimal("100")


def _validate_employee_id(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return "employee id must be an integer"
    if value <= 0:
        return "employee id must be greater than zero"
    return None


def _validate_email(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return "email is required"
    if not EMAIL_PATTERN.match(value):
        return "email format is invalid"
    return None


def _validate_salary(value: Any) -> str | None:
    if isinstance(value, bool):
        return "salary must be numeric"
    try:
        salary = Decimal(str(value))
    except (InvalidOperation, TypeError):
        return "salary must be numeric"
    if salary <= 0:
        return "salary must be greater than zero"
    return None


def process_employee_data(records: list[dict[str, Any]]) -> dict[str, Any]:
    valid_records = []
    invalid_records = []
    salaries: list[Decimal] = []

    for index, record in enumerate(records):
        errors = []

        employee_id_error = _validate_employee_id(record.get("id"))
        email_error = _validate_email(record.get("email"))
        salary_error = _validate_salary(record.get("salary"))

        for field, error in (
            ("id", employee_id_error),
            ("email", email_error),
            ("salary", salary_error),
        ):
            if error:
                errors.append({"field": field, "message": error})

        if errors:
            invalid_records.append(
                {
                    "index": index,
                    "record": record,
                    "errors": errors,
                }
            )
            continue

        normalized = dict(record)
        normalized["salary"] = Decimal(str(record["salary"]))
        valid_records.append(normalized)
        salaries.append(normalized["salary"])

    summary = {
        "total_records": len(records),
        "valid_count": len(valid_records),
        "invalid_count": len(invalid_records),
        "salary_total": sum(salaries, Decimal("0")),
        "salary_average": (
            sum(salaries, Decimal("0")) / len(salaries) if salaries else Decimal("0")
        ),
        "salary_min": min(salaries) if salaries else None,
        "salary_max": max(salaries) if salaries else None,
        "error_counts": Counter(
            error["field"] for item in invalid_records for error in item["errors"]
        ),
    }

    return {
        "valid_records": valid_records,
        "invalid_records": invalid_records,
        "summary": summary,
    }


def _simplify_user(user: dict[str, Any]) -> dict[str, Any]:
    address = user.get("address") or {}
    company = user.get("company") or {}

    return {
        "external_id": user.get("id"),
        "name": user.get("name"),
        "username": user.get("username"),
        "email": user.get("email"),
        "city": address.get("city"),
        "company_name": company.get("name"),
    }


def _chunks(items: list[dict[str, Any]], batch_size: int):
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def sync_users(
    timeout: float = 5,
    retries: int = 3,
    batch_size: int | None = None,
    session: requests.Session | None = None,
) -> list[dict[str, Any]] | list[list[dict[str, Any]]]:
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")
    if retries < 1:
        raise ValueError("retries must be at least one")
    if batch_size is not None and batch_size < 1:
        raise ValueError("batch_size must be at least one")

    http = session or requests.Session()
    url = "https://jsonplaceholder.typicode.com/users"

    for attempt in range(1, retries + 1):
        try:
            logger.info("fetching users", extra={"attempt": attempt, "url": url})
            response = http.get(url, timeout=timeout)

            if response.status_code in TRANSIENT_STATUS_CODES:
                raise requests.HTTPError(
                    f"transient status code {response.status_code}",
                    response=response,
                )

            response.raise_for_status()
            users = response.json()
            simplified = [_simplify_user(user) for user in users]
            logger.info("users fetched", extra={"count": len(simplified)})

            if batch_size:
                return list(_chunks(simplified, batch_size))
            return simplified

        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
            logger.warning(
                "user sync attempt failed",
                extra={"attempt": attempt, "error": str(exc)},
            )
            if attempt == retries:
                logger.error("user sync failed after retries", extra={"url": url})
                return []
            time.sleep(min(2 ** (attempt - 1), 5))
        except ValueError as exc:
            logger.error("invalid user payload", extra={"error": str(exc)})
            return []

    return []
