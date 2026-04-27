-- View: Pitchbook.live.investors
-- Joins prod investors with the App overlay table, which holds custom fields
-- entered by users in Grist and upsynced back to BigQuery.
-- The Grist refresh queries this view so that user annotations survive
-- each pipeline refresh cycle.

SELECT p.*, a.custom AS custom_overlay
FROM `Prod.investors_prod` p
LEFT JOIN `App.overlay_investors_current` a
  ON a.investor_id = p.investor_id;
