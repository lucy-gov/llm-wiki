# De-identification bridge

The only path from this vault into the main wiki.

1. In a session opened **in this directory**, draft a candidate `finding` page
   in `analysis/outbound/<slug>.md`. Pseudonyms only.
2. Review the draft yourself for re-identification risk: names, titles, agency
   identification, distinctive events, dates, and combinations of these.
3. Confirm the denylist is current (`python3 scripts/build-denylist.py`).
4. Copy the file by hand into the main wiki at `wiki/findings/<slug>.md`. No
   tool automates this step, deliberately.
5. Commit in the main wiki. The pre-commit hook checks the page against the
   denylist; a block means the draft still contains an identifier.
