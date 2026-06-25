# Sociolinguistics and Sociophonetics Research Knowledge Base

This brief proposes a Markdown-first, Obsidian-native knowledge base for a sociolinguistics and sociophonetics researcher. V1 should focus on the simplest useful action: the researcher drops raw PDF papers into the vault and asks the knowledge base to process them.

## 1. Current Design Position

V1 core:

```text
Raw PDF intake zone
  -> agent extracts metadata/text
  -> agent creates Obsidian paper notes
  -> researcher reviews/edits in Obsidian
  -> agents use Markdown notes for search, synthesis, and brainstorming
```

Core decisions:

- Raw PDF files are the primary input for v1.
- Obsidian Markdown is the source of truth for the knowledge base.
- Agents update only the Obsidian vault.
- Zotero is not part of the v1 core; it should be designed as an optional plugin.
- No SQLite or vector database is required for the core v1.
- Crossref, OpenAlex, and Semantic Scholar may be used as optional bibliographic metadata authorities for reconciliation, duplicate detection, and author/title cleanup. They are not evidence sources for KB claims.
- The graph is expressed through Markdown links, frontmatter, tags, aliases, and relation-style bullets.
- Paper processing is model-agnostic in the CLI. Paper understanding is an agent/subagent contract: export extracted-text tasks, let any harness model produce structured JSON, then apply it back to Markdown.
- Deterministic extraction/enrichment remains available as an offline fallback and regression-test mode.

This keeps v1 local, inspectable, and easy to test with real papers.

## 2. Comparison With Karpathy's LLM Wiki

Andrej Karpathy's "LLM Wiki" pattern is a strong fit because it separates raw sources from an agent-maintained working wiki. Its central idea is that knowledge should compound: useful synthesis, cross-links, contradictions, and answers should be written back into the wiki rather than rediscovered from scratch every time.

Keep these parts:

- Raw sources remain stable and traceable.
- Agents help maintain Markdown pages.
- Obsidian is the human reading/editing interface.
- `index.md` and `log.md` provide navigation and memory.
- Useful query answers can be filed back into the vault.
- Periodic linting can catch orphan notes, missing links, duplicate concepts, and stale synthesis.

Modify these parts for this research use case:

- Raw PDFs are the primary intake source in v1.
- The graph is initially Markdown-native, not database-native.
- Paper notes stay close to source evidence.
- Concept, variable, method, community, question, and synthesis notes are the evolving interpretation layer.
- Zotero and discovery APIs are optional plugins, not trusted core dependencies.

In short: Karpathy's wiki is the right memory pattern; v1 should be an Obsidian vault that turns raw PDFs into durable, linked research notes.

## 3. Why Raw PDF First

Raw PDF input matches the lowest-friction researcher behavior:

> "I found a paper. I dropped it into the KB. Please process it."

This gives the system an immediate practical loop without requiring Zotero setup, API keys, graph databases, or external discovery tools.

Benefits:

- fastest path to a working prototype
- local-first and private
- no dependence on Zotero metadata quality
- easy to inspect and correct
- compatible with later Zotero integration
- good test of the actual hard problem: extracting useful scholarly structure from papers

The v1 bottleneck is not scale. It is whether the paper notes, links, and syntheses are useful enough for real academic thinking.

## 4. What Counts as the Graph

In v1, the graph is not a separate database. It is an Obsidian/Markdown graph with typed conventions.

There are two layers:

```text
Visible graph:
Obsidian wikilinks between notes

Typed graph:
relation-style bullets inside notes, e.g.
- studies_variable:: [[variables/mandarin-rhotics]]
- uses_method:: [[methods/mixed-effects-models]]
```

Obsidian gives the human-visible graph. The typed bullets give agents more precise edges to parse.

Graph structure lives in Markdown:

- frontmatter fields
- wikilinks
- tags
- aliases
- relation sections
- recurring relation-style bullets

