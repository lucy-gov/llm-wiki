# Restricted vault

**This repository contains identifiable human subjects data under IRB protocol.**

- **Never add a git remote.** Not GitHub, not a private host, not a backup
  remote. Only the contract and scripts are tracked; data files are ignored.
  Back up according to the protocol's data management plan.
- **Nothing leaves this directory except by hand.** Candidate findings go in
  `analysis/outbound/`; the researcher reviews them for re-identification risk
  and copies them into the main wiki manually (see `BRIDGE.md`).
- **Rebuild the denylist after every change** to `participants.csv` or
  `denylist-extra.txt`:

  ```sh
  python3 scripts/build-denylist.py
  ```

  This writes hashed identifiers to `~/.config/llm-wiki/denylist`, which the
  main wiki's pre-commit hook uses to block participant names, emails, and
  phone numbers. The main side cannot tell when the denylist is stale, so this
  step is your responsibility.
