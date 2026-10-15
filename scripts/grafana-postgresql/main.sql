-- Stock Grafana 13.2.3 schema signature; read-only, no empty-database initialization.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '10s';
DO $guard$
DECLARE actual text;
BEGIN
  IF current_database() <> 'grafana' OR current_user <> 'grafana'
     OR (SELECT system_identifier::text FROM pg_control_system()) <> '7584099661242523698' THEN
    RAISE EXCEPTION 'Retained Grafana physical database identity rejected';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_roles r ON r.oid=c.relowner
             WHERE c.relnamespace='public'::regnamespace AND c.relkind IN ('r','p') AND r.rolname <> 'grafana') THEN
    RAISE EXCEPTION 'Retained Grafana schema owner rejected';
  END IF;
  SELECT encode(sha256(convert_to((
SELECT json_build_object(
  'columns', (SELECT json_agg(row_to_json(t)) FROM (
    SELECT table_name,column_name,data_type,udt_name,is_nullable,column_default
    FROM information_schema.columns WHERE table_schema='public'
    ORDER BY table_name,ordinal_position) t),
  'constraints', (SELECT json_agg(row_to_json(t)) FROM (
    SELECT c.relname,t.conname,t.contype,pg_get_constraintdef(t.oid,true) definition
    FROM pg_constraint t JOIN pg_class c ON c.oid=t.conrelid
    WHERE t.connamespace='public'::regnamespace ORDER BY c.relname,t.conname) t),
  'indexes', (SELECT json_agg(row_to_json(t)) FROM (
    SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public'
    ORDER BY tablename,indexname) t)
)
  )::jsonb::text,'UTF8')),'hex') INTO actual;
  IF actual IS DISTINCT FROM 'b6f101e43c7767cb9bf779c8e76d602086e84b6db3cfea302fb1bd556c8bdbe9' THEN
    RAISE EXCEPTION 'Retained Grafana stock schema contract rejected';
  END IF;
  SELECT encode(sha256(convert_to((
SELECT jsonb_build_object(
  'migration_log', (SELECT jsonb_agg(jsonb_build_array(migration_id,sql,success,error) ORDER BY migration_id,id) FROM public.migration_log),
  'resource_migration_log', (SELECT jsonb_agg(jsonb_build_array(migration_id,sql,success,error) ORDER BY migration_id,id) FROM public.resource_migration_log),
  'secret_migration_log', (SELECT jsonb_agg(jsonb_build_array(migration_id,sql,success,error) ORDER BY migration_id,id) FROM public.secret_migration_log),
  'unifiedstorage_migration_log', (SELECT jsonb_agg(jsonb_build_array(migration_id,sql,success,error) ORDER BY migration_id,id) FROM public.unifiedstorage_migration_log)
)
  )::text,'UTF8')),'hex') INTO actual;
  IF actual IS DISTINCT FROM '8937bbf74a20a46011d80235bc7444307d352ac4218cdd4e38f4ac608110b08b' THEN
    RAISE EXCEPTION 'Retained Grafana initialized state rejected: native migration records';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public."user" WHERE is_disabled=false AND is_service_account=false)
     OR NOT EXISTS (SELECT 1 FROM public.data_source)
     OR NOT EXISTS (SELECT 1 FROM public.resource WHERE resource='dashboards')
     OR NOT EXISTS (SELECT 1 FROM public.resource_history)
     OR NOT EXISTS (SELECT 1 FROM public.data_keys)
     OR EXISTS (SELECT 1 FROM public.migration_log WHERE NOT success)
     OR EXISTS (SELECT 1 FROM public.resource_migration_log WHERE NOT success)
     OR EXISTS (SELECT 1 FROM public.secret_migration_log WHERE NOT success)
     OR EXISTS (SELECT 1 FROM public.unifiedstorage_migration_log WHERE NOT success) THEN
    RAISE EXCEPTION 'Retained Grafana initialized state rejected';
  END IF;
END
$guard$;
COMMIT;