Agents may maintain `.research-kb/index.json` as a generated cache of note paths, node types, links, and typed edges. For large vaults, agents should probe `.research-kb/search/*.jsonl` instead of reading the whole cache. These caches are not authoritative; deleting and regenerating them from Markdown should be safe.

Example:

```markdown
---
type: paper
paper_id: zhang-tone-2023
intake_source: raw_pdf
raw_pdf_path: raw/papers/zhang-tone-2023.pdf
title: "..."
year: 2023
kb_status: needs_review
review_state: agent_draft
---

## Linguistic Variables

- studies_variable:: [[variables/tone-register]]

## Social Factors

- tests_social_factor:: [[concepts/gender]]

## Methods and Measures

- uses_method:: [[methods/mixed-effects-models]]
- measured_by:: [[methods/f0-contour-analysis]]

## Key Findings

- finding:: Tone realization differs by speaker group in interaction with stance.
  - supports:: [[concepts/indexicality]]
  - evidence:: p. 14, Table 2
```

This is readable for the researcher and structured enough for agents.

## 5. Graph Nodes

In v1, every important node is a Markdown note. The note's `type` frontmatter defines the node type.

Core node types:

| Node type | Folder | Meaning |
| --- | --- | --- |
| `paper` | `papers/` | A source-grounded note for one raw PDF |
| `concept` | `concepts/` | A theory, construct, social factor, or analytic category |
| `variable` | `variables/` | A linguistic variable, variant set, feature, or realization |
| `method` | `methods/` | A method, measure, task, model, instrument, or software tool |
| `community` | `communities/` | A speech community, population, place, language variety, or participant group |
| `research_question` | `questions/` | An active idea, literature question, or project seed |
| `synthesis` | `syntheses/` | A cross-paper literature memo or thematic synthesis |

Examples:

```text
papers/labov-1966-social-stratification.md
concepts/indexicality.md
concepts/gender.md
variables/mandarin-rhotics.md
methods/mixed-effects-models.md
methods/f3-lowering.md
communities/beijing-mandarin-speakers.md
questions/2026-06-23-rhotics-and-gendered-identity.md
syntheses/rhotics-and-indexicality.md
```

Node roles:

- Paper nodes should stay close to what a specific paper says.
- Concept nodes can accumulate definitions, debates, and theoretical tensions.
- Variable nodes describe linguistic objects and link to papers that study them.
- Method nodes describe analytical tools and link to papers that use them.
- Community nodes describe populations, places, language varieties, and samples.
- Research question nodes capture the researcher's active thinking.
- Synthesis nodes produce cross-paper arguments, gap maps, and literature overviews.

## 6. Graph Edges

Edges are Markdown links with relation labels. A plain Obsidian link says two notes are related. A typed edge says how they are related.

Plain link:

```markdown
[[concepts/indexicality]]
```

Typed edge:

```markdown
- supports:: [[concepts/indexicality]]
```

Core edge types:

| Edge | Typical source | Typical target | Meaning |
| --- | --- | --- | --- |
| `studies_variable::` | paper | variable | Paper studies this linguistic variable |
| `has_variant::` | variable | variable/concept | Variable has this variant or realization |
| `measured_by::` | paper/variable | method | Variable or paper uses this measure |
| `uses_method::` | paper | method | Paper uses this method/model/task |
| `uses_dataset::` | paper | method/community/synthesis | Paper uses this corpus/dataset |
| `samples_community::` | paper | community | Paper samples this population/place/variety |
| `tests_social_factor::` | paper | concept | Paper analyzes this social factor |
| `finding::` | paper | text block | Paper reports this finding |
| `supports::` | finding/paper/synthesis | concept/synthesis/question | Evidence supports a claim or concept |
| `complicates::` | finding/paper/synthesis | concept/synthesis/question | Evidence complicates a claim |
| `contradicts::` | finding/paper/synthesis | concept/synthesis/question | Evidence contradicts a claim |
| `extends::` | paper/synthesis | concept/paper/synthesis | Extends prior work |
| `relevant_to::` | paper/concept/variable/method | research_question | Relevant to an active question |
| `evidence::` | finding | page/table/quote text | Source location for a claim |

