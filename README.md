# protonmail-mcp

A small, local-first, **read-only** MCP server that lets ChatGPT search and read a Proton Mail
account through Proton Mail Bridge.

The project intentionally does less than a normal email client. It cannot send, reply, delete,
move, archive, label, mark read/unread, or download attachment bytes.

## What ChatGPT gets

Four read-only tools:

- `proton_health` - verify Bridge connectivity without reading messages
- `list_mailboxes` - list folders/labels
- `search_mail` - search mail and return metadata plus optional short snippets
- `get_message` - fetch one decoded text message plus attachment metadata

Example prompts after connecting the app:

```text
Search my Proton inbox for mail from Proton about security keys.

Find emails with "Daybreak Blue" from the last 30 days and summarize the important ones.

Read the message with the subject "Interview details" and tell me the date and action items.
```

## Why Proton Mail Bridge

Proton Mail Bridge decrypts Proton Mail locally and exposes IMAP to local email clients. This
server connects only to that local IMAP interface. Use the Bridge-generated IMAP password, never
your Proton Account password.

## Requirements

- A Proton plan that includes Proton Mail Bridge
- Proton Mail Bridge installed and signed in
- Python 3.10+
- `uv` recommended, or ordinary `pip`
- ChatGPT Developer Mode plus a way to expose the local MCP through OpenAI Secure MCP Tunnel

## Install

Unzip the project, then:

```bash
cd protonmail-mcp
cp .env.example .env
chmod 600 .env
$EDITOR .env
uv sync --extra dev
uv run protonmail-mcp doctor
```

Fill `.env` from **Proton Mail Bridge -> Mailbox details**. Port and security mode can vary, so use
what Bridge actually shows.

Start the server:

```bash
uv run protonmail-mcp serve
```

Default endpoint:

```text
http://127.0.0.1:8765/mcp
```

See [`docs/CHATGPT_SETUP.md`](docs/CHATGPT_SETUP.md) for the ChatGPT connection steps.

## pip alternative

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
protonmail-mcp doctor
protonmail-mcp serve
```

## Search API

`search_mail` accepts:

- `query`: IMAP text search across headers/body
- `sender`: sender filter
- `subject`: subject filter
- `after`: inclusive ISO date, for example `2026-09-01`
- `before`: exclusive ISO date
- `mailbox`: exact mailbox name, or omit to search All Mail when available
- `limit`: capped locally, default 20
- `include_snippet`: return a short text preview, default true

Search results include an opaque `ref`. Pass that ref to `get_message`.

## Read-only guarantees in this codebase

This is not only a prompt-level promise.

1. There is no SMTP implementation or dependency.
2. Every `SELECT` call uses `readonly=True`.
3. Every body fetch uses `BODY.PEEK`.
4. There is no code path calling IMAP `STORE`, `COPY`, `MOVE`, `APPEND`, or `EXPUNGE`.
5. MCP tools declare the standard read-only annotation.
6. The MCP HTTP listener refuses non-loopback hosts.
7. The Bridge IMAP target refuses non-loopback hosts unless you explicitly opt in.

You can audit these claims with:

```bash
rg -n 'STORE|COPY|MOVE|APPEND|EXPUNGE|SMTP|BODY\\[' src tests
```

`BODY[` should appear only in tests that verify the parser's fake IMAP response. Production fetch
queries use `BODY.PEEK`.

## TLS note

Proton Mail Bridge normally uses a locally generated self-signed TLS certificate. This project
therefore defaults to certificate verification off **only for the loopback Bridge connection**.
Non-loopback IMAP is blocked by default, and if explicitly enabled it requires TLS verification.

## Prompt-injection note

Email is attacker-controlled input. A malicious message can contain text such as "ignore your
instructions". The server converts HTML to inert text, never loads remote content, and marks mail
as untrusted external data in tool responses. The model still needs to treat message content as
data rather than instructions.

## Tests

```bash
uv run pytest
uv run ruff check .
```

The tests include a contract check that searches use read-only mailbox selection and
`BODY.PEEK`.

## Current limitations

- No attachment body retrieval, only metadata.
- No conversation/thread reconstruction yet.
- Search uses IMAP semantics, so advanced Proton web-search syntax is not implemented.
- Very large messages are withheld above `PROTON_MCP_MAX_MESSAGE_BYTES` instead of pulling large
  attachments into model context.
- ChatGPT custom MCP apps currently require ChatGPT web according to OpenAI's help documentation.

## License

MIT
