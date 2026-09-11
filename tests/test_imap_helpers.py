import os

import pytest

from protonmail_mcp.config import ConfigurationError, Settings
from protonmail_mcp.imap_client import make_ref, parse_list_line, parse_ref


def test_ref_round_trip() -> None:
    ref = make_ref("Folders/Receipts", "12345")
    assert parse_ref(ref) == ("Folders/Receipts", "12345")


def test_ref_rejects_non_numeric_uid() -> None:
    ref = make_ref("INBOX", "abc")
    with pytest.raises(Exception):
        parse_ref(ref)


def test_parse_list_line() -> None:
    mailbox = parse_list_line(b'(\\HasNoChildren \\Inbox) "/" "INBOX"')
    assert mailbox.name == "INBOX"
    assert mailbox.delimiter == "/"
    assert "\\Inbox" in mailbox.flags
    assert mailbox.selectable is True


def test_nonlocal_imap_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROTON_BRIDGE_USERNAME", "test@example.com")
    monkeypatch.setenv("PROTON_BRIDGE_PASSWORD", "bridge-password")
    monkeypatch.setenv("PROTON_BRIDGE_HOST", "mail.example.com")
    monkeypatch.delenv("PROTON_MCP_ALLOW_NONLOCAL_IMAP", raising=False)
    with pytest.raises(ConfigurationError):
        Settings.from_env()


def test_public_summary_does_not_leak_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROTON_BRIDGE_USERNAME", "test@example.com")
    monkeypatch.setenv("PROTON_BRIDGE_PASSWORD", "super-secret")
    monkeypatch.setenv("PROTON_BRIDGE_HOST", "127.0.0.1")
    settings = Settings.from_env()
    assert "super-secret" not in repr(settings.public_summary())
    assert "bridge_password" not in settings.public_summary()
