# Obsidian V1 Blueprint: Sociolinguistics and Sociophonetics KB

This blueprint describes a first build of the researcher's knowledge base using raw PDF intake, Obsidian, Markdown templates, and agents that operate on the vault. Zotero is treated as an optional plugin, not part of v1 core.

## 1. Product Thesis

The v1 KB should be a personal scholarly memory system:

- The researcher drops PDFs into the vault.
- Agents process those PDFs into structured Markdown paper notes.
- Obsidian becomes the human review, reading, and synthesis surface.
- Agents help create, link, search, synthesize, and lint notes.
- Zotero and external discovery tools can be added later as plugins.

The aim is not to automate scholarship. The aim is to make the researcher's curated reading compound over time.

## 2. Core Architecture

```text
raw/papers/
  -> PDF extraction
  -> bundled paper process agent understanding/summarization from extracted text
  -> papers/<paper_id>.md
  -> linked Obsidian notes
  -> agent search/synthesis workflows
```

V1 excludes:

- Zotero as a required dependency
- Zotero write-back
- Better BibTeX as a required dependency
- SQLite graph
- vector database
- OpenAlex/Semantic Scholar as core KB inputs
- Neo4j/RDF
- web app/dashboard

These may become later plugins, but they should not be part of the first build.

## 3. Trust Boundary

The KB has one v1 intake rule:

> A paper enters the KB when the researcher drops a PDF into `raw/papers/` and asks the agent to process it.

Agents may:

- read raw PDFs from `raw/papers/`
- extract text and metadata
- create or update Obsidian notes
- propose links, summaries, findings, and synthesis
- mark uncertainty clearly

Agents may not:

- silently add external papers
- modify Zotero
- treat external search results as trusted evidence
- overwrite researcher-reviewed notes without preserving prior content or marking changes

## 4. Vault Layout

The installed Codex skill is not the vault. The skill is reusable tooling, while the vault is a user-selected content root opened in Obsidian. A user may have many vaults using the same installed skill.

Agents should always target the selected vault path with `--vault /path/to/user-vault` and should not store user PDFs, notes, or `.research-kb/` state inside the installed skill directory.

Canonical templates should ship with the installed skill and be copied into the selected vault by `init`. The vault's `templates/` folder is then the researcher-editable override layer.

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
      README.md
      library.bib
