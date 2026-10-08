# Analytics Engineering

SQL patterns for correctness problems that show up in production reporting.

- [`time_handling/dst_safe_scheduling/`](time_handling/dst_safe_scheduling) - Run a daily job at a fixed local time across daylight saving changes, with an idempotent run guard and tests for both transition days
