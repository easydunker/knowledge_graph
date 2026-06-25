# Research KB Workflows

## Vault Selection

1. Use a user-selected Obsidian vault root for all content.
2. Do not store user PDFs, notes, or `.research-kb/` state in the installed skill directory.
3. If the user has not provided a vault path, ask for one before bootstrapping.
4. Bootstrap the selected vault with:

   ```bash
   python3 <skill-dir>/scripts/research_kb.py --vault /path/to/user-selected-vault init
   ```

`init` copies canonical templates from `<skill-dir>/templates/` into `/path/to/user-selected-vault/templates/`. Existing vault templates are treated as researcher customization and are not overwritten unless `init --force` is used. Note generation resolves templates in this order: vault template, installed skill template, embedded fallback.

## Intake and Processing

1. Confirm the PDFs are already in `raw/papers/`.
2. Run `python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault process`.
3. Run `python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault build-jobs refresh`.
4. Run `python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault build-jobs status`.
5. Run `python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault build-jobs export-paper --batch-size 10`.
6. When Codex subagents are available, spawn one worker per exported `.research-kb/agent-tasks/paper/*.agent-task.json` file. Instruct the worker to act as `research-kb.paper-process`, read `references/paper-process-agent.md`, analyze only the task's extracted text, and write one result JSON to the task's `result_path`.
7. If subagents are unavailable, the current agent may perform the same `research-kb.paper-process` contract manually, or another model/human may write the same JSON.
8. Run `python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault build-jobs apply-paper`. This applies returned JSON, creates candidate graph nodes by default, runs quality guard for touched papers, and marks paper jobs complete only when quality passed.
9. Repeat `build-jobs status`, `build-jobs export-paper --batch-size N`, and `build-jobs apply-paper` until no paper jobs remain pending/exported/running/result_written.
10. Run `python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault reconcile-metadata --apply` to use Crossref, OpenAlex, and Semantic Scholar to confirm bibliographic metadata, apply high-confidence metadata cleanup, and produce duplicate/stale candidate clusters. OpenAlex and Semantic Scholar API keys are optional. Omit `--apply` only for report-only reconciliation.
11. Run `python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault build-jobs export-curator --batch-size 20`.
12. When Codex subagents are available, spawn one worker per exported `.research-kb/curator-tasks/jobs/*.curator-task.json` file. Instruct the worker to act as `research-kb.node-curator`, read `references/node-curator-agent.md`, and write one result JSON to the task's `result_path`.
13. Run `python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault build-jobs apply-curator`.
14. Run `python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault build-report`.
15. Inspect generated paper notes in `papers/`, curated graph notes, and the build report.
14. Improve draft notes from the PDF and extracted text only:
   - summary
   - research question
   - data and participants
   - variables and social factors
   - methods and measures
   - key findings
   - limitations
   - useful quotes
15. Add typed wikilinks to existing nodes when substantively relevant.
16. Create new node notes only after searching for duplicates; use `status: candidate` when uncertain.
17. Append important actions to `log.md` and keep `index.md` brief.
18. Let the CLI regenerate `.research-kb/index.json` and `.research-kb/search/*.jsonl`; do not hand-edit generated machine caches.

The processor is deterministic and model-agnostic. It hashes PDFs, extracts metadata/text, creates conservative draft notes, and skips PDFs already represented by `pdf_sha256`.

The model-assisted understanding step is outside the CLI. `build-jobs export-paper` and the lower-level `agent-context` command export portable tasks with instructions, existing metadata, known graph nodes, extracted PDF text, an expected JSON schema, the `research-kb.paper-process` agent name, and a target `result_path`. Any harness can satisfy that contract: Codex subagents, another skill, a local model, a remote model gateway, or a human-edited JSON file.

The `build-jobs` commands are the default for Codex or any quota-constrained harness. They keep vault-local ledgers under `.research-kb/jobs/`, export bounded batches, resume after interruption, and treat paper processing as complete only after the result is applied and quality guard passes. The lower-level commands remain available for harnesses that already provide their own queue:

```bash
python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault agent-context
python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault apply-analysis .research-kb/agent-results/*.json --create-nodes
python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault quality-guard
python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault curator-context
python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault apply-curation .research-kb/curator-results/*.json
```

For real research PDFs, prefer running with a Python environment that has `pymupdf4llm` and `pypdf` installed. `pymupdf4llm` is the preferred backend and extracts LLM-ready Markdown; `pypdf` remains a compatibility fallback. Without optional PDF libraries, the fallback extractor is intentionally conservative: it may create useful hash-tracked draft notes, but title, author, and text fields may be incomplete and should stay marked as uncertain.

