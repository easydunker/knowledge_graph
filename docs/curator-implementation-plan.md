# Curator Implementation Plan

This plan turns the curator design into an installable Research KB skill workflow. The goal is an autonomous initial or incremental build: the harness receives a user instruction, processes supplied PDFs, builds high-quality paper notes, enriches the graph, checks integrity, and reports only the issues that need human judgment.

The implementation keeps the core rule intact: the Markdown vault is the source of truth, raw PDFs enter through `raw/papers/`, and the skill remains model-agnostic. The CLI exports task JSON; the harness or subagents do the model work; the CLI validates and applies returned JSON.

Related design notes:

- [Curator agent design](curator-agent-design.md)
- [Paper-process quality guard TODO](todo-agent-quality-guard.md)
- [PDF parser comparison](pdf-parser-comparison.md)
- [Metadata reconciliation plan](metadata-reconciliation-plan.md)

## Decisions

- Curation is part of the default build and incremental-build workflow.
- The curator may update full non-paper node bodies, not only managed sections.
- The curator may create new synthesis notes when evidence is strong; those notes are created as `status: active`.
- The curator may auto-merge duplicate nodes when confidence is high.
- Merged notes are moved to `archive/merged/`, not deleted.
- Duplicate paper notes can be auto-merged only with very strong identity evidence.
- Crossref, OpenAlex, and Semantic Scholar may be used for metadata reconciliation and duplicate/stale-node detection.
- OpenAlex and Semantic Scholar API keys are optional; the workflow must run without them using conservative unauthenticated requests.
- External metadata providers are not evidence sources for scholarly claims.
- Quality-failed paper notes remain searchable, but they are skipped for curation and synthesis.
- Query agents must not rely on quality-failed paper summaries as evidence; they must load full extracted/source text before using those papers.
- Failed paper-process outputs are recorded for manual retry, not automatically retried.
- Only initial-build and incremental-build modes are in scope for now.

## Target Build Pipeline

```text
init/check vault
  -> extract PDFs
  -> create draft paper notes
  -> export paper-process tasks
  -> run paper-process agents
  -> apply paper analyses with build provenance
  -> run quality guard
  -> reconcile metadata with Crossref/OpenAlex/Semantic Scholar
  -> cluster duplicate and stale candidate nodes
  -> exclude quality-failed papers from downstream curation
  -> export node-curator tasks for affected nodes
  -> run node-curator agents
  -> apply node curation
  -> create active synthesis notes when evidence is strong
  -> auto-merge high-confidence duplicates into archive
  -> run graph integrity checks and safe fixes
  -> refresh indexes
  -> write build report
```

The high-level harness instruction can be "build/update this KB." Internally, the workflow remains stepwise and inspectable.

## Extraction Backend

Use `pymupdf4llm` as the preferred PDF extraction backend because it produces LLM-friendly Markdown and handles multi-column papers, tables, and structure better than plain `pypdf` extraction.

Extraction priority:

1. `pymupdf4llm`
   - output Markdown for the paper-process agent
   - preserve layout cues such as headings and tables
   - record backend/version and extracted text hash
2. `pymupdf` / `fitz`
   - fallback plain text extraction when `pymupdf4llm` is unavailable
3. `pypdf`
   - compatibility fallback when PyMuPDF is unavailable
4. minimal literal extraction
   - last-resort draft only, marked low confidence

Installation guidance should recommend:

```bash
python -m pip install pymupdf4llm pypdf
python - <<'PY'
import pymupdf4llm
print("pymupdf4llm ok")
PY
```

The skill should remain graceful when `pymupdf4llm` is absent. A missing preferred backend should lower extraction confidence, not block vault creation.

## Metadata Reconciliation

Add a reconciliation stage after quality guard and before node-curator export.

Purpose:

- correct or confirm paper title, DOI, year, venue, and author display names
- add stable external identifiers to paper and author frontmatter
- detect duplicate paper notes
- detect duplicate or invalid non-paper candidate notes
- produce graph-integrity clusters for the curator

Provider order:

1. Crossref
   - preferred for DOI/title/venue metadata
   - no API key required
   - optional `mailto` configuration
