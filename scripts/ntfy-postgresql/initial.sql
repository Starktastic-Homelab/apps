-- Exact initial schema SQL from ntfy v2.29.0 tools/pgimport, f18d1137c63a26e85b91ce639e7bc72bb9a82736.
-- Require an empty application catalog; never use on an existing ntfy database.
BEGIN;
SET LOCAL statement_timeout = '20s';
DO $empty$
BEGIN
  IF current_database() <> 'ntfy' OR current_user <> 'ntfy'
     OR (SELECT count(*) FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind IN ('r','p')) <> 0 THEN
    RAISE EXCEPTION 'ntfy import requires an empty canonical application database';
  END IF;
END
$empty$;

		CREATE TABLE IF NOT EXISTS tier (
			id TEXT PRIMARY KEY,
			code TEXT NOT NULL,
			name TEXT NOT NULL,
			messages_limit BIGINT NOT NULL,
			messages_expiry_duration BIGINT NOT NULL,
			emails_limit BIGINT NOT NULL,
			calls_limit BIGINT NOT NULL,
			reservations_limit BIGINT NOT NULL,
			attachment_file_size_limit BIGINT NOT NULL,
			attachment_total_size_limit BIGINT NOT NULL,
			attachment_expiry_duration BIGINT NOT NULL,
			attachment_bandwidth_limit BIGINT NOT NULL,
			stripe_monthly_price_id TEXT,
			stripe_yearly_price_id TEXT,
			UNIQUE(code),
			UNIQUE(stripe_monthly_price_id),
			UNIQUE(stripe_yearly_price_id)
		);
		CREATE TABLE IF NOT EXISTS "user" (
		    id TEXT PRIMARY KEY,
			tier_id TEXT REFERENCES tier(id),
			user_name TEXT NOT NULL UNIQUE,
			pass TEXT NOT NULL,
			role TEXT NOT NULL CHECK (role IN ('anonymous', 'admin', 'user')),
			prefs JSONB NOT NULL DEFAULT '{}',
			sync_topic TEXT NOT NULL,
			provisioned BOOLEAN NOT NULL,
			stats_messages BIGINT NOT NULL DEFAULT 0,
			stats_emails BIGINT NOT NULL DEFAULT 0,
			stats_calls BIGINT NOT NULL DEFAULT 0,
			stripe_customer_id TEXT UNIQUE,
			stripe_subscription_id TEXT UNIQUE,
			stripe_subscription_status TEXT,
			stripe_subscription_interval TEXT,
			stripe_subscription_paid_until BIGINT,
			stripe_subscription_cancel_at BIGINT,
			created BIGINT NOT NULL,
			deleted BIGINT
		);
		CREATE TABLE IF NOT EXISTS user_access (
			user_id TEXT NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
			topic TEXT NOT NULL,
			read BOOLEAN NOT NULL,
			write BOOLEAN NOT NULL,
			owner_user_id TEXT REFERENCES "user"(id) ON DELETE CASCADE,
			provisioned BOOLEAN NOT NULL,
			PRIMARY KEY (user_id, topic)
		);
		CREATE TABLE IF NOT EXISTS user_token (
			user_id TEXT NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
			token TEXT NOT NULL UNIQUE,
			label TEXT NOT NULL,
			last_access BIGINT NOT NULL,
			last_origin TEXT NOT NULL,
			expires BIGINT NOT NULL,
			provisioned BOOLEAN NOT NULL,
			PRIMARY KEY (user_id, token)
		);
		CREATE TABLE IF NOT EXISTS user_phone (
			user_id TEXT NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
			phone_number TEXT NOT NULL,
			PRIMARY KEY (user_id, phone_number)
		);
		CREATE TABLE IF NOT EXISTS schema_version (
			store TEXT PRIMARY KEY,
			version INT NOT NULL
		);
		INSERT INTO "user" (id, user_name, pass, role, sync_topic, provisioned, created)
		VALUES ('u_everyone', '*', '', 'anonymous', '', false, EXTRACT(EPOCH FROM NOW())::BIGINT)
		ON CONFLICT (id) DO NOTHING;
		INSERT INTO schema_version (store, version) VALUES ('user', 6) ON CONFLICT (store) DO NOTHING;
		CREATE TABLE IF NOT EXISTS message (
			id BIGSERIAL PRIMARY KEY,
			mid TEXT NOT NULL,
			sequence_id TEXT NOT NULL,
			time BIGINT NOT NULL,
			event TEXT NOT NULL,
			expires BIGINT NOT NULL,
			topic TEXT NOT NULL,
			message TEXT NOT NULL,
			title TEXT NOT NULL,
			priority INT NOT NULL,
			tags TEXT NOT NULL,
			click TEXT NOT NULL,
			icon TEXT NOT NULL,
			actions TEXT NOT NULL,
			attachment_name TEXT NOT NULL,
			attachment_type TEXT NOT NULL,
			attachment_size BIGINT NOT NULL,
			attachment_expires BIGINT NOT NULL,
			attachment_url TEXT NOT NULL,
			attachment_deleted BOOLEAN NOT NULL DEFAULT FALSE,
			sender TEXT NOT NULL,
			user_id TEXT NOT NULL,
			content_type TEXT NOT NULL,
			encoding TEXT NOT NULL,
			published BOOLEAN NOT NULL DEFAULT FALSE
		);
		CREATE INDEX IF NOT EXISTS idx_message_mid ON message (mid);
		CREATE INDEX IF NOT EXISTS idx_message_sequence_id ON message (sequence_id);
		CREATE INDEX IF NOT EXISTS idx_message_topic_published_time ON message (topic, published, time, id);
		CREATE INDEX IF NOT EXISTS idx_message_published_expires ON message (published, expires);
		CREATE INDEX IF NOT EXISTS idx_message_sender_attachment_expires ON message (sender, attachment_expires) WHERE user_id = '';
		CREATE INDEX IF NOT EXISTS idx_message_user_id_attachment_expires ON message (user_id, attachment_expires);
		CREATE TABLE IF NOT EXISTS message_stats (
			key TEXT PRIMARY KEY,
			value BIGINT
		);
		INSERT INTO message_stats (key, value) VALUES ('messages', 0) ON CONFLICT (key) DO NOTHING;
		CREATE TABLE IF NOT EXISTS schema_version (
			store TEXT PRIMARY KEY,
			version INT NOT NULL
		);
		INSERT INTO schema_version (store, version) VALUES ('message', 14) ON CONFLICT (store) DO NOTHING;
		CREATE TABLE IF NOT EXISTS webpush_subscription (
			id TEXT PRIMARY KEY,
			endpoint TEXT NOT NULL UNIQUE,
			key_auth TEXT NOT NULL,
			key_p256dh TEXT NOT NULL,
			user_id TEXT NOT NULL,
			subscriber_ip TEXT NOT NULL,
			updated_at BIGINT NOT NULL,
			warned_at BIGINT NOT NULL DEFAULT 0
		);
		CREATE INDEX IF NOT EXISTS idx_webpush_subscriber_ip ON webpush_subscription (subscriber_ip);
		CREATE INDEX IF NOT EXISTS idx_webpush_updated_at ON webpush_subscription (updated_at);
		CREATE INDEX IF NOT EXISTS idx_webpush_user_id ON webpush_subscription (user_id);
		CREATE TABLE IF NOT EXISTS webpush_subscription_topic (
			subscription_id TEXT NOT NULL REFERENCES webpush_subscription (id) ON DELETE CASCADE,
			topic TEXT NOT NULL,
			PRIMARY KEY (subscription_id, topic)
		);
		CREATE INDEX IF NOT EXISTS idx_webpush_topic ON webpush_subscription_topic (topic);
		CREATE TABLE IF NOT EXISTS schema_version (
			store TEXT PRIMARY KEY,
			version INT NOT NULL
		);
		INSERT INTO schema_version (store, version) VALUES ('webpush', 1) ON CONFLICT (store) DO NOTHING;
-- Remove only the proven blank target seed so source anonymous.created is preserved.
DO $seed$
BEGIN
  IF (SELECT count(*) FROM public."user") <> 1
     OR NOT EXISTS (SELECT 1 FROM public."user" WHERE id='u_everyone' AND user_name='*' AND pass=''
                    AND role='anonymous' AND prefs='{}'::jsonb AND provisioned=false
                    AND sync_topic='' AND stats_messages=0 AND stats_emails=0 AND stats_calls=0) THEN
    RAISE EXCEPTION 'Unexpected ntfy initial seed';
  END IF;
END
$seed$;
DELETE FROM public."user" WHERE id='u_everyone';
COMMIT;
