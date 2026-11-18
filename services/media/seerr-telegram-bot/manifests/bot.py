"""Telegram bot that files Seerr and Seerr-RU requests as the person asking.

Flow: a title -> pick a match -> (series) pick seasons -> pick a Seerr (only if they use both) -> request.
Strangers link first: a Jellyfin Quick Connect code, or the chat ID saved by hand.

People are recognised by the Telegram chat ID in their own Seerr profile
(Settings > Notifications > Telegram), saved by the Link flow or by hand. Both Seerrs import
users from the same Jellyfin, so the Jellyfin user ID finds the same person in the other one.
Requests carry X-API-User, so each person's own permissions, auto-approve and quotas apply.

Request buttons carry their whole state in callback_data, so a restart loses nothing;
only a pending Quick Connect link lives in memory.
Standard library only: it runs from a ConfigMap on the stock python image.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

MAX_RESULTS = 8
MAX_QUERY = 200
MEDIA_AVAILABLE = 5  # Seerr MediaStatus.AVAILABLE
NOTIFY_APPROVED, NOTIFY_AVAILABLE = 4, 8  # Seerr Notification.MEDIA_APPROVED / MEDIA_AVAILABLE bits
MAX_SEASON_BUTTONS = 90  # Telegram caps a keyboard at 100 buttons
USERS_TTL = 300  # rebuild the Telegram -> Seerr map this often...
MISS_TTL = 60  # ...or this often while unknown people write

TG_API = ""  # set in main(); holds the bot token, so never log it
INSTANCES = []  # [{"name", "url", "key"}], set in main()
_people = {"map": {}, "at": float("-inf")}
_submitted = set()  # (chat, message_id) whose request button was already pressed
# Telegram user ID -> (Quick Connect secret, deadline). The secret signs someone in: never log or show it.
# shortcut: in memory, so a restart mid-link means tapping Link again; fine for a few-minute flow.
_links = {}
LINK_TTL = 540  # Jellyfin forgets a Quick Connect request after 10 minutes

HELP = "Send me the name of a movie or series and I'll request it for you."


class Expired(Exception):
    """A button whose data no longer makes sense."""


class SeerrDown(Exception):
    pass


class NotYet(Exception):
    """Quick Connect code not approved in Jellyfin yet."""


def log(*parts):
    print(*parts, file=sys.stderr, flush=True)


def http(url, body=None, headers=None, timeout=30):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json", **(headers or {})}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as err:
        try:
            return err.code, json.loads(err.read() or b"null")
        except ValueError:
            return err.code, None


def seerr_call(inst, path, headers, body=None):
    try:
        return http(inst["url"] + "/api/v1" + path, body, headers)
    except OSError as err:  # refused, reset, DNS, timeout: Seerr is restarting or gone
        raise SeerrDown(f"{inst['name']}: {type(err).__name__}") from None


def seerr_public(inst, path, body=None):
    """Seerr's own Quick Connect login routes: no key, nobody to act as yet."""
    return seerr_call(inst, path, {}, body)


def seerr_admin(inst, path):
    """Admin-key call. Only for reading the user list: anything else goes through seerr_as."""
    return seerr_call(inst, path, {"X-Api-Key": inst["key"]})


def seerr_as(inst, uid, path, body=None):
    # Without X-API-User the admin key acts as user 1.
    return seerr_call(inst, path, {"X-Api-Key": inst["key"], "X-API-User": str(int(uid))}, body)


def tg(method, **params):
    status, resp = http(TG_API + method, params, timeout=params.get("timeout", 0) + 30)
    if not (resp or {}).get("ok"):
        raise RuntimeError(f"Telegram {method}: HTTP {status} {(resp or {}).get('description')}")
    return resp["result"]


# --- who is asking ---------------------------------------------------------


def list_users(inst):
    skip = 0
    while True:
        status, page = seerr_admin(inst, f"/user?take=100&skip={skip}")
        if status != 200:
            raise SeerrDown(f"{inst['name']} user list: HTTP {status}")
        yield from page["results"]
        skip += 100
        if skip >= page["pageInfo"]["results"]:
            return


def jellyfin_key(value):
    # Seerr's normalizeJellyfinGuid: the same GUID with or without dashes, any case.
    return (value or "").replace("-", "").lower() or None


