"""RSS feed of the blog: parsing and turning posts into LXMF messages."""
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

USER_AGENT = "lxmf_publish (+https://gluek.info)"


@dataclass
class Post:
    guid: str
    title: str
    link: str
    description: str
    published: float  # unix time, 0 if the feed has no date


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def parse(xml_bytes):
    """Posts from an RSS 2.0 document, newest first."""
    posts = []
    for item in ET.fromstring(xml_bytes).iter("item"):
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or link).strip()
        if not guid:
            continue
        try:
            published = parsedate_to_datetime(item.findtext("pubDate")).timestamp()
        except (TypeError, ValueError):
            published = 0.0
        posts.append(Post(
            guid=guid,
            title=(item.findtext("title") or "").strip(),
            link=link,
            description=(item.findtext("description") or "").strip(),
            published=published,
        ))
    return sorted(posts, key=lambda p: p.published, reverse=True)


def nomadnet_page(link, node_hash):
    """https://gluek.info/blog/<slug>/ → <node>:/page/blog/<slug>.mu, or None for other links."""
    m = re.match(r"^https?://[^/]+/(blog|projects)/([^/?#]+)/?$", link)
    if not m or not node_hash:
        return None
    return f"{node_hash}:/page/{m.group(1)}/{m.group(2)}.mu"


def message_for(post, node_hash):
    """(title, content) of the LXMF message announcing a post."""
    lines = []
    if post.description:
        lines += [post.description, ""]
    page = nomadnet_page(post.link, node_hash)
    if page:
        lines.append(f"NomadNet: {page}")
    if post.link:
        lines.append(f"Сайт: {post.link}")
    return post.title, "\n".join(lines).strip()
