from __future__ import annotations

from contextlib import contextmanager

from protonmail_mcp.config import Settings
from protonmail_mcp.imap_client import ProtonBridgeClient


class FakeIMAP:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def select(self, mailbox: str, readonly: bool = False):
        self.calls.append(("select", mailbox, readonly))
        return "OK", [b"1"]

    def uid(self, command: str, *args):
        self.calls.append(("uid", command, *args))
        if command == "SEARCH":
            return "OK", [b"42"]
        if command == "FETCH" and "HEADER.FIELDS" in str(args[-1]):
            header = (
                b"Subject: Test\r\nFrom: Alice <alice@example.com>\r\n"
                b"To: Bob <bob@example.com>\r\nDate: Thu, 10 Sep 2026 12:00:00 -0400\r\n"
                b"Message-ID: <x@example.com>\r\n\r\n"
            )
            return "OK", [(b"42 (RFC822.SIZE 500 {150}", header), b")"]
        if command == "FETCH" and "BODY.PEEK[TEXT]" in str(args[-1]):
            return "OK", [(b"42 (BODY[TEXT] {5}", b"hello"), b")"]
        if command == "FETCH" and str(args[-1]) == "(BODY.PEEK[])":
            raw = (
                b"Subject: Test\r\nFrom: Alice <alice@example.com>\r\n"
                b"To: Bob <bob@example.com>\r\nDate: Thu, 10 Sep 2026 12:00:00 -0400\r\n"
                b"Message-ID: <x@example.com>\r\nContent-Type: text/plain; charset=utf-8\r\n"
                b"\r\nhello body"
            )
            return "OK", [(b"42 (BODY[] {200}", raw), b")"]
        raise AssertionError((command, args))


class FakeClient(ProtonBridgeClient):
    def __init__(self, settings: Settings, fake: FakeIMAP):
        super().__init__(settings)
        self.fake = fake

    @contextmanager
    def connection(self):
        yield self.fake

    def _search_targets(self, requested):
        from protonmail_mcp.imap_client import Mailbox

        return [Mailbox(name="INBOX", flags=("\\Inbox",), delimiter="/")]


def _settings() -> Settings:
    return Settings(
        bridge_host="127.0.0.1",
        bridge_port=1143,
        bridge_username="u",
        bridge_password="p",
        bridge_security="starttls",
        bridge_verify_tls=False,
        allow_nonlocal_imap=False,
        bind_host="127.0.0.1",
        bind_port=8765,
        max_message_bytes=10_000_000,
        max_body_chars=50_000,
        max_search_limit=50,
        snippet_chars=1200,
        snippet_fetch_bytes=16000,
        max_mailboxes=50,
    )


def test_search_uses_readonly_select_and_peek() -> None:
    fake = FakeIMAP()
    result = FakeClient(_settings(), fake).search_mail(query="hello", limit=1)
    assert result["count"] == 1
    assert all(call[2] is True for call in fake.calls if call[0] == "select")
    fetch_calls = [call for call in fake.calls if call[:2] == ("uid", "FETCH")]
    assert fetch_calls
    assert all("BODY.PEEK" in str(call) for call in fetch_calls)
    assert not any(" STORE " in f" {call} " for call in fake.calls)


def test_get_message_uses_peek_and_readonly_select() -> None:
    fake = FakeIMAP()
    client = FakeClient(_settings(), fake)
    result = client.get_message("eyJtIjoiSU5CT1giLCJ1IjoiNDIifQ")
    assert result["body"] == "hello body"
    assert all(call[2] is True for call in fake.calls if call[0] == "select")
    assert any(str(call[-1]) == "(BODY.PEEK[])" for call in fake.calls if call[:2] == ("uid", "FETCH"))