def build_people():
    """Telegram user ID (str) -> {instance index: Seerr user ID}."""
    claims = {}  # chat ID -> [(instance index, Seerr ID, Jellyfin key)]
    by_jellyfin = [{} for _ in INSTANCES]  # per instance: Jellyfin key -> Seerr ID
    for i, inst in enumerate(INSTANCES):
        for user in list_users(inst):
            jf = jellyfin_key(user.get("jellyfinUserId"))
            if jf:
                by_jellyfin[i][jf] = user["id"]
            status, settings = seerr_admin(inst, f"/user/{user['id']}/settings/notifications")
            chat = str((settings or {}).get("telegramChatId") or "").strip()
            if status == 200 and chat:
                claims.setdefault(chat, []).append((i, user["id"], jf))
    people = {}
    for chat, rows in claims.items():
        # One person may save the ID in both Seerrs; two people saving it is ambiguous.
        if len({jf or (i, uid) for i, uid, jf in rows}) > 1:
            log(f"chat ID {chat} is saved by more than one Seerr user, ignoring it")
            continue
        jf = rows[0][2]
        ids = {i: by_jellyfin[i][jf] for i in range(len(INSTANCES)) if jf in by_jellyfin[i]}
        ids.update({i: uid for i, uid, _ in rows})
        people[chat] = ids
    return people


def person_for(tg_id):
    age = time.monotonic() - _people["at"]
    if age > USERS_TTL or (str(tg_id) not in _people["map"] and age > MISS_TTL):
        try:
            _people["map"] = build_people()
        except SeerrDown as err:
            if not _people["map"]:
                raise
            log(f"{err}; keeping the previous people map")  # one Seerr down must not block the other
        _people["at"] = time.monotonic()
    return _people["map"].get(str(tg_id))


def primary(person):
    i = min(person)
    return INSTANCES[i], person[i]


# --- linking with Jellyfin Quick Connect ------------------------------------
# The bot drives Seerr's own Quick Connect login on the first Seerr: the person approves a code
# in Jellyfin, Seerr signs them in (creating the account only if its new-sign-in setting allows),
# and the bot saves their Telegram ID in their Seerr profiles, which is what build_people reads.
# shortcut: only the first Seerr signs them in (a code works once); Seerr-RU joins when they sign in there.


def link_button():
    return [[button("🔗 Link with Jellyfin", "l")]]


def start_link(tg_id):
    inst = INSTANCES[0]
    status, resp = seerr_public(inst, "/auth/jellyfin/quickconnect/initiate", {})
    if status != 200 or not (resp or {}).get("secret"):
        log(f"{inst['name']} Quick Connect initiate: HTTP {status}")
        return "Jellyfin Quick Connect isn't available right now. Try again later.", link_button()
    now = time.monotonic()
    for stale in [k for k, (_, deadline) in _links.items() if deadline < now]:
        del _links[stale]
    _links[tg_id] = (resp["secret"], now + LINK_TTL)
    return (
        f"In Jellyfin, open your profile, then Quick Connect, and enter this code:\n{resp['code']}\nThen tap Done.",
        [[button("Done", "k")]],
    )


def save_chat_id(inst, uid, tg_id):
    """False if the profile already holds another Telegram ID: a code someone was talked into
    entering must not move their account to a stranger's Telegram."""
    # As the person themselves: Seerr attaches brand-new settings to the caller. The save overwrites
    # every notification field, so send back what is there with only the chat ID changed.
    path = f"/user/{uid}/settings/notifications"
    current = checked(inst, *seerr_as(inst, uid, path))
    saved = str(current.get("telegramChatId") or "").strip()
    if saved and saved != str(tg_id):
        return False
    # Also tick Seerr's "approved" and "available" Telegram notices, added to whatever they ticked.
    # Only here, at link time, so unticking them later in Seerr sticks.
    types = dict(current.get("notificationTypes") or {})
    types["telegram"] = int(types.get("telegram") or 0) | NOTIFY_APPROVED | NOTIFY_AVAILABLE
    checked(inst, *seerr_as(inst, uid, path, {**current, "telegramChatId": str(tg_id), "notificationTypes": types}))
    return True