Example mini graph inside a paper note:

```markdown
## Graph Edges

- studies_variable:: [[variables/mandarin-rhotics]]
- tests_social_factor:: [[concepts/gender]]
- samples_community:: [[communities/beijing-mandarin-speakers]]
- uses_method:: [[methods/sociolinguistic-interview]]
- uses_method:: [[methods/mixed-effects-models]]
- measured_by:: [[methods/f3-lowering]]

## Key Findings

- finding:: Rhotics are used stylistically across gendered personae.
  - evidence:: p. 14, Table 2
  - supports:: [[concepts/indexicality]]
  - complicates:: [[concepts/speaker-category]]
```

This represents paths such as:

```text
paper -> studies_variable -> Mandarin rhotics
paper -> tests_social_factor -> gender
paper -> uses_method -> mixed-effects models
finding -> supports -> indexicality
```

The design rule is: paper notes should contain enough typed edges that an agent can reconstruct why the paper matters.

## 7. Core Note Types

Start with seven note types:

| Note type | Folder | Purpose |
| --- | --- | --- |
| Paper | `papers/` | Source-grounded note for one raw PDF |
| Concept | `concepts/` | Theory or analytic construct |
| Variable | `variables/` | Linguistic variable, variant, or feature |
| Method | `methods/` | Method, measure, model, tool, or task |
| Community | `communities/` | Speech community, population, place, or variety |
| Research question | `questions/` | Brainstorming and project seeds |
| Synthesis | `syntheses/` | Cross-paper literature synthesis |

This is enough for sociolinguistics and sociophonetics without forcing a rigid ontology.

## 8. Raw PDF Intake

Recommended raw zone:

```text
raw/
  papers/
  processed/
  failed/
```

V1 should focus on PDFs only. Other inputs such as BibTeX, RIS, DOI lists, and Zotero metadata can come later.

Workflow:

1. Researcher drops PDFs into `raw/papers/`.
2. Researcher asks the KB agent to process the raw zone.
3. Agent extracts available PDF metadata and text.
4. CLI creates a draft paper note in `papers/`.
5. CLI records `intake_source: raw_pdf`, `raw_pdf_path`, and `pdf_sha256`.
6. CLI generates a stable local `paper_id`.
7. Agent exports a portable paper-understanding task with extracted text and an expected JSON schema.
8. The bundled `research-kb.paper-process` agent analyzes the task from extracted text only, returning structured summaries, findings, evidence anchors, and candidate graph links. In Codex, spawn one worker subagent per exported paper task.
9. CLI applies the returned JSON to Markdown and marks uncertainty clearly.
10. Agent proposes links to concepts, variables, methods, and communities.
11. Agent moves successfully processed PDFs to `raw/processed/` or records their processed status.
12. Researcher reviews the note in Obsidian.

Example frontmatter:

```yaml
---
type: paper
paper_id: zhang-tone-2023
intake_source: raw_pdf
raw_pdf_path: raw/processed/zhang-tone-2023.pdf
title: "..."
authors: []
year:
doi:
publication:
kb_status: needs_review
review_state: agent_draft
aliases: []
created:
updated:
---
```

## 9. Zotero as Optional Plugin

Zotero should be a plugin, not part of v1 core.

Plugin purpose:

- read a Zotero/Better BibTeX export
- copy Zotero metadata and tags into paper notes
- reconcile raw-PDF notes with Zotero citekeys
- optionally create paper notes from Zotero entries when the researcher enables the plugin

Recommended plugin path:

```text
Zotero local library
  -> Better BibTeX auto-export
  -> plugins/zotero/library.bib
  -> agent reconciliation with existing paper notes
```

Plugin rules:

