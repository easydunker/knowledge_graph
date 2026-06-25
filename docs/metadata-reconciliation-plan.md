# Metadata Reconciliation Plan

This plan adds Crossref, OpenAlex, and Semantic Scholar as optional bibliographic metadata authorities for the Research KB. The goal is to reduce duplicate and invalid notes caused by imperfect PDF extraction, especially author-name and title variants, without changing the core evidence rule.

External metadata may clean bibliographic identity. It must not add papers to the KB by itself, and it must not support claims in paper, concept, synthesis, or query answers. Scholarly claims still come from researcher-supplied PDFs and curated vault notes.

## Providers

### Crossref

Use Crossref first for DOI, title, publication year, venue, and author-list reconciliation.

Strengths:

- strong DOI coverage
- useful title and author metadata for published works
- no API key required

Configuration:

```yaml
metadata_reconciliation:
  crossref:
    enabled: true
    mailto: ""
```

The `mailto` field is optional but recommended for polite API use.

### OpenAlex

Use OpenAlex for work IDs, author IDs, institution hints, alternate title/name variants, and cross-provider identity checks.

Strengths:

- official scholarly graph API
- work, author, institution, source, and topic entities
- usable without an API key
- optional API key or account configuration can improve rate/usage behavior when available

Configuration:

```yaml
metadata_reconciliation:
  openalex:
    enabled: true
    mailto: ""
    api_key_env: "OPENALEX_API_KEY"
```

`OPENALEX_API_KEY` is optional. If absent, the system should use unauthenticated requests. `mailto` is also optional but recommended.

### Semantic Scholar

Use Semantic Scholar as a secondary cross-check for paper identity, author identity, venue, year, citation graph hints, and alternate metadata when Crossref/OpenAlex are weak.

Strengths:

- useful paper and author entities
- often good for computer science and NLP papers
- can provide extra disambiguation signals

Configuration:

```yaml
metadata_reconciliation:
  semantic_scholar:
    enabled: true
    api_key_env: "SEMANTIC_SCHOLAR_API_KEY"
```

The API key is optional. If absent, the system should use public unauthenticated behavior and conservative rate limits.

## Trust Boundary

External provider records are maintenance metadata, not KB evidence.

Allowed uses:

- confirm or correct paper title, DOI, year, venue, and author display names
- add stable external IDs to paper and author frontmatter
- identify likely duplicate paper notes
- identify likely duplicate author/concept/method/variable/community nodes
- help the curator decide whether a stale candidate node should merge or move to archive

Forbidden uses:

- add a paper that the researcher did not supply as a PDF
- cite external abstracts or snippets as evidence for research claims
- create synthesis claims from external metadata
- replace researcher-reviewed content silently
- treat Google Scholar or web-search results as trusted KB evidence

## Build Stage

Add metadata reconciliation after paper-process analysis and before node curation:

```text
raw PDF intake
  -> PDF extraction
  -> paper-process agent
  -> apply paper analysis
  -> quality guard
  -> metadata reconciliation
  -> duplicate/stale candidate clustering
  -> node curator tasks
  -> apply curation and merge/archive plans
  -> lint/index/build-report
```

This order lets provider metadata work from the best available local title/author/DOI extraction, while still preventing quality-failed paper notes from driving graph curation.

## Paper Matching

The reconciliation task should query providers using the strongest available fields:

1. DOI
2. normalized title plus year
3. normalized title plus first author
4. normalized title alone, only if the title is distinctive

Record matches in paper frontmatter:

```yaml
external_ids:
  doi: "10.xxxx/example"
  crossref_doi: "10.xxxx/example"
  openalex_work_id: "https://openalex.org/W..."
  semantic_scholar_paper_id: "..."
metadata_reconciliation:
  state: matched
  confidence: high
  checked_at: "2026-06-25T00:00:00Z"
  providers: ["crossref", "openalex", "semantic_scholar"]
  notes:
    - "DOI and normalized title agree across Crossref and OpenAlex."
```

