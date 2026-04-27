# Analytics Engineering

This section showcases my approach to building **reliable, maintainable analytics systems** that sit between raw data and analytical consumption layers.

The focus is on:
- Defensive data transformations
- Reusable SQL patterns
- Time- and schedule-safe logic
- Preventing edge-case failures in production BI environments

Rather than treating analytics as dashboards alone, I approach it as **software engineering applied to data workflows**.

---

## Key Areas

### Time Handling
Patterns that address scheduling and timezone pitfalls, including DST-safe trigger logic used in BI tools and scheduled jobs.

### SQL Patterns
Reusable SQL techniques for:
- Incremental logic
- Calendar alignment
- Deduplication and windowing
- Guarding against silent data drift

### dbt
Analytics-engineering workflows built using dbt, including:
- Staging → intermediate → mart patterns
- Tests and assumptions encoded as code
- Documentation-driven transformations

---

## Design Principles

- **Explicit over implicit**  
  Timezones, filters, assumptions, and boundaries are always encoded in logic.

- **Production-first**  
  Code is written for long-running systems, not one-off analysis.

- **Composable**  
  Patterns are designed to be reused across models, tools, and projects.

- **Tool-agnostic**  
  Logic is portable across BigQuery, dbt, Looker, and schedulers.

This structure reflects real-world analytics engineering work beyond ad-hoc querying.