- read-only by default
- no Zotero write-back in v1
- no direct writes to `zotero.sqlite`
- Zotero metadata should enrich existing notes, not replace researcher-reviewed notes silently

This keeps the core KB usable even if the researcher does not configure Zotero.

## 10. Metadata Reconciliation APIs

Crossref, OpenAlex, and Semantic Scholar should be available as optional metadata reconciliation providers. Their purpose is to reduce duplicate or invalid notes caused by imperfect PDF extraction, especially OCR-damaged titles and author names.

The trusted KB evidence boundary does not change. External provider records may clean bibliographic identity, but they must not add papers to the KB by themselves and must not support scholarly claims.

Core KB answers should rely on:

- processed raw PDFs
- Obsidian paper notes
- concept/variable/method/community/question/synthesis notes
- explicit citations and evidence in the vault

Allowed reconciliation uses:

- confirm DOI, title, year, venue, and author display names
- store stable external IDs such as DOI, OpenAlex work/author IDs, and Semantic Scholar paper/author IDs
- detect duplicate paper notes by DOI, title, year, author list, and stable provider IDs
- detect duplicate or invalid author nodes caused by OCR or PDF extraction errors
- provide candidate duplicate/stale-node clusters to the curator

Provider policy:

- Crossref is preferred for DOI/title/venue metadata and requires no API key.
- OpenAlex is preferred for work IDs, author IDs, institutions, and broad scholarly graph metadata. It must work without an API key; an OpenAlex API key may be configured optionally.
- Semantic Scholar is a secondary cross-check for paper and author identity. Its API key is optional.

External metadata should be cached under `.research-kb/metadata-cache/` and reconciliation reports should be written under `.research-kb/reconciliation/`. These are build artifacts, not source-of-truth notes.

Optional later discovery mode remains separate:

```text
research idea/question
  -> external discovery assistant
  -> candidate papers
  -> researcher reviews
  -> researcher drops selected PDFs into raw/papers/
  -> papers enter KB through raw PDF intake
```

External candidates should never be silently treated as KB evidence.

See [Metadata Reconciliation Plan](metadata-reconciliation-plan.md).

## 11. No Core Vector DB or SQLite

For v1, use Obsidian search, tags, links, and structured Markdown. A separate vector database or SQLite graph would add overhead before the note schema has proven itself.

Possible later upgrades:

- SQLite generated from Markdown if structured queries become painful.
- SQLite FTS if keyword search over notes needs to be automated outside Obsidian.
- Local embeddings if fuzzy semantic search becomes important.
- Crossref/OpenAlex/Semantic Scholar metadata reconciliation if duplicate detection and bibliographic cleanup need external identifiers.
- OpenAlex/Semantic Scholar discovery plugin if literature discovery becomes a separate workflow.

## 12. Agent Workflows

### Workflow A: Process Raw PDFs

1. Agent scans `raw/papers/`.
2. Agent detects unprocessed PDFs.
3. Agent extracts text and metadata.
4. CLI creates a draft note in `papers/`.
5. CLI records PDF path, PDF hash, extraction status, and uncertain fields.
6. Agent exports `agent-context` JSON for each paper note. The task names `research-kb.paper-process` and includes a result path.
7. A Codex worker subagent running the bundled paper process agent analyzes the extracted text only and returns JSON matching the schema. If subagents are unavailable, another harness model or human can satisfy the same contract.
8. CLI applies the returned analysis to add a concise summary, research question, data, variables, social factors, methods, findings, limitations, useful quotes, and evidence anchors.
9. Agent proposes Markdown links and creates candidate graph nodes only when requested.
10. Optional metadata reconciliation checks Crossref, OpenAlex, and Semantic Scholar for bibliographic identity, title/author cleanup, and duplicate/stale candidate clusters.
11. Curator agents review graph-integrity tasks, including duplicate or invalid non-paper notes, and propose high-confidence merge/archive actions.
12. Agent updates `index.md` and `log.md`.