If confidence is not high, record a review item instead of rewriting frontmatter.

## Author Reconciliation

Author nodes should be created and merged more strictly than concept or method nodes.

High-confidence author cleanup can use:

- exact match to a provider author display name on a high-confidence matched paper
- same paper, same author position, and near-identical normalized name
- one name is a clear OCR/diacritic corruption of the other
- one candidate is orphaned or only linked by the same paper

Examples:

```text
Carolyn P Ros -> Carolyn P Rose
A Seza Do Gru Z -> A. Seza Dogruoz
James Stanford -> James N. Stanford
```

Do not auto-merge author nodes when:

- both nodes are active or researcher-reviewed and identity is uncertain
- names could plausibly be different people
- papers, years, or coauthors conflict
- the only evidence is provider search similarity without local paper support

Author frontmatter may store provider IDs as hints:

```yaml
external_ids:
  openalex_author_id: "https://openalex.org/A..."
  semantic_scholar_author_id: "..."
metadata_reconciliation:
  state: matched
  confidence: medium
```

Provider IDs should help future matching, but they should not turn author nodes into general biographies unless the researcher asks for that.

## Duplicate and Invalid Node Detection

The CLI should generate duplicate/stale clusters before curator work:

```text
.research-kb/reconciliation/
  paper-matches/*.json
  author-matches/*.json
  duplicate-clusters/*.json
  invalid-candidates/*.json
```

Cluster signals:

- same stable external paper ID
- same DOI
- near-identical normalized title
- near-identical normalized author name on the same matched paper
- same inbound paper set and similar slug
- orphan candidate note with phrase-like title
- candidate note created from generated wikilink but no live inbound edge remains

The curator receives these clusters as graph-integrity tasks and must choose:

```text
merge
archive_invalid
keep_separate
needs_human_review
```

Auto-apply only high-confidence `merge` and `archive_invalid` decisions. Ambiguous clusters go to the build report.

## Archive Policy

Never delete stale notes during automatic cleanup. Move them to:

```text
archive/merged/
archive/invalid/
```

Archived notes should preserve provenance:

```yaml
type: archived_node
archive_reason: duplicate_metadata_reconciliation
merged_into: authors/carolyn-p-rose.md
archived_at: "2026-06-25T00:00:00Z"
archived_by: research-kb.curator
metadata_reconciliation:
  providers: ["openalex", "crossref"]
  confidence: high
```

Live notes should receive aliases for merged variants when useful.

## Build Report

The build report should include:

```text
Metadata reconciliation:
  Crossref checked: 20
  OpenAlex checked: 20
  Semantic Scholar checked: 18
  High-confidence paper matches: 17
  Medium-confidence matches needing review: 3
  Duplicate clusters found: 8
  Auto-merged nodes: 4
  Archived invalid candidates: 3
  Needs human review: 2
```

## Implementation Steps

1. Add config fields for provider enablement, optional `mailto`, optional API-key environment names, cache directory, and rate limits.
2. Add a `reconcile-metadata` CLI command.
3. Query Crossref, OpenAlex, and Semantic Scholar using DOI/title/author/year from paper notes.
4. Cache raw provider responses under `.research-kb/metadata-cache/`.
5. Write paper and author match reports under `.research-kb/reconciliation/`.
6. Add deterministic duplicate/stale candidate clustering.
7. Pass reconciliation clusters into curator tasks.
8. Extend curator schema to support `archive_invalid` decisions.
9. Apply high-confidence merge/archive decisions deterministically.
10. Surface medium/low-confidence matches in `build-report`.

## Sources

- Crossref REST API: https://api.crossref.org
- OpenAlex API documentation: https://developers.openalex.org/api-reference/introduction
- Semantic Scholar Academic Graph API: https://www.semanticscholar.org/product/api
