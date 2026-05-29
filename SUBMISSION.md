# Driftal Python + Integration Engineering Assessment

## Section 1 - Production Incident Debugging

Original issue:

```python
def calculate_bonus(salary, percentage):
    return salary / percentage
```

Findings:

| Severity | Issue | Impact |
| --- | --- | --- |
| Critical | Formula is wrong. Bonus should be salary * percentage / 100, not salary / percentage. | Payroll amount is incorrect. |
| Critical | `bonus_pct` can be zero. | Division by zero in production. |
| High | `salary` can be `None`. | Runtime failure during payroll run. |
| Medium | No validation for non-numeric or negative values. | Bad upstream data creates wrong results. |
| Medium | Money calculation uses normal numeric inputs without clear precision handling. | Possible rounding or consistency issues. |

Corrected code is in `assessment_solution.py`:

```python
def calculate_bonus(salary, percentage):
    salary_value = Decimal(str(salary))
    percentage_value = Decimal(str(percentage))

    if salary_value <= 0:
        raise ValueError("salary must be greater than zero")
    if percentage_value < 0:
        raise ValueError("percentage cannot be negative")

    return salary_value * percentage_value / Decimal("100")
```

Prevention:

- Add unit tests for valid salary, `None`, zero percent, negative values, and non-numeric values.
- Validate incoming payroll data before calculation.
- Log rejected records with employee id and reason.
- Add data quality checks before payroll files are sent.
- Use code review checklist items for money calculation and edge cases.

## Section 2 - Employee Data Processing

Implemented in `process_employee_data(records)` inside `assessment_solution.py`.

It validates:

- Employee id is a positive integer.
- Email has a basic valid format.
- Salary is numeric and greater than zero.

Output includes:

- `valid_records`
- `invalid_records`
- detailed field-level errors
- summary statistics: counts, total salary, average salary, min salary, max salary, and error counts

## Section 3 - API Integration

Implemented in `sync_users()` inside `assessment_solution.py`.

Key decisions:

- Uses `requests.Session` so callers can reuse HTTP connections.
- Timeout is configurable and validated.
- Retries transient failures up to the requested retry count.
- Treats `408`, `429`, `500`, `502`, `503`, and `504` as transient.
- Returns an empty list after final failure instead of crashing the job.
- Logs fetch attempts, retry failures, success count, and final failure.
- Supports optional batch output using `batch_size`.
- Includes unit tests with a fake session, so tests do not depend on the live API.

Simplified schema:

```python
{
    "external_id": user.get("id"),
    "name": user.get("name"),
    "username": user.get("username"),
    "email": user.get("email"),
    "city": address.get("city"),
    "company_name": company.get("name"),
}
```

## Section 4 - Architecture: SuccessFactors -> Python -> Snowflake

I would build the pipeline as a scheduled extraction job with checkpoints. The Python layer would read records from SuccessFactors in pages, validate and transform each page, write staged files to object storage, and then load into Snowflake using `COPY INTO` or Snowpipe depending on latency needs.

For memory efficiency, I would avoid loading all 500,000 records at once. The job should stream or page through records, process batches like 5,000 or 10,000 rows, and write each batch to compressed files such as CSV or Parquet. This keeps memory predictable and also makes retries easier because failed batches can be retried separately.

Retry strategy should separate transient and permanent failures. Network timeouts, rate limits, and 500 responses can use exponential backoff with jitter. Validation failures should not be retried blindly; they should go to a rejection table or file with the exact reason. Each run should have a run id, batch id, source timestamp, and status.

Duplicate detection can be handled using a business key such as employee id plus effective date or last modified timestamp. In Snowflake, I would load into a staging table first, then merge into the final table. The merge can update changed employees and ignore exact duplicates. A hash of important fields is useful to detect whether a record actually changed.

Monitoring should cover row counts, rejected row count, API latency, retry count, Snowflake load failures, and total runtime. Alerts should trigger when the job fails, the rejection rate crosses a threshold, row counts are unexpectedly low or high, or data freshness falls behind the expected daily schedule.

Credentials should be stored in a secrets manager, not in code or config files. API credentials and Snowflake credentials should be rotated regularly. Snowflake access should use least privilege, ideally with a dedicated service role that can load and merge only the needed tables.

For scalability, the pipeline can split work by page, department, region, or last modified time window. Snowflake loading should use staged files instead of row by row inserts. If volume increases beyond daily batch needs, the same design can move toward event-based ingestion or more frequent incremental runs.

## Section 5 - Code Review

Code reviewed:

```python
import requests

def get_user(id):
    response = requests.get(
        f"https://api.company.com/users/{id}"
    )
    return response.json()

for i in range(10000):
    user = get_user(i)
    print(user["name"])
```

| Severity | Finding | Recommendation |
| --- | --- | --- |
| Critical | No timeout on HTTP requests. One slow request can hang the whole process. | Pass a timeout, for example `timeout=5`. |
| Critical | No error handling for network failures, 4xx, 5xx, or invalid JSON. | Use `raise_for_status()`, catch expected exceptions, and log failures. |
| High | Performs 10,000 sequential API calls. | Use a bulk endpoint if available, otherwise use controlled concurrency or batching. |
| High | No retry strategy for transient failures. | Retry timeouts, 429, and 5xx with exponential backoff. |
| High | Potential rate limit problem. | Respect API rate limit headers and add throttling. |
| Medium | Assumes every response contains `name`. | Use validation or safe access with clear handling for missing fields. |
| Medium | Uses `id` as parameter name, shadowing Python built-in `id`. | Rename to `user_id`. |
| Medium | Prints directly instead of structured logging or output handling. | Use logging or write results to a controlled destination. |
| Medium | Hard-coded base URL. | Move base URL to config/environment. |
| Low | No tests and no type hints. | Add unit tests with mocked HTTP responses. |

## Section 6 - AI Usage Reflection

1. I used ChatGPT to help structure the solution, identify edge cases, and draft tests.
2. AI generated the first version of the Python module, tests, and written notes.
3. I reviewed the assignment requirements, checked the generated approach, and would adjust naming, assumptions, and examples before final submission.
4. The main risk with AI is that it can over engineer small tasks or miss company specific assumptions. I checked for that by keeping the implementation small and testable.
5. With another day, I would add more realistic integration tests, configure structured JSON logging, and add a small command line runner for the employee processing and user sync flows.
