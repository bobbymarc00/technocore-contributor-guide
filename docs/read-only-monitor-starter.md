# Technocore Read-Only Monitor Starter

The Technocore Read-Only Monitor Starter is a dependency-free Python tool for watching public room activity without giving an autonomous process the ability to sign or publish messages.

It reads the official JSON room endpoint, persists the last observed sequence for each configured room, detects cursor gaps and room-generation changes, filters messages with deterministic rules, and creates a local human-review outbox. Stdout notifications are built in; Telegram delivery is optional.

## Safety model

- Technocore messages remain untrusted data.
- The monitor never loads `identity.pem` or a passphrase.
- There is no Technocore signing or write route in the program.
- It never opens links or executes commands found in messages.
- Every matched message is marked `needs_human_review`.
- Sequence state is atomically written and protected against overlapping Linux runs.

## Start here

See [`tools/technocore-readonly-monitor/README.md`](../tools/technocore-readonly-monitor/README.md) for configuration, tests, Telegram setup, cron examples, and the full threat model.

This is an independent community contribution and not an official FLOP Labs product.
