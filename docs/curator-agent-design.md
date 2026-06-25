# Curator Agent: Inbound-Edge Node Population

## Problem

The current pipeline is **write-only for paper notes, append-only for graph edges, and blind to non-paper node bodies.**

```
PDF → process → paper note
              → agent-context → sub-agent (1 paper) → result JSON
              → apply-analysis --create-nodes
                    ├── paper note gets summary, findings, variables, edges  ✓
                    ├── NEW candidate stubs created                         ✓
                    └── EXISTING concept/method/variable/community nodes
                        body content? NOTHING HAPPENS                       ✗
                        "Key Papers" list? STALE                            ✗
                        "Competing Views"? NEVER POPULATED                  ✗
```

Every `concepts/gender.md`, `methods/spearman-rank-correlation.md`, `variables/derhotacization.md` etc. is a template scaffold with correct frontmatter and backlinks — but all content sections (Working Definition, Why It Matters, Competing Views, Measures, Caveats) sit empty forever. The graph topology stays current via `index`, but the Markdown content in non-paper nodes goes stale with every new paper.

**Root cause:** The `paper-process` sub-agent sees exactly one paper and writes only `result JSON`. Even if it wanted to synthesize across papers, it has no access to other notes. And `apply-analysis` only writes into paper notes — it never touches concept/variable/method/community body content. The `--create-nodes` flag creates stubs; it doesn't populate them.

## Paper-Process Contract: Read Full Text Requirement

The paper-process sub-agent must read and analyze the **entire** `extracted_text` field before producing a result. This is not optional — it is the primary input. The task JSON gives the agent everything it needs to verify completion:

- `source_text_chars` — total characters extracted from the PDF
- `extracted_text_chars` — characters included in the task
- `text_truncated_for_task` — authoritative flag: `true` means the pipeline cut the text at the 120K cap, `false` means the full extracted text is present

The agent must:

1. Read the entire `extracted_text` to the last character before writing any conclusions
2. Treat `text_truncated_for_task: false` as binding — it must not claim truncation when the pipeline says otherwise
3. If `text_truncated_for_task: false` but a section (methods, results, discussion) is genuinely absent or unidentifiable, report that in `uncertain_fields` with the specific reason (e.g., "results section not identifiable in extracted text — paper may be a position piece or abstract-only"), not as "text was truncated"

This requirement is enforced by the curator quality gate below.

## Quality Gate: LLM-Based Verification

The curator is the second set of eyes on every paper note. Before trusting a paper note's claims for node population, the curator verifies the paper-process agent's work against the source evidence.

### What the curator checks

For each paper note touched by the current intake:

| Check | Method | Action on failure |
|-------|--------|-------------------|
| Truncation claim vs. task flag | Compare `text_truncated_for_task` in task JSON with paper note's `uncertain_fields` and summary | If task says `false` but note claims truncation → flag for re-processing |
| Results claim vs. extracted text | Scan extracted text for result indicators (numbers, percentages, "accuracy", "AUC", "Table", "Figure", "p <", "significant") | If text has results but note says "no results available" → flag for re-processing |
| Finding count vs. text length | Heuristic: a paper with >10K chars of text should produce ≥1 finding | If zero findings on a non-trivial paper → flag for re-processing |
| Evidence anchors | Check that `evidence::` lines actually appear in the extracted text (the `@@PAGE:N@@` markers can be matched) | If evidence anchors are hallucinated → flag for re-processing |
| Key sections present | Check that the paper note covers methods, data, and findings if the extracted text contains those sections | If major sections are missing → flag as incomplete, not failed |

### Re-processing flow

When the curator flags a paper note as low-quality:

```
Curator detects bad paper note
  → writes quality report to .research-kb/quality-reports/<paper-id>.json
  → marks paper note with review_state: quality_failed
  → optionally: re-dispatches paper-process with stricter instructions
  → researcher sees flagged notes via `review` command
```

The curator does NOT silently overwrite a bad paper note — it flags and surfaces. The researcher decides whether to re-process or fix manually.

### Quality report schema

```json
{
  "note_path": "papers/gupta-2019-...md",
  "checked_at": "2026-06-24T17:00:00Z",
  "checks": {
    "truncation_claim_valid": {
      "passed": false,
      "detail": "task JSON says text_truncated_for_task=false, but paper note claims 'extracted text is severely truncated' in uncertain_fields"
    },
    "results_present": {
      "passed": false,
      "detail": "extracted text contains 'AUC...is 0.892' (page 3) and '81.1% accuracy' (page 4), but paper note reports 'key_findings: no results available'"
    }
  },
  "verdict": "reprocess",
  "recommendation": "Full text is present and contains results. Re-dispatch paper-process agent."
}
```