### Workflow B: Given an Idea, Find Papers and Directions

Input: a loose research idea.

Agent should:

- Search paper notes, synthesis notes, concepts, variables, methods, communities, and questions.
- Match query entities to graph nodes.
- Traverse typed edges and backlinks from matched nodes.
- Return relevant KB papers only.
- Explain relevance using evidence paths and snippets.
- Suggest possible directions.
- State gaps in the current vault.

Recommended traversal procedure:

1. Extract entities from the idea: variables, social factors, methods, communities, concepts, and language varieties.
2. Resolve entities to existing nodes by filename, aliases, headings, and full-text search.
3. From matched nodes, find paper notes that link to them through typed edges.
4. Prefer typed edges over untyped mentions.
5. Rank papers higher when they match multiple nodes or contain useful `finding::` and `evidence::` lines.
6. Return evidence paths, for example `idea -> [[variables/mandarin-rhotics]] -> studies_variable -> [[papers/zhang-2023-rhotics]] -> finding -> [[concepts/indexicality]]`.

### Workflow C: Given Writing, Find Papers to Support It

Input: a paragraph, section, or draft.

Agent should:

- Extract claims from the text.
- Match claims to paper notes, findings, concepts, methods, and syntheses.
- Use typed edges such as `supports::`, `complicates::`, `contradicts::`, and `evidence::`.
- Suggest supporting or complicating citations from the curated KB.
- Flag unsupported or overbroad claims.
- Suggest where synthesis notes can enrich the writing.

### Workflow D: Given a Question, Find Relevant Papers

Input: a research or literature question.

Agent should:

- Search the Obsidian vault.
- Traverse Markdown links from concepts, variables, methods, communities, and syntheses to papers.
- Prefer explicit typed paths over keyword matches.
- Return relevant papers with short rationales.
- Include evidence paths such as `question -> concept -> paper -> finding`.
- Identify missing areas in the KB.

### Workflow E: Lint the Vault

Periodic checks:

- PDF in `raw/papers/` without a paper note.
- paper note missing `raw_pdf_path`.
- paper note missing title/year/authors.
- paper note without summary.
- paper note without links to any concept, variable, method, or community.
- concept page with no linked papers.
- duplicate concepts or variables.
- research question with no relevant papers.
- synthesis note that has not been updated after new related papers were added.

## 13. Recommended Vault Layout

The Codex skill and helper scripts are reusable tooling. They should live outside the user's research content, such as in `~/.codex/skills/research-kb/` or a development repository. Each user or project should choose a separate Obsidian vault root for the actual knowledge base content.

Agents should always operate on the selected vault path explicitly, for example `--vault /path/to/user-vault`, and should not write PDFs, notes, or `.research-kb/` state into the installed skill directory.

Canonical templates ship with the installed skill and are copied into each selected vault during `init`. The vault-local `templates/` folder is the user's customization layer; generation should prefer vault templates, then installed skill templates, then embedded fallbacks.

```text
research-kb/
  index.md
  log.md
  AGENTS.md

  .research-kb/
    config.yaml
    index.json

  raw/
    papers/
    processed/
    failed/

  papers/
  concepts/
  variables/
  methods/
  communities/
  questions/
  syntheses/
  templates/

  plugins/
    zotero/
      library.bib
      README.md
```

The `plugins/zotero/` folder exists as a placeholder for a later optional integration; it is not required for v1.

`index.md` is the human-facing Obsidian entry point. `.research-kb/index.json` is a generated machine cache for agents and CLI tools; it should be regenerated from Markdown notes rather than treated as the source of truth.

## 14. MVP Build Sequence

### Phase 1: Vault Foundation

- Create folders and templates.
- Create raw PDF intake folders.
- Create `AGENTS.md` rules for PDF processing, citation, linking, uncertainty, and updates.
- Create `index.md`, `log.md`, `.research-kb/config.yaml`, and `.research-kb/index.json`.

