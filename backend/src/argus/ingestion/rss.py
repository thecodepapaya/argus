"""Small, dependency-free RSS/Atom metadata collector used by ARGUS."""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _plain_text(value: str) -> str:
    """Convert RSS HTML/CDATA fragments into safe, readable display text."""
    parser = _TextExtractor()
    parser.feed(unescape(value))
    parser.close()
    return " ".join(" ".join(parser.parts).split())


def _text(element, names: tuple[str, ...]) -> str:
    for name in names:
        found = element.find(name)
        if found is not None and found.text:
            return _plain_text(found.text)
    return ""


def _parse_date(value: str) -> str:
    if not value:
        return datetime.now(UTC).isoformat()
    try:
        return parsedate_to_datetime(value).astimezone(UTC).isoformat()
    except (TypeError, ValueError):
        return datetime.now(UTC).isoformat()


def fetch_rss(url: str, source_name: str = "RSS source", limit: int = 30) -> list[dict]:
    """Fetch a permitted RSS or Atom feed and return canonical document candidates.

    Caller is responsible for adding approved feeds to the source registry. Requests
    use conservative limits so this adapter is safe for local collection.
    """
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ValueError("Only absolute HTTP(S) feed URLs are accepted")
    request = Request(url, headers={"User-Agent": "ARGUS/0.5 (public metadata research)"})
    with urlopen(request, timeout=12) as response:  # nosec B310: scheme is allow-listed above
        body = response.read(1_500_000)
    root = ElementTree.fromstring(body)
    items = root.findall(".//item")
    atom_entries = root.findall("{http://www.w3.org/2005/Atom}entry")
    records = []
    for item in (items or atom_entries)[:limit]:
        atom = item.tag.endswith("entry")
        title = _text(item, ("title", "{http://www.w3.org/2005/Atom}title"))
        link = _text(item, ("link",))
        if atom:
            link_element = item.find("{http://www.w3.org/2005/Atom}link")
            link = link_element.get("href", "") if link_element is not None else ""
        if not title or not link:
            continue
        records.append({
            "id": f"rss:{source_name}:{link}", "source": source_name, "source_class": "established_technical_press",
            "title": title, "url": link,
            "published_at": _parse_date(_text(item, ("pubDate", "published", "updated", "{http://www.w3.org/2005/Atom}published", "{http://www.w3.org/2005/Atom}updated"))),
            "excerpt": _text(item, ("description", "summary", "{http://www.w3.org/2005/Atom}summary"))[:500],
            "retrieved_at": datetime.now(UTC).isoformat(),
        })
    return records
