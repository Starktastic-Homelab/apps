# ADR 0021: Authentik login pages and mails match the dashboards

- **Status:** Accepted
- **Date:** 2026-11-14

## Context

The dashboards moved to "liquid glass" on an aurora (ADR 0020) and the mark became a sigma (#1612). The
Authentik login pages and mails still carried the old identity: a crimson theme, a grid with red circuit lines,
and a mail header typed as white and red words. Red is now reserved for errors and alarms.

Authentik is on chart 2026.8.5. Read from its source and docs at that tag:

- Brand CSS reaches every Authentik interface (login, user settings, admin), not only the login pages. The
  documented hooks are CSS variables and `::part()`; `ak-flow-executor` exposes `main`, `branding` and `footer`.
  Class selectors still match because the CSS is also copied into each component, a path the source marks as
  deprecated. The `--ak-accent-50…900` ramp the old theme set no longer exists.
- Our `templates/base.html` replaces Authentik's own `email/base.html`, so built-in mails (event notifications,
  admin-sent invitations) inherit it. They set dark text inline.
- Uploaded media is served through short-lived signed links, so a mail cannot point at a picture there. A mail
  whose body contains `cid:logo` gets `web/dist/assets/icons/icon_left_brand.png` attached inline.
- A `.txt` file beside a mail template becomes the mail's plain-text part. Ours had none.

## Decision

1. **Look.** Login pages use the household dashboard's tokens: brand blue `#3B82F6` on navy `#0F0F1A`, its
   aurora still as the background, a glass card, and red only for errors. Mails use the same colours as solid
   fills, because mail clients have no blur or transparency.
2. **Name.** The title stays `Starktastic Services` (browser tab, mail footer, invitation text, welcome
   subject). The logo is the mark beside the one word `Starktastic`.
3. **Wordmark.** In `branding/logo.svg` the word is outlined from Manrope ExtraBold, the dashboards' typeface,
   so it looks the same on every device. A comment in the file records how it was traced.
4. **Login CSS, by hook.**
   - Nothing is set on `:root`. With the crimson rules gone, the admin and user interfaces show Authentik's own
     blue.
   - Everything glass is set on `ak-flow-executor`, through its parts and through variables it passes down, so
     only login pages change. `body:has(ak-flow-executor)` puts the aurora on phones too, where Authentik
     shows no picture.
   - Rules that need a class inside a component sit in a `no-hook` block, inside a container style query on a
     variable only `ak-flow-executor` sets. If an upgrade stops them matching, or a browser has no style
     queries, fields and buttons keep Authentik's own shapes with a solid blue button.
5. **Mail mark.** A 96 px PNG of the mark (`branding/mail-mark.png`) is mounted over Authentik's stock mail
   logo and referenced as `cid:logo`, so it travels inside each mail. The wordmark beside it is live text.
6. **Mail HTML.** Tables and inline styles carry everything a mail needs; the `<style>` block holds extras
   only, among them a light text colour for built-in mails. No `bgcolor` attributes, so a client that drops all
   CSS shows dark text on white. Each of the three mails gets a `.txt` twin.

## Rationale

- **CSS on documented hooks only.** Safest across upgrades, but fields and buttons sit inside nested components
  with no parts: they would keep Authentik's stock shapes inside a glass card.
- **Class selectors everywhere, as before.** Least work, but all of it rides the deprecated path, and it
  restyles the admin and user interfaces as well; glass fields on a light theme would be unreadable.
- **Chosen: hooks for the frame, a marked block for the inner controls.** The same rule as ADR 0020: what must
  not break stands on stable hooks, and what can only break cosmetically is fenced and named.
- **Mail mark:** a hosted picture has no fixed address on Authentik; a letter σ in a drawn tile renders
  everywhere but is each device's font, not the mark. An attached picture is the exact mark and needs no
  "load images" click.

## Consequences

- The mount shadows one file inside the Authentik image. If an upgrade moves that file, mails show Authentik's
  logo until the mount path is fixed; nothing else breaks.
- A wordmark change means tracing the word again.
- Some mail clients show the attached mark as a paperclip. Outlook for Windows squares rounded corners and
  drops the header glow.
- Built-in mails are readable only where the client keeps `<style>` blocks. No built-in mail is configured in
  Git today.
- Nothing in CI renders the login pages or the mails. They were checked by hand on a throwaway Authentik
  2026.8.5: sign-in, a wrong password, sign-up and recovery, with the three mails caught by a local mail sink.
  After an Authentik upgrade, look at the login page. Real mail clients are not tested.
- Authentik draws a field's error icon as a background image, so the block sets `background-color`, never the
  `background` shorthand, which would tile the icon across the field.
- The mails are still sent as "Ben Plus".
