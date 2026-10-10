\set ON_ERROR_STOP on
SET statement_timeout = '60s';
\set config `cat /config/config.json`
CREATE TEMP TABLE config AS SELECT :'config'::jsonb AS value;
DO $$
DECLARE c jsonb := (SELECT value FROM config);
        deadline timestamptz := clock_timestamp() + interval '30 seconds';
BEGIN
  IF current_database() <> 'postgres' OR current_user <> 'postgres'
     OR c->>'expectedSystemIdentifier' IS NULL
     OR c->>'expectedSystemIdentifier' !~ '^[0-9]+$'
     OR c->>'expectedSystemIdentifier' <> (SELECT system_identifier::text FROM pg_control_system())
     OR pg_is_in_recovery() THEN RAISE EXCEPTION 'Server identity rejected'; END IF;
  WHILE NOT pg_try_advisory_lock(1346848082, 1) LOOP
    IF clock_timestamp() >= deadline THEN RAISE EXCEPTION 'Enrollment lock timeout'; END IF;
    PERFORM pg_sleep(0.1);
  END LOOP;
  IF (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(c) k)
       <> ARRAY['entries','expectedSystemIdentifier','version']
     OR c->'version' <> '1'::jsonb OR jsonb_typeof(c->'entries') <> 'array'
     OR jsonb_typeof(c->'expectedSystemIdentifier') <> 'string' THEN
    RAISE EXCEPTION 'Invalid enrollment config';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_namespace WHERE nspname='homelab_enrollment'
      AND nspowner='postgres'::regrole AND NOT EXISTS
        (SELECT FROM aclexplode(nspacl) a WHERE a.grantee <> 'postgres'::regrole))
     OR NOT EXISTS (SELECT FROM pg_class WHERE oid=to_regclass('homelab_enrollment.enrollments')
        AND relkind='r' AND relowner='postgres'::regrole AND NOT relrowsecurity AND NOT relforcerowsecurity
        AND NOT EXISTS (SELECT FROM aclexplode(relacl) a WHERE a.grantee <> 'postgres'::regrole)) THEN
    RAISE EXCEPTION 'Registry missing or unsafe';
  END IF;
  IF (SELECT array_agg(attname::text ORDER BY attnum) FROM pg_attribute
       WHERE attrelid='homelab_enrollment.enrollments'::regclass AND attnum>0 AND NOT attisdropped)
       <> ARRAY['id','database_name','role_name','mode','phase']
     OR EXISTS (SELECT FROM pg_attribute WHERE attrelid='homelab_enrollment.enrollments'::regclass
       AND attnum>0 AND (attisdropped OR atttypid<>'text'::regtype OR NOT attnotnull OR atthasdef OR attgenerated<>'' OR attidentity<>''))
     OR (SELECT count(*) FROM pg_constraint WHERE conrelid='homelab_enrollment.enrollments'::regclass AND contype<>'n') <> 5
     OR (SELECT array_agg(pg_get_constraintdef(oid) ORDER BY pg_get_constraintdef(oid)) FROM pg_constraint
         WHERE conrelid='homelab_enrollment.enrollments'::regclass AND convalidated AND contype<>'n')
       <> ARRAY['CHECK ((mode = ANY (ARRAY[''new''::text, ''adopt''::text])))',
                'CHECK ((phase = ANY (ARRAY[''provisioning''::text, ''ready''::text])))',
                'PRIMARY KEY (id)', 'UNIQUE (database_name)', 'UNIQUE (role_name)']
     OR EXISTS (SELECT FROM pg_trigger WHERE tgrelid='homelab_enrollment.enrollments'::regclass AND NOT tgisinternal)
     OR EXISTS (SELECT FROM pg_rewrite WHERE ev_class='homelab_enrollment.enrollments'::regclass)
     OR EXISTS (SELECT FROM pg_index WHERE indrelid='homelab_enrollment.enrollments'::regclass AND NOT indisvalid) THEN
    RAISE EXCEPTION 'Registry structure changed';
  END IF;
END $$;
CREATE TEMP TABLE entries AS
SELECT e->>'id' AS id,e->>'database' AS database_name,e->>'role' AS role_name,
       e->>'mode' AS mode,e->>'passwordKey' AS password_key,e AS raw
