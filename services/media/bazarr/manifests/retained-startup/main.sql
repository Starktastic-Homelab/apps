-- Read-only canonical login rejects empty/wrong retained Bazarr state.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '10s';
DO $guard$
DECLARE expected text;
BEGIN
  IF current_database() <> 'bazarr' OR current_user <> 'bazarr' THEN
    RAISE EXCEPTION 'Retained Bazarr database identity rejected';
  END IF;
  IF (SELECT count(*) FROM pg_catalog.pg_class
      WHERE relnamespace='public'::regnamespace AND relkind IN ('r','p')) <> 17 THEN
    RAISE EXCEPTION 'Retained Bazarr unexpected schema rejected';
  END IF;
  FOREACH expected IN ARRAY ARRAY[
    'system', 'table_announcements', 'table_blacklist', 'table_blacklist_movie',
    'table_episodes', 'table_episodes_subtitles', 'table_history', 'table_history_movie',
    'table_languages_profiles', 'table_movies', 'table_movies_rootfolder', 'table_movies_subtitles',
    'table_settings_languages', 'table_settings_notifier', 'table_shows', 'table_shows_rootfolder', 'alembic_version'
  ] LOOP
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public'
                   AND table_name=expected AND table_type='BASE TABLE') THEN
      RAISE EXCEPTION 'Retained Bazarr schema rejected';
    END IF;
  END LOOP;
  IF (SELECT count(*) FROM public.alembic_version) <> 1
     OR NOT EXISTS (SELECT 1 FROM public.alembic_version WHERE version_num='537e9b4d10e3')
     OR (SELECT count(*) FROM public.system) <> 1
     OR NOT EXISTS (SELECT 1 FROM public.system WHERE configured='1')
     OR NOT EXISTS (SELECT 1 FROM public.table_languages_profiles)
     OR (NOT EXISTS (SELECT 1 FROM public.table_shows) AND NOT EXISTS (SELECT 1 FROM public.table_movies)) THEN
    RAISE EXCEPTION 'Retained Bazarr initialized data rejected';
  END IF;
END
$guard$;
COMMIT;
