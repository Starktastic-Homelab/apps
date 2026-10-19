-- Read-only canonical ntfy login. No empty database initialization or credential output.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '10s';
DO $guard$
DECLARE actual jsonb; expected jsonb; versions jsonb;
BEGIN
  IF current_database() <> 'ntfy' OR current_user <> 'ntfy'
     OR (SELECT system_identifier::text FROM pg_control_system()) <> '7584099661242523698' THEN
    RAISE EXCEPTION 'Retained ntfy physical database identity rejected';
  END IF;
  IF (SELECT count(*) FROM pg_catalog.pg_class
      WHERE relnamespace='public'::regnamespace AND relkind IN ('r','p')) <> 12
     OR EXISTS (SELECT 1 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_roles r ON r.oid=c.relowner
                WHERE c.relnamespace='public'::regnamespace AND c.relkind IN ('r','p') AND r.rolname <> 'ntfy') THEN
    RAISE EXCEPTION 'Retained ntfy unexpected schema rejected';
  END IF;
  SELECT jsonb_object_agg(table_name,cols) INTO actual FROM (
    SELECT table_name,jsonb_agg(jsonb_build_array(column_name,data_type,is_nullable) ORDER BY ordinal_position) cols
    FROM information_schema.columns WHERE table_schema='public' GROUP BY table_name
  ) columns;
  expected := $columns${"message":[["id","bigint","NO"],["mid","text","NO"],["sequence_id","text","NO"],["time","bigint","NO"],["event","text","NO"],["expires","bigint","NO"],["topic","text","NO"],["message","text","NO"],["title","text","NO"],["priority","integer","NO"],["tags","text","NO"],["click","text","NO"],["icon","text","NO"],["actions","text","NO"],["attachment_name","text","NO"],["attachment_type","text","NO"],["attachment_size","bigint","NO"],["attachment_expires","bigint","NO"],["attachment_url","text","NO"],["attachment_deleted","boolean","NO"],["sender","text","NO"],["user_id","text","NO"],["content_type","text","NO"],["encoding","text","NO"],["published","boolean","NO"]],"message_stats":[["key","text","NO"],["value","bigint","YES"]],"schema_version":[["store","text","NO"],["version","integer","NO"]],"tier":[["id","text","NO"],["code","text","NO"],["name","text","NO"],["messages_limit","bigint","NO"],["messages_expiry_duration","bigint","NO"],["emails_limit","bigint","NO"],["calls_limit","bigint","NO"],["reservations_limit","bigint","NO"],["attachment_file_size_limit","bigint","NO"],["attachment_total_size_limit","bigint","NO"],["attachment_expiry_duration","bigint","NO"],["attachment_bandwidth_limit","bigint","NO"],["stripe_monthly_price_id","text","YES"],["stripe_yearly_price_id","text","YES"]],"user":[["id","text","NO"],["tier_id","text","YES"],["user_name","text","NO"],["pass","text","NO"],["role","text","NO"],["prefs","jsonb","NO"],["sync_topic","text","NO"],["provisioned","boolean","NO"],["stats_messages","bigint","NO"],["stats_emails","bigint","NO"],["stats_calls","bigint","NO"],["stripe_customer_id","text","YES"],["stripe_subscription_id","text","YES"],["stripe_subscription_status","text","YES"],["stripe_subscription_interval","text","YES"],["stripe_subscription_paid_until","bigint","YES"],["stripe_subscription_cancel_at","bigint","YES"],["created","bigint","NO"],["deleted","bigint","YES"]],"user_access":[["user_id","text","NO"],["topic","text","NO"],["read","boolean","NO"],["write","boolean","NO"],["owner_user_id","text","YES"],["provisioned","boolean","NO"]],"user_email":[["user_id","text","NO"],["email","text","NO"],["is_primary","boolean","NO"]],"user_magic_link":[["token_hash","text","NO"],["kind","text","NO"],["user_id","text","NO"],["email","text","YES"],["expires","bigint","NO"],["created","bigint","NO"]],"user_phone":[["user_id","text","NO"],["phone_number","text","NO"]],"user_token":[["user_id","text","NO"],["token","text","NO"],["label","text","NO"],["last_access","bigint","NO"],["last_origin","text","NO"],["expires","bigint","NO"],["provisioned","boolean","NO"]],"webpush_subscription":[["id","text","NO"],["endpoint","text","NO"],["key_auth","text","NO"],["key_p256dh","text","NO"],["user_id","text","NO"],["subscriber_ip","text","NO"],["updated_at","bigint","NO"],["warned_at","bigint","NO"]],"webpush_subscription_topic":[["subscription_id","text","NO"],["topic","text","NO"]]}$columns$::jsonb;
  SELECT jsonb_object_agg(store,version) INTO versions FROM public.schema_version;
  -- Stock v2.31.0 adds only claimed_at in message schema 15 -> 16.
  IF versions = '{"user":9,"message":16,"webpush":1}'::jsonb THEN
    expected := jsonb_set(expected, '{message}',
      (expected->'message') || '[["claimed_at","bigint","NO"]]'::jsonb);
  ELSIF versions IS DISTINCT FROM '{"user":9,"message":15,"webpush":1}'::jsonb THEN
    RAISE EXCEPTION 'Retained ntfy unqualified schema version rejected';
  END IF;
  IF actual IS DISTINCT FROM expected THEN
    RAISE EXCEPTION 'Retained ntfy incomplete columns rejected';
  END IF;
  IF (SELECT count(*) FROM public.schema_version) <> 3
     OR NOT EXISTS (SELECT 1 FROM public."user" WHERE id='u_everyone' AND user_name='*' AND role='anonymous')
     OR NOT EXISTS (SELECT 1 FROM public."user" WHERE role='admin')
     OR NOT EXISTS (SELECT 1 FROM public.message_stats WHERE key='messages' AND value >= 0) THEN
    RAISE EXCEPTION 'Retained ntfy initialized state rejected';
  END IF;
END
$guard$;
COMMIT;
