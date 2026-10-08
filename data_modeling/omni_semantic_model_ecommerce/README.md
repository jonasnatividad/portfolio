# Omni Semantic Model: Online Retailer (thelook_ecommerce)

A semantic model for [Omni](https://omni.co) built on BigQuery's free public dataset
`bigquery-public-data.thelook_ecommerce`, a synthetic online clothing retailer with
orders, items, products, customers, inventory, web events and distribution centers.

The goal is the same as for any company model: give business users a small set of
trusted, well-described datasets (topics) so "revenue", "open orders" or "eligible
customer" mean one thing everywhere.

## Layout

```
omni_semantic_model_ecommerce/
├── settings/
│   ├── model.yml              # included schemas, calendar, access grants
│   └── relationships.yml      # every join, declared once
├── schemas/
│   ├── base/                  # one view per source table
│   │   ├── orders.view.yml
│   │   ├── order_items.view.yml
│   │   ├── products.view.yml
│   │   ├── users.view.yml
│   │   ├── inventory_items.view.yml
│   │   ├── events.view.yml
│   │   └── distribution_centers.view.yml
│   ├── reporting_views/       # SQL-defined (query) views with business logic
│   │   ├── date_spine.query.view.yml
│   │   └── orders_eligible_for_repeat_campaign.query.view.yml
│   └── snapshots/
│       └── order_status_daily_snapshot.query.view.yml
└── topics/                    # what end users actually browse
    ├── orders.topic.yml
    ├── customers.topic.yml
    ├── inventory.topic.yml
    └── order_status_snapshot.topic.yml
```

In Omni's own Git layout these files are the model file, the relationships file,
`*.view` / `*.query.view` files and `*.topic` files. They are grouped into folders and
given a `.yml` suffix here so the structure reads clearly on GitHub; the YAML inside
follows Omni's view, relationship and topic parameters.

## Design choices

**Base, then reporting, then topics.**
- *Base views* map one-to-one to source tables. They only rename, type, describe and
  add simple derived fields (age bands, yes/no flags, durations) plus standard
  measures. No joins, no filters that hide rows.
- *Reporting views* are SQL query views for logic that does not fit a single table:
  a detached calendar and a campaign-eligibility rule set. Keeping a business rule in
  one view means every dashboard and export uses the same definition.
- *Topics* are the presentation layer: a base view, the joins it needs, a curated field
  list (personal data removed where it is not needed), default filters and AI context
  that tells Omni's assistant which measure "revenue" means.

**Relationships in one place.** All joins live in `relationships.yml`, written from the
finer grain to the coarser grain with an explicit `relationship_type`, so Omni can
detect fan-out and compute measures correctly (symmetric aggregates). Two joins are
marked `reversible` so the customer topic can start from `users` and reach orders and
web events.

**Measures defined once, composed later.** Ratios (`return_rate`, `gross_margin_pct`,
`sell_through_rate`, `session_conversion_rate`) are built from other measures with
`SAFE_DIVIDE`, so they stay correct at any level of grouping. Filtered measures
(`completed_order_count`, `units_in_stock`) use `filters:` rather than separate SQL.

**Detached date spine.** `date_spine` has no foreign keys. It generates one row per day
so trend charts show zero-activity days and so the snapshot view has a calendar to
expand against.

**Snapshot pattern.** The source only stores each order's current status, but it keeps
the timestamp of every milestone. `order_status_daily_snapshot` crosses orders with a
365-day calendar and works out the end-of-day status on each date, which gives
backlog and aging trends without a nightly copy job. The view's header comment shows
how to persist it as an append-only, partitioned table (BigQuery scheduled query) when
history must be frozen.

**Campaign eligibility as a view.** `orders_eligible_for_repeat_campaign` returns one row
per customer whose last order was completed and delivered 30 to 90 days ago, who has no
open order, and who returns at most half of their orders. It also splits the audience
into three send waves.

**Governance.** Cost and margin fields carry `required_access_grants: [finance_only]`,
driven by a `department` user attribute. Name, email and location detail are hidden in
base views and left out of topics that do not need them.

## Pointing it at the public dataset

1. In BigQuery, make sure your billing project (`your-gcp-project`) has the BigQuery API
   enabled. Queries against `bigquery-public-data` are billed to your project; the
   dataset is small (well under the 1 TB monthly free tier for normal use).
2. Create a service account in `your-gcp-project` with **BigQuery Job User** and
   **BigQuery Data Viewer**, and download a key or use workload identity.
3. In Omni, add a BigQuery connection:
   - Billing project: `your-gcp-project`
   - Default database/project: `bigquery-public-data`
   - Include schema: `thelook_ecommerce`
4. Let Omni generate the schema, then connect the model to a Git repository and copy
   these files in (or paste each file into the matching file in the Omni IDE).
5. Validate the model in the IDE and open the **Orders & Revenue** topic.

## Example questions the model answers

- Net revenue and gross margin by month and product category (Orders & Revenue)
- Return rate by acquisition source and age band (Orders & Revenue)
- How many customers are in each send wave this week (Customers)
- Units in stock older than 180 days by distribution center (Inventory)
- Open-order backlog per day for the last 90 days (Order Status Over Time)