2. OpenAlex
   - preferred for work IDs, author IDs, institutions, and cross-provider scholarly graph metadata
   - must work without an API key
   - optional API key via environment variable, for example `OPENALEX_API_KEY`
3. Semantic Scholar
   - secondary cross-check for paper and author identity
   - optional API key via environment variable, for example `SEMANTIC_SCHOLAR_API_KEY`

The reconciliation stage must cache provider responses and write audit records:

```text
.research-kb/metadata-cache/
.research-kb/reconciliation/paper-matches/
.research-kb/reconciliation/author-matches/
.research-kb/reconciliation/duplicate-clusters/
.research-kb/reconciliation/invalid-candidates/
```

External metadata may update bibliographic fields only when confidence is high. It must not create KB evidence, synthesis claims, or new papers.

Confidence rules:

- `high`: DOI match, or exact/near-exact normalized title plus compatible year and author list across at least one trusted provider.
- `medium`: title/author/year mostly match but DOI is absent or providers disagree on some fields.
- `low`: title-only or fuzzy match without enough author/year support.

Only high-confidence paper and author metadata should auto-apply. Medium and low confidence matches go to the build report and curator review.

Example config:

```yaml
metadata_reconciliation:
  enabled: true
  cache_dir: .research-kb/metadata-cache
  reports_dir: .research-kb/reconciliation
  crossref:
    enabled: true
    mailto: ""
  openalex:
    enabled: true
    mailto: ""
    api_key_env: OPENALEX_API_KEY
  semantic_scholar:
    enabled: true
    api_key_env: SEMANTIC_SCHOLAR_API_KEY
```

## Durable Build Provenance

Do not depend on `.research-kb/agent-tasks/` existing forever. Task and result files are generated build state. Paper notes should preserve minimal build-only provenance so future quality checks can understand what happened.

Example paper-note frontmatter:

```yaml
kb_build:
  extraction:
    backend: pymupdf4llm
    backend_version: ""
    extracted_format: markdown
    extracted_text_sha256: ""
    extracted_text_chars: 18021
    text_truncated_for_task: false
  paper_process:
    source: research-kb.paper-process
    model_capability: academic-medium
    result_sha256: ""
    applied_at: 2026-06-24T17:08:00Z
  quality:
    state: passed
    checked_at: 2026-06-24T17:12:00Z
```

`kb_build` is for maintenance only. Query, claim-support, and synthesis agents must ignore it except when the user asks about processing quality, provenance, review state, or KB maintenance.

## Paper-Process Quality Improvements

Update `references/paper-process-agent.md` and the output schema so the process agent must:

- read the entire `extracted_text` field
- treat `text_truncated_for_task` as authoritative
- distinguish "pipeline truncated the text" from "section not identifiable"
- report section coverage for methods, data, results, discussion, conclusion
- include evidence anchors for key findings
- produce a quality self-check

Add required result fields:

```json
{
  "text_truncated_for_task_acknowledged": false,
  "section_coverage": {
    "methods": "found",
    "results": "found",
    "discussion": "found"
  },
  "quality_self_check": {
    "read_full_extracted_text": true,
    "evidence_anchors_present": true
  }
}
```

`apply-analysis` should validate these fields. Weak or invalid outputs should be marked for review rather than silently applied as trustworthy notes.

## Quality Guard

Add a quality guard phase after `apply-analysis`.

Outputs:

```text
.research-kb/quality-reports/<paper-id>.json
```

Paper-note failure marker:

```yaml
review_state: quality_failed
kb_build:
  quality:
    state: failed
```

Checks:

- task/provenance says `text_truncated_for_task: false`, but note claims truncation
- substantial extracted text produced zero findings
- source text appears to contain results, but note says no results are available
- evidence anchors are missing, vague, or unsupported
- methods/data/findings are absent without a specific explanation

Quality-failed papers:

- remain searchable
- are listed in build reports
- are excluded from curator node enrichment
- are excluded from automatic synthesis creation
- are excluded as evidence for auto-merge
- require full extracted/source text loading before query agents use them as evidence
- are not retried automatically

## Node Curator

Add files:

```text
skills/research-kb/agents/node-curator.yaml
skills/research-kb/references/node-curator-agent.md
```

Add CLI stages:

