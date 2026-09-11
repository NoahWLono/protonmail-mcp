from __future__ import annotations

import base64
import html
import re
from email.header import decode_header
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "svg", "noscript"}:
            self._skip_depth += 1
        elif self._skip_depth == 0 and tag.lower() in {"br", "p", "div", "li", "tr", "h1", "h2", "h3"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "svg", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        elif self._skip_depth == 0 and tag.lower() in {"p", "div", "li", "tr"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._chunks.append(data)

    def text(self) -> str:
        return "".join(self._chunks)


def decode_header_value(value: str | None) -> str:
    if not value:
        return ""
    parts: list[str] = []
    for chunk, charset in decode_header(value):
        if isinstance(chunk, bytes):
            for candidate in [charset, "utf-8", "latin-1"]:
                if not candidate:
                    continue
                try:
                    parts.append(chunk.decode(candidate, errors="replace"))
                    break
                except (LookupError, UnicodeDecodeError):
                    continue
            else:
                parts.append(chunk.decode("utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return "".join(parts)


def decode_imap_utf7(value: str) -> str:
    """Decode IMAP modified UTF-7 without depending on private stdlib codecs."""
    output: list[str] = []
    i = 0
    while i < len(value):
        if value[i] != "&":
            output.append(value[i])
            i += 1
            continue
        end = value.find("-", i)
        if end == -1:
            output.append(value[i:])
            break
        token = value[i + 1 : end]
        if token == "":
            output.append("&")
        else:
            b64 = token.replace(",", "/")
            b64 += "=" * ((4 - len(b64) % 4) % 4)
            try:
                raw = base64.b64decode(b64)
                output.append(raw.decode("utf-16-be"))
            except (ValueError, UnicodeDecodeError):
                output.append(value[i : end + 1])
        i = end + 1
    return "".join(output)


def encode_imap_utf7(value: str) -> str:
    """Encode a Unicode mailbox name as IMAP modified UTF-7."""
    output: list[str] = []
    non_ascii: list[str] = []

    def flush() -> None:
        if not non_ascii:
            return
        raw = "".join(non_ascii).encode("utf-16-be")
        encoded = base64.b64encode(raw).decode("ascii").rstrip("=").replace("/", ",")
        output.append(f"&{encoded}-")
        non_ascii.clear()

    for char in value:
        code = ord(char)
        if 0x20 <= code <= 0x7E:
            flush()
            output.append("&-" if char == "&" else char)
        else:
            non_ascii.append(char)
    flush()
    return "".join(output)


def html_to_text(raw_html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(raw_html)
        parser.close()
        text = parser.text()
    except Exception:
        text = re.sub(r"<[^>]+>", " ", raw_html)
    return normalize_text(html.unescape(text))


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _part_text(part: Message) -> str:
    try:
        content = part.get_content()  # type: ignore[attr-defined]
        if isinstance(content, str):
            return content
    except Exception:
        pass

    payload = part.get_payload(decode=True)
    if payload is None:
        raw = part.get_payload()
        return raw if isinstance(raw, str) else ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def extract_body_text(message: Message, max_chars: int) -> tuple[str, bool]:
    plain: list[str] = []
    html_parts: list[str] = []

    for part in message.walk():
        if part.is_multipart():
            continue
        disposition = (part.get_content_disposition() or "").lower()
        filename = part.get_filename()
        if disposition == "attachment" or filename:
            continue
        content_type = part.get_content_type().lower()
        if content_type == "text/plain":
            plain.append(_part_text(part))
        elif content_type == "text/html":
            html_parts.append(_part_text(part))

    if plain:
        body = normalize_text("\n\n".join(plain))
    elif html_parts:
        body = html_to_text("\n\n".join(html_parts))
    else:
        body = ""

    truncated = len(body) > max_chars
    if truncated:
        body = body[:max_chars].rstrip() + "\n\n[truncated by protonmail-mcp]"
    return body, truncated


def extract_addresses(message: Message, header_name: str) -> list[dict[str, str]]:
    values = message.get_all(header_name, [])
    decoded_values = [decode_header_value(value) for value in values]
    result: list[dict[str, str]] = []
    for name, address in getaddresses(decoded_values):
        if name or address:
            result.append({"name": name, "email": address})
    return result


def message_date_iso(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt is None:
            return None
        return dt.isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def attachment_metadata(message: Message) -> list[dict[str, object]]:
    attachments: list[dict[str, object]] = []
    index = 0
    for part in message.walk():
        if part.is_multipart():
            continue
        disposition = (part.get_content_disposition() or "").lower()
        filename = part.get_filename()
        if disposition != "attachment" and not filename:
            continue
        payload = part.get_payload(decode=True)
        attachments.append(
            {
                "index": index,
                "filename": decode_header_value(filename) if filename else None,
                "content_type": part.get_content_type(),
                "size_bytes": len(payload) if payload is not None else None,
            }
        )
        index += 1
    return attachments


def sanitize_partial_preview(text: str, max_chars: int) -> str:
    # Partial MIME fetches can contain MIME boundaries and per-part headers. Keep the preview
    # useful while avoiding accidental giant base64 blobs.
    text = re.sub(r"(?im)^--[-=_A-Za-z0-9.+/]{8,}.*$", " ", text)
    text = re.sub(
        r"(?im)^(content-type|content-transfer-encoding|content-disposition|mime-version):.*$",
        " ",
        text,
    )
    text = re.sub(r"(?m)^[A-Za-z0-9+/]{120,}={0,2}$", "[binary/encoded data omitted]", text)
    text = normalize_text(text)
    return text[:max_chars].rstrip()
