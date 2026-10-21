"""Update the recent blog posts section from the blog's public RSS feed."""

import html
import pathlib
import re
import xml.etree.ElementTree as ET
from datetime import timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.request import Request, urlopen

ROOT = pathlib.Path(__file__).parent.resolve()
RSS_URL = "https://blog.im0o.top/rss.xml"
POST_LIMIT = 5
BLOG_TIMEZONE = timezone(timedelta(hours=8))


class PlainTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        self.parts.append(" ")

    def handle_endtag(self, tag):
        self.parts.append(" ")


def escape_markdown(text: str) -> str:
    text = html.escape(text, quote=False)
    return re.sub(r"([\\`*_{}\[\]])", r"\\\1", text)


def parse_latest_posts(feed: bytes) -> list[str]:
    # The blog emits RSS 2.0, with public posts ordered by publication date.
    items = ET.fromstring(feed).findall("./channel/item")[:POST_LIMIT]
    if not items:
        raise ValueError("RSS feed contains no posts; refusing to clear README")

    lines = []
    for item in items:
        title = " ".join((item.findtext("title") or "").split())
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        if not title or not link or not pub_date:
            raise ValueError("RSS item is missing title, link or pubDate")
        date = parsedate_to_datetime(pub_date)
        if date.tzinfo is None:
            raise ValueError("RSS pubDate is missing its timezone")
        date = date.astimezone(BLOG_TIMEZONE).date().isoformat()
        lines.append(f"- [{escape_markdown(title)}]({link}) - {date}")

        parser = PlainTextParser()
        parser.feed(item.findtext("description") or "")
        parser.close()
        description = " ".join("".join(parser.parts).split())
        if not description or description == "文章描述":
            continue
        if len(description) > 50:
            description = description[:50] + "..."
        lines.append(f"  *{escape_markdown(description)}*")
    return lines


def get_latest_posts() -> list[str]:
    # Cloudflare rejects urllib's default Python-urllib User-Agent.
    request = Request(RSS_URL, headers={
        "User-Agent": "Jz0ojiang-README/1.0 (+https://github.com/jz0ojiang/jz0ojiang)",
    })
    with urlopen(request, timeout=30) as response:
        return parse_latest_posts(response.read())


def replace_chunk(content, marker, chunk, inline=False):
    start = f"<!-- {marker} starts -->"
    end = f"<!-- {marker} ends -->"
    if content.count(start) != 1 or content.count(end) != 1:
        raise ValueError(f"README must contain exactly one {marker} marker pair")
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if not inline:
        chunk = f"\n{chunk}\n"
    rewritten, count = pattern.subn(lambda _: start + chunk + end, content)
    if count != 1:
        raise ValueError(f"README {marker} markers are out of order")
    return rewritten


def update_readme(readme: pathlib.Path) -> None:
    content = readme.read_text(encoding="utf-8")
    latest_posts = "\n\n".join(get_latest_posts())
    rewritten = replace_chunk(content, "latest_posts", latest_posts)
    if rewritten != content:
        readme.write_text(rewritten, encoding="utf-8")


if __name__ == "__main__":
    update_readme(ROOT / "README.md")
