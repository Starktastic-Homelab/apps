# seerr-telegram-bot

A Telegram bot for Seerr and Seerr-RU requests. Someone sends a title, picks the match, and picks seasons
for a series. If they've signed in to both Seerrs, they then pick which one gets the request; if only
one, they confirm it with a single Request button. The bot files it as that person (`X-API-User`), so
their own permissions, auto-approve and quotas apply. `manifests/bot.py` is standard-library Python,
mounted from a ConfigMap on the stock `python` image. There's no image to build.

## How people are recognised

Each person saves their Telegram chat ID in their own Seerr profile: **Settings > Notifications >
Telegram > Chat ID**. Saving it in one Seerr is enough. Both Seerrs import users from the same Jellyfin, so
the bot finds the same person in the other one by Jellyfin user ID, once they've signed in there (a Jellyfin
user has no Seerr account until their first sign-in). A stranger gets a reply with their
chat ID and nothing else. A chat ID saved by two different people is ignored.

Seerr hides that profile tab unless its Telegram agent is enabled and has a bot username.

## Setup

1. Create the bot with @BotFather (`/newbot`). Keep the token and the bot's username.
2. In both Seerrs, open **Settings > Notifications > Telegram**. Enable it, then enter the bot username,
   the same token, and your own chat ID. Seerr's own status messages ("approved", "available") then
   arrive in the same chat as the bot. Each Seerr notifies only the people who saved their chat ID there.
3. Seal the secret from `manifests/`. Each Seerr's API key is under **Settings > General**.

   ```sh
   ../../../../scripts/seal.sh seerr-telegram-bot-secret media
   TELEGRAM_BOT_TOKEN=...
   SEERR_API_KEY=...
   SEERR_RU_API_KEY=...
   ```

   Press Ctrl+D. It replaces `seerr-telegram-bot-secret.yaml`, which `manifests/kustomization.yaml` already lists.
4. Each person messages the bot, copies the chat ID it replies with into their Seerr profile, and tries again
   a minute later.

## Notes

- Telegram allows one poller per token, so the Deployment is `replicas: 1` with `Recreate`.
- Button state lives in the buttons (`callback_data`), so a restart loses nothing.
- Tests: `python3 -m unittest discover -s services/media/seerr-telegram-bot/manifests` (not in CI).