Success: raw PDFs can be detected from `raw/papers/`, and the machine index can be refreshed from the Markdown graph.

### Phase 2: First 10 PDFs

- Drop 10 handpicked PDFs into `raw/papers/`.
- Generate draft paper notes.
- Extract summaries, variables, methods, findings, limitations, useful quotes, and links.
- Create starter concept/variable/method/community pages.

Success: the researcher can browse papers and follow useful links in Obsidian.

### Phase 3: First Agent Queries

- Test the three target workflows:
  - idea -> relevant papers and directions
  - draft -> supporting/enriching citations
  - question -> relevant papers
- Save good outputs as question or synthesis notes.

Success: answers are useful using only the processed PDF vault.

### Phase 4: Vault Health

- Add lint checks for unprocessed PDFs, missing metadata, missing summaries, orphan concepts, duplicate pages, and stale syntheses.
- Add metadata reconciliation checks for duplicate/stale non-paper nodes, provider match confidence, and unresolved bibliographic conflicts.

Success: the KB improves as it grows.

### Phase 5: Optional Plugins

Only after raw-PDF-first workflow proves useful:

- Zotero/Better BibTeX plugin
- Crossref/OpenAlex/Semantic Scholar metadata reconciliation
- SQLite/FTS generated from Markdown
- local embeddings
- OpenAlex/Semantic Scholar discovery plugin
- review dashboard or small web app

## 15. Design Decisions to Discuss

1. Should processed PDFs be moved to `raw/processed/`, or kept in `raw/papers/` with a status log?
2. Should paper filenames use generated `paper_id`, extracted DOI slug, or author-year-title slug?
3. Should PDF text extraction happen automatically, or should v1 allow manual paste/extracted text fallback?
4. Should raw-PDF paper notes be treated as trusted immediately, or as `needs_review` until checked?
5. Should agents create new concept/variable/method pages freely, or only propose them?
6. Should the Zotero plugin reconcile by DOI, title, PDF hash, or citekey?
7. Which metadata reconciliation actions should auto-apply, and which should always require researcher review?
8. Should the first test focus on brainstorming, draft support, or question answering?

## 16. Current Recommendation

Build v1 as an Obsidian vault with raw PDF intake and optional metadata reconciliation.

Use Markdown as the durable graph:

```text
raw PDFs
  -> paper notes
  -> concepts
  -> variables
  -> methods
  -> communities
  -> questions
  -> syntheses
```

Do not add Zotero, SQLite, vector search, discovery automation, or write-back automation until the researcher has used the raw-PDF workflow with real papers. Crossref, OpenAlex, and Semantic Scholar may be added earlier as metadata reconciliation providers because they reduce duplicate/stale nodes without changing the evidence boundary.

The first useful demo should be:

> Drop 10 PDFs into `raw/papers/`, generate Obsidian notes, then ask: "Given this research idea, what papers in my curated KB are relevant, what do they support, and what directions could I pursue?"

## 17. Sources Consulted

- Andrej Karpathy, "LLM Wiki": https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- Obsidian documentation: https://help.obsidian.md/
- Better BibTeX automatic export: https://retorque.re/zotero-better-bibtex/exporting/auto/
- Zotero Web API documentation: https://www.zotero.org/support/dev/web_api/v3/basics
- Zotero direct SQLite access warning: https://www.zotero.org/support/dev/client_coding/direct_sqlite_database_access
- Microsoft GraphRAG: https://microsoft.github.io/graphrag/
- GraphRAG paper: https://arxiv.org/abs/2404.16130
- LightRAG project: https://github.com/HKUDS/LightRAG
- HippoRAG paper: https://arxiv.org/abs/2405.14831
- CLDF specification: https://cldf.clld.org/
- OLAC metadata/language archive standard overview: https://standards.clarin.eu/sis/views/view-sb.xq?id=SBOLAC
