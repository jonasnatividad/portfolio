-- Target tables in Postgres (Supabase, Cloud SQL or any Postgres 13+).
-- Run once before the first sync. The service creates retail.sync_state itself.

CREATE SCHEMA IF NOT EXISTS retail;

CREATE TABLE IF NOT EXISTS retail.orders (
    order_id      bigint PRIMARY KEY,
    user_id       bigint,
    status        text,
    gender        text,
    created_at    timestamptz,
    shipped_at    timestamptz,
    delivered_at  timestamptz,
    returned_at   timestamptz,
    num_of_item   integer
);

CREATE TABLE IF NOT EXISTS retail.order_items (
    id                 bigint PRIMARY KEY,
    order_id           bigint,
    user_id            bigint,
    product_id         bigint,
    inventory_item_id  bigint,
    status             text,
    created_at         timestamptz,
    shipped_at         timestamptz,
    delivered_at       timestamptz,
    returned_at        timestamptz,
    sale_price         numeric(12, 2)
);
CREATE INDEX IF NOT EXISTS order_items_order_id_idx ON retail.order_items (order_id);

CREATE TABLE IF NOT EXISTS retail.users (
    id              bigint PRIMARY KEY,
    first_name      text,
    last_name       text,
    email           text,
    age             integer,
    gender          text,
    state           text,
    city            text,
    country         text,
    postal_code     text,
    traffic_source  text,
    created_at      timestamptz
);

CREATE TABLE IF NOT EXISTS retail.products (
    id                      bigint PRIMARY KEY,
    cost                    numeric(12, 4),
    category                text,
    name                    text,
    brand                   text,
    retail_price            numeric(12, 4),
    department              text,
    sku                     text,
    distribution_center_id  bigint
);

CREATE TABLE IF NOT EXISTS retail.distribution_centers (
    id         bigint PRIMARY KEY,
    name       text,
    latitude   double precision,
    longitude  double precision
);

-- Read-only role for the app that consumes the copy (optional).
-- CREATE ROLE retail_reader NOLOGIN;
-- GRANT USAGE ON SCHEMA retail TO retail_reader;
-- GRANT SELECT ON ALL TABLES IN SCHEMA retail TO retail_reader;
