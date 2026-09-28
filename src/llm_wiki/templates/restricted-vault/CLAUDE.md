# Restricted vault: agent contract

This directory contains identifiable human subjects data collected under an IRB
protocol. It is a different contract from the main wiki's, and it is stricter.

## Hard prohibitions

- Never copy content out of this directory, and never write to any path outside it.
- Never read from or write to the main wiki repository.
- Never add a git remote, push, or run any command that transmits these files.
- Never include a participant's name, title, contact details, or identifying
  agency detail in anything written to `analysis/outbound/`.

## What you may do

- Read transcripts and notes here to help the researcher analyze them.
- Draft **de-identified** candidate `finding` pages in `analysis/outbound/`,
  using pseudonyms from `participants.csv` only, with this frontmatter:

  ```yaml
  type: finding
  title: ""
  projects: []
  created: YYYY-MM-DD
  updated: YYYY-MM-DD
  tags: []
  publish: false
  study: own:<study-name>
  participants_referenced: []   # pseudonyms only
  confidence: tentative         # strong|moderate|tentative
  ```
- Flag anything in a draft you think could re-identify someone. Small
  populations (California has a bounded number of state agencies) make
  combinations of role, agency size, and events identifying even without names.

## Reminders to give the researcher

- After any change to `participants.csv` or `denylist-extra.txt`, rerun
  `python3 scripts/build-denylist.py`.
- The copy from `analysis/outbound/` into the main wiki is manual. Offer to
  review a draft for re-identification risk; never offer to perform the copy.
