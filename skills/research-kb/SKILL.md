---
name: research-kb
description: Build, operate, query, review, and repair a local Obsidian-first research knowledge base from researcher-supplied PDFs. Use when Codex is asked to process raw research PDFs, create source-grounded paper notes, maintain typed Markdown graph links, answer questions from a curated vault, suggest citations from existing notes, lint or fix a knowledge base, bootstrap a new research KB vault, or install a reusable Codex skill for scholarly Markdown knowledge-base workflows.
---

# Research KB

## Core Rule

Treat the Markdown vault as the source of truth and `raw/papers/` as the only trusted v1 paper intake zone. Do not add external papers, modify Zotero, or treat web search results as KB evidence unless the user explicitly supplies the PDF and it enters through the vault. Crossref, OpenAlex, and Semantic Scholar may be used only for bibliographic metadata reconciliation, duplicate detection, and author/title cleanup; they are not evidence sources for scholarly claims.

## Quick Start

Keep the installed skill directory separate from the user's knowledge base. The skill directory contains reusable instructions and scripts. The user-selected vault root contains PDFs, notes, Obsidian settings, `.research-kb/`, and all knowledge-base content.

Find or choose the vault root first. If the user has not supplied a path, ask for the desired Obsidian vault location before bootstrapping. A vault root usually contains `AGENTS.md`, `index.md`, `log.md`, `raw/papers/`, and folders such as `papers/`, `concepts/`, `variables/`, `methods/`, `communities/`, `questions/`, and `syntheses/`.

Use the bundled CLI for the vault lifecycle. The CLI is model-agnostic: it never calls an LLM provider, never requires a provider API key, and treats model reasoning as an agent/subagent contract.

When Codex subagents are available, process PDFs with the bundled paper process agent by default. The CLI should extract PDFs and export tasks; spawn one `research-kb.paper-process` worker per task to understand and summarize one paper from extracted text; then apply the worker JSON back into Markdown.

```bash
VAULT="/path/to/user-selected-vault"
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" init
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" index
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" process
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" agent-context
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" apply-analysis .research-kb/agent-results/*.json --create-nodes
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" quality-guard
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" reconcile-metadata
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" curator-context
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" apply-curation .research-kb/curator-results/*.json
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" build-report
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" query "rhotics, gender, and identity" --mode idea
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" review
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" lint
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" lint --fix
```

For real PDFs, prefer a Python environment with `pymupdf4llm` and `pypdf` installed. `pymupdf4llm` is the preferred extraction backend because it produces LLM-ready Markdown; `pypdf` remains a compatibility fallback. If optional PDF libraries are unavailable, the CLI still creates conservative hash-tracked drafts and marks uncertain extraction fields for review.

Agent-assisted paper understanding:

1. Run `process` to create paper notes with `raw_pdf_path` and `pdf_sha256`.
2. Run `agent-context` to export `.research-kb/agent-tasks/*.agent-task.json`.
3. Read `references/paper-process-agent.md` and `references/agent-contract.md`.
4. In Codex, spawn one worker subagent per task. Give each worker exactly one task JSON path and the instruction to act as `research-kb.paper-process`, write only the result JSON to the task's `result_path`, and avoid editing notes directly.
5. Save returned JSON under `.research-kb/agent-results/`.
6. Run `apply-analysis ... --create-nodes` to write source-grounded sections and candidate graph nodes.
7. Run `quality-guard` to mark low-quality paper-process outputs. Quality-failed papers remain searchable but are skipped by curation and synthesis.
8. Run `reconcile-metadata` to query Crossref, OpenAlex, and Semantic Scholar for bibliographic metadata and duplicate/stale node clusters. OpenAlex and Semantic Scholar API keys are optional. Use `--apply` only when you want high-confidence paper metadata updates written to frontmatter.
9. Run `curator-context`, spawn `research-kb.node-curator` workers, and run `apply-curation` to enrich non-paper nodes, create strong active synthesis notes, and apply high-confidence merge/archive plans.

Use `enrich --create-nodes` only as deterministic offline fallback when no agent/subagent reasoning is available.

## Harness Subagent Guidance

This skill can tell a harness how to use subagents, but it does not itself grant permission to spawn them. If the current harness requires explicit authorization, the user should say something like: "Use subagents for paper processing and curation."

When the user explicitly authorizes subagents or delegated agent work, the harness should:

1. Run `agent-context`.
2. Spawn one `research-kb.paper-process` worker per `.research-kb/agent-tasks/*.agent-task.json`, or process tasks in batches for large vaults.
3. Apply results with `apply-analysis --create-nodes`.
4. Run `quality-guard`.
5. Run `reconcile-metadata`, using Crossref, OpenAlex, and Semantic Scholar only for bibliographic cleanup.
6. Run `curator-context`.
7. Spawn one `research-kb.node-curator` worker per `.research-kb/curator-tasks/*.curator-task.json`, or process tasks in batches for large vaults.
8. Apply results with `apply-curation`.
9. Run `lint`, `index`, and `build-report`.

