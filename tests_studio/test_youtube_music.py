"""Music-only enforcement across provider resolution and queue entry points."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from studio.providers import YouTube
from studio.queue import Queue
from studio.settings import Settings
from test_core import track, user


def video(ident="abcdefghijk", category="10"):
    snippet = {"title": "Official Music Video #music", "channelTitle": "Music channel", "channelId": "channel"}
    if category is not None:
        snippet["categoryId"] = category
    return {"id": ident, "snippet": snippet, "contentDetails": {"duration": "PT3M"}, "status": {"embeddable": True}}


class MusicTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = Settings(Path(self.tmp.name) / "settings.json")
        self.settings.save({"block_explicit": False})
        self.youtube = YouTube(Mock(), self.settings)
        self.queue = Queue(Path(self.tmp.name) / "queue.db", self.settings)
        self.addCleanup(lambda: self.queue.db.close())

    async def test_links_require_music_in_both_player_modes(self):
        for mode in ("embedded", "chrome"):
            self.settings.save({"youtube_player_mode": mode})
            for category in ("20", "22", "24", None, "", 10):
                with self.subTest(mode=mode, category=category):
                    self.youtube.api = AsyncMock(return_value={"items": [video(category=category)]})
                    with self.assertRaisesRegex(ValueError, "only accepts.*Music"):
                        await self.youtube.resolve("abcdefghijk")
            self.youtube.api = AsyncMock(return_value={"items": [video()]})
            resolved = await self.youtube.resolve("abcdefghijk")
            self.assertEqual(resolved["youtube_category_id"], "10")

    async def test_search_filters_category_and_rechecks_each_result(self):
        self.youtube.api = AsyncMock(side_effect=[
            {"items": [{"id": {"videoId": "abcdefghijk"}}, {"id": {"videoId": "lmnopqrstuv"}}]},
            {"items": [video(category="20")]}, {"items": [video("lmnopqrstuv")]},
        ])
        results = await self.youtube.search("music")
        self.assertEqual(self.youtube.api.await_args_list[0].args[1]["videoCategoryId"], "10")
        self.assertEqual([r["id"] for r in results], ["lmnopqrstuv"])

    async def test_mixed_playlist_keeps_only_music_in_original_order(self):
        ids = ("abcdefghijk", "lmnopqrstuv", "zyxwvutsrqp")
        self.youtube.api = AsyncMock(side_effect=[
            {"items": [{"contentDetails": {"videoId": i}} for i in ids]},
            {"items": [video(ids[2]), video(ids[1], "24"), video(ids[0])]},
        ])
        self.assertEqual([t["id"] for t in await self.youtube.playlist("playlist")], [ids[0], ids[2]])

    def test_no_role_or_redemption_can_bypass_queue_policy(self):
        invalid = {**track("abcdefghijk", "youtube"), "youtube_category_id": "20"}
        for roles, owner, redemption in ((["viewer"], False, None), (["mod"], False, None), (["broadcaster"], True, None), (["viewer"], False, {"id": "redeem"})):
            with self.subTest(roles=roles, owner=owner, points=redemption is not None):
                with self.assertRaisesRegex(ValueError, "only accepts.*Music"):
                    self.queue.add(invalid, user(), roles, owner=owner, redemption=redemption)
        self.assertEqual(self.queue.state["items"], [])

    def test_approval_and_next_track_reject_non_music(self):
        item = self.queue.add(track("abcdefghijk", "youtube"), user(), ["broadcaster"], owner=True)
        item["track"]["youtube_category_id"] = "24"
        with self.assertRaisesRegex(ValueError, "only accepts.*Music"):
            self.queue.approve(item["id"])
        self.assertIsNone(self.queue.next_item())
        self.assertEqual(item["status"], "blocked")

    def test_saved_unknown_category_is_blocked_without_deleting_request(self):
        item = self.queue.add(track("abcdefghijk", "youtube"), user(), ["broadcaster"], owner=True,
                              redemption={"id": "redeem", "reward_id": "reward"})
        del item["track"]["youtube_category_id"]
        self.queue.save()
        self.queue.db.close()
        self.queue = Queue(Path(self.tmp.name) / "queue.db", self.settings)
        saved = self.queue.state["items"][0]
        self.assertEqual(saved["status"], "blocked")
        self.assertIn("request its link again", saved["reason"])
        self.assertEqual(self.queue.state["settlements"][0]["status"], "CANCELED")
        with self.assertRaises(ValueError):
            self.queue.approve(saved["id"])

    def test_spotify_still_accepted_without_youtube_metadata(self):
        self.assertEqual(self.queue.add(track(), user(), ["broadcaster"], owner=True)["status"], "queued")
