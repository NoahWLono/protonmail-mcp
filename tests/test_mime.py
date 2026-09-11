from email import policy
from email.parser import BytesParser

from protonmail_mcp.mime import (
    decode_header_value,
    decode_imap_utf7,
    encode_imap_utf7,
    extract_body_text,
    html_to_text,
)


def test_imap_utf7_round_trip() -> None:
    names = ["INBOX", "Receipts & Travel", "日本語", "Café/Été", "A&B"]
    for name in names:
        assert decode_imap_utf7(encode_imap_utf7(name)) == name


def test_decode_rfc2047_header() -> None:
    assert decode_header_value("=?utf-8?b?Q2Fmw6k=?=") == "Café"


def test_prefers_plain_text_over_html() -> None:
    raw = b"""\
MIME-Version: 1.0\r
Content-Type: multipart/alternative; boundary=x\r
\r
--x\r
Content-Type: text/plain; charset=utf-8\r
\r
Hello plain\r
--x\r
Content-Type: text/html; charset=utf-8\r
\r
<b>Hello html</b>\r
--x--\r
"""
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    body, truncated = extract_body_text(msg, 1000)
    assert body == "Hello plain"
    assert truncated is False


def test_html_to_text_ignores_script() -> None:
    assert html_to_text("<p>Hello</p><script>steal()</script><p>World</p>") == "Hello\n\nWorld"
