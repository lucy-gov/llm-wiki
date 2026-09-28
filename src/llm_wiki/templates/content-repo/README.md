# {{title}}

The private content repository for an LLM-maintained research wiki built with
[llm-wiki]({{tools_url}}). The agent contract is `CLAUDE.md`.

## Setup

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

Open this directory as an Obsidian vault with wikilinks on and "New link format"
set to "Absolute path in vault".

## Upgrading the tools

Change the commit in `requirements.txt` and `rev` in `.pre-commit-config.yaml`
together, then reinstall. pip treats a new commit with the same package version
as already installed, so force the tools reinstall:

```sh
pip install --force-reinstall --no-deps "$(grep '^llm-wiki' requirements.txt)"
pip install -r requirements.txt
wiki-bib --version   # should show the new short SHA, without -dirty
```

Commit the pin bump on its own.

## Layout

- `raw/` — immutable sources. Read, never written.
- `wiki/` — the knowledge layer, maintained by the agent.
- `design/` — the design layer. May cite `wiki/`; `wiki/` never cites it.
- `data/` — structured research data.
- `index.md` — router; `wiki/<type>/index.md` — catalogs.
- `brief.md` — regenerated each morning.