def finish_link(tg_id):
    secret, deadline = _links.get(tg_id, (None, 0.0))
    if time.monotonic() > deadline:
        _links.pop(tg_id, None)
        return "That code has expired. Tap Link to get a new one.", link_button()
    inst = INSTANCES[0]
    status, resp = seerr_public(inst, "/auth/jellyfin/quickconnect/check?secret=" + urllib.parse.quote(secret, safe=""))
    if status == 200 and not (resp or {}).get("authenticated"):
        raise NotYet
    if status != 200:  # Jellyfin no longer knows the code
        _links.pop(tg_id, None)
        return "That code has expired. Tap Link to get a new one.", link_button()
    status, user = seerr_public(inst, "/auth/jellyfin/quickconnect/authenticate", {"secret": secret})
    _links.pop(tg_id, None)  # a secret signs in once
    if status == 403:
        return f"{inst['name']} has no account for you and won't create one. Ask your Seerr admin to add you.", []
    if status != 200 or "id" not in (user or {}):
        raise SeerrDown(f"{inst['name']} Quick Connect sign-in: HTTP {status}")
    if not save_chat_id(inst, user["id"], tg_id):
        log(f"telegram {tg_id}: {inst['name']} user {user['id']} already has another chat ID, not linked")
        return (
            "Your Seerr account is already linked to another Telegram account. To move it here, clear "
            "the chat ID in your Seerr profile (Settings > Notifications > Telegram), then tap Link again.",
            [],
        )
    jf = jellyfin_key(user.get("jellyfinUserId"))
    for other in INSTANCES[1:]:
        try:  # best effort: only Seerr's own notifications from that Seerr depend on it
            uid = next((u["id"] for u in list_users(other) if jf and jellyfin_key(u.get("jellyfinUserId")) == jf), None)
            if uid is not None and not save_chat_id(other, uid, tg_id):
                log(f"telegram {tg_id}: {other['name']} user {uid} has another chat ID, left as is")
        except SeerrDown as err:
            log(f"{err}; chat ID not saved there")
    log(f"telegram {tg_id} linked to {inst['name']} user {user['id']}")
    try:
        _people["map"], _people["at"] = build_people(), time.monotonic()
    except SeerrDown as err:  # the link is saved; the next message rebuilds the map
        log(err)
        _people["at"] = float("-inf")
        return "✅ Linked. Seerr is slow to answer right now, so send me a title in a minute.", []
    if str(tg_id) not in _people["map"]:
        return "Linked, but another Seerr account has the same chat ID saved. Clear it there, then try again.", []
    name = user.get("displayName") or user.get("jellyfinUsername") or "you"
    return f"✅ Linked as {name}. Now send me a title.", []


# --- Seerr reads ------------------------------------------------------------


def checked(inst, status, body):
    if status != 200:
        raise SeerrDown(f"{inst['name']} answered HTTP {status}")
    return body


def search(ctx, query):
    inst, uid = ctx
    path = "/search?query=" + urllib.parse.quote(query, safe="") + "&page=1"
    results = checked(inst, *seerr_as(inst, uid, path))["results"]
    return [r for r in results if r.get("mediaType") in ("movie", "tv")][:MAX_RESULTS]


def details(ctx, kind, tmdb):
    inst, uid = ctx
    return checked(inst, *seerr_as(inst, uid, ("/movie/" if kind == "m" else "/tv/") + str(tmdb)))


def label(kind, item):
    title = item.get("title") or item.get("name") or "?"
    year = (item.get("releaseDate") or item.get("firstAirDate") or "")[:4]
    return f"{'🎬' if kind == 'm' else '📺'} {title}" + (f" ({year})" if year else "")


def season_numbers(show):
    # Same set Seerr's "all" uses: no specials, no seasons without episodes.
    return [
        s["seasonNumber"]
        for s in show.get("seasons") or []
        if s.get("seasonNumber", 0) > 0 and s.get("episodeCount", 0) > 0
    ]


def picked(numbers, mask):
    return [n for i, n in enumerate(numbers) if mask >> i & 1]


# --- views: each returns (text, keyboard rows) -----------------------------


def button(text, data):
    assert len(data.encode()) <= 64, data  # Telegram's callback_data limit
    return {"text": text, "callback_data": data}


def first_step(result):
    return f"s:{result['id']}:0" if result["mediaType"] == "tv" else f"d:m:{result['id']}:-"


