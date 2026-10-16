-- Stock pgAdmin9.18 native schema52: reject loss before stock initialization.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '10s';
DO $guard$
DECLARE actual text;
BEGIN
  IF current_database() <> 'pgadmin' OR current_user <> 'pgadmin'
     OR (SELECT system_identifier::text FROM pg_control_system()) <> '7584099661242523698' THEN
    RAISE EXCEPTION 'Retained pgAdmin physical database identity rejected';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_roles r ON r.oid=c.relowner
             WHERE c.relnamespace='public'::regnamespace AND c.relkind IN ('r','p','S') AND r.rolname <> 'pgadmin') THEN
    RAISE EXCEPTION 'Retained pgAdmin schema owner rejected';
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
  IF actual IS DISTINCT FROM '60e89b98ff8d9bb20ad69a29d7de943d98bda3b96f4645e95316f30b37b5efee' THEN
    RAISE EXCEPTION 'Retained pgAdmin stock schema contract rejected';
  END IF;
  SELECT encode(sha256(convert_to((
SELECT jsonb_build_object('version',(SELECT jsonb_agg(to_jsonb(t) ORDER BY name) FROM public.version t),'alembic_version',(SELECT jsonb_agg(to_jsonb(t) ORDER BY version_num) FROM public.alembic_version t))
  )::jsonb::text,'UTF8')),'hex') INTO actual;
  IF actual IS DISTINCT FROM 'dfd8854c0b184e4b5d99c513858f87b3dfd464196b816b2c88c485f4ee07f922' THEN
    RAISE EXCEPTION 'Retained pgAdmin initialized state rejected: markers';
  END IF;
  SELECT encode(sha256(convert_to((
SELECT jsonb_agg(to_jsonb(t) ORDER BY name) FROM public.keys t
  )::jsonb::text,'UTF8')),'hex') INTO actual;
  IF actual IS DISTINCT FROM '3e1c6e0bf817519fa64d4f363ad7b3101ece83f70953339cb753d695dbc1565e' THEN
    RAISE EXCEPTION 'Retained pgAdmin initialized state rejected: keys';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public."user" u
       JOIN public.roles_users ru ON ru.user_id=u.id JOIN public.role r ON r.id=ru.role_id
       WHERE u.active AND NOT coalesce(u.locked,false) AND u.auth_source='internal'
         AND u.password IS NOT NULL AND u.password<>'' AND r.name='Administrator') THEN
    RAISE EXCEPTION 'Retained pgAdmin initialized state rejected: active administrator';
  END IF;
END
$guard$;
COMMIT;
