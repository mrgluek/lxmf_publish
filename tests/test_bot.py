import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import feed  # noqa: E402
from database import Database  # noqa: E402

RSS = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Blog</title>
<item><title>Old post</title><link>https://gluek.info/blog/old-post/</link>
<guid isPermaLink="true">https://gluek.info/blog/old-post/</guid><description>Old one</description>
<pubDate>Mon, 20 Oct 2026 10:00:00 GMT</pubDate></item>
<item><title>A project</title><link>https://gluek.info/projects/thing/</link>
<description>Project page</description><pubDate>Wed, 22 Oct 2026 22:05:00 GMT</pubDate></item>
<item><title>No date</title><link>https://example.com/x</link></item>
</channel></rss>"""

NODE = "77777777db2b0274d56ae73fb7518a4a"


class FeedTest(unittest.TestCase):
    def test_parse_sorts_newest_first_and_uses_link_as_guid(self):
        posts = feed.parse(RSS)
        self.assertEqual([p.title for p in posts], ["A project", "Old post", "No date"])
        self.assertEqual(posts[0].guid, "https://gluek.info/projects/thing/")
        self.assertEqual(posts[2].published, 0.0)

    def test_nomadnet_page(self):
        self.assertEqual(feed.nomadnet_page("https://gluek.info/blog/old-post/", NODE),
                         f"{NODE}:/page/blog/old-post.mu")
        self.assertEqual(feed.nomadnet_page("https://gluek.info/projects/thing", NODE),
                         f"{NODE}:/page/projects/thing.mu")
        self.assertIsNone(feed.nomadnet_page("https://example.com/x", NODE))
        self.assertIsNone(feed.nomadnet_page("https://gluek.info/blog/old-post/", ""))

    def test_message_for(self):
        title, content = feed.message_for(feed.parse(RSS)[1], NODE)
        self.assertEqual(title, "Old post")
        self.assertEqual(content, f"Old one\n\nNomadNet: {NODE}:/page/blog/old-post.mu\n"
                                  "Сайт: https://gluek.info/blog/old-post/")


class CommandTest(unittest.TestCase):
    def test_parse_command(self):
        import bot
        self.assertEqual(bot.parse_command("Подписаться"), "sub")
        self.assertEqual(bot.parse_command("  /sub please"), "sub")
        self.assertEqual(bot.parse_command("отписаться"), "unsub")
        self.assertEqual(bot.parse_command("/LAST"), "last")
        self.assertEqual(bot.parse_command("привет"), "help")
        self.assertEqual(bot.parse_command(""), "help")
        self.assertEqual(bot.parse_command(None), "help")


class DatabaseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self.tmp.name, "bot.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_subscribe_cycle(self):
        self.assertTrue(self.db.subscribe("aa"))
        self.assertFalse(self.db.subscribe("aa"))
        self.assertTrue(self.db.is_subscribed("aa"))
        self.assertEqual(self.db.subscribers(), ["aa"])
        self.assertTrue(self.db.unsubscribe("aa"))
        self.assertFalse(self.db.unsubscribe("aa"))
        self.assertEqual(self.db.subscribers(), [])

    def test_seen_posts(self):
        self.assertFalse(self.db.has_seen_any())
        self.db.mark_seen(["a", "b"])
        self.assertTrue(self.db.has_seen_any())
        self.assertEqual(self.db.unseen(["a", "c"]), ["c"])


if __name__ == "__main__":
    unittest.main()