def view_seasons(person, tmdb, mask):
    show = details(primary(person), "t", tmdb)
    numbers = season_numbers(show)
    rows = []
    # shortcut: shows with more seasons than fit on a keyboard only offer "All seasons";
    # page the buttons if someone needs to pick from those.
    if len(numbers) <= MAX_SEASON_BUTTONS:
        buttons = [
            button(("✅ " if mask >> i & 1 else "") + f"S{n}", f"s:{tmdb}:{mask ^ (1 << i):x}")
            for i, n in enumerate(numbers)
        ]
        rows = [buttons[k : k + 5] for k in range(0, len(buttons), 5)]
    last = [button("All seasons", f"d:t:{tmdb}:all")]
    count = len(picked(numbers, mask))
    if count:
        last.append(button(f"Next ▶ ({count})", f"d:t:{tmdb}:{mask:x}"))
    rows.append(last)
    return f"{label('t', show)}\nWhich seasons?", rows


def describe(kind, item, sel):
    text = label(kind, item)
    if kind == "t":
        nums = picked(season_numbers(item), int(sel, 16)) if sel != "all" else None
        text += " — all seasons" if nums is None else " — seasons " + ", ".join(map(str, nums))
    return text


def view_destination(person, kind, tmdb, sel):
    text = describe(kind, details(primary(person), kind, tmdb), sel)
    if len(person) == 1:
        # Only signed in to one Seerr: no picker, but still one tap to confirm the title.
        (i,) = person
        return f"{text}\nRequest this on {INSTANCES[i]['name']}?", [[button("Request", f"r:{kind}:{tmdb}:{sel}:{i}")]]
    rows = [[button(INSTANCES[i]["name"], f"r:{kind}:{tmdb}:{sel}:{i}")] for i in sorted(person)]
    return f"{text}\nSend the request to:", rows


def submit(person, kind, tmdb, sel, i, tg_id):
    if i not in person:
        raise Expired
    inst, uid = INSTANCES[i], person[i]
    item = details((inst, uid), kind, tmdb)
    text = describe(kind, item, sel)
    # Seerr only blocks a repeat movie request while one is open; once completed it would take
    # another. Series are fine: Seerr drops seasons that are already there.
    if kind == "m" and (item.get("mediaInfo") or {}).get("status") == MEDIA_AVAILABLE:
        return f"{text}\n✅ Already available on {inst['name']}.", []
    # is4k must be explicit: Seerr's duplicate checks compare it, and undefined matches nothing.
    body = {"mediaType": "movie" if kind == "m" else "tv", "mediaId": tmdb, "is4k": False}
    if kind == "t":
        body["seasons"] = "all" if sel == "all" else picked(season_numbers(item), int(sel, 16))
    status, resp = seerr_as(inst, uid, "/request", body)
    log(f"telegram {tg_id} as {inst['name']} user {uid}: {body} -> HTTP {status}")
    # Only 201 creates a request; 202 means every season was already requested or available.
    if status == 201:
        state = "approved" if (resp or {}).get("status") == 2 else "waiting for approval"
        return f"{text}\n✅ Requested on {inst['name']}, {state}.", []
    return f"{text}\n❌ {inst['name']}: {(resp or {}).get('message') or f'HTTP {status}'}", []


def route(person, data, tg_id):
    """Callback data -> view.

    s:<tmdb>:<mask>             season picker (mask = hex bitset over season_numbers)
    d:m:<tmdb>:-                destination for a movie
    d:t:<tmdb>:<all|mask>       destination for a series
    r:<as d>:<instance index>   file the request
    """
    if m := re.fullmatch(r"s:(\d+):([0-9a-f]{1,24})", data):
        return view_seasons(person, int(m[1]), int(m[2], 16))
    if m := re.fullmatch(r"([dr]):(m:\d+:-|t:\d+:(?:all|[0-9a-f]{1,24}))(?::(\d))?", data):
        kind, tmdb, sel = m[2].split(":")
        if m[1] == "d" and m[3] is None:
            return view_destination(person, kind, int(tmdb), sel)
        if m[1] == "r" and m[3] is not None:
            return submit(person, kind, int(tmdb), sel, int(m[3]), tg_id)
    raise Expired


# --- Telegram handlers ------------------------------------------------------


