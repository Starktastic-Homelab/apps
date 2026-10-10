\set ON_ERROR_STOP on
SET statement_timeout = '60s';
SELECT set_config('homelab.expected', :'expected', false);
DO $$
DECLARE deadline timestamptz := clock_timestamp() + interval '30 seconds';
BEGIN
  IF current_database() <> 'postgres' OR current_user <> 'postgres'
     OR current_setting('homelab.expected') !~ '^[0-9]+$'
     OR current_setting('homelab.expected') <> (SELECT system_identifier::text FROM pg_control_system())
     OR pg_is_in_recovery() THEN
    RAISE EXCEPTION 'Bootstrap identity rejected';
  END IF;
  WHILE NOT pg_try_advisory_lock(1346848082, 1) LOOP
    IF clock_timestamp() >= deadline THEN RAISE EXCEPTION 'Enrollment lock timeout'; END IF;
    PERFORM pg_sleep(0.1);
  END LOOP;
END $$;
BEGIN;
CREATE SCHEMA homelab_enrollment AUTHORIZATION postgres;
REVOKE ALL ON SCHEMA homelab_enrollment FROM PUBLIC;
CREATE TABLE homelab_enrollment.enrollments (
  id text PRIMARY KEY,
  database_name text NOT NULL UNIQUE,
  role_name text NOT NULL UNIQUE,
  mode text NOT NULL CHECK (mode IN ('new', 'adopt')),
  phase text NOT NULL CHECK (phase IN ('provisioning', 'ready'))
);
REVOKE ALL ON homelab_enrollment.enrollments FROM PUBLIC;
COMMIT;
