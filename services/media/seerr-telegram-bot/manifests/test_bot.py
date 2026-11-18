"""Offline tests for bot.py: python3 -m unittest discover -s services/media/seerr-telegram-bot/manifests"""

import os
import re
import sys
import unittest
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bot  # noqa: E402

MAIN, RU = "http://seerr", "http://ru"
BEN_JF, ANN_JF, X_JF, Y_JF = ("%032x" % n for n in (0xBE, 0xA, 0xC, 0xD))
USERS = {  # (id, Jellyfin ID, saved Telegram chat ID)
    MAIN: [(5, BEN_JF, "111"), (6, ANN_JF, None), (7, X_JF, "333")],
    # Seerr-RU holds Ben's GUID dashed and upper-case: still the same person.
    RU: [(9, "-".join((BEN_JF[:8].upper(), BEN_JF[8:])), None), (3, None, "222"), (4, Y_JF, "333"), (10, ANN_JF, "")],
}
SHOW = {
    "name": "Breaking Bad",
    "firstAirDate": "2008-01-20",
    "seasons": [{"seasonNumber": n, "episodeCount": 0 if n == 4 else 7} for n in range(5)],
}
MOVIE = {"title": "The Matrix", "releaseDate": "1999-03-31"}
BEN = {0: 5, 1: 9}


class Fake:
    def __init__(self):
        self.seerr, self.telegram = [], []
        self.search = [{"mediaType": "movie", "id": 603, **MOVIE}, {"mediaType": "tv", "id": 1396, **SHOW}]
        self.show = SHOW
        self.request_reply = (201, {"status": 1})
        self.movie = MOVIE
        self.down = set()

    def __call__(self, url, body=None, headers=None, timeout=30):
        if url.startswith("TG/"):
            self.telegram.append((url[3:], body))
            return 200, {"ok": True, "result": True}
        base, path = url.split("/api/v1", 1)
        self.seerr.append((base, path, body, headers))
        if base in self.down:
            raise urllib.error.URLError("connection refused")
        users = USERS[base]
        if path.startswith("/user?"):
            return 200, {"pageInfo": {"results": len(users)}, "results": [{"id": u, "jellyfinUserId": jf} for u, jf, _ in users]}
        if m := re.fullmatch(r"/user/(\d+)/settings/notifications", path):
            return 200, {"telegramChatId": next(c for u, _, c in users if u == int(m[1]))}
        if path.startswith("/search?"):
            return 200, {"results": self.search + [{"mediaType": "person", "id": 1, "name": "Keanu"}]}
        if re.fullmatch(r"/tv/\d+", path):
            return 200, self.show
        if path == "/movie/603":
            return 200, self.movie
        if path == "/request":
            return self.request_reply
        raise AssertionError(path)


def private(tg_id, **extra):
    return {"chat": {"id": tg_id, "type": "private"}, "from": {"id": tg_id}, **extra}


def buttons(rows):
    return [(b["text"], b["callback_data"]) for row in rows for b in row]


