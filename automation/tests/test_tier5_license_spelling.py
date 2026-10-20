"""#370: customer copy uses American license; identifiers keep their spelling."""

import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

from config import DESKTOP_DIR, SERVER_DIR, WEBSITE_DIR


BAD_SPELLING = re.compile(r"licence|licencing", re.IGNORECASE)


def assert_american(copy, source):
    assert not BAD_SPELLING.search(copy), f"{source}: use American license: {copy}"


class CustomerHTML(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.source = source
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        attrs = dict(attrs)
        for name in ("title", "alt", "aria-label", "placeholder"):
            assert_american(attrs.get(name) or "", self.source)
        if tag == "meta" and (attrs.get("name") or "").lower() == "description":
            assert_american(attrs.get("content") or "", self.source)

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            assert_american(data, self.source)


def test_xaml_customer_text_uses_american_license():
    attributes = {"Text", "Content", "Header", "ToolTip", "Title",
                  "AutomationProperties.Name", "AutomationProperties.HelpText"}
    for path in Path(DESKTOP_DIR).rglob("*.xaml"):
        if {"bin", "obj"} & set(path.parts):
            continue
        for element in ET.parse(path).iter():
            for name, value in element.attrib.items():
                if name in attributes and not value.startswith("{"):
                    assert_american(value, path)
            if element.text and element.text.strip():
                assert_american(element.text, path)
            if element.tail and element.tail.strip():
                assert_american(element.tail, path)


def test_site_html_customer_text_uses_american_license():
    for path in Path(WEBSITE_DIR).rglob("*.html"):
        CustomerHTML(path).feed(path.read_text(encoding="utf-8-sig"))


def test_email_subject_and_bodies_use_american_license():
    # Render the real template: comments, JS identifiers and JSON keys aren't copy.
    script = """
const { licenseEmail } = require('./email');
console.log(JSON.stringify(licenseEmail({
  licenseKey: 'TEST-KEY', email: 'customer@example.test', status: 'active'
})));
"""
    result = subprocess.run([shutil.which("node") or "node", "-e", script],
                            cwd=SERVER_DIR, capture_output=True, encoding="utf-8",
                            check=True, timeout=60)
    message = json.loads(result.stdout)
    for field in ("subject", "text", "html"):
        assert_american(message[field], f"email {field}")
