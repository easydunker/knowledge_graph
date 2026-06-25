# Research KB Agent Skill

This repository packages `research-kb`, a reusable agent skill for building and maintaining an Obsidian-first research knowledge base from researcher-supplied PDFs.

The repo is not intended to be the user's knowledge-base vault. It contains the skill instructions, templates, scripts, agent contracts, and design documentation that an agent harness can install and use against a separate user-selected vault.

## What The Skill Does

`research-kb` helps an agent harness:

- bootstrap a local Obsidian vault for research notes
- ingest user-supplied PDFs from `raw/papers/`
- create hash-tracked paper notes that preserve `raw_pdf_path` and `pdf_sha256`
- export model-agnostic paper-processing tasks for LLM subagents
- resume quota-limited processing through vault-local job ledgers
- apply paper-process results only after validation and quality checks
- reconcile bibliographic metadata with Crossref, OpenAlex, and Semantic Scholar
- curate author, concept, variable, method, community, and synthesis notes
- query the curated vault for topic, author, citation-support, and previous-studies workflows
- lint, review, repair, and report on KB integrity

The CLI bundled in the skill is model-agnostic. It does not call an LLM provider or require an LLM API key. Model reasoning is handled by the host harness or subagents through JSON task/result contracts.

## Repo vs Vault

Keep these separate:

- **This repository / installed skill:** reusable tooling, templates, scripts, references, and agent definitions.
- **User-selected vault:** the actual knowledge-base content, including PDFs, Markdown notes, Obsidian settings, `.research-kb/` state, indexes, task files, result files, and reports.

A typical user vault contains:

```text
AGENTS.md
index.md
log.md
raw/papers/
papers/
authors/
concepts/
variables/
methods/
communities/
questions/
syntheses/
.research-kb/
```

The installed skill should never store a user's PDFs or KB content inside the skill directory.

## Installation

Install or copy `skills/research-kb/` into the harness's Codex skills directory, usually:

```text
~/.codex/skills/research-kb/
```

For a full Mac-oriented setup, including Python environment checks and optional PDF extraction dependencies, see:

- [INSTALL.md](INSTALL.md)

Recommended optional Python packages for real PDFs:

- `pymupdf4llm`
- `pypdf`

`pymupdf4llm` is preferred because it extracts LLM-ready Markdown from academic PDFs. The skill remains graceful when optional PDF libraries are unavailable, but output quality may be lower.

## Harness Workflow

The intended user experience is:

1. The user selects a vault root outside this repo.
2. The user places PDFs in the vault's `raw/papers/`.
3. The agent harness invokes the `research-kb` skill.
4. The skill initializes or refreshes the vault scaffold.
5. Deterministic intake creates conservative draft paper notes.
6. The harness exports a small batch of paper-process jobs.
7. Paper-process subagents read one task each and write result JSON only.
8. The skill applies results, creates candidate graph nodes, and runs quality guard.
9. A paper is considered processed only after its result is applied and quality guard passes.
10. The harness repeats batches until the build queue is complete.
11. Metadata reconciliation cleans high-confidence bibliographic fields and detects duplicate or stale nodes.
12. Curator subagents enrich non-paper notes and propose high-confidence merge/archive plans.
13. The skill refreshes indexes, writes a build report, and leaves review items for the researcher.

The quota-resilient queue is the default for Codex-like harnesses. It records state under the user's vault:

```text
.research-kb/jobs/
  paper-process.jsonl
  node-curation.jsonl
  build-runs.jsonl
  status.json
```

This lets later runs resume without the root harness remembering which PDFs were already processed.

## Agent Contracts

The skill includes bundled agent contracts and references:

- `research-kb.paper-process`: understands one paper from one exported task JSON and writes one result JSON.
- `research-kb.node-curator`: enriches one non-paper node from quality-passed paper evidence and reconciliation records.
- `research-kb.query`: supports clue-based search over the generated index.
- `research-kb.claim-support`: suggests supporting, complicating, contradictory, or missing KB evidence for draft prose.
- `research-kb.synthesis`: discusses previous studies from bounded retrieval over the current KB.

Each worker should be scoped to one task or bounded retrieval packet. Subagents should not edit Markdown notes directly; they write JSON to the task's `result_path`, and the CLI applies validated results.

## Evidence Policy

The Markdown vault is the source of truth for KB claims.

Rules:

- Raw PDFs enter through `raw/papers/`.
- Do not add external papers unless the user supplies the PDF.
- Do not modify Zotero.
- Do not treat web search results as trusted KB evidence.
- Crossref, OpenAlex, and Semantic Scholar may be used only for bibliographic reconciliation, duplicate detection, and author/title cleanup.
- Provider metadata is not evidence for scholarly claims.
- Quality-failed paper notes remain searchable, but curation and synthesis should not use them as evidence unless the harness loads full extracted/source text and clearly warns about quality state.

## Graph Model

Nodes are Markdown notes. Important node types include:

- `paper`
- `author`
- `concept`
- `variable`
- `method`
- `community`
- `research_question`
- `synthesis`

Edges are typed wikilinks in Markdown, for example:

```markdown
- authored_by:: [[authors/example-author]]
- studies_variable:: [[variables/mandarin-rhotics]]
- uses_method:: [[methods/mixed-effects-models]]
- supports:: [[concepts/indexicality]]
```

Typed links let the harness retrieve evidence paths instead of relying only on keyword search.

## Machine State

The user vault may contain generated machine state:

```text
.research-kb/index.json
.research-kb/search/*.jsonl
.research-kb/jobs/*.jsonl
.research-kb/agent-tasks/
.research-kb/agent-results/
.research-kb/curator-tasks/
.research-kb/curator-results/
.research-kb/quality-reports/
.research-kb/metadata-cache/
.research-kb/reconciliation/
```

These files support indexing, resumable builds, agent handoff, quality reports, metadata reconciliation, and query probing. They are vault-local tool state, not the scholarly source of truth.

## Project Docs

- [Knowledge base design](docs/knowledge-base-design.md)
- [Obsidian v1 blueprint](docs/obsidian-v1-blueprint.md)
- [Installation guide](INSTALL.md)
- [Curator implementation plan](docs/curator-implementation-plan.md)
- [Quota-resilient build plan](docs/quota-resilient-build-plan.md)
- [Metadata reconciliation plan](docs/metadata-reconciliation-plan.md)
- [Query architecture](docs/query-architecture.md)
- [Public PDF quality evaluation](docs/public-pdf-quality-evaluation.md)

## Repository Layout

```text
skills/research-kb/        reusable Codex skill package
skills/research-kb/SKILL.md
skills/research-kb/scripts/
skills/research-kb/agents/
skills/research-kb/references/
skills/research-kb/templates/
docs/                      design notes and implementation plans
scripts/                   development wrappers and evaluation helpers
plugins/                   optional future integrations
```

## Development Notes

This repo includes development wrappers and evaluation helpers, but the canonical installed artifact is `skills/research-kb/`. When changing workflow behavior, update the skill instructions, references, installation guide, and design docs together so future harnesses receive a coherent skill package.
