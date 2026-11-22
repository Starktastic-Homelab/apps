-- Read-only canonical app login rejects empty or wrong retained Seerr data.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '10s';
DO $guard$
DECLARE
  expected text;
BEGIN
  IF current_database() NOT IN ('seerr', 'seerr_ru') OR current_user <> current_database() THEN
    RAISE EXCEPTION 'Retained Seerr database identity rejected';
  END IF;
  FOREACH expected IN ARRAY ARRAY[
    'blocklist', 'discover_slider', 'issue', 'issue_comment', 'media', 'media_request',
    'override_rule', 'season', 'season_request', 'session', 'user',
    'user_push_subscription', 'user_settings', 'watchlist', 'migrations'
  ] LOOP
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_schema = 'public' AND table_name = expected
                   AND table_type = 'BASE TABLE') THEN
      RAISE EXCEPTION 'Retained Seerr schema rejected';
    END IF;
  END LOOP;
  IF (SELECT count(*) FROM public.migrations) < 19
     OR NOT EXISTS (SELECT 1 FROM public.migrations
                    WHERE timestamp = 1781732098511
                    AND name = 'AddIgnoreQuotaToMediaRequest1781732098511')
     OR NOT EXISTS (SELECT 1 FROM public."user" WHERE id = 1) THEN
    RAISE EXCEPTION 'Retained Seerr initialized data rejected';
  END IF;
END
$guard$;
COMMIT;