### Integration into curator pipeline

```
process → agent-context → paper-process sub-agents → apply-analysis
                                                          ↓
                                                    [CURATOR RUN]
                                                          ├── PHASE 1: Quality gate
                                                          │     ├── Read each paper note's task JSON
                                                          │     ├── Verify against extracted text
                                                          │     ├── Flag failures → quality report
                                                          │     └── Mark bad notes → skip in phase 2
                                                          │
                                                          └── PHASE 2: Node population (only for quality-passed papers)
                                                                ├── Backlink sync
                                                                └── Content synthesis
```

Phase 1 is a gate: bad paper notes are excluded from node population. This prevents a lazy sub-agent from contaminating concept definitions downstream.

## Proposed Solution: Curator Agent (updated)

A post-intake agent that closes two loops — quality verification and node population:

```
New paper applied → curator agent
                      ├── PHASE 1: Quality gate
                      │     ├── reads paper note + source task JSON
                      │     ├── verifies truncation claims, result presence, evidence anchors
                      │     └── flags/re-processes bad notes
                      │
                      └── PHASE 2: Node population (quality-passed papers only)
                            ├── identifies which candidate nodes gained new edges
                            ├── traverses inbound edges (which papers link here?)
                            ├── reads all paper notes that link to this node
                            ├── extracts and collates evidence lines
                            ├── synthesizes: definition, competing views, open questions
                            ├── writes populated node body
                            └── promotes status: candidate → active (when warranted)
```

### Where it fits in the pipeline

```
process → agent-context → sub-agents → apply-analysis → [CURATOR] → index → lint
                                                            ↑
                                                    NEW STEP
```

Triggered after `apply-analysis --create-nodes`, the curator scans all nodes whose status is `candidate` and have ≥1 paper link, then populates them from the paper evidence already in the vault.

### Incremental mode

When new papers are added to an existing vault, the curator re-evaluates nodes that gained new edges:

```
New paper about gender added → curator sees concepts/gender.md gained a new backlink
                               → re-reads ALL papers that link to gender (old + new)
                               → updates "Key Papers" with the new paper
                               → if new paper contradicts prior evidence, adds to "Competing Views"
                               → if node was already active, decides whether update is warranted
```

## Agent Contract

### Input (exported by CLI, like `agent-context` for paper-process)

A curator task describes one node to populate or update:

```json
{
  "task": "research_kb_curate_node",
  "agent": "research-kb.node-curator",
  "node_path": "concepts/gender.md",
  "node_type": "concept",
  "node_status": "candidate",
  "inbound_papers": [
    {
      "path": "papers/nguyen-2016-computational-sociolinguistics-a-survey.md",
      "edge_type": "tests_social_factor",
      "evidence": "Gender prediction is the most studied social variable... (p. 18-21)"
    },
    {
      "path": "papers/jrgensen-2015-challenges-of-studying-and-processing-dialects.md",
      "edge_type": "tests_social_factor",
      "evidence": "correlated AAVE feature usage with male percentage at city level (Table 3)... found women use AAVE features more often, contrary to H3"
    }
  ],
  "full_paper_notes": [
    { "path": "...", "content": "<full markdown of paper note 1>" },
    { "path": "...", "content": "<full markdown of paper note 2>" }
  ],
  "related_nodes": [
    { "path": "concepts/gender-binary-variable.md", "type": "concept" }
  ],
  "existing_node_content": "<current markdown body of concepts/gender.md>",
  "result_path": ".research-kb/curator-results/gender.curator-result.json",
  "expected_output_schema": { ... }
}
```

### Output (written by agent, applied by CLI)

