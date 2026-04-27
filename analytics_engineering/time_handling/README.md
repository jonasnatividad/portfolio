# Time Handling Patterns

This directory contains **reusable SQL and modeling patterns for handling time-based edge cases** commonly encountered in analytics platforms and data warehouses.

Time-related bugs are some of the hardest to detect in production, especially when they involve:
- Daylight Saving Time (DST)
- Timezone conversions
- Scheduler drift
- Daily vs hourly boundary logic

The utilities in this folder are designed to make **time behavior explicit, predictable, and production-safe**.

---

## Included Patterns

### DST-Safe Triggers
Logic for generating daily trigger values that do **not shift during DST transitions**, intended for:
- Looker `sql_trigger_value`
- Scheduled refresh guards
- Incremental partition boundaries

---

## Philosophy

Rather than relying on implicit timezone behavior from BI tools or schedulers, these patterns:
- Explicitly calculate calendar boundaries
- Treat timezones as first-class logic
- Prefer deterministic outputs over convenience

This approach reduces silent failures and makes scheduling behavior easier to reason about year-round.
