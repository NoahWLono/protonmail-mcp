from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigurationError(RuntimeError):
    """Raised when configuration is missing or unsafe."""


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ConfigurationError(f"{name} must be >= {minimum}")
    return value


def is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower().strip("[]")
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _read_password() -> str:
    direct = os.getenv("PROTON_BRIDGE_PASSWORD", "")
    if direct:
        return direct

    password_file = os.getenv("PROTON_BRIDGE_PASSWORD_FILE", "")
    if not password_file:
        raise ConfigurationError(
            "Set PROTON_BRIDGE_PASSWORD or PROTON_BRIDGE_PASSWORD_FILE to the password "
            "shown by Proton Mail Bridge. Do not use your Proton Account password."
        )

    path = Path(password_file).expanduser()
    if not path.is_file():
        raise ConfigurationError(f"Password file does not exist: {path}")

    try:
        mode = path.stat().st_mode & 0o777
    except OSError as exc:
        raise ConfigurationError(f"Could not inspect password file: {path}") from exc
    if mode & 0o077:
        raise ConfigurationError(
            f"Password file {path} is readable by group/others; run chmod 600 {path}"
        )

    secret = path.read_text(encoding="utf-8").strip("\r\n")
    if not secret:
        raise ConfigurationError(f"Password file is empty: {path}")
    return secret


@dataclass(frozen=True, slots=True)
class Settings:
    bridge_host: str
    bridge_port: int
    bridge_username: str
    bridge_password: str
    bridge_security: str
    bridge_verify_tls: bool
    allow_nonlocal_imap: bool
    bind_host: str
    bind_port: int
    max_message_bytes: int
    max_body_chars: int
    max_search_limit: int
    snippet_chars: int
    snippet_fetch_bytes: int
    max_mailboxes: int

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()

        bridge_host = os.getenv("PROTON_BRIDGE_HOST", "127.0.0.1").strip()
        bridge_username = os.getenv("PROTON_BRIDGE_USERNAME", "").strip()
        if not bridge_username:
            raise ConfigurationError(
                "Set PROTON_BRIDGE_USERNAME to the IMAP username shown by Proton Mail Bridge"
            )

        security = os.getenv("PROTON_BRIDGE_SECURITY", "starttls").strip().lower()
        if security not in {"starttls", "ssl", "plain"}:
            raise ConfigurationError(
                "PROTON_BRIDGE_SECURITY must be one of: starttls, ssl, plain"
            )

        allow_nonlocal = _bool_env("PROTON_MCP_ALLOW_NONLOCAL_IMAP", False)
        if not is_loopback_host(bridge_host) and not allow_nonlocal:
            raise ConfigurationError(
                "Refusing a non-loopback IMAP host. Proton Mail Bridge should normally be at "
                "127.0.0.1/localhost. Set PROTON_MCP_ALLOW_NONLOCAL_IMAP=1 only if you have "
                "intentionally secured a remote IMAP path."
            )

        verify_tls = _bool_env("PROTON_BRIDGE_VERIFY_TLS", False)
        if not is_loopback_host(bridge_host) and security in {"starttls", "ssl"} and not verify_tls:
            raise ConfigurationError(
                "TLS certificate verification cannot be disabled for a non-loopback IMAP host"
            )
        if not is_loopback_host(bridge_host) and security == "plain":
            raise ConfigurationError("Plain IMAP is never allowed for a non-loopback host")

        bind_host = os.getenv("PROTON_MCP_BIND_HOST", "127.0.0.1").strip()
        if not is_loopback_host(bind_host):
            raise ConfigurationError(
                "This build intentionally refuses to expose its unauthenticated MCP endpoint on a "
                "non-loopback interface. Use Secure MCP Tunnel from the same machine instead."
            )

        return cls(
            bridge_host=bridge_host,
            bridge_port=_int_env("PROTON_BRIDGE_PORT", 1143),
            bridge_username=bridge_username,
            bridge_password=_read_password(),
            bridge_security=security,
            bridge_verify_tls=verify_tls,
            allow_nonlocal_imap=allow_nonlocal,
            bind_host=bind_host,
            bind_port=_int_env("PROTON_MCP_PORT", 8765),
            max_message_bytes=_int_env("PROTON_MCP_MAX_MESSAGE_BYTES", 10 * 1024 * 1024),
            max_body_chars=_int_env("PROTON_MCP_MAX_BODY_CHARS", 50_000),
            max_search_limit=_int_env("PROTON_MCP_MAX_SEARCH_LIMIT", 50),
            snippet_chars=_int_env("PROTON_MCP_SNIPPET_CHARS", 1_200),
            snippet_fetch_bytes=_int_env("PROTON_MCP_SNIPPET_FETCH_BYTES", 16_000),
            max_mailboxes=_int_env("PROTON_MCP_MAX_MAILBOXES", 50),
        )

    def public_summary(self) -> dict[str, object]:
        return {
            "bridge_host": self.bridge_host,
            "bridge_port": self.bridge_port,
            "bridge_username": self.bridge_username,
            "bridge_security": self.bridge_security,
            "bridge_verify_tls": self.bridge_verify_tls,
            "mcp_bind_host": self.bind_host,
            "mcp_port": self.bind_port,
            "max_message_bytes": self.max_message_bytes,
            "max_body_chars": self.max_body_chars,
            "max_search_limit": self.max_search_limit,
        }
