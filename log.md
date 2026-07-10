# KB Log

Record important ingest, review, synthesis, and cleanup actions here.

## 2026-06-23

- Vault scaffold created.
- Implemented reusable KB helper CLI and installable Codex skill covering raw PDF intake, graph querying, review queues, linting, and safe fixes.
- Tested intake on public ACL research PDFs in temporary vaults and optimized metadata extraction, fallback PDF parsing, ACL year inference, author heuristics, lint output, and extraction-confidence reporting.
- Added and passed a full-cycle public PDF quality evaluation covering process, enrich, candidate node creation, lint, review, and query ranking.
- Opened the vault in Obsidian and set the Graph view filter to the KB node folders (`papers`, `concepts`, `variables`, `methods`, `communities`, `questions`, `syntheses`).
- Implemented the split index design: root `index.md` for human Obsidian navigation and `.research-kb/index.json` for generated machine-readable tool state.
- Clarified and tested the tool-vs-vault separation: the installed skill is reusable tooling, while each user's KB content lives in a user-selected Obsidian vault passed with `--vault`.
- Ran the full public-PDF sample workflow in a temporary vault, reviewed note/query quality, and improved extraction cleanup, page-aware evidence anchors, fallback abstract selection, identity-edge precision, query scoring, and evaluation timing/quality checks.
- Replaced the built-in provider-specific LLM path with a model-agnostic agent contract: `agent-context` exports portable paper-analysis tasks, `apply-analysis` imports returned JSON, and deterministic `process`/`enrich` remain provider-free.

## 2026-07-10

- Added an end-to-end, researcher-facing build contract so a harness must finish paper processing and node curation before calling a KB build complete; documented the small final spot-check and exception workflow for non-technical researchers.
- Made curation accept only quality-passed paper notes as evidence, added one automatic retry allowance to new paper jobs, and made build status recommend retrying failed jobs.
- Updated build reports with an explicit workflow state, concise exception output, and a deterministic sample of quality-passed notes for researcher audit.
