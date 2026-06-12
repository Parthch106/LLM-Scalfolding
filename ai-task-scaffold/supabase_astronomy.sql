-- ============================================================
-- Astronomy Observation Catalog — Supabase Schema
-- Run this in: SQL Editor → New Query → Run
-- ============================================================

-- Drop old tables (clean switch)
DROP TABLE IF EXISTS tasks CASCADE;

-- Keep ai_action_log as-is (audit log is domain-agnostic)

-- 1. Main catalog table
CREATE TABLE IF NOT EXISTS celestial_objects (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  catalog_id         TEXT NOT NULL UNIQUE,  -- e.g. "HD 209458", "2023 BX1"
  name               TEXT,                  -- common name
  object_type        TEXT NOT NULL CHECK (object_type IN ('Star','Exoplanet','Asteroid','Galaxy','Nebula','Comet')),
  spectral_class     TEXT,                  -- O B A F G K M (stars only)
  magnitude          FLOAT,                 -- apparent magnitude (lower = brighter)
  distance_ly        FLOAT,                 -- distance in light-years
  observation_status TEXT NOT NULL DEFAULT 'Unobserved'
    CHECK (observation_status IN ('Unobserved','Scheduled','Observed','Confirmed','Anomalous')),
  priority           TEXT NOT NULL DEFAULT 'Medium'
    CHECK (priority IN ('Low','Medium','High','Critical')),
  tags               TEXT[] DEFAULT '{}',
  notes              TEXT,
  user_id            UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001',
  created_at         TIMESTAMPTZ DEFAULT NOW()
);

-- Disable RLS for demo (no real auth)
ALTER TABLE celestial_objects DISABLE ROW LEVEL SECURITY;

