-- View: Pitchbook.live.deals
-- Joins prod deals with the App overlay table, which holds custom fields
-- entered by users in Grist and upsynced back to BigQuery.
-- The Grist refresh queries this view so that user annotations survive
-- each pipeline refresh cycle.

SELECT p.*, a.custom AS custom_overlay
FROM `Prod.deals_prod` p
LEFT JOIN `App.overlay_deals_current` a
  ON a.deal_id = p.deal_id;
