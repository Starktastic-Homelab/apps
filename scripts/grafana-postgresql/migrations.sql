SELECT jsonb_build_object(
  'migration_log', (SELECT jsonb_agg(jsonb_build_array(migration_id,sql,success,error) ORDER BY migration_id,id) FROM public.migration_log),
  'resource_migration_log', (SELECT jsonb_agg(jsonb_build_array(migration_id,sql,success,error) ORDER BY migration_id,id) FROM public.resource_migration_log),
  'secret_migration_log', (SELECT jsonb_agg(jsonb_build_array(migration_id,sql,success,error) ORDER BY migration_id,id) FROM public.secret_migration_log),
  'unifiedstorage_migration_log', (SELECT jsonb_agg(jsonb_build_array(migration_id,sql,success,error) ORDER BY migration_id,id) FROM public.unifiedstorage_migration_log)
);
