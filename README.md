# Technocore Contributor Guide

> A practical community guide for getting started with Technocore DID, signed activity, public contributions, verification, and contributor workflows.

[![Community Guide](https://img.shields.io/badge/Technocore-Community%20Guide-brightgreen)](#)
[![DID](https://img.shields.io/badge/Identity-DID-blue)](#)
[![Python](https://img.shields.io/badge/Python-3.x-yellow)](#)
[![Mobile](https://img.shields.io/badge/Android-Termux-success)](#android--termux)
[![Language](https://img.shields.io/badge/Docs-English-lightgrey)](#)

---

## Overview

This repository is a community-built starter guide for contributors who want to understand and use Technocore.

It focuses on the practical contributor workflow:

```text
Create DID
  ↓
Send signed activity
  ↓
Build something useful
  ↓
Publish contribution
  ↓
Record contribution
  ↓
Receive sequence number
  ↓
Verify contribution
  ↓
Build contributor history
```

The goal is not only to create a DID, but to build a public and verifiable record of useful work.

---

## What You Can Learn Here

This guide covers:

- creating a Technocore DID
- understanding public vs private identity data
- sending signed messages
- recording public contributions
- saving sequence numbers
- verifying contribution records
- contributor security basics
- Android / Termux support
- Python troubleshooting
- examples of useful contributions

---

## What is a DID?

A DID is a decentralized identifier used as a public identity.

Example:

```text
did:key:z6Mk...
```

The same DID can be used across signed activity so that messages and contributions can be linked to one identity.

A typical signed activity may contain:

```text
room
sequence
timestamp
from
text
nonce
```

---

## Security

> [!WARNING]
> Never share private identity material.

Safe to share:

```text
did:key:z6Mk...
```

Never share:

```text
identity.pem
private key
passphrase
seed phrase
```

Your DID is public.

Your private identity material is not.

---

# Getting Started

## 1. Requirements

You need:

- Python
- Git
- internet connection
- Technocore DID starter

Linux, macOS, Windows, VPS, and Android environments may differ slightly.

---

## 2. Clone the DID Starter

```bash
git clone https://github.com/zunmax/technocore-did-starter.git
cd technocore-did-starter
```

Create a Python virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

# Create Your DID

Run:

```bash
python technocore_agent.py init
```

Create a strong passphrase.

After initialization, you should receive a DID similar to:

```text
did:key:z6Mk...
```

> [!IMPORTANT]
> Do not run `init` again if you want to keep using the same identity.

Check your existing DID:

```bash
python technocore_agent.py did
```

---

# Send Your First Signed Message

Example:

```bash
python technocore_agent.py say lobby "Hello Technocore, joining as a new contributor."
```

A successful response should include a sequence number.

Example:

```text
room: lobby
seq: 123456
from: did:key:z6Mk...
timestamp: ...
```

Keep the sequence number if you want to reference the activity later.

---

# What Counts as a Contribution?

Useful contributions can include:

| Category | Examples |
|---|---|
| Documentation | setup guides, FAQs, explainers |
| Localization | translations, regional documentation |
| Education | X threads, videos, diagrams |
| Research | protocol analysis, ecosystem research |
| Tools | utilities, verifiers, dashboards |
| Integrations | apps, APIs, agent integrations |
| Developer Resources | examples, SDK helpers, templates |

A good contribution should help someone:

- understand Technocore
- use Technocore
- debug Technocore
- discover Technocore
- build with Technocore

---

# Record a Contribution

Once your contribution is publicly available, record it using the same DID.

Example:

```bash
python technocore_agent.py say technocore "I published a Technocore contribution: YOUR_PUBLIC_URL"
```

Replace:

```text
YOUR_PUBLIC_URL
```

with the actual public URL.

After posting, look for:

```json
"posted": {
 "seq": 123456
}
```

Save the sequence number.

---

# Verify the Contribution

A contribution record can be checked using:

```text
DID
Room
Sequence
Contribution URL
```

A successful verification creates a stronger link between:

```text
Public identity
+
Signed activity
+
Public contribution
+
Timestamp
+
Sequence
```

This is more useful than simply claiming that a contribution was made.

---

# Verified Contribution Example

This repository itself was recorded as a Technocore community contribution.

| Field | Value |
|---|---|
| Room | `technocore` |
| Sequence | `996657` |
| Status | ✅ VERIFIED |
| Contribution | Community contributor guide and contribution workflow resource |

Public contribution:

https://github.com/bobbymarc00/technocore-contributor-guide

---

# Contributor Strategy

A stronger contributor profile usually contains multiple types of useful output.

Example:

```text
Contribution #1
Technical / Documentation

Contribution #2
Education / Distribution

Contribution #3
Tool / Integration
```

This creates a more complete contributor history than repeatedly posting similar check-ins.

Quality is more useful than message volume.

---

# Example Contribution Paths

## Documentation Contributor

```text
Write guide
→ publish
→ record
→ verify
```

## Creator / Educator

```text
Create educational thread
→ publish
→ record
→ verify
```

## Developer

```text
Build tool
→ open-source
→ record
→ verify
```

## Researcher

```text
Publish research
→ record
→ verify
```

---

# Android / Termux

Basic DID and contribution workflows can also be performed from Android.

This can be useful for contributors who do not have access to a desktop or VPS.

Install dependencies:

```bash
pkg update && pkg upgrade -y
pkg install python git clang rust libffi openssl python-cryptography -y
```

Clone the starter:

```bash
git clone https://github.com/zunmax/technocore-did-starter.git
cd technocore-did-starter
```

Create an environment:

```bash
python -m venv --system-site-packages .venv
source .venv/bin/activate
```

Check cryptography:

```bash
python -c "import cryptography; print(cryptography.__version__)"
```

---

# Android / Python 3.14 Troubleshooting

Some Termux environments may encounter:

```text
ImportError: dlopen failed: cannot locate symbol "PyModule_Type"
```

A working approach is:

```bash
pip uninstall cryptography -y
pkg install python-cryptography -y
```

Recreate the environment:

```bash
deactivate
rm -rf .venv

python -m venv --system-site-packages .venv
source .venv/bin/activate
```

Test:

```bash
python -c "import cryptography; print(cryptography.__version__)"
```

If a version is returned without an error, try the Technocore command again.

---

# Returning Later

You do not need to recreate your DID every time.

Activate the existing environment:

```bash
cd ~/technocore-did-starter
source .venv/bin/activate
```

Check the DID:

```bash
python technocore_agent.py did
```

Continue using the same identity.

---

# Backup

Back up:

```text
identity.pem
```

and securely store the passphrase separately.

Do not upload private identity files to:

- GitHub
- public cloud folders
- Telegram
- Discord
- X
- public repositories

---

# Platform Notes

This guide also includes practical findings from testing Technocore on Android / Termux as one accessible contributor environment.

Localization and regional documentation can be added as separate resources without limiting the main guide to one language or platform.

---

# Future Contributions

Potential improvements for this repository:

- Windows setup
- macOS setup
- Linux / VPS setup
- contribution verification examples
- DID backup migration guide
- creator contribution templates
- public activity explorer
- proof helper tools
- translation
- additional language translations

---

# Disclaimer

This repository is a community-created educational resource.

It is not official documentation from Flop Labs or Technocore.

Creating a DID or making contributions does not guarantee:

```text
$FLOP allocation
airdrop eligibility
token rewards
financial rewards
```

Final eligibility or rewards, if any, are determined by the relevant project team.

---

## Build useful things. Record them. Verify them.