def markup(rows):
    return {"inline_keyboard": rows}


def unknown_text(tg_id):
    return (
        "I don't know you yet. Tap Link to connect your Jellyfin account.\n\n"
        "Or save this chat ID in your Seerr profile, under Settings > Notifications > Telegram, "
        f"and message me again in a minute:\n{tg_id}"
    )


def on_message(msg):
    if msg.get("chat", {}).get("type") != "private" or "from" not in msg:
        return  # groups: a saved chat ID could be a group's, so only ever trust from.id in private
    chat, tg_id = msg["chat"]["id"], msg["from"]["id"]
    text = (msg.get("text") or "").strip()[:MAX_QUERY]
    try:
        person = person_for(tg_id)
        if not person:
            return tg("sendMessage", chat_id=chat, text=unknown_text(tg_id), reply_markup=markup(link_button()))
        if not text or text.startswith("/"):
            return tg("sendMessage", chat_id=chat, text=HELP)
        results = search(primary(person), text)
        if not results:
            return tg("sendMessage", chat_id=chat, text=f"Nothing found for “{text}”.")
        if len(results) == 1:
            reply, rows = route(person, first_step(results[0]), tg_id)
        else:
            reply = "Which one did you mean?"
            rows = [[button(label("m" if r["mediaType"] == "movie" else "t", r), first_step(r))] for r in results]
        tg("sendMessage", chat_id=chat, text=reply, reply_markup=markup(rows))
    except SeerrDown as err:
        log(err)
        tg("sendMessage", chat_id=chat, text="Seerr isn't answering right now. Try again later.")


def on_callback(query):
    note, sending = None, None
    try:
        msg = query.get("message") or {}
        if msg.get("chat", {}).get("type") != "private":
            return
        tg_id, data = query["from"]["id"], query.get("data") or ""
        person = person_for(tg_id)
        if data in ("l", "k") and person and tg_id not in _links:
            note = "You're already linked. Send me a title."
            return
        if data in ("l", "k"):
            text, rows = start_link(tg_id) if data == "l" else finish_link(tg_id)
        elif not person:
            note = "I don't know you yet. Send me any message."
            return
        else:
            if data.startswith("r:"):
                # A double tap lands before the first edit removes the buttons; file once.
                sending = (msg["chat"]["id"], msg["message_id"])
                if sending in _submitted:
                    note, sending = "Already sent.", None
                    return
                if len(_submitted) > 1000:  # shortcut: forget old ones wholesale, fine at household volume
                    _submitted.clear()
                _submitted.add(sending)
            text, rows = route(person, data, tg_id)
        tg("editMessageText", chat_id=msg["chat"]["id"], message_id=msg["message_id"], text=text, reply_markup=markup(rows))
    except NotYet:
        note = "Not approved yet. Enter the code in Jellyfin, then tap Done."
    except Expired:
        note = "This button has expired. Send the title again."
    except SeerrDown as err:
        log(err)
        _submitted.discard(sending)  # nothing was filed, so the same button may retry
        note = "Seerr isn't answering right now. Try again later."
    finally:
        tg("answerCallbackQuery", callback_query_id=query["id"], **({"text": note} if note else {}))


def main():
    global TG_API
    TG_API = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/"
    INSTANCES[:] = [
        {"name": name, "url": os.environ[prefix + "_URL"].rstrip("/"), "key": os.environ[prefix + "_API_KEY"]}
        for name, prefix in (("Seerr", "SEERR"), ("Seerr-RU", "SEERR_RU"))
    ]
    offset, delay = 0, 1
    log("polling Telegram")
    while True:
        try:
            updates = tg("getUpdates", offset=offset, timeout=50, allowed_updates=["message", "callback_query"])
            delay = 1
        except Exception as err:  # network or Telegram trouble: back off, never die
            log(f"getUpdates: {type(err).__name__}: {err}")
            time.sleep(delay)
            delay = min(delay * 2, 60)
            continue
        for update in updates:
            offset = update["update_id"] + 1
            try:
                if "message" in update:
                    on_message(update["message"])
                elif "callback_query" in update:
                    on_callback(update["callback_query"])
            except Exception as err:
                log(f"update {update['update_id']}: {type(err).__name__}: {err}")


if __name__ == "__main__":
    main()
