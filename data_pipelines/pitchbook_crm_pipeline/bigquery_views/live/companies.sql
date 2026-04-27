-- View: Pitchbook.live.companies
-- Joins prod companies with the App overlay table, which holds custom fields
-- entered by users in Grist and upsynced back to BigQuery.
-- The Grist refresh queries this view so that user annotations (notes, status
-- flags, relationship tracking, etc.) survive each pipeline refresh cycle.

SELECT p.*, a.custom AS custom_overlay
FROM `Prod.companies_prod` p
LEFT JOIN `App.overlay_companies_current` a
  ON a.company_id = p.company_id;
