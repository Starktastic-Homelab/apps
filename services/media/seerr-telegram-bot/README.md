# seerr-telegram-bot

A Telegram bot for Seerr and Seerr-RU requests. Someone sends a title, picks the match, and picks seasons
for a series. If they've signed in to both Seerrs, they then pick which one gets the request; if only
one, they confirm it with a single Request button. The bot files it as that person (`X-API-User`), so
their own permissions, auto-approve and quotas apply. `manifests/bot.py` is standard-library Python,
mounted from a ConfigMap on the stock `python` image. There's no image to build.

## How people are recognised

The bot reads the Telegram chat ID saved in each person's Seerr profile (**Settings > Notifications >
Telegram > Chat ID**). Both Seerrs import users from the same Jellyfin, so one saved ID is enough: the
bot finds the same person in the other Seerr by Jellyfin user ID, once they've signed in there. A
chat ID saved by two different people is ignored.

A stranger gets two ways in:

- **Link with Jellyfin** (the button): the bot shows a Quick Connect code, the person enters it in
  Jellyfin (profile > Quick Connect) and taps Done. The bot runs Seerr's own Quick Connect sign-in on
  the first Seerr, which creates their Seerr account only if Seerr's "Enable New Jellyfin Sign-In" is on,
  then saves their chat ID in every Seerr they have an account in. Only the first Seerr signs them in:
  a code works once, so Seerr-RU joins when they sign in there themselves. It never replaces a chat
  ID that's already saved: moving an account to another Telegram means clearing it in Seerr first.
- **By hand**: the reply also shows their chat ID to paste into their Seerr profile. Seerr hides that
  profile tab unless its Telegram agent is enabled and has a bot username.

## Setup

1. Create the bot with @BotFather (`/newbot`). Keep the token and the bot's username.
2. Seal the secret from `manifests/`. Each Seerr's API key is under **Settings > General**.

   ```sh
   ../../../../scripts/seal.sh seerr-telegram-bot-secret media
   TELEGRAM_BOT_TOKEN=...
   SEERR_API_KEY=...
   SEERR_RU_API_KEY=...
   ```

   Press Ctrl+D. It replaces `seerr-telegram-bot-secret.yaml`, which `manifests/kustomization.yaml` already lists.
3. Keep Quick Connect on in Jellyfin (**Dashboard > General**), for the Link button.
4. Optional, for Seerr's own status messages ("approved", "available") in the same chat, and for linking
   by hand: in both Seerrs, open **Settings > Notifications > Telegram**, enable it, and enter the bot
   username, the same token and your own chat ID. Each Seerr notifies only people whose chat ID it has
   and who tick Telegram notification types in their profile (none are ticked by default).

## Notes

- Telegram allows one poller per token, so the Deployment is `replicas: 1` with `Recreate`.
- Request buttons carry their state in `callback_data`, so a restart loses nothing. Only a pending
  Quick Connect link lives in memory; its secret is never shown or logged.
- Tests: `python3 -m unittest discover -s services/media/seerr-telegram-bot/manifests` (not in CI).