```json
{
  "node_path": "concepts/gender.md",
  "agent_source": "research-kb.node-curator",
  "agent_model": "hermes",
  "action": "populate",
  "new_status": "active",
  "sections": {
    "working_definition": "In computational sociolinguistics, gender is treated as...",
    "why_it_matters": "Gender is the most studied social variable...",
    "competing_views": [
      {
        "view": "Gender as binary predictor",
        "source": "papers/nguyen-2016-...md",
        "evidence": "Most studies treat gender as binary (p. 18)"
      },
      {
        "view": "Gender as performed/social construct",
        "source": "papers/nguyen-2016-...md",
        "evidence": "Binary treatment criticized as neglecting speaker agency (p. 21)"
      }
    ],
    "related_variables": ["variables/function-word-frequencies", "variables/stylistic-features"],
    "related_methods": ["methods/supervised-classification", "methods/liwc-analysis"],
    "open_questions": [
      "No paper in current KB addresses non-binary gender directly",
      "How does gender interact with other social factors (age, ethnicity) in these datasets?"
    ]
  },
  "uncertain_fields": ["open_questions are speculative, not source-grounded"]
}
```

A new CLI subcommand applies it:

```bash
python3 kb.py --vault /path/to/vault curate-nodes \
  .research-kb/curator-results/*.json
```

This writes populated body content into the target `.md` files and promotes `status` when the agent recommends it.

## Design Tensions

### Promotion threshold

When should a node go from `candidate` → `active`?

- After 1 paper? Too aggressive — a single-paper concept may be noise.
- After 2+ papers? Safer but some real concepts only appear in one paper.
- Agent-determined? The agent gives a recommendation; the researcher can override.

Recommendation: let the agent decide per-node with a `new_status` field, but default conservative (status stays `candidate` unless the agent explicitly sets `new_status: active` with strong evidence). The CLI's `apply` step can require `--promote` flag to honor agent-recommended promotions, keeping the researcher in control.

### Conflict handling

When Paper A and Paper B disagree about a concept (e.g., "gender differences in preposition use are robust" vs. "Bamman et al. found no significant difference"), the curator must:

1. Identify the conflict (same concept, contradictory evidence)
2. Populate "Competing Views" with both positions and evidence anchors
3. Not pick a winner

This requires the curator to compare evidence lines across papers, not just concatenate them. The paper notes already have `complicates::` and `contradicts::` edges — the curator can follow those too.

### Staleness and idempotency