```bash
research_kb.py --vault "$VAULT" reconcile-metadata
research_kb.py --vault "$VAULT" curator-context
research_kb.py --vault "$VAULT" apply-curation .research-kb/curator-results/*.json
```

`curator-context` exports one task per affected node. In initial-build mode, affected nodes are nodes created or linked by the current batch. In incremental-build mode, affected nodes are nodes with new or changed inbound edges from newly processed quality-passed papers.

Task input should include:

- node path, type, status, aliases, and current body
- inbound paper edges from quality-passed papers
- compact evidence packets from paper notes
- related nodes
- stale backlink findings
- duplicate candidates
- metadata reconciliation clusters
- invalid/stale candidate node candidates
- synthesis opportunities in the local neighborhood
- result path and expected output schema

The curator may update the full body of non-paper nodes. It must preserve raw source evidence, explicit uncertainty, and researcher-reviewed content unless the harness is explicitly operating with force semantics.

## Node Types to Enrich

Concept nodes:

- working definition
- why it matters
- key papers
- competing views
- related variables/methods/communities
- open questions

Variable nodes:

- variants
- measurement
- social meaning
- related methods
- related communities
- evidence-backed findings

Method nodes:

- what the method does
- assumptions
- common use in this KB
- limitations
- papers using the method

Community nodes:

- sampled populations
- geographic or social scope
- datasets
- variables studied
- caveats and representation limits

Author nodes:

- papers by the author in this KB
- recurring topics, methods, variables, and collaborators
- no invented biography or affiliation unless source-grounded in supplied notes

## Synthesis Creation

The curator may create active synthesis notes only when evidence is strong.

Strong evidence threshold:

- 3 or more quality-passed papers support a shared topic, variable, method, or community pattern
- or 2 or more quality-passed papers clearly complicate or contradict each other
- or 2 or more papers plus 1 existing active node form a clear research theme
- or the synthesis answers a likely researcher query better than any single node page

Synthesis notes should include:

```yaml
type: synthesis
status: active
created_by: research-kb.curator
source_scope:
  papers_considered: 12
  papers_used: 5
  coverage_limited: false
```

Body sections:

```markdown
## Claim

## Supporting Papers

## Complicating Evidence

## Methodological Differences

## Gaps

## Candidate Links
```

Weak or speculative synthesis opportunities should be reported, not created.

## Auto-Merge and Archive

The curator may propose merges, but the CLI applies them deterministically.

Auto-merge non-paper nodes only when:

- normalized names are identical or near-identical spelling variants
- provider-backed metadata says the variants refer to the same paper author or work
- acronym expansion is clear, such as `svm` to `support-vector-machine`
- one node is a stub and the other is clearly the fuller duplicate
- all edges can move without semantic change
- no researcher-reviewed content would be overwritten
- there are no conflicting frontmatter fields

Do not auto-merge merely related concepts, such as `gender` and `gender identity`, or broad/narrow method relations, such as `classification` and `logistic regression`.

Paper-note auto-merge requires very strong identity evidence:

- same `pdf_sha256`
- same normalized DOI
- same Crossref/OpenAlex/Semantic Scholar work identifier
- same normalized title plus same first author plus same year
- same stable external paper identifier if present in supplied metadata

Never auto-merge papers when DOI conflicts, titles materially conflict, or years differ without a stronger identity key.

Invalid candidate nodes may be archived when:

- the title is phrase-like rather than a valid author/concept/method/variable/community name
- no live paper note links to it
- the only source was a generated wikilink or OCR-corrupted extraction
- provider metadata on the matched paper gives a clearly incompatible canonical author/title

Examples:

```text
authors/previous-tone-normalization-methods-mainly.md -> archive/invalid/authors/
authors/one-methodological-issue-in-tonal-acoustic.md -> archive/invalid/authors/
authors/a-seza-do-gru-z.md -> merge into authors/a-seza-dogruoz.md
authors/carolyn-p-ros.md -> merge into authors/carolyn-p-rose.md
```

Merged notes move to:

```text
archive/merged/authors/
archive/merged/concepts/
archive/merged/variables/
archive/merged/methods/
archive/merged/communities/
archive/merged/syntheses/
archive/merged/papers/
archive/invalid/authors/
archive/invalid/concepts/
archive/invalid/variables/
archive/invalid/methods/
archive/invalid/communities/
```

