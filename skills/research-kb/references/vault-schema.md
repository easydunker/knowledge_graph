# Research KB Vault Schema

## Trust Boundary

- The installed skill directory is tooling only; it must not contain user KB content.
- The user-selected vault root is the content authority.
- Raw PDFs enter only through `raw/papers/`.
- External search may identify candidate readings, but it is not trusted KB evidence.
- Zotero data is optional plugin metadata and must not replace reviewed Markdown content silently.
- Paper notes must preserve `raw_pdf_path` and `pdf_sha256`.

## Folders

```text
index.md
log.md
AGENTS.md
.research-kb/config.yaml
.research-kb/index.json
.research-kb/search/
raw/papers/
raw/processed/
raw/failed/
papers/
authors/
concepts/
variables/
methods/
communities/
questions/
syntheses/
templates/
plugins/zotero/
```

`index.md` is the human-facing Obsidian entry point. `.research-kb/index.json` is a generated machine cache used by agents and CLI tools. `.research-kb/search/*.jsonl` is a generated probe index for large-vault search. The Markdown notes remain the source of truth.

Vault-local `templates/*.md` files are researcher-overridable copies of the installed skill's canonical templates. Keep the standard headings unless intentionally changing the agent/indexing workflow.

## Node Types

| Type | Folder | Role |
| --- | --- | --- |
| `paper` | `papers/` | Source-grounded note for one raw PDF |
| `author` | `authors/` | Local author identity represented in the curated KB |
| `concept` | `concepts/` | Theory, construct, social factor, or analytic category |
| `variable` | `variables/` | Linguistic variable, variant set, feature, or realization |
| `method` | `methods/` | Method, measure, task, model, instrument, or software tool |
| `community` | `communities/` | Speech community, population, place, language variety, or participant group |
| `research_question` | `questions/` | Active idea, literature question, or project seed |
| `synthesis` | `syntheses/` | Cross-paper literature memo or thematic synthesis |

## Paper Frontmatter

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

Use `kb_status: reviewed` and `review_state: researcher_reviewed` only when the researcher has actually reviewed the note.

## Relation Labels

Prefer these typed Markdown edges:

```text
studies_variable::
has_variant::
measured_by::
uses_method::
uses_dataset::
samples_community::
tests_social_factor::
authored_by::
coauthored_with::
works_on::
finding::
supports::
complicates::
contradicts::
extends::
relevant_to::
evidence::
```

Typed edges should usually point to Obsidian wikilinks:

```markdown
- studies_variable:: [[variables/mandarin-rhotics]]
- uses_method:: [[methods/mixed-effects-models]]
- authored_by:: [[authors/author-name]]
- finding:: Rhotics pattern differently across stance-linked speaker groups.
  - evidence:: p. 12, Table 3
  - supports:: [[concepts/indexicality]]
```

Author nodes are local KB identities. Create or merge them only from paper metadata or extracted PDF text. Do not infer ORCID, affiliation, or identity merges from web search unless the researcher supplies and reviews that evidence.

If a useful node is uncertain, create it with `status: candidate` or mark the edge with `#candidate` plus an `uncertainty::` line.

## Resolution Order

When resolving an author, concept, variable, method, community, question, or synthesis:

1. exact wikilink path
2. exact filename slug
3. frontmatter aliases
4. heading/title match
5. full-text search fallback

Search before creating new notes to avoid duplicates.
