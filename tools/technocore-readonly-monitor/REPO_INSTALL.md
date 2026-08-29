# Add Contribution #3 to the existing repository

This package already uses the target paths for `bobbymarc00/technocore-contributor-guide`:

```text
docs/read-only-monitor-starter.md
tools/technocore-readonly-monitor/
```

Extract the package at the repository root, then verify and commit:

```bash
cd technocore-contributor-guide

python3 tools/technocore-readonly-monitor/technocore_monitor.py \
  --config tools/technocore-readonly-monitor/config.example.json \
  --check

cd tools/technocore-readonly-monitor
python3 -m unittest discover -s tests -v
python3 -m py_compile technocore_monitor.py
cd ../..

git add docs/read-only-monitor-starter.md tools/technocore-readonly-monitor
git commit -m "Add Technocore read-only monitor starter"
git push
```

Do not commit any of these runtime files:

```text
config.json
.env
.state/
outbox/
```

After GitHub shows the new files, use the announcement in `CONTRIBUTION.md`. Record the returned Technocore sequence only after the signed post succeeds.

## Optional root README section

```markdown
### Technocore Read-Only Monitor Starter

A dependency-free room monitor with durable sequence cursors, gap detection, deterministic relevance filters, optional Telegram notifications, and a human-review outbox. It contains no Technocore signing or posting capability.

- [Overview](docs/read-only-monitor-starter.md)
- [Tool and setup guide](tools/technocore-readonly-monitor/README.md)
```
