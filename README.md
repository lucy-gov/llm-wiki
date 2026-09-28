# llm-wiki
Tools for building and maintaining an LLM-authored research wiki: Zotero-backed ingest, mechanical quote verification, provenance linting, and instrument versioning over plain markdown.

This repository holds code, templates, and synthetic test fixtures only. The wiki itself lives in a separate private content repository, and nothing from it ever enters this one.

## Status

Early development. Available now: `wiki-init`, the leak-prevention hooks, and the read path: `wiki-bib`, `wiki-extract`, `wiki-links`, and `wiki-index`. The ingest, verification, lint, export, and publishing tools are in progress.

OCR for image-only PDFs needs [`ocrmypdf`](https://ocrmypdf.readthedocs.io/) on `PATH` (`brew install ocrmypdf`); without it, `wiki-extract` reports such PDFs as `no-text`.

## Instantiating a wiki

1. Copy `src/llm_wiki/templates/wiki.toml.template` somewhere outside this repo and fill in your projects.
2. Scaffold the private content repository, pinned to a pushed commit of this repo:

   ```sh
   wiki-init ../my-wiki-content --config path/to/wiki.toml
   ```

   The pin defaults to the running code's commit and is refused if the working tree is dirty; pass `--tools-rev <sha>` to override.
3. In the new repository, follow its README: create a virtualenv, `pip install -r requirements.txt`, and install the hooks.
4. If the work involves human subjects data, scaffold the restricted vault. Never give it a remote:

   ```sh
   wiki-init ../research-restricted --restricted
   ```

## Development

```sh
uv sync
uv run pytest
.venv/bin/pre-commit install --hook-type pre-commit --hook-type commit-msg
```

Test fixtures must be synthetic, and every citekey in `tests/`, `src/llm_wiki/templates/`, and root-level markdown carries the `fx_` prefix. The hook and the test suite both enforce this. Commits that change `.gitignore` need `[ignore-change]` in the message.