Archive frontmatter:

```yaml
type: archived_node
archive_reason: merged_duplicate
merged_into: methods/support-vector-machine.md
merged_at: 2026-06-24T17:00:00Z
merged_by: research-kb.curator
original_type: method
```

Archived notes should be excluded from normal query evidence and graph search indexes. They are maintenance history, not live KB nodes.

## Graph Integrity

Graph integrity should be enforced by deterministic CLI checks, not by the LLM curator alone.

Add or extend `lint` / `graph-check` to detect:

- missing linked notes
- duplicate node candidates
- stale candidate nodes with no inbound paper links
- phrase-like author nodes and other invalid candidate nodes
- metadata reconciliation conflicts
- stale `Key Papers` lists
- active nodes with no inbound paper evidence
- candidate nodes with enough inbound evidence for review
- links to nodes in the wrong folder for their type
- papers linking to nonexistent authors, variables, methods, communities
- archived nodes still linked from live notes
- quality-failed papers used in curated node sections

Safe fixes can run automatically during build. Ambiguous fixes should be listed in the build report.

## Query Boundaries

Search indexes should include quality state so failed notes can be discovered:

```json
{
  "path": "papers/gupta-2019.md",
  "review_state": "quality_failed",
  "raw_pdf_path": "raw/papers/N19-3013.pdf"
}
```

Query behavior:

- quality-passed notes can be used as KB evidence
- quality-failed notes can be returned as possible hits
- if a quality-failed note is loaded, the harness must load full extracted/source text before relying on it
- archived notes are excluded from normal evidence unless the user asks about KB maintenance/history
- `kb_build` provenance is ignored during normal answer generation

## Scale Policy

For broad nodes with many inbound papers, curator tasks should not include every full note.

Use staged context:

1. include compact evidence packets first
2. rank inbound papers by relation type, evidence density, and recency in current build
3. include full paper-note content only for a bounded subset
4. report coverage limits

Curator output should include:

```json
{
  "coverage": {
    "inbound_papers_total": 142,
    "papers_read": 20,
    "coverage_limited": true
  }
}
```

## Implementation Order

1. Upgrade extraction.
   - Add `pymupdf4llm` preference.
   - Preserve fallback extraction.
   - Record extraction backend and text hash in `kb_build`.

2. Strengthen paper-process contract.
   - Update `paper-process-agent.md`.
   - Extend result schema.
   - Validate self-check fields in `apply-analysis`.

3. Add quality guard.
   - Export quality reports.
   - Mark failed notes.
   - Exclude failed notes from curation.
   - Show failed notes in `review`.

4. Add graph integrity checks.
   - Stale backlinks.
   - wrong-folder links.
   - duplicate candidates.
   - archived-node leakage.

5. Add metadata reconciliation.
   - Add Crossref lookup.
   - Add OpenAlex lookup with optional API key.
   - Add Semantic Scholar lookup with optional API key.
   - Cache provider responses.
   - Export paper/author match reports and duplicate/stale clusters.

6. Add node curator contract.
   - Add `node-curator.yaml`.
   - Add `node-curator-agent.md`.
   - Add `curator-context`.
   - Add `apply-curation`.

7. Add synthesis creation.
   - Implement strong-evidence threshold.
   - Create active synthesis notes.
   - Record source scope and coverage.

8. Add merge/archive support.
   - Apply high-confidence merge plans.
   - Rewrite links.
   - Move old notes to `archive/merged/`.
   - Move invalid stale candidates to `archive/invalid/`.
   - Exclude archive from normal query/index.

9. Add harness build workflow docs.
   - Initial build.
   - Incremental build.
   - Build report format.
   - Manual retry path for quality-failed papers.

## Build Report

Every build should end with a report:

```text
Processed PDFs: 20
Paper notes applied: 17
Quality failed: 3
Curated nodes: 42
Created synthesis notes: 5
Metadata matches: 18 high / 3 review
Duplicate clusters: 8
Auto-merged duplicates: 2
Archived invalid notes: 3
Safe graph fixes applied: 8
Needs user review: 4
```

The report should list quality-failed papers, metadata reconciliation conflicts, skipped curator inputs, merge/archive actions, synthesis notes created, and ambiguous issues that require user judgment.