`apply-analysis` is conservative. It applies source-grounded sections only from returned JSON, preserves researcher-reviewed notes unless `--force` is passed, marks inferred links as `#candidate`, creates `status: candidate` nodes only with `--create-nodes`, and leaves paper notes in review status.

`quality-guard` records durable build quality state. `build-jobs apply-paper` runs quality guard for touched papers automatically. Quality-failed paper notes remain searchable, but they are skipped by curation and synthesis creation. If a query later loads a quality-failed paper, the harness should load full extracted/source text before using it as evidence.

`reconcile-metadata` uses Crossref, OpenAlex, and Semantic Scholar only as bibliographic authorities. It may confirm title, DOI, year, venue, author display names, and stable external IDs; it also generates duplicate/stale-node clusters for curation under `.research-kb/reconciliation/`. It must not add papers, cite provider abstracts, or use external metadata as evidence for scholarly claims. Crossref needs no API key. OpenAlex and Semantic Scholar API keys are optional; when absent, the harness should use unauthenticated requests with conservative rate limits.

`build-jobs export-curator` and the lower-level `curator-context` export node curation tasks from quality-passed paper evidence and metadata reconciliation clusters. `build-jobs apply-curator` and the lower-level `apply-curation` can rewrite non-paper nodes, create active synthesis notes when evidence is strong, and apply high-confidence merge plans by moving old notes into `archive/merged/` or stale invalid notes into `archive/invalid/`.

`build-report` summarizes paper counts, quality failures, curated nodes, curator-created syntheses, archived notes, lint counts, and notes needing user review.

`enrich --create-nodes` remains a deterministic fallback that uses text heuristics only. Use it for regression tests, offline smoke tests, or when no agent/subagent reasoning is available.

## Query: Idea to Papers and Directions

1. Run:

   ```bash
   python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault query "idea text" --mode idea
   ```

2. Read the returned paper notes and any matched concept, variable, method, community, or synthesis notes.
3. Prefer typed evidence paths over keyword-only matches.
4. Answer with relevant KB papers, why each matters, evidence paths, possible directions, and gaps.
5. If the answer is useful and should compound, save it as a question or synthesis note:

   ```bash
   python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault query "idea text" --mode idea --save questions/short-slug.md
   ```

For topic, author, title, DOI, year, method, variable, or other clear clue searches, a Codex harness may delegate to `research-kb.query`. The query agent should support vaults up to 10,000 papers, each up to about 10,000 words, by using the index and query outputs before reading detailed paper notes. It should return evidence packets, not just prose.

## Query: Draft to Supporting Citations

1. Run `query --mode draft` with the paragraph or claim.
2. Identify claims that are supported, complicated, contradicted, or missing support in the current KB.
3. Recommend only citations represented by existing paper notes.
4. Flag overbroad claims rather than smoothing over weak evidence.

For paragraph or multi-paragraph enrichment, a Codex harness may delegate to `research-kb.claim-support`. It must suggest only: split the prose into claims, suggest supporting or complicating KB papers, report missing support, and avoid rewriting unless the user explicitly asks.

## Query: Question to Relevant Papers

1. Run `query --mode question`.
2. Read matched papers and synthesis notes.
3. Provide a short answer from the current KB only.
4. State what the KB does not yet cover.

For "discuss previous studies" requests, a Codex harness may delegate to `research-kb.synthesis`. It should search the corpus-scale index first, select a bounded detailed subset for synthesis, compare papers by author/topic/method/variable/community/finding as appropriate, and report coverage limits.

## Review and Fix

Use:

```bash
python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault review
python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault lint
python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault lint --fix
python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault index
```

`review` lists paper notes still marked `needs_review`, `agent_draft`, or `quality_failed`.

`lint` checks for missing folders, unprocessed PDFs, missing `raw_pdf_path`, missing `pdf_sha256`, missing title/year/authors, missing summaries, missing graph links, duplicate papers, broken wikilinks, orphan nodes, stale Key Papers lists, live links to archived notes, and synthesis notes without paper links.

`index` refreshes root `index.md`, `.research-kb/index.json`, and the JSONL probe indexes under `.research-kb/search/`.

`lint --fix` creates missing scaffold files and refreshes both indexes. Add `--create-missing-linked-notes` only when it is acceptable to create candidate stubs for broken wikilinks.

## Creating Nodes

Use `new-node` for a clean template:

```bash
python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault new-node concept "Indexicality"
python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault new-node variable "Mandarin rhotics" --status candidate
```

Before creating a node, search filenames, aliases, headings, and full text. Do not create duplicate pages.