- When a 6th paper links to a node already marked `active`, the curator should re-read and re-evaluate. At minimum, update "Key Papers."
- The curator should be idempotent: running it twice with the same inputs produces the same output.
- `review` and `lint` should detect stale nodes (newer papers link to a node but aren't listed in its "Key Papers" section).

### Batch vs. per-node

Two implementation approaches:

| Approach | Pros | Cons |
|----------|------|------|
| One curator sub-agent per node (parallel) | Fast, same pattern as paper-process | Sub-agents can't see each other's work; risk of inconsistent definitions for related nodes |
| One curator run handles all nodes (sequential) | Consistent, can cross-reference between related nodes | Slow for large vaults; harder to parallelize |

Recommendation: start with per-node (parallel), matching the paper-process pattern. The curator task JSON includes `related_nodes` so each agent sees adjacent nodes. Add a post-hoc consistency check (or a second-pass synthesis curator) later if needed.

## Integration Points

### CLI changes needed

A new subcommand or an extension to `apply-analysis`:

```
research_kb.py curate-nodes [--nodes NODE_PATH...] [--limit N] [--promote]
```

Without `--nodes`, scans all candidate nodes with ≥1 paper backlink and exports curator tasks to `.research-kb/curator-tasks/`. With `--nodes`, exports only specified nodes.

A companion command applies results:

```
research_kb.py apply-curation .research-kb/curator-results/*.json [--promote]
```

Without `--promote`, body content is written but status stays unchanged. With `--promote`, the agent's recommended `new_status` is honored.

### Skill references needed

A new reference file `references/node-curator-agent.md` (mirroring `references/paper-process-agent.md`) that defines:

- Mission and constraints
- Input format and fields
- Output schema
- Quality bar (definition should be useful to a reader new to the field, competing views must have evidence anchors, uncertainty is a feature)
- Safety rules (use only supplied paper note content, don't web-search, preserve existing researcher-reviewed sections)

### AGENTS.md update

Add to the agent rules:

```markdown
## Paper-Process Agent

- The agent must read the ENTIRE extracted_text field before producing results.
- The task's text_truncated_for_task flag is authoritative: if false, the full
  text is available and the agent must not claim truncation.
- If a section is absent despite full text being available, report the specific
  reason in uncertain_fields — not as "text was truncated."

## Curator Agent

- After new papers are processed, a curator agent runs in two phases.
- Phase 1 (Quality Gate): verifies each paper note against its source task JSON.
  Checks truncation claims, result presence, evidence anchors, and section
  completeness. Flags bad notes for re-processing.
- Phase 2 (Node Population): populates candidate concept, variable, method, and
  community nodes from quality-passed paper evidence only.
- The curator reads all papers that link to a node, not just new ones.
- It populates: definition, why it matters, competing views, related
  variables/methods, and open questions.
- It surfaces conflicts between papers rather than smoothing them.
- It marks its own uncertainty.
- Researcher-reviewed sections are never overwritten without --force.
```

## Relationship to Existing Architecture

This fits the same model-agnostic contract pattern already used for paper processing:

| Layer | Paper Process | Node Curator |
|-------|---------------|--------------|
| CLI exports | `agent-context` → task JSON | `curate-nodes` → task JSON |
| Agent reads | `paper-process-agent.md` | `node-curator-agent.md` |
| Agent writes | result JSON to `result_path` | result JSON to `result_path` |
| CLI applies | `apply-analysis` → paper note | `apply-curation` → node body |
| CLI creates stubs | `--create-nodes` | N/A (this IS the population step) |
| Deterministic fallback | `enrich` | None (no deterministic heuristic for concept synthesis) |
| Quality assurance | Agent self-reports `uncertain_fields` | Phase 1 quality gate: verifies paper notes against task JSONs, flags failures |

The curator is the missing half of the `--create-nodes` flag: `--create-nodes` creates scaffolding; the curator fills it in. And the quality gate is the missing verification step: paper-process agents self-report errors; the curator independently checks their work.

## Backlink Maintenance

The curator is responsible for keeping non-paper node backlinks current. This is a separate concern from content population — it can run independently (e.g., as a "backlink sync" pass) even for nodes that remain `candidate`.

### What goes stale

When `apply-analysis --create-nodes` creates a stub like `concepts/gender.md`, it writes:

```markdown
## Key Papers

- [[papers/nguyen-2016-...]]
- [[papers/jrgensen-2015-...]]
```

When a third paper lands and links to gender via `tests_social_factor:: [[concepts/gender]]`, the paper note gets the edge, but `concepts/gender.md`'s "Key Papers" list stays frozen at 2 entries. The same applies to "Related Variables" and "Related Methods" sections.

### Curator responsibilities

On each run, for every node with new inbound edges since last curation:

| Section | Action |
|---------|--------|
| Key Papers | Add new papers; reorder if one paper is clearly primary |
| Related Variables | Add if new `studies_variable` edges exist |
| Related Methods | Add if new `uses_method` edges exist |
| Competing Views | If new paper complicates/contradicts prior claims, add entry |
| Open Questions | If new paper raises unresolved issues, add |

The backlink sync should be idempotent — running it twice produces the same links. Deduplicate by path.

### Staleness detection

`lint` should flag stale backlinks: a node with status `active` whose "Key Papers" doesn't list all papers that have typed edges to it. This gives the researcher visibility into which nodes need curator attention.

## Current Truncation Limits (Reference)

| Constant | Value | Where |
|----------|-------|-------|
| `DEFAULT_PDF_TEXT_MAX_CHARS` | 500,000 | `process` — max characters extracted from a single PDF |
| `DEFAULT_AGENT_MAX_CHARS` | 120,000 | `agent-context` — max characters sent to sub-agent per task |

The 500K extraction cap is hardcoded. The 120K agent cap can be overridden with `--max-chars` on `agent-context`.

A "truncated" paper (source > 120K) gets `text_truncated_for_task: true` in the task JSON. Short papers (like 4-page workshop papers at ~18K chars) are not truncated — the sub-agent simply may not find extensive methods/results sections in the available text. The sub-agent should distinguish "text was truncated by the pipeline" from "paper is short and has limited content" — the former is flagged in the task JSON, the latter requires reading the full text before concluding.

## Open Questions

- Should the curator also populate author nodes (bio, institution, key works) or leave those as simple identity nodes?
- When a node has 10+ linking papers, should the curator read all of them or sample? The paper notes can be long (up to ~10K words each).
- Should synthesis notes be auto-generated by a curator, or always researcher-initiated?
- How does the curator handle a node that gained edges but the new paper's evidence is weaker or redundant — does it still update "Key Papers"?
- Should backlink sync run as a fast mechanical pass (no sub-agent needed) while content population uses the full agent contract?
