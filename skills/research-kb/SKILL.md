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

For a non-technical researcher, the normal request is simply: **"Build my research knowledge base from the PDFs in `raw/papers/`. Continue until the build is complete, then give me the researcher check."** Read `references/researcher-guide.md` before presenting this workflow or its final report. The researcher should only need to prepare the PDFs and inspect the final spot-check sample and exceptions; do not ask them to export jobs, copy JSON files, or decide which command comes next.

When Codex subagents are available, process PDFs with the bundled paper process agent by default. For quota-constrained harnesses, prefer the resumable `build-jobs` workflow: export a small batch, spawn `research-kb.paper-process` workers for that batch, apply returned results, run quality guard automatically, then resume later from the vault-local job ledger. `agent-context` and `build-jobs export-paper` include the full retained extracted text by default. Use `--max-chars <N>` only when a smaller/local harness needs an explicit task-size cap; `--max-chars 0` means no task-level cap.

```bash
VAULT="/path/to/user-selected-vault"
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" init
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" index
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" process
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" build-jobs refresh
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" build-jobs status
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" build-jobs export-paper --batch-size 10
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" build-jobs apply-paper
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" reconcile-metadata --apply
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" build-jobs export-curator --batch-size 20
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" build-jobs apply-curator
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" build-report
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" query "rhotics, gender, and identity" --mode idea
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" review
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" lint
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" lint --fix
```

For real PDFs, prefer a Python environment with `pymupdf4llm` and `pypdf` installed. `pymupdf4llm` is the preferred extraction backend because it produces LLM-ready Markdown; `pypdf` remains a compatibility fallback. If optional PDF libraries are unavailable, the CLI still creates conservative hash-tracked drafts and marks uncertain extraction fields for review.

Quota-resilient agent-assisted paper understanding:

1. Run `process` to create paper notes with `raw_pdf_path` and `pdf_sha256`.
2. Run `build-jobs refresh` to create or update `.research-kb/jobs/*.jsonl`.
3. Run `build-jobs export-paper --batch-size 5` to `20`, depending on available quota.
4. Read `references/paper-process-agent.md` and `references/agent-contract.md`.
5. In Codex, spawn one worker subagent per exported task. Give each worker exactly one task JSON path and the instruction to act as `research-kb.paper-process`, write only the result JSON to the task's `result_path`, and avoid editing notes directly.
6. Run `build-jobs apply-paper`. This applies returned JSON, creates candidate graph nodes by default, runs `quality-guard` for touched papers, and marks a paper job complete only when quality passed.
7. Repeat `build-jobs status`, `build-jobs export-paper --batch-size N`, and `build-jobs apply-paper` until no pending paper jobs remain.
8. Run `reconcile-metadata --apply` to query Crossref, OpenAlex, and Semantic Scholar for bibliographic metadata, write high-confidence title/DOI/year/venue/author cleanup to paper frontmatter, and produce duplicate/stale node clusters. OpenAlex and Semantic Scholar API keys are optional. Omit `--apply` only for dry-run/report-only reconciliation.
9. Run `build-jobs export-curator --batch-size 10` to `20`, spawn `research-kb.node-curator` workers for exported tasks, and run `build-jobs apply-curator` to enrich non-paper nodes, create strong active synthesis notes, and apply high-confidence merge/archive plans.

Use `enrich --create-nodes` only as deterministic offline fallback when no agent/subagent reasoning is available.

## Harness Subagent Guidance

This skill can tell a harness how to use subagents, but it does not itself grant permission to spawn them. If the current harness requires explicit authorization, the user should say something like: "Use subagents for paper processing and curation."

When the user explicitly authorizes subagents or delegated agent work, the harness should:

1. Run `agent-context`.
2. Spawn one `research-kb.paper-process` worker per `.research-kb/agent-tasks/*.agent-task.json`, or process tasks in batches for large vaults.
3. Apply results with `apply-analysis --create-nodes`.
4. Run `quality-guard`.
5. Run `reconcile-metadata --apply`, using Crossref, OpenAlex, and Semantic Scholar only for bibliographic cleanup. This writes only high-confidence paper metadata updates and never treats provider metadata as evidence for scholarly claims.
6. Run `curator-context`.
7. Spawn one `research-kb.node-curator` worker per `.research-kb/curator-tasks/*.curator-task.json`, or process tasks in batches for large vaults.
8. Apply results with `apply-curation`.
9. Run `lint`, `index`, and `build-report`.