```

Folder roles:

| Folder | Role |
| --- | --- |
| `raw/papers/` | New PDFs waiting to be processed |
| `raw/processed/` | PDFs already processed or registered |
| `raw/failed/` | PDFs that could not be parsed cleanly |
| `papers/` | One note per processed PDF/paper |
| `concepts/` | Theories and analytic constructs |
| `variables/` | Linguistic variables, variants, features |
| `methods/` | Methods, measures, tasks, models, tools |
| `communities/` | Speech communities, populations, places, varieties |
| `questions/` | Research ideas and literature questions |
| `syntheses/` | Cross-paper literature syntheses |
| `templates/` | Reusable Obsidian note templates |
| `plugins/` | Optional integrations, not v1 core |
| `.research-kb/` | Generated tool state, including the machine index cache and JSONL search probe indexes |

`index.md` is the human-facing vault front door. `.research-kb/index.json` and `.research-kb/search/*.jsonl` are regenerated from Markdown notes for agents and CLI tools; they are not a second source of truth. Large-vault query agents should search the JSONL probe indexes rather than loading all summaries into context.

## 5. Naming Rules

Recommended filenames:

```text
papers/<paper_id>.md
concepts/<slug>.md
variables/<slug>.md
methods/<slug>.md
communities/<slug>.md
questions/<date>-<short-slug>.md
syntheses/<short-topic>.md
```

Recommended `paper_id` format:

```text
<first-author-last-name>-<year>-<short-title-slug>
```

Examples:

```text
papers/labov-1966-social-stratification.md
papers/zhang-2023-tone-register.md
concepts/indexicality.md
variables/mandarin-rhotics.md
methods/mixed-effects-models.md
questions/2026-06-23-vowel-quality-and-local-identity.md
```

If metadata cannot be extracted, use a temporary ID:

```text
papers/temp-2026-06-23-001.md
```

## 6. Frontmatter Standards

### Paper Frontmatter

```yaml
---
type: paper
paper_id:
intake_source: raw_pdf
raw_pdf_path:
pdf_sha256:
title:
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

`kb_status` values:

- `needs_ingest`
- `needs_review`
- `reviewed`
- `deprecated`

`review_state` values:

- `agent_draft`
- `needs_review`
- `researcher_reviewed`

`intake_source` values:

- `raw_pdf`
- `zotero_plugin`
- `raw_pdf_and_zotero_plugin`

### Concept Frontmatter

```yaml
---
type: concept
aliases: []
status: working
created:
updated:
---
```

### Variable Frontmatter

```yaml
---
type: variable
aliases: []
level: phonetic|phonological|morphosyntactic|lexical|discourse|prosodic|other
language_variety:
status: working
created:
updated:
---
```

### Research Question Frontmatter

```yaml
---
type: research_question
status: active
created_from:
related_concepts: []
related_variables: []
created:
updated:
---
```

## 7. Templates

### `templates/paper.md`

```markdown
---
type: paper
paper_id: {{paper_id}}
intake_source: raw_pdf
raw_pdf_path: {{raw_pdf_path}}
pdf_sha256: {{pdf_sha256}}
title: "{{title}}"
authors: {{authors}}
year: {{year}}
doi: "{{doi}}"
publication: "{{publication}}"
kb_status: needs_review
review_state: agent_draft
aliases: []
created: {{date}}
updated: {{date}}
---

# {{title}}

## Source

- PDF: {{raw_pdf_path}}
- DOI:

## One-Paragraph Summary

## Research Question

## Data and Participants

## Linguistic Variables

- studies_variable::

## Social Factors

- tests_social_factor::

## Methods and Measures

- uses_method::
- measured_by::

## Key Findings

- finding::
  - evidence::
  - supports::
  - complicates::

## Theoretical Contribution

## Limitations

## Useful Quotes

## Extraction Notes

- metadata_confidence:
- text_extraction_status:
- uncertain_fields:

## Links

- Concepts:
- Variables:
- Methods:
- Communities:
- Related papers:
```

### `templates/concept.md`

```markdown
---
type: concept
aliases: []
status: working
created: {{date}}
updated: {{date}}
---

# {{title}}

## Working Definition

## Why It Matters

## Key Papers

## Competing Views

## Related Variables

## Related Methods

## Open Questions
```

### `templates/variable.md`

```markdown
---
type: variable
aliases: []
level:
language_variety:
status: working
created: {{date}}
updated: {{date}}
---

# {{title}}

## Description

## Variants or Realizations

## Measures

## Social Factors

## Key Papers

## Open Questions
```

### `templates/research-question.md`

```markdown
---
type: research_question
status: active
created_from:
related_concepts: []
related_variables: []
created: {{date}}
updated: {{date}}
---

# {{title}}

## Prompt

## Why This Seems Interesting

## Relevant Papers in KB

## Evidence Paths

## Possible Directions

## Gaps in the KB

## Next Reading From Existing KB
```

### `templates/synthesis.md`

```markdown
---
type: synthesis
topic:
status: working
created: {{date}}
updated: {{date}}
---

# {{title}}

## Scope

## Short Synthesis

## Main Claims

## Supporting Papers

## Tensions or Contradictions

## Methods and Data Patterns

## Gaps

## Useful Citations
```

## 8. Relation Syntax

Use simple relation-like bullets in Markdown. This makes the vault readable while still giving agents structure.

## 8.1 Node Model

Every Markdown note is a graph node. The node ID is the file path, and the node type is the `type` field in frontmatter.

| Node type | Folder | Required identity fields |
| --- | --- | --- |
| `paper` | `papers/` | `paper_id`, `title`, `raw_pdf_path`, `pdf_sha256` |
| `concept` | `concepts/` | filename/title, optional `aliases` |
| `variable` | `variables/` | filename/title, optional `aliases`, optional `level` |
| `method` | `methods/` | filename/title, optional `aliases` |
| `community` | `communities/` | filename/title, optional `aliases` |
| `research_question` | `questions/` | filename/title, `status` |
| `synthesis` | `syntheses/` | filename/title, `topic` |

Agents should resolve node references in this order:

1. exact wikilink path
2. exact filename slug
3. frontmatter aliases
4. heading/title match
5. full-text search fallback

## 8.2 Edge Model

Typed edges use this shape:

```markdown
- relation_name:: [[target-note]]
```

Nested evidence edges are allowed under a `finding::` line:

```markdown
- finding:: Rhotics are used stylistically across gendered personae.
  - evidence:: p. 12, Table 3
  - supports:: [[concepts/indexicality]]
```

An edge has these logical fields:

```yaml
source_node: current note path
relation: relation_name
target: wikilink target or text value
context: nearest heading
evidence: nested evidence line, if present
review_state: inherited from note unless otherwise marked
```

Recommended relation labels:

```text
studies_variable::
has_variant::
measured_by::
uses_method::
uses_dataset::
samples_community::
tests_social_factor::
finding::
supports::
complicates::
contradicts::
extends::
relevant_to::
evidence::
```

Relation meanings:

| Relation | Source | Target | Meaning |
| --- | --- | --- | --- |
| `studies_variable::` | paper | variable | Paper studies this linguistic variable |
| `has_variant::` | variable | variable/concept | Variable has this variant or realization |
| `measured_by::` | paper/variable | method | Variable or paper uses this measurement |
| `uses_method::` | paper | method | Paper uses this method/model/task |
| `uses_dataset::` | paper | method/community/synthesis | Paper uses this corpus/dataset |
| `samples_community::` | paper | community | Paper samples this group/place/variety |
| `tests_social_factor::` | paper | concept | Paper analyzes this social factor |
| `finding::` | paper | text | Paper reports this finding |
| `supports::` | finding/paper/synthesis | concept/question/synthesis | Evidence supports a claim or idea |
| `complicates::` | finding/paper/synthesis | concept/question/synthesis | Evidence adds nuance or boundary conditions |
| `contradicts::` | finding/paper/synthesis | concept/question/synthesis | Evidence conflicts with a claim or prior finding |
| `extends::` | paper/synthesis | paper/concept/synthesis | Extends prior work |
| `relevant_to::` | any major node | research_question | Relevant to an active question |
| `evidence::` | finding | page/table/quote text | Source location or evidence snippet |

Example:

```markdown
- studies_variable:: [[variables/mandarin-rhotics]]
- tests_social_factor:: [[concepts/gender]]
- uses_method:: [[methods/mixed-effects-models]]
- finding:: Rhotics pattern differently across stance-linked speaker groups.
  - evidence:: p. 12, Table 3
  - supports:: [[concepts/indexicality]]
```

## 8.3 Paper Mini Graph

Every paper note should contain a mini graph. This gives agents a consistent extraction target.

Recommended paper graph sections:

```markdown
## Graph Edges

- studies_variable::
- tests_social_factor::
- samples_community::
- uses_method::
- measured_by::
- uses_dataset::

## Key Findings

- finding::
  - evidence::
  - supports::
  - complicates::
  - contradicts::
```

If the agent is uncertain, it should still preserve the candidate edge but mark it:

```markdown
- studies_variable:: [[variables/mandarin-rhotics]] #candidate
```

or:

```markdown
- studies_variable:: unknown
  - uncertainty:: The paper mentions rhoticization, but the exact variable label needs review.
```

## 9. Raw PDF Intake Workflow

### Setup

Create:

```text
raw/papers/
raw/processed/
raw/failed/
```

### Agent Processing

When the agent processes raw PDFs:

1. Scan `raw/papers/`.
2. Compute `pdf_sha256` for each PDF.
3. Skip PDFs already represented by an existing paper note with the same hash.
4. Extract embedded metadata.
5. Extract text.
6. Infer title, authors, year, DOI, and publication when possible.
7. Generate `paper_id`.
8. Create `papers/<paper_id>.md` from `templates/paper.md`.
9. Export a model-agnostic paper-analysis task with extracted text, the expected JSON schema, `agent: research-kb.paper-process`, and a result path.
10. In Codex, spawn one worker subagent per task using the bundled paper process agent instructions to understand and summarize the paper from extracted text only.
11. Apply the returned JSON to draft structured sections with summary, research question, data, methods, findings, limitations, quotes, and evidence anchors.
12. Extract candidate graph edges into the paper mini graph.
13. Create or propose links to concepts, variables, methods, and communities.
14. Move the PDF to `raw/processed/` or leave it in place and record status.
15. Append a short entry to `log.md`.

The CLI should not call a model provider directly. Model-assisted paper understanding belongs to the surrounding agent harness, using `agent-context` and `apply-analysis` as the interchange format. In Codex, the skill should use the bundled `research-kb.paper-process` worker instructions by default. Deterministic `enrich` remains available as an offline fallback.

If extraction fails:

1. Move or register the PDF under `raw/failed/`.
2. Create a minimal paper note only if enough metadata exists.
3. Record what failed and what the researcher should provide.

## 10. Agent Workflows

### A. Idea to Papers and Directions

Input: research idea.

Agent steps:

1. Identify concepts, variables, methods, communities, and social factors in the idea.
2. Resolve those entities to graph nodes using filenames, aliases, headings, and full-text search.
3. Traverse typed edges and backlinks from matched nodes.
4. Retrieve papers connected by typed edges such as `studies_variable::`, `tests_social_factor::`, `uses_method::`, and `supports::`.
5. Rank papers by graph match strength and evidence quality.
6. Return relevant KB papers with rationales and evidence paths.
7. Propose research directions grounded in those papers.
8. State gaps in the KB.

Output shape:

```markdown
## Interpreted Idea

## Relevant Papers in the KB

- [[papers/paper-id]] — rationale; evidence path.

## Possible Directions

1. Direction...
   - Internal support:
   - Gap:

## Gaps in Current KB

## Suggested Notes to Create or Update
```

Ranking rules:

1. Highest: paper matches multiple query nodes through typed edges.
2. High: paper has `finding::` lines with nested `evidence::`.
3. High: reviewed notes outrank agent drafts.
4. Medium: paper is linked by backlinks but relation is untyped.
5. Low: paper only contains keyword mentions.
6. Penalize: uncertain/candidate edges unless no better evidence exists.

### B. Draft to Supporting Citations

Input: draft paragraph or section.

Agent steps:

1. Extract claims.
2. Classify claims as background, theoretical, empirical, methodological, or interpretive.
3. Resolve claim entities to concept, variable, method, community, and synthesis nodes.
4. Search typed edges, especially `supports::`, `complicates::`, `contradicts::`, and `evidence::`.
5. Suggest citations using paper titles/links, and DOI if available.
6. Flag unsupported or overbroad claims.

Output shape:

```markdown
## Claims Detected

## Suggested Citations

- Claim:
  - Suggested paper:
  - Why:
  - Caveat:

## Possible Enrichments

## Claims Needing More Support
```

### C. Question to Relevant Papers

Input: research/literature question.

Agent steps:

1. Parse question into concepts, variables, methods, communities, and social factors.
2. Resolve these to graph nodes.
3. Traverse typed edges and backlinks.
4. Return relevant papers, synthesis notes, and concept pages.
5. Provide a short answer from the curated KB.
6. Identify missing areas.

Output shape:

```markdown
## Short Answer From Current KB

## Relevant Papers

## Evidence Paths

## Related Concepts and Variables

## What the KB Does Not Yet Cover
```

## 10.1 Graph Traversal Algorithm

Agents should use this retrieval pattern before falling back to broad full-text search:

1. Parse the request into candidate entities:
   - linguistic variables
   - variants or features
   - social factors
   - communities/language varieties
   - methods/measures
   - concepts/theories
   - datasets/corpora
2. Resolve entities to existing nodes.
3. For each matched node, collect:
   - incoming typed edges from paper notes
   - outgoing typed edges from the node note
   - Obsidian backlinks
   - synthesis notes linking to the node
4. Expand one hop to papers, findings, concepts, and syntheses.
5. Optionally expand two hops when the query is broad or exploratory.
6. Rank candidate papers and synthesis notes.
7. Return evidence paths, not just titles.

Example evidence path:

```text
user idea: rhotics + gender + identity
-> [[variables/mandarin-rhotics]]
-> studies_variable::
-> [[papers/zhang-2023-rhotics]]
-> finding:: Rhotics are used stylistically across gendered personae.
-> supports::
-> [[concepts/indexicality]]
```

Agents should include paths like this in answers because they make the graph inspectable.

### D. Vault Lint

Agent checks:

- PDF in `raw/papers/` without paper note.
- processed PDF without corresponding paper note.
- paper note without `raw_pdf_path`.
- paper note without `pdf_sha256`.
- missing title/year/authors.
- paper note with no summary.
- paper note with no concept/variable/method/community links.
- duplicate paper notes by hash, DOI, title, or filename.
- duplicate concept or variable pages.
- orphan concept pages.
- stale synthesis pages after new relevant papers were added.
- research questions with no linked papers.

## 11. `AGENTS.md` Rules

The vault should include an `AGENTS.md` with rules like:

```markdown
# Agent Rules

## Authority

- Raw PDFs enter through `raw/papers/`.
- Do not add external papers unless the user supplies the PDF.
- Zotero is optional plugin data, not v1 core authority.
- Do not modify Zotero.

## Paper Notes

- Keep paper notes source-grounded.
- Always record `raw_pdf_path` and `pdf_sha256`.
- Use agent/subagent paper understanding when available, but only from extracted PDF text.
- Mark uncertain metadata and uncertain summaries.
- Preserve researcher-reviewed content.

## Links

- Link concepts, variables, methods, and communities when they are substantively relevant.
- Do not create duplicate pages; search first.
- If a new page is useful but uncertain, create it with `status: candidate`.

## Synthesis

- Synthesis notes may compare, generalize, and identify gaps.
- Distinguish supported claims from hypotheses.
- Include paper links and source evidence for claims.

## Updates

- Append important actions to `log.md`.
- Keep `index.md` useful and brief.
- Keep machine-maintained state under `.research-kb/`; regenerate `.research-kb/index.json` from notes instead of hand-editing it.
```

## 12. Zotero Plugin

Zotero should be implemented later as a plugin.

Suggested plugin folder:

```text
plugins/
  zotero/
    README.md
    library.bib
    mapping.md
```

Plugin capabilities:

- read Better BibTeX export
- match Zotero items to existing paper notes by DOI, title, PDF hash, or author-year-title
- add Zotero citekey/tag metadata to paper note frontmatter
- create paper notes from Zotero entries if explicitly requested

Plugin restrictions:

- no Zotero write-back in v1
- no direct writes to `zotero.sqlite`
- no silent replacement of reviewed Markdown content

## 13. MVP Test

Use 10 handpicked raw PDFs.

Test 1:

> Given this idea, what papers in my KB are relevant, and what research directions could I pursue?

Test 2:

> Given this draft paragraph, which papers in my KB support or complicate the claims?

Test 3:

> Given this question, what does my current KB say, and what is missing?

The prototype succeeds if the researcher can inspect the answer in Obsidian and see exactly which processed paper notes it relied on.

## 14. Later Upgrade Points

Add only after the raw-PDF-first workflow proves valuable:

- Zotero/Better BibTeX plugin.
- SQLite generated from Markdown for structured querying.
- Local embeddings for fuzzy semantic search.
- OpenAlex/Semantic Scholar discovery plugin for external candidate papers.
- Zotero API/plugin write-back for low-risk status tags.
- A web dashboard for review queues.

## 15. Strong Recommendation

Start with the boring version:

```text
raw PDF folder
PDF extraction
Obsidian
Markdown templates
Agent workflows
```

The first technical challenge is not database scale or Zotero integration. It is making the paper notes disciplined enough that the researcher and agents can both trust them.

## 16. Source Anchors

- Andrej Karpathy's LLM Wiki pattern: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- Obsidian documentation: https://help.obsidian.md/
- Better BibTeX automatic export: https://retorque.re/zotero-better-bibtex/exporting/auto/
- Zotero Web API: https://www.zotero.org/support/dev/web_api/v3/basics
- Zotero direct SQLite access warning: https://www.zotero.org/support/dev/client_coding/direct_sqlite_database_access
- Microsoft GraphRAG: https://microsoft.github.io/graphrag/
- LightRAG: https://github.com/HKUDS/LightRAG
- CLDF: https://cldf.clld.org/
