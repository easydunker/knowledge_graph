# Sociolinguistics and Sociophonetics KB V1

This is an Obsidian-first research knowledge base for sociolinguistics and sociophonetics. V1 is raw-PDF-first: drop handpicked papers into `raw/papers/`, run the intake script, then review and develop the generated Markdown notes in Obsidian.

## Quick Start

1. Open this folder as an Obsidian vault.
2. Drop PDF papers into `raw/papers/`.
3. Run:

```bash
python3 scripts/process_raw_pdfs.py
```

4. Review generated notes in `papers/`.
5. Use links and relation-style bullets to connect papers to concepts, variables, methods, communities, questions, and syntheses.

The script is non-destructive by default: PDFs stay in `raw/papers/`. Use `--move` if you want successfully processed PDFs moved to `raw/processed/`.

```bash
python3 scripts/process_raw_pdfs.py --move
```

PDF text extraction uses `pypdf` when it is installed. Without `pypdf`, the script still creates draft notes from filenames and records `text_extraction_status: pypdf_not_available`.

## Project Docs

- [Knowledge base design](docs/knowledge-base-design.md)
- [Obsidian v1 blueprint](docs/obsidian-v1-blueprint.md)

## V1 Architecture

```text
raw/papers/
  -> PDF extraction
  -> papers/<paper_id>.md
  -> linked Obsidian notes
  -> agent search/synthesis workflows
```

Zotero is not required for v1. A future optional integration can live under `plugins/zotero/`.

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
