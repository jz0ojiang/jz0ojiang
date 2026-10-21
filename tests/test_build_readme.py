import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from build_readme import (
    RSS_URL,
    get_latest_posts,
    parse_latest_posts,
    replace_chunk,
    update_readme,
)


def make_feed(posts):
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    for post in posts:
        item = ET.SubElement(channel, "item")
        for key, value in post.items():
            ET.SubElement(item, key).text = value
    return ET.tostring(rss, encoding="utf-8")


def make_post(**overrides):
    return {
        "title": "最新文章",
        "link": "https://blog.im0o.top/posts/example",
        "pubDate": "Mon, 30 Mar 2026 16:37:45 GMT",
        "description": "文章摘要",
        **overrides,
    }


class LatestPostsTests(unittest.TestCase):
    def test_reads_rss_and_uses_blog_timezone(self):
        self.assertEqual(
            parse_latest_posts(make_feed([make_post()])),
            [
                "- [最新文章](https://blog.im0o.top/posts/example) - 2026-03-31",
                "  *文章摘要*",
            ],
        )

    def test_limits_to_five_posts_in_feed_order(self):
        posts = [make_post(title=f"文章 {i}") for i in range(7)]
        links = parse_latest_posts(make_feed(posts))[::2]
        self.assertEqual(len(links), 5)
        for i, link in enumerate(links):
            self.assertIn(f"[文章 {i}]", link)

    def test_missing_empty_and_placeholder_descriptions_are_omitted(self):
        missing = make_post()
        del missing["description"]
        for post in [missing, make_post(description=""), make_post(description="文章描述")]:
            with self.subTest(post=post):
                self.assertEqual(len(parse_latest_posts(make_feed([post]))), 1)

    def test_normalizes_html_entities_and_whitespace(self):
        post = make_post(description="<p>第一行<br/>第二行</p>\n<p>A &amp; B</p>")
        self.assertEqual(
            parse_latest_posts(make_feed([post]))[1],
            "  *第一行 第二行 A &amp; B*",
        )

    def test_truncates_long_descriptions(self):
        lines = parse_latest_posts(make_feed([make_post(description="长" * 51)]))
        self.assertEqual(lines[1], "  *" + "长" * 50 + "...*")

    def test_escapes_markdown_and_raw_html(self):
        lines = parse_latest_posts(make_feed([
            make_post(title="[版本] *发布* <预览>", description="带 [release/v1] 和 *星号*"),
        ]))
        self.assertIn(r"\[版本\] \*发布\* &lt;预览&gt;", lines[0])
        self.assertEqual(lines[1], r"  *带 \[release/v1\] 和 \*星号\**")

    def test_rejects_empty_or_invalid_feed(self):
        for feed in [make_feed([]), b"<html>Not a feed</html>"]:
            with self.subTest(feed=feed), self.assertRaises(ValueError):
                parse_latest_posts(feed)
        with self.assertRaises(ET.ParseError):
            parse_latest_posts(b"not XML")

    def test_rejects_missing_required_fields_and_invalid_dates(self):
        for field in ["title", "link", "pubDate"]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                parse_latest_posts(make_feed([make_post(**{field: ""})]))
        for date in ["invalid", "Mon, 30 Mar 2026 16:37:45"]:
            with self.subTest(date=date), self.assertRaises(ValueError):
                parse_latest_posts(make_feed([make_post(pubDate=date)]))

    @patch("build_readme.urlopen")
    def test_fetches_public_rss_with_timeout(self, urlopen):
        urlopen.return_value.__enter__.return_value.read.return_value = make_feed([make_post()])
        self.assertEqual(len(get_latest_posts()), 2)
        urlopen.assert_called_once()
        args, kwargs = urlopen.call_args
        self.assertEqual(args[0].full_url, RSS_URL)
        self.assertEqual(
            args[0].get_header("User-agent"),
            "Jz0ojiang-README/1.0 (+https://github.com/jz0ojiang/jz0ojiang)",
        )
        self.assertEqual(kwargs, {"timeout": 30})


class ReadmeTests(unittest.TestCase):
    CONTENT = "before\n<!-- latest_posts starts -->\nold\n<!-- latest_posts ends -->\nafter\n"

    def test_replaces_only_marked_section_and_preserves_backslashes(self):
        chunk = r"new \1 \[release\]"
        self.assertEqual(
            replace_chunk(self.CONTENT, "latest_posts", chunk),
            self.CONTENT.replace("\nold\n", f"\n{chunk}\n"),
        )

    def test_rejects_missing_duplicate_or_reversed_markers(self):
        for content in ["no markers", self.CONTENT * 2,
                        "<!-- latest_posts ends --><!-- latest_posts starts -->"]:
            with self.subTest(content=content), self.assertRaises(ValueError):
                replace_chunk(content, "latest_posts", "new")

    @patch("build_readme.get_latest_posts", return_value=["- new post", "  *summary*"])
    def test_update_is_idempotent(self, get_posts):
        with tempfile.TemporaryDirectory() as directory:
            readme = Path(directory) / "README.md"
            readme.write_text(self.CONTENT, encoding="utf-8")
            update_readme(readme)
            expected = self.CONTENT.replace("\nold\n", "\n- new post\n\n  *summary*\n")
            self.assertEqual(readme.read_text(encoding="utf-8"), expected)
            with patch.object(Path, "write_text") as write:
                update_readme(readme)
                write.assert_not_called()

    def test_fetch_failures_leave_readme_unchanged(self):
        errors = [HTTPError(RSS_URL, 503, "Unavailable", {}, None),
                  ValueError("empty feed"), ET.ParseError("bad XML")]
        with tempfile.TemporaryDirectory() as directory:
            readme = Path(directory) / "README.md"
            readme.write_text(self.CONTENT, encoding="utf-8")
            for error in errors:
                with self.subTest(error=error), patch("build_readme.get_latest_posts", side_effect=error):
                    with self.assertRaises(type(error)):
                        update_readme(readme)
                    self.assertEqual(readme.read_text(encoding="utf-8"), self.CONTENT)


if __name__ == "__main__":
    unittest.main()
