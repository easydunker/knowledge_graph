# Query Architecture: Harness-Native Search Loop

## Current State

The `research-kb` skill uses a single-pass, CLI-driven query:

```
harness runs: python3 kb.py query "user question" --mode idea
CLI does:   token matching → graph traversal → scoring → ranked results
harness:    reads matched notes → synthesizes answer → done
```

**Limitations:**

- Token matching is brittle. "sociolinguistic variation in tone" scores differently than "socially conditioned tonal variation."
- No reflection. The harness has no mechanism to evaluate whether results are good or try alternative entry points.
- No multi-hop traversal. The CLI does one-hop from matched nodes to papers. The harness can't follow chains like paper → finding → concept → other paper.
- At large scale (10K+ papers), the model has no ability to iteratively refine search patterns.

## Target Architecture

Three components working together:

### 1. Updated Query CLI (`research-kb` skill)

Add `--nodes` flag to `query_vault()` in `research_kb.py`:

```
python3 kb.py query --nodes "methods/semitone-transformation,concepts/variationist-tone-normalization" --mode idea
```

Bypasses token matching. Starts traversal from resolved node paths. Follows typed edges to papers, scores normally, returns ranked results. Same deterministic engine, new entry point.

### 2. Bundled Query-Side Agents

Start with query-side agents bundled inside `research-kb`. A later `research-kb-query` split is possible if discovery grows too large, but v1 should avoid extra installation complexity.

**Key additions:**

- **Entity resolution instructions.** Parse user question into candidate entities. Match against index nodes by title, aliases, and semantic similarity. Convert to node paths.
- **Author nodes.** Authors are graph nodes so researchers can ask for a person's work. Paper notes should connect with `authored_by:: [[authors/name]]`; author identity remains local to the KB unless reviewed.

- **Search loop.** The model generates query formulations, the CLI runs them, the model evaluates results:
  ```
  1. Parse question → generate initial query string
  2. CLI query "raw string" → evaluate coverage
  3. Read top paper notes → extract linked concepts/variables/methods
  4. CLI query --nodes "discovered/paths" → find papers missed by token match
  5. Repeat with alternative entry points
  6. Synthesize with coverage report
  ```

- **Coverage reporting.** Every answer must report:
  - What was found and how (token match vs. typed-edge traversal)
  - What entry points were tried
  - What entry points were NOT tried
  - What the current KB does not cover

- **Query-side subagents.** The host harness delegates retrieval/synthesis tasks to bundled agents:
  - `research-kb.query` for topic, author, title, DOI/year, method, variable, community, and clue-based lookup.
  - `research-kb.claim-support` for paragraph enrichment. It suggests supporting, complicating, contradictory, or missing KB evidence; it does not rewrite unless explicitly asked.
  - `research-kb.synthesis` for previous-studies discussions.

**Capacity target:** each query-side agent must handle a vault of up to 10,000 papers, each up to about 10,000 words. Agents must not read the whole vault, full machine index, or all paper summaries into context. They use staged retrieval: JSONL probe-index search first, candidate pool second, bounded detailed paper-note reading third, then coverage reporting. If hundreds or thousands of papers are relevant, report the limit and propose a narrower follow-up.

### 3. Index as Probe Target (large-vault optimization)

At small scale (≤50 papers): harness may read small query outputs and selected index records, but should still prefer the probe-index habit.

At large scale (up to 10K papers): the root harness uses file search or `rg` to probe generated JSONL search indexes:

```
rg -i "tone normaliz|semitone|Lobanov" .research-kb/search/*.jsonl
rg -i "Dong Nguyen" .research-kb/search/papers.jsonl .research-kb/search/nodes.jsonl
```

The search index format should support this with bounded records:

```text
.research-kb/search/manifest.json
.research-kb/search/papers.jsonl
.research-kb/search/nodes.jsonl
.research-kb/search/edges.jsonl
```

The harness searches these files, resolves candidate papers/nodes, then feeds the small candidate set to the CLI or query-side agent.

**Index density target:** Each paper entry carries identity (title, year, authors), one-paragraph summary, typed edges, linked node identities, and trust status. Evidence and uncertainty text stays in Markdown — the index carries the claim, not the justification.

## Architecture Split

```
research-kb              → Content lifecycle
                           init, process, agent-context, apply-analysis,
                           lint, review, new-node, index generation

research-kb query agents → Discovery
                           entity resolution, search loop, claim support,
                           synthesis, coverage reporting
                           (uses research-kb CLI + vault schema)
```

Users install `research-kb` first. Split query agents into a separate `research-kb-query` skill only if the bundled query resources become too large or need independent release.

## Division of Labor

| Concern | Who owns it | Why |
|---------|------------|-----|
| Token matching, graph traversal, scoring | CLI (deterministic) | Mechanical problem, not a reasoning problem |
| Entity resolution, query formulation | Model | Semantic problem — needs understanding of domain vocabulary |
| Search loop iteration, coverage evaluation | Model | Reasoning problem — "did I find enough? what else should I try?" |
| Reading paper notes, synthesizing answer | Model | Synthesis problem — needs to connect findings across papers |
| PDF processing, vault maintenance, linting | CLI (deterministic) | Content integrity — should never depend on LLM quality |
| Index generation | CLI (deterministic) | Cache of Markdown truth — regenerable, not authoritative |

## Implementation Plan

### Phase 1: CLI `--nodes` flag

- [ ] Add `--nodes` argument to `query_vault()` in `research_kb.py`
- [ ] Resolve node paths, start traversal from matched nodes instead of token matching
- [ ] Same scoring algorithm, same output format
- [ ] Test: `python3 kb.py query --nodes "methods/semitone-transformation-relative-to-speaker-average-pitch"`

### Phase 2: Query agent scaffold

- [x] Add query-side agent references inside `skills/research-kb`
- [ ] Entity resolution instructions (question → candidate entities → node paths)
- [ ] Search loop instructions (formulate → CLI query → evaluate → iterate)
- [ ] Coverage report format specification
- [ ] Reference `skills/research-kb/references/vault-schema.md` for node types and relation labels

### Phase 3: Query agent subagents

- [x] Create `skills/research-kb/agents/query.yaml`
- [x] Create `skills/research-kb/agents/claim-support.yaml`
- [x] Create `skills/research-kb/agents/synthesis.yaml`
- [x] Add 10k-paper / 10k-word-per-paper corpus capacity contract
- [ ] Harden output format: evidence packets, claim matrix, and synthesis coverage report
- [ ] Test against installed sample vault (5 papers)

### Phase 4: Large-vault index format

- [ ] Define lean index format: identity + summary + edges + trust status (no evidence/uncertainty)
- [ ] Ensure index is `search_files`-friendly (flat JSON array or per-paper files)
- [ ] Update `index` command to generate lean format alongside full format
- [ ] Test search loop against synthetic 100-paper vault

### Phase 5: Reflection prompts

- [ ] Add reflection step to search loop: "I tried these entry points. Here's what I found. Here's what I didn't try. Should I continue?"
- [ ] Multi-hop traversal: paper → finding → concept → other paper
- [ ] Gap reporting: "The KB has no papers connecting concept X to method Y"