For quota-constrained Codex runs, replace steps 1-8 with the job-aware commands: `build-jobs refresh`, `build-jobs export-paper --batch-size N`, `build-jobs apply-paper`, `reconcile-metadata --apply`, `build-jobs export-curator --batch-size N`, and `build-jobs apply-curator`. Keep each worker scoped to one task JSON and require it to write only the task's `result_path`. For large vaults, batch workers by retrieval shard or note type so the root harness never needs to load the whole graph or all paper summaries at once.

### Completion Contract For A Full Build

When the user asks to build or update a KB, the harness owns the queue. Do not stop after `process`, `enrich`, applying a single batch, or creating candidate nodes. For a batch of roughly 60 papers, use bounded paper batches (normally 5 to 10) and repeat this cycle until the paper ledger has no work-in-progress jobs (`pending`, `retry_pending`, `exported`, `running`, `result_written`, or `applied`). A failed or quality-failed job is an explicit exception, never successful completion:

1. `process`, then `build-jobs refresh` and `build-jobs status`.
2. Export the next paper batch, delegate every exported task, and apply its returned results.
3. If a result fails validation or quality, retry that specific paper once with the failure report in its worker instructions. Keep any paper that still fails in the exception list; never silently treat it as complete or use it for curation.
4. Reconcile metadata after the paper queue is terminal.
5. Export, delegate, and apply curator batches until the curator ledger has no unfinished jobs. A curator failure that has exhausted its retries belongs in the exception list; curators must receive only quality-passed paper evidence.
6. Run `lint`, `index`, and `build-report`. Report `ready_for_researcher_spot_check` only when both job ledgers are complete, lint has no errors, and no unresolved exception remains.

If the harness cannot delegate workers, explain that paper understanding is not yet running and ask for permission or a configured model runner; deterministic node creation is not an acceptable substitute for populated paper or graph notes.

When this repository is the vault, the wrapper is:

```bash
python3 scripts/kb.py init
python3 scripts/kb.py index
python3 scripts/kb.py process
python3 scripts/kb.py build-jobs refresh
python3 scripts/kb.py build-jobs export-paper --batch-size 10
python3 scripts/kb.py build-jobs apply-paper
python3 scripts/kb.py reconcile-metadata --apply
python3 scripts/kb.py build-jobs export-curator --batch-size 20
python3 scripts/kb.py build-jobs apply-curator
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
- **Process PDFs:** run `process`; then prefer `build-jobs refresh`, `build-jobs export-paper --batch-size N`, subagent workers, and `build-jobs apply-paper` so interrupted or quota-limited runs can resume. Use lower-level `agent-context` and `apply-analysis --create-nodes` only when the harness has its own queue system. Use `enrich --create-nodes` only for deterministic fallback drafts.
- **Reconcile metadata:** run `reconcile-metadata --apply` during the default build to use Crossref, OpenAlex, and Semantic Scholar to confirm bibliographic metadata, write high-confidence title/DOI/year/venue/author cleanup, and detect duplicate/stale nodes. OpenAlex and Semantic Scholar API keys are optional. Do not use provider metadata as evidence for KB claims; omit `--apply` only for report-only reconciliation.
- **Curate the KB:** after paper jobs are quality-passed and metadata is reconciled, prefer `build-jobs export-curator --batch-size N`, delegate to `research-kb.node-curator`, and run `build-jobs apply-curator`. The lower-level `curator-context` and `apply-curation` commands remain available for harness-owned queues. The curator enriches author/concept/variable/method/community nodes, creates active synthesis notes only when evidence is strong, and can propose high-confidence merges that the CLI archives under `archive/merged/`.
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

Read `references/researcher-guide.md` when the user is a non-technical researcher, requests an end-to-end build, or needs to understand what to inspect after a build.

Read `references/paper-process-agent.md` when processing PDFs with Codex subagents or when you need the canonical paper understanding/summarization behavior.

Read `references/agent-contract.md` when validating paper-process task JSON or result JSON.

Read `references/node-curator-agent.md` when curating non-paper nodes, creating strong synthesis notes, or applying high-confidence merge/archive plans.

Read `references/agent-capacity.md` before using query-side agents over multiple papers. Query-side agents are expected to handle vaults up to 10,000 papers, each up to about 10,000 words, through staged retrieval and bounded detailed reading.

Read `references/query-agent.md`, `references/claim-support-agent.md`, or `references/synthesis-agent.md` when delegating lookup/discovery, paragraph support, or previous-studies synthesis.