FROM config, jsonb_array_elements(value->'entries') e;
DO $$
DECLARE e record; r record; d record; l record;
BEGIN
  IF EXISTS (SELECT FROM entries WHERE
      (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(raw) k)
        <> ARRAY['database','id','mode','passwordKey','role']
      OR EXISTS (SELECT FROM jsonb_each(raw) WHERE jsonb_typeof(value)<>'string')
      OR id IS NULL OR database_name IS NULL OR role_name IS NULL OR mode IS NULL OR password_key IS NULL
      OR id !~ '^[a-z][a-z0-9_-]{0,62}$' OR database_name !~ '^[a-z][a-z0-9_]{0,62}$'
      OR role_name !~ '^[a-z][a-z0-9_]{0,62}$' OR password_key !~ '^[a-z][a-z0-9_-]{0,62}$'
      OR mode NOT IN ('new','adopt') OR role_name='postgres' OR role_name LIKE 'pg\_%'
      OR database_name IN ('postgres','template0','template1'))
    OR EXISTS (SELECT FROM entries GROUP BY id HAVING count(*)>1)
    OR EXISTS (SELECT FROM entries GROUP BY database_name HAVING count(*)>1)
    OR EXISTS (SELECT FROM entries GROUP BY role_name HAVING count(*)>1)
    OR EXISTS (SELECT FROM entries GROUP BY password_key HAVING count(*)>1) THEN
    RAISE EXCEPTION 'Invalid enrollment entries';
  END IF;
  FOR e IN SELECT * FROM entries LOOP
    SELECT * INTO l FROM homelab_enrollment.enrollments WHERE id=e.id;
    IF l.id IS NOT NULL AND (l.database_name<>e.database_name OR l.role_name<>e.role_name OR l.mode<>e.mode) THEN
      RAISE EXCEPTION 'Recorded binding changed';
    END IF;
    IF EXISTS (SELECT FROM homelab_enrollment.enrollments WHERE id<>e.id
        AND (database_name=e.database_name OR role_name=e.role_name)) THEN
      RAISE EXCEPTION 'Identity already recorded';
    END IF;
    SELECT * INTO r FROM pg_roles WHERE rolname=e.role_name;
    SELECT * INTO d FROM pg_database WHERE datname=e.database_name;
    IF l.id IS NULL AND e.mode='new' THEN
      IF r.oid IS NOT NULL OR d.oid IS NOT NULL THEN RAISE EXCEPTION 'New identity already exists'; END IF;
    ELSE
      IF r.oid IS NULL OR r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication
        OR r.rolbypassrls OR NOT r.rolinherit OR r.rolvaliduntil IS NOT NULL
        OR (e.mode='new' AND EXISTS (SELECT FROM pg_auth_members WHERE member=r.oid)) THEN
        RAISE EXCEPTION 'Role missing or incompatible';
      END IF;
      IF e.mode='adopt' AND EXISTS (
        WITH RECURSIVE parents(oid) AS (
          SELECT roleid FROM pg_auth_members WHERE member=r.oid
          UNION SELECT m.roleid FROM pg_auth_members m JOIN parents p ON m.member=p.oid)
        SELECT FROM parents JOIN pg_roles p USING(oid)
        WHERE p.rolsuper OR p.rolcreatedb OR p.rolcreaterole OR p.rolreplication OR p.rolbypassrls OR p.rolname LIKE 'pg\_%') THEN
        RAISE EXCEPTION 'Elevated membership';
      END IF;
      IF l.phase='provisioning' THEN
        IF e.mode<>'new' OR r.rolcanlogin THEN RAISE EXCEPTION 'Invalid pending role'; END IF;
      ELSIF NOT r.rolcanlogin OR d.oid IS NULL THEN RAISE EXCEPTION 'Established identity missing'; END IF;
      IF d.oid IS NOT NULL AND (d.datdba<>r.oid OR NOT d.datallowconn OR d.datistemplate) THEN
        RAISE EXCEPTION 'Database incompatible';
      END IF;
    END IF;
  END LOOP;
END $$;
\if :preflight
\o :rows
SELECT e.id,e.database_name,e.role_name,e.mode,e.password_key,
       (e.mode='adopt' OR l.phase='ready') IS TRUE AS verify
FROM entries e LEFT JOIN homelab_enrollment.enrollments l USING(id) ORDER BY e.id;
\o
\else
SELECT id,database_name AS database,role_name AS role,mode,password_key AS key FROM entries WHERE id=:'entry' \gset
SELECT NOT EXISTS (SELECT FROM homelab_enrollment.enrollments WHERE id=:'id') AS unknown \gset
-- boundary: before-role
\if :unknown
SELECT :'mode'='new' AS create_new \gset
\if :create_new
BEGIN;
SELECT format('CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT', :'role') \gexec
INSERT INTO homelab_enrollment.enrollments VALUES (:'id',:'database',:'role','new','provisioning');
COMMIT;
\endif
\endif
-- boundary: after-role
SELECT EXISTS (SELECT FROM homelab_enrollment.enrollments WHERE id=:'id' AND phase='provisioning') AS provisioning \gset
\setenv ENROLL_DATABASE :database
\setenv ENROLL_ROLE :role
\setenv ENROLL_KEY :key
\if :provisioning
SET password_encryption='scram-sha-256';
\password :"role"
-- boundary: after-password
SELECT format('CREATE DATABASE %I OWNER %I', :'database', :'role') WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname=:'database') \gexec
-- boundary: after-database
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'database') \gexec
\! /bin/sh /scripts/enroll.sh schema
\if :SHELL_ERROR
DO $$ BEGIN RAISE EXCEPTION 'Enrollment child failed'; END $$;
\endif
-- boundary: after-schema
BEGIN;
UPDATE homelab_enrollment.enrollments SET phase='ready' WHERE id=:'id';
SELECT format('ALTER ROLE %I LOGIN', :'role') \gexec
COMMIT;
\endif
-- boundary: after-ready
\! /bin/sh /scripts/enroll.sh verify-login
\if :SHELL_ERROR
DO $$ BEGIN RAISE EXCEPTION 'Enrollment child failed'; END $$;
\endif
\if :unknown
\if :create_new
\else
INSERT INTO homelab_enrollment.enrollments VALUES (:'id',:'database',:'role','adopt','ready');
\endif
\endif
\endif
