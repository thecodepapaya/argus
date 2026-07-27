import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from argus.ingestion.rss import _plain_text


class RssSanitizationTests(unittest.TestCase):
    def test_html_feed_fragments_become_plain_readable_text(self):
        value = '<a href="https://example.test">Readable headline</a> <font color="#666">Example source</font>'
        self.assertEqual(_plain_text(value), "Readable headline Example source")
