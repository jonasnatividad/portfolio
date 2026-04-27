# DST-Safe Daily Trigger (Eastern Time)

## Overview

This SQL pattern generates a **day-level trigger value that is immune to Daylight Saving Time (DST) transitions** for the Eastern US time zone.

It was originally designed for use in **Looker `sql_trigger_value` fields**, where DST-related hour shifts can cause scheduled refreshes to:
- Fire an hour early or late
- Skip a refresh
- Create duplicate daily partitions

This logic ensures **consistent daily behavior across DST boundaries**.

---

## Problem

Most BI tools and schedulers rely on timestamps that shift when DST starts or ends.

For Eastern Time:
- EST = UTC-5
- EDT = UTC-4

When DST changes:
- “Midnight Eastern” is no longer a fixed UTC offset
- Daily triggers based on timestamps can break

---

## Solution

This query:
1. Dynamically calculates:
   - Second Sunday in March (DST start)
   - First Sunday in November (DST end)
2. Determines whether the current time is in **EDT or EST**
3. Applies a **fixed UTC offset** depending on the active timezone
4. Produces a **stable integer day index** that does not shift during DST transitions

---

## Primary Use Case

### Looker `sql_trigger_value`

```sql
sql_trigger_value: (
  SELECT day_index FROM ...
)
