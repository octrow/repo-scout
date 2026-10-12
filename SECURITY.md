**English** | [Русский](SECURITY.ru.md)

# Security

Report a vulnerability privately: [open a security advisory](https://github.com/octrow/repo-scout/security/advisories/new). Do not open a public issue for it.

You get a first answer within 7 days. Fixes go into the next release; only the latest release is supported.

repo-scout runs on your machine. It reads GitHub through your `gh` login and keeps API keys in `~/.config/repo-scout/.env` (readable only by you). It sends a key only to the endpoint that key belongs to.
