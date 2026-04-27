# Data Modeling

This section showcases my approach to building **clear, governed semantic layers** that translate raw data into consistent, business-ready metrics.

The focus here is not data transformation, but **metric definition, abstraction, and usability** across BI tools.

---

## Scope

The models in this directory are responsible for:
- Defining metrics once and reusing them everywhere
- Creating consistent business logic across teams
- Preventing metric drift between dashboards
- Making analytics self-service without sacrificing correctness

Transformations, scheduling logic, and pipeline orchestration are handled elsewhere in the portfolio.

---

## Modeling Tools

### LookML
Looker semantic models defining:
- Dimensions, measures, and metrics
- Business logic abstractions
- Metric labeling and grouping
- Drill paths and explore usability

### Omni YAML
Omni semantic models with:
- YAML-based metric definitions
- Shared measures across datasets
- Consistent naming and formatting
- Analytics-engineer-friendly version control

---

## Modeling Principles

- **Single source of truth**  
  Metrics are defined once and reused across all reports.

- **Business-first semantics**  
  Models reflect how the business thinks, not how raw tables are structured.

- **Explicit logic**  
  All filters, flags, and assumptions are encoded in the semantic layer.

- **Separation of concerns**  
  Data modeling focuses on *what metrics mean*, not *how data is processed*.

- **Analyst usability**  
  Field naming, grouping, and descriptions are optimized for exploration and self-service.

---

## What This Demonstrates

This section demonstrates experience with:
- Designing enterprise semantic layers
- Managing metric governance at scale
- Supporting both technical and non-technical stakeholders
- Maintaining long-term consistency in BI environments

These models are designed to survive team growth, tool changes, and evolving business requirements.
