-- Canonical app-role login must not let stock Prowlarr bootstrap empty main data.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '10s';
DO $guard$
DECLARE
  expected text;
BEGIN
  IF current_database() <> 'prowlarr_main' OR current_user <> 'prowlarr_main' THEN
    RAISE EXCEPTION 'Retained Prowlarr database identity rejected';
  END IF;
  FOREACH expected IN ARRAY ARRAY[
    'AppSyncProfiles', 'ApplicationIndexerMapping', 'ApplicationStatus',
    'Applications', 'Commands', 'Config', 'CustomFilters', 'DownloadClientStatus',
    'DownloadClients', 'History', 'IndexerDefinitionVersions', 'IndexerProxies',
    'IndexerStatus', 'Indexers', 'NotificationStatus', 'Notifications',
    'ScheduledTasks', 'Tags', 'Users', 'VersionInfo'
  ] LOOP
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_schema = 'public' AND table_name = expected
                   AND table_type = 'BASE TABLE') THEN
      RAISE EXCEPTION 'Retained Prowlarr schema rejected';
    END IF;
  END LOOP;
  IF NOT EXISTS (SELECT 1 FROM public."VersionInfo" WHERE "Version" >= 44)
     OR NOT EXISTS (SELECT 1 FROM public."Users")
     OR NOT EXISTS (SELECT 1 FROM public."Config") THEN
    RAISE EXCEPTION 'Retained Prowlarr initialized data rejected';
  END IF;
END
$guard$;
COMMIT;