-- 2. Seed data — 20 real/realistic celestial objects
INSERT INTO celestial_objects (catalog_id, name, object_type, spectral_class, magnitude, distance_ly, observation_status, priority, tags, notes) VALUES

  -- ── Stars ──────────────────────────────────────────────────────────────────
  ('Proxima Centauri',  'Proxima Centauri',  'Star',      'M',  11.13,    4.24,   'Confirmed',  'High',     ARRAY['red-dwarf','nearest-star','flare-star'],
   'Closest star to Earth. Hosts Proxima b in habitable zone. High flare activity.'),

  ('Alpha Centauri A',  'Rigil Kentaurus',   'Star',      'G',  -0.01,    4.37,   'Confirmed',  'Medium',   ARRAY['binary','solar-analog','bright'],
   'Part of triple star system. Similar to our Sun in size and spectral class.'),

  ('Betelgeuse',        'Betelgeuse',        'Star',      'M',   0.42,  700.0,    'Observed',   'Critical', ARRAY['red-supergiant','variable','pre-supernova'],
   'Dramatic dimming event in 2019-2020. Supernova candidate within 100,000 years.'),

  ('HD 209458',         'Osiris',            'Star',      'G',   7.65,  159.0,    'Confirmed',  'High',     ARRAY['transiting-host','hot-jupiter-host'],
   'First star confirmed to have a transiting exoplanet. Benchmark for atmospheric studies.'),

  ('Tau Ceti',          'Tau Ceti',          'Star',      'G',   3.50,   11.9,    'Observed',   'High',     ARRAY['solar-analog','planetary-system','nearby'],
   'Has at least 4 planets. Two are in the habitable zone. Heavy debris disk.'),

  ('Vega',              'Vega',              'Star',      'A',   0.03,   25.0,    'Confirmed',  'Low',      ARRAY['bright','debris-disk','pole-star-future'],
   'Reference star for magnitude scale. Rotating so fast it bulges at equator.'),

  ('Sirius A',          'Sirius',            'Star',      'A',  -1.46,    8.6,    'Confirmed',  'Low',      ARRAY['brightest-star','binary','dog-star'],
   'Brightest star in night sky. Sirius B is a white dwarf companion.'),

  -- ── Exoplanets ─────────────────────────────────────────────────────────────
  ('TRAPPIST-1e',       'TRAPPIST-1e',       'Exoplanet', NULL,  NULL,   39.6,    'Scheduled',  'Critical', ARRAY['habitable-zone','rocky','biosignature-target','jwst'],
   'Best candidate for atmospheric biosignature detection. JWST scheduled observations pending.'),

  ('Kepler-452b',       'Earth''s Cousin',   'Exoplanet', NULL,  NULL, 1400.0,    'Observed',   'Medium',   ARRAY['habitable-zone','super-earth','kepler'],
   'Orbits a G-type star with 385-day year. ~60% larger than Earth. Unconfirmed atmosphere.'),

  ('51 Pegasi b',       'Dimidium',          'Exoplanet', NULL,  NULL,   50.9,    'Confirmed',  'Low',      ARRAY['hot-jupiter','first-exoplanet','nobel-prize'],
   'First exoplanet discovered around a sun-like star (1995). Orbits in 4.2 days.'),

  ('GJ 1214b',          'GJ 1214b',          'Exoplanet', NULL,  NULL,   40.0,    'Observed',   'High',     ARRAY['water-world','sub-neptune','thick-atmosphere'],
   'Likely has a thick steam atmosphere. Featureless transmission spectrum — clouds or water?'),

  -- ── Asteroids ──────────────────────────────────────────────────────────────
  ('99942 Apophis',     'Apophis',           'Asteroid',  NULL,  NULL,    0.0,    'Scheduled',  'Critical', ARRAY['near-earth','potentially-hazardous','2029-flyby'],
   'Will pass within 32,000 km of Earth in 2029 — closer than some satellites. Being monitored.'),

  ('101955 Bennu',      'Bennu',             'Asteroid',  NULL,  NULL,    0.0,    'Confirmed',  'High',     ARRAY['near-earth','carbon-rich','osiris-rex-sample'],
   'OSIRIS-REx returned samples in 2023. B-type carbonaceous asteroid. Impact probability 1/2700 by 2182.'),

  ('162173 Ryugu',      'Ryugu',             'Asteroid',  NULL,  NULL,    0.0,    'Confirmed',  'High',     ARRAY['near-earth','c-type','hayabusa2-sample'],
   'Hayabusa2 returned samples in 2020. Organic molecules and water-bearing minerals confirmed.'),

  ('2023 BX1',          '2023 BX1',          'Asteroid',  NULL,  NULL,    0.0,    'Unobserved', 'Medium',   ARRAY['near-earth','newly-discovered','composition-unknown'],
   'Discovered hours before impacting over Germany in Jan 2023. Composition uncharacterised.'),

  -- ── Galaxies ───────────────────────────────────────────────────────────────
  ('M31',               'Andromeda Galaxy',  'Galaxy',    NULL,   3.44,  2537000, 'Confirmed',  'Medium',   ARRAY['local-group','spiral','collision-course'],
   'Will collide with Milky Way in ~4.5 billion years. Has at least 1 trillion stars.'),

  ('M33',               'Triangulum Galaxy', 'Galaxy',    NULL,   5.72,  2730000, 'Scheduled',  'Low',      ARRAY['local-group','spiral','smallest-local-group'],
   'Third-largest in Local Group. Debate on whether it is a satellite of Andromeda.'),

  -- ── Nebulae ────────────────────────────────────────────────────────────────
  ('M16 Pillars',       'Pillars of Creation','Nebula',   NULL,  NULL,   6500.0,  'Observed',   'Medium',   ARRAY['star-forming','eagle-nebula','jwst-imaged'],
   'Active star-forming region. JWST 2022 image revealed previously hidden protostars.'),

  ('M1',                'Crab Nebula',       'Nebula',    NULL,   8.4,   6500.0,  'Confirmed',  'Low',      ARRAY['supernova-remnant','pulsar','1054-ad-explosion'],
   'Remnant of SN 1054. Contains a pulsar spinning 30 times per second.'),

  ('M42',               'Orion Nebula',      'Nebula',    NULL,   4.0,   1344.0,  'Anomalous',  'High',     ARRAY['star-forming','nearest-nebula','trapezium'],
   'Unexpected radio emission detected 2024-03. Source unidentified. Flagged for follow-up.');
