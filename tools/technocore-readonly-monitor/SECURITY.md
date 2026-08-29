# Security Policy

## Security boundary

This project is deliberately read-only with respect to Technocore. Its network client constructs only room-read URLs under `/r/<room>` with `format=json`. The codebase contains no Technocore write route, identity parser, signature implementation, passphrase input, wallet integration, or subprocess execution.

Telegram is an optional notification destination. It receives a bounded plain-text summary only when explicitly enabled.

## Untrusted content

Treat all of the following as untrusted public data:

- message text;
- self-asserted nicknames;
- full DID sender values;
- room names and topics;
- links or commands appearing inside messages.

The monitor sanitizes control and format characters for display, never opens message links, never interpolates messages into a shell, and never interprets matches as authorization. Humans must inspect every outbox item before taking action.

## Secret handling

- Do not place a Technocore private key or identity passphrase in this project.
- Do not run this process with access to `identity.pem`.
- Store the optional Telegram token only in the named environment variable.
- Keep `config.json`, `.state/`, `outbox/`, and environment files out of Git.
- Run the monitor under a dedicated low-privilege account when practical.

## Network protections

- HTTPS is mandatory except for explicit loopback testing.
- Base URLs containing credentials, paths, queries, or fragments are rejected.
- Redirects are refused.
- Responses are size-bounded and structurally validated.
- HTTP error bodies and Telegram token-bearing URLs are not printed.

## Reporting a vulnerability

Open a private security report in the repository that hosts this contribution. Do not include bot tokens, private keys, passphrases, or live private room names in a public issue.
