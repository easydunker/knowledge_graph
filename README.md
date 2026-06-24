# Sociolinguistics and Sociophonetics KB V1

This is an Obsidian-first research knowledge base for sociolinguistics and sociophonetics. V1 is raw-PDF-first: drop handpicked papers into `raw/papers/`, run the intake script, then review and develop the generated Markdown notes in Obsidian.

## Tool vs Vault

The reusable skill is tooling. It can live in `~/.codex/skills/research-kb/` or in this development repo.

The knowledge-base content should live in a separate user-selected Obsidian vault root, for example `~/Documents/research-kb/` or a project-specific research folder. That vault root contains `raw/papers/`, `papers/`, `concepts/`, `index.md`, `.research-kb/`, and the rest of the user's notes.

For an installed skill, bootstrap a selected vault with:

```bash
VAULT="$HOME/Documents/research-kb"
python3 ~/.codex/skills/research-kb/scripts/research_kb.py --vault "$VAULT" init
```

For this development repo's wrapper, pass `--vault` when targeting a separate content vault:

```bash
python3 scripts/kb.py --vault "$VAULT" init
```

## Quick Start for This Demo Vault

1. Open this folder as an Obsidian vault.
2. Drop PDF papers into `raw/papers/`.
3. Run:

```bash
python3 scripts/kb.py process
```

4. Review generated notes in `papers/`.
5. Use links and relation-style bullets to connect papers to concepts, variables, methods, communities, questions, and syntheses.

The script is non-destructive by default: PDFs stay in `raw/papers/`. Use `--move` if you want successfully processed PDFs moved to `raw/processed/`.

```bash
python3 scripts/kb.py process --move
```

PDF text extraction uses `pypdf` when it is installed, which is strongly recommended for real research PDFs. Without `pypdf`, the script attempts a best-effort literal text extraction, still creates draft notes when possible, and records uncertainty in `text_extraction_status`, `metadata_confidence`, and `uncertain_fields`.

The core CLI does not call any model provider or require an API key. `process` creates hash-tracked paper-note drafts. For model-assisted understanding, export a portable agent task, let the current harness, subagent, or another skill produce the analysis JSON, then apply it back to the vault:

```bash
python3 scripts/kb.py process
python3 scripts/kb.py agent-context
# Run an agent/subagent/skill on .research-kb/agent-tasks/*.agent-task.json.
python3 scripts/kb.py apply-analysis .research-kb/agent-results/*.json --create-nodes
```

`enrich --create-nodes` remains available as a deterministic offline fallback for tests or quick drafts. The skill workflow should prefer `agent-context` plus `apply-analysis` when the host harness has an LLM or subagent system.

The legacy entry point still works:

```bash
python3 scripts/process_raw_pdfs.py
```

## KB Helper CLI

The reusable helper covers the main v1 lifecycle:

```bash
python3 scripts/kb.py init
python3 scripts/kb.py index
python3 scripts/kb.py process
python3 scripts/kb.py enrich --create-nodes
python3 scripts/kb.py query "rhotics, gender, and identity" --mode idea
python3 scripts/kb.py query "draft paragraph or claim" --mode draft
python3 scripts/kb.py review
python3 scripts/kb.py lint
python3 scripts/kb.py lint --fix
```

The same engine is bundled as an installable Codex skill under `skills/research-kb/`.
Copy that folder into another user's `~/.codex/skills/` to make `$research-kb` available.

`enrich` is conservative: it fills draft paper-note sections from extracted PDF text, marks inferred graph edges as `#candidate`, creates missing candidate nodes only with `--create-nodes`, and keeps notes in `needs_review` until a researcher checks them.

To run the public-PDF quality evaluation in a temporary vault:

```bash
python3 scripts/evaluate_public_pdfs.py --python /path/to/python-with-pypdf
```

## Project Docs

- [Knowledge base design](docs/knowledge-base-design.md)
- [Obsidian v1 blueprint](docs/obsidian-v1-blueprint.md)
- [Installation guideline](docs/installation-guideline.md)
- [Public PDF quality evaluation](docs/public-pdf-quality-evaluation.md)

## V1 Architecture

```text
raw/papers/
  -> PDF extraction
  -> papers/<paper_id>.md
  -> linked Obsidian notes
  -> .research-kb/index.json
  -> agent search/synthesis workflows
```

Zotero is not required for v1. A future optional integration can live under `plugins/zotero/`.

## Index Locations

`index.md` lives at the vault root and is the human-facing Obsidian entry point.

`.research-kb/index.json` is the machine-maintained cache regenerated from the Markdown notes by `init`, `index`, `process`, `enrich`, `query --save`, `new-node`, and `lint --fix`.

The Markdown notes remain the source of truth. The JSON index is disposable tool state.

## Graph Model

Nodes are Markdown notes. The `type` field in frontmatter defines the node type:

- `paper`
- `concept`
- `variable`
- `method`
- `community`
- `research_question`
- `synthesis`

Edges are typed wikilinks:

```markdown
- studies_variable:: [[variables/mandarin-rhotics]]
- uses_method:: [[methods/mixed-effects-models]]
- supports:: [[concepts/indexicality]]
```

Paper notes should contain a small graph in their relation sections so agents can retrieve evidence paths instead of only keyword matches.

## Main Workflows

- Process raw PDFs into paper notes.
- Given an idea, find relevant papers and suggest directions.
- Given writing, suggest supporting or complicating citations.
- Given a question, find relevant papers and synthesize what the current KB says.
- Lint the vault for missing notes, orphan nodes, duplicate concepts, and stale syntheses.

## Suggested First Test

Drop 10 handpicked PDFs into `raw/papers/`, run the intake script, review the generated notes, then ask:

> Given this research idea, what papers in my curated KB are relevant, what do they support, and what directions could I pursue?
