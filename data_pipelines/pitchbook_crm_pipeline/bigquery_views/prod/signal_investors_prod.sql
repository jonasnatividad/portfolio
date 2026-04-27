-- View: Pitchbook.prod.signal_investors_prod
-- Pass-through view exposing all columns from signal_investors_clean.
-- Serves as the reference list for signal investor matching across
-- deals_prod and companies_prod.

SELECT *
FROM `your-project-id`.`Clean`.`signal_investors_clean`;
