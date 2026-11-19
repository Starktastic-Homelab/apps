# seerr-telegram-bot

A Telegram bot for Seerr and Seerr-RU requests. Someone sends a title, picks the match, and picks seasons
for a series. If they've signed in to both Seerrs, they then pick which one gets the request; if only
one, they confirm it with a single Request button. The bot files it as that person (`X-API-User`), so
their own permissions, auto-approve and quotas apply. `manifests/bot.py` is standard-library Python,
mounted from a ConfigMap on the stock `python` image. There's no image to build.

For a list with posters, type the bot's username and a title in its chat (`@bot dune`), or tap
**🖼 With posters** under a text search. Telegram shows each match with a small poster; picking one posts
it as a TMDB link and the bot carries on from there. This only works in the bot's own chat.

## How people are recognised

The bot reads the Telegram chat ID saved in each person's Seerr profile (**Settings > Notifications >
Telegram > Chat ID**). Both Seerrs import users from the same Jellyfin, so one saved ID is enough: the
bot finds the same person in the other Seerr by Jellyfin user ID, once they've signed in there. A
chat ID saved by two different people is ignored.

A stranger gets two ways in:

- **Link with Jellyfin** (the button): the bot shows a Quick Connect code, the person enters it in
  Jellyfin (profile > Quick Connect) and taps Done. The bot runs Seerr's own Quick Connect sign-in on
  the first Seerr, which creates their Seerr account only if Seerr's "Enable New Jellyfin Sign-In" is on,
  then saves their chat ID in every Seerr they have an account in and ticks Seerr's "approved" and
  "available" Telegram notices there, on top of anything they ticked. Only the first Seerr signs them in:
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
4. For the poster list, turn on inline mode: `/setinline` in @BotFather, pick the bot, and give a placeholder
   such as `Search a title…`. Without it, **🖼 With posters** only types the bot's name into the chat.
5. Optional, for Seerr's own status messages ("approved", "available") in the same chat, and for linking
   by hand: in both Seerrs, open **Settings > Notifications > Telegram**, enable it, and enter the bot
   username and the same token. Each Seerr notifies only people whose chat ID it has and who have
   Telegram notification types ticked in their profile: linking ticks "approved" and "available", people
   who link by hand tick them themselves (Seerr ticks none by default). The agent's own Chat ID is only
   for admin-wide alerts; Seerr skips a person's notices when their chat ID equals it.

## Notes

- Telegram allows one poller per token, so the Deployment is `replicas: 1` with `Recreate`.
- Request buttons carry their state in `callback_data`, so a restart loses nothing. Only a pending
  Quick Connect link lives in memory; its secret is never shown or logged.
- Posters are TMDB image URLs (`image.tmdb.org`); Telegram fetches them, the pod downloads nothing.
- Tests: `python3 -m unittest discover -s services/media/seerr-telegram-bot/manifests` (not in CI).
