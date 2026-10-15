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
);
