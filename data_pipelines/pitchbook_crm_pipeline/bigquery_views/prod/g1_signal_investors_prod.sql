-- View: Pitchbook.prod.g1_signal_investors_prod
-- A curated subset of signal_investors_clean filtered to a specific list of
-- investor IDs representing the fund's highest-priority signal investors (G1 tier).
-- The ID list is maintained manually and updated as the conviction list evolves.

SELECT
  *
FROM `your-project-id`.`Clean`.`signal_investors_clean`
WHERE
  investor_id IN (
    'INVESTOR_ID_01',
    'INVESTOR_ID_02',
    'INVESTOR_ID_03',
    'INVESTOR_ID_04',
    'INVESTOR_ID_05',
    'INVESTOR_ID_06',
    'INVESTOR_ID_07',
    'INVESTOR_ID_08',
    'INVESTOR_ID_09',
    'INVESTOR_ID_10',
    'INVESTOR_ID_11',
    'INVESTOR_ID_12',
    'INVESTOR_ID_13',
    'INVESTOR_ID_14',
    'INVESTOR_ID_15',
    'INVESTOR_ID_16',
    'INVESTOR_ID_17',
    'INVESTOR_ID_18',
    'INVESTOR_ID_19',
    'INVESTOR_ID_20',
    'INVESTOR_ID_21',
    'INVESTOR_ID_22'
  );