class BotTest(unittest.TestCase):
    def setUp(self):
        self.fake = Fake()
        bot.http = self.fake
        bot.TG_API = "TG/"
        bot.INSTANCES[:] = [{"name": "Seerr", "url": MAIN, "key": "k0"}, {"name": "Seerr-RU", "url": RU, "key": "k1"}]
        bot._people.update(map={}, at=float("-inf"))
        bot._submitted.clear()

    def tearDown(self):
        # The admin key acts as user 1 unless X-API-User is set: only the user scan may omit it.
        for _, path, _, headers in self.fake.seerr:
            if not path.startswith("/user"):
                self.assertIn("X-API-User", headers, path)

    def test_people_are_matched_across_both_seerrs(self):
        # 111: saved in Seerr, found in Seerr-RU by Jellyfin ID. 222: local Seerr-RU user.
        # 333: saved by two different people, so nobody gets it.
        self.assertEqual(bot.build_people(), {"111": BEN, "222": {1: 3}})

    def test_unknown_person_gets_their_id_and_nothing_else(self):
        bot.on_message(private(999, text="matrix"))
        (method, body), = self.fake.telegram
        self.assertEqual(method, "sendMessage")
        self.assertIn("999", body["text"])
        self.assertTrue(all(path.startswith("/user") for _, path, _, _ in self.fake.seerr))

    def test_groups_are_ignored(self):
        bot.on_message({"chat": {"id": -5, "type": "group"}, "from": {"id": 111}, "text": "matrix"})
        self.assertEqual((self.fake.telegram, self.fake.seerr), ([], []))

    def test_several_matches_ask_which_one(self):
        bot.on_message(private(111, text="the matrix!"))
        (_, body), = self.fake.telegram
        self.assertEqual(body["text"], "Which one did you mean?")
        self.assertEqual(
            buttons(body["reply_markup"]["inline_keyboard"]),
            [("🎬 The Matrix (1999)", "d:m:603:-"), ("📺 Breaking Bad (2008)", "s:1396:0")],
        )
        search = next(p for _, p, _, _ in self.fake.seerr if p.startswith("/search"))
        self.assertEqual(search, "/search?query=the%20matrix%21&page=1")

    def test_one_match_skips_to_seasons(self):
        self.fake.search = self.fake.search[1:]
        bot.on_message(private(111, text="breaking bad"))
        (_, body), = self.fake.telegram
        self.assertEqual(body["text"], "📺 Breaking Bad (2008)\nWhich seasons?")
        # no specials, no season without episodes, nothing picked yet so no Next
        self.assertEqual(
            buttons(body["reply_markup"]["inline_keyboard"]),
            [("S1", "s:1396:1"), ("S2", "s:1396:2"), ("S3", "s:1396:4"), ("All seasons", "d:t:1396:all")],
        )

    def test_toggling_a_season(self):
        _, rows = bot.route(BEN, "s:1396:2", 111)
        self.assertEqual(
            buttons(rows),
            [("S1", "s:1396:3"), ("✅ S2", "s:1396:0"), ("S3", "s:1396:6"), ("All seasons", "d:t:1396:all"), ("Next ▶ (1)", "d:t:1396:2")],
        )

    def test_picker_when_they_use_both_seerrs(self):
        text, rows = bot.route(BEN, "d:t:1396:6", 111)
        self.assertEqual(text, "📺 Breaking Bad (2008) — seasons 2, 3\nSend the request to:")
        self.assertEqual(buttons(rows), [("Seerr", "r:t:1396:6:0"), ("Seerr-RU", "r:t:1396:6:1")])

    def test_one_seerr_only_confirms(self):
        text, rows = bot.route({1: 3}, "d:m:603:-", 222)
        self.assertEqual(text, "🎬 The Matrix (1999)\nRequest this on Seerr-RU?")
        self.assertEqual(buttons(rows), [("Request", "r:m:603:-:1")])

    def test_request_picked_seasons_as_the_person(self):
        text, rows = bot.route(BEN, "r:t:1396:6:1", 111)
        base, _, body, headers = self.fake.seerr[-1]
        self.assertEqual((base, body, headers["X-API-User"]), (RU, {"mediaType": "tv", "mediaId": 1396, "is4k": False, "seasons": [2, 3]}, "9"))
        self.assertEqual(text, "📺 Breaking Bad (2008) — seasons 2, 3\n✅ Requested on Seerr-RU, waiting for approval.")
        self.assertEqual(rows, [])

    def test_all_seasons_already_there(self):
        self.fake.request_reply = (202, {"message": "No seasons available to request"})
        text, _ = bot.route(BEN, "r:t:1396:all:0", 111)
        self.assertEqual(self.fake.seerr[-1][2]["seasons"], "all")
        self.assertEqual(text, "📺 Breaking Bad (2008) — all seasons\n❌ Seerr: No seasons available to request")

    def test_movie_auto_approved(self):
        self.fake.request_reply = (201, {"status": 2})
        text, _ = bot.route(BEN, "r:m:603:-:0", 111)
        self.assertEqual(self.fake.seerr[-1][2], {"mediaType": "movie", "mediaId": 603, "is4k": False})
        self.assertEqual(text, "🎬 The Matrix (1999)\n✅ Requested on Seerr, approved.")

    def test_bad_buttons_expire(self):
        for data in ("", "x", "r:t:1396:zz:0", "r:m:603:all:0", "d:t:1396:-", "d:m:603:-:0", "r:t:1396:all:1"):
            with self.subTest(data=data), self.assertRaises(bot.Expired):
                bot.route({0: 5}, data, 111)

    def test_expired_button_is_answered(self):
        bot.on_callback({"id": "q1", "from": {"id": 111}, "data": "nope", "message": private(111, message_id=7)})
        self.assertEqual(self.fake.telegram, [("answerCallbackQuery", {"callback_query_id": "q1", "text": "This button has expired. Send the title again."})])

    def test_season_buttons_fit_telegram_limits(self):
        many = lambda n: {**SHOW, "seasons": [{"seasonNumber": s, "episodeCount": 1} for s in range(1, n + 1)]}  # noqa: E731
        self.fake.show = many(bot.MAX_SEASON_BUTTONS)
        _, rows = bot.route(BEN, f"s:9999999:{(1 << bot.MAX_SEASON_BUTTONS) - 1:x}", 111)  # button() asserts <= 64 bytes
        self.assertLessEqual(sum(map(len, rows)), 100)
        self.fake.show = many(bot.MAX_SEASON_BUTTONS + 1)
        _, rows = bot.route(BEN, "s:1396:0", 111)
        self.assertEqual(buttons(rows), [("All seasons", "d:t:1396:all")])


    def test_available_movie_is_not_requested_again(self):
        self.fake.movie = {**MOVIE, "mediaInfo": {"status": bot.MEDIA_AVAILABLE}}
        text, _ = bot.route(BEN, "r:m:603:-:1", 111)
        self.assertEqual(text, "🎬 The Matrix (1999)\n✅ Already available on Seerr-RU.")
        self.assertNotIn("/request", [p for _, p, _, _ in self.fake.seerr])

    def test_unreachable_seerr_gets_a_reply(self):
        bot._people.update(map=bot.build_people(), at=bot.time.monotonic())  # known, then Seerr goes away
        self.fake.down.add(MAIN)
        bot.on_message(private(111, text="matrix"))
        self.assertEqual(self.fake.telegram[-1][1]["text"], "Seerr isn't answering right now. Try again later.")

    def test_one_seerr_down_keeps_the_known_people(self):
        bot._people["map"] = bot.build_people()
        self.fake.down.add(RU)
        self.assertEqual(bot.person_for(111), BEN)  # rebuild failed, previous map kept

    def test_double_tap_files_once(self):
        tap = {"id": "q", "from": {"id": 111}, "data": "r:m:603:-:0", "message": private(111, message_id=7)}
        bot.on_callback(tap)
        bot.on_callback(tap)
        self.assertEqual([p for _, p, _, _ in self.fake.seerr].count("/request"), 1)
        self.assertEqual(self.fake.telegram[-1], ("answerCallbackQuery", {"callback_query_id": "q", "text": "Already sent."}))


class LoopTest(unittest.TestCase):
    def test_a_failing_update_is_skipped_not_retried(self):
        polls, handled = [], []

        def tg(method, **params):
            polls.append(params["offset"])
            if len(polls) == 1:
                return [{"update_id": 41, "message": "boom"}, {"update_id": 42, "message": "ok"}]
            raise SystemExit  # stop the endless loop

        def on_message(msg):
            handled.append(msg)
            if msg == "boom":
                raise RuntimeError("handler bug")

        env = {"TELEGRAM_BOT_TOKEN": "t", "SEERR_URL": "a/", "SEERR_API_KEY": "k", "SEERR_RU_URL": "b", "SEERR_RU_API_KEY": "k"}
        saved = bot.tg, bot.on_message, dict(os.environ)
        bot.tg, bot.on_message = tg, on_message
        os.environ.update(env)
        try:
            with self.assertRaises(SystemExit):
                bot.main()
        finally:
            bot.tg, bot.on_message = saved[0], saved[1]
            os.environ.clear()
            os.environ.update(saved[2])
        self.assertEqual((handled, polls), (["boom", "ok"], [0, 43]))
        self.assertEqual([i["url"] for i in bot.INSTANCES], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