Keep each worker scoped to one task JSON and require it to write only the task's `result_path`. For large vaults, batch workers by retrieval shard or note type so the root harness never needs to load the whole graph or all paper summaries at once.

When this repository is the vault, the wrapper is:

```bash
python3 scripts/kb.py init
python3 scripts/kb.py index
python3 scripts/kb.py process
python3 scripts/kb.py agent-context
python3 scripts/kb.py apply-analysis .research-kb/agent-results/*.json --create-nodes
python3 scripts/kb.py quality-guard
python3 scripts/kb.py reconcile-metadata
python3 scripts/kb.py curator-context
python3 scripts/kb.py apply-curation .research-kb/curator-results/*.json
python3 scripts/kb.py build-report
python3 scripts/kb.py query "your question"
python3 scripts/kb.py lint
```

For development or demos, the wrapper can also target a separate vault:

```bash
python3 scripts/kb.py --vault /path/to/user-selected-vault init
```

## Workflow Choice

- **Bootstrap or install a vault:** run `init`, then inspect `AGENTS.md`, templates, and `index.md`.
- **Process PDFs:** run `process`; then run `agent-context`, use the bundled `research-kb.paper-process` agent through Codex subagents when available, and run `apply-analysis --create-nodes`. Use `enrich --create-nodes` only for deterministic fallback drafts.
- **Reconcile metadata:** run `reconcile-metadata` to use Crossref, OpenAlex, and Semantic Scholar to confirm bibliographic metadata and detect duplicate/stale nodes. OpenAlex and Semantic Scholar API keys are optional. Do not use provider metadata as evidence for KB claims.
- **Curate the KB:** run `quality-guard`, then `curator-context`, then delegate to `research-kb.node-curator`, and finally run `apply-curation`. The curator enriches author/concept/variable/method/community nodes, creates active synthesis notes only when evidence is strong, and can propose high-confidence merges that the CLI archives under `archive/merged/`.
- **Query the KB:** run `query`; then read the returned paper and synthesis notes before answering so the final response is grounded in the curated vault. For richer retrieval, use bundled query-side subagents: `research-kb.query` for topic/author/title/metadata clues, `research-kb.claim-support` for suggest-only paragraph support, and `research-kb.synthesis` for previous-studies discussions.
- **Review and repair:** run `review` and `lint`; use `lint --fix` only for safe scaffold/index fixes. Use `--create-missing-linked-notes` only when missing wikilinks are substantively useful candidate nodes.
- **Create graph nodes:** search first, then run `new-node` or create from templates with `status: candidate` when uncertain.

Keep `index.md` at the vault root as the human-facing Obsidian entry point. Keep generated tool state under `.research-kb/`; `.research-kb/index.json` and `.research-kb/search/*.jsonl` are disposable caches regenerated from Markdown notes by `index`, `init`, `process`, `enrich`, `query --save`, `new-node`, or `lint --fix`. For large vaults, query agents should probe `.research-kb/search/*.jsonl` instead of loading the full index into context.

Never create or store a user's KB content inside the installed skill directory.

Canonical Markdown templates live in the installed skill's `templates/` folder. `init` copies them into the selected vault's `templates/` folder without overwriting existing vault templates unless `--force` is passed. Note generation uses this resolution order: vault template override first, installed skill template second, embedded fallback last.

## Source-Grounded Paper Notes

Always preserve `raw_pdf_path` and `pdf_sha256`. Do not overwrite researcher-reviewed notes. If metadata, summaries, or graph links are uncertain, say so in the note using `uncertain_fields`, `#candidate`, or `uncertainty::`.

Paper notes should include:

- one-paragraph source-grounded summary
- research question
- data and participants
- linguistic variables
- social factors
- methods and measures
- key findings with `evidence::` page, section, table, or quote anchors where possible
- links to concepts, variables, methods, communities, related papers, questions, or syntheses

## References

Read `references/vault-schema.md` when you need the folder layout, frontmatter, node types, or relation labels.

Read `references/workflows.md` when you need the step-by-step intake, query, citation-support, synthesis, review, or lint/fix workflow.

Read `references/paper-process-agent.md` when processing PDFs with Codex subagents or when you need the canonical paper understanding/summarization behavior.

Read `references/agent-contract.md` when validating paper-process task JSON or result JSON.

Read `references/node-curator-agent.md` when curating non-paper nodes, creating strong synthesis notes, or applying high-confidence merge/archive plans.

Read `references/agent-capacity.md` before using query-side agents over multiple papers. Query-side agents are expected to handle vaults up to 10,000 papers, each up to about 10,000 words, through staged retrieval and bounded detailed reading.

Read `references/query-agent.md`, `references/claim-support-agent.md`, or `references/synthesis-agent.md` when delegating lookup/discovery, paragraph support, or previous-studies synthesis.
