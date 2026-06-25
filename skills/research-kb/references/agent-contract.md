# Agent Contract

Use this reference when implementing or validating Research KB agent/subagent outputs. The CLI remains model-agnostic: agents write JSON, and `research_kb.py build-jobs apply-paper` or the lower-level `apply-analysis` validates and applies paper results to Markdown notes.

## Paper Process Contract

Input files are emitted by:

```bash
python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault build-jobs export-paper --batch-size 10
# or, for harnesses with their own queue:
python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault agent-context
```

Each task describes one paper and includes:

- `agent`: `research-kb.paper-process`
- `primary_goal`: `understand_and_summarize_input_paper`
- `note_path`, `raw_pdf_path`, `pdf_sha256`
- `known_nodes`
- `extracted_text`
- `source_text_chars`, `extracted_text_chars`, and `text_truncated_for_task`
- `expected_json_schema`
- `result_path`

The process agent writes one JSON file per task to the task's `result_path`. Job-aware exports usually place results under `.research-kb/agent-results/paper/`; lower-level exports may use `.research-kb/agent-results/`.

## Output Shape

Use this envelope:

```json
{
  "note_path": "papers/example.md",
  "agent_source": "research-kb.paper-process",
  "agent_model": "codex",
  "analysis": {}
}
```

The `analysis` object must match the task's `expected_json_schema`. Required top-level fields are:

- `title`, `authors`, `year`, `doi`, `publication`
- `one_paragraph_summary`
- `research_question`
- `data_and_participants`
- `linguistic_variables`
- `social_factors`
- `methods_and_measures`
- `graph_edges`
- `key_findings`
- `theoretical_contribution`
- `limitations`
- `useful_quotes`
- `uncertain_fields`
- `text_truncated_for_task_acknowledged`
- `section_coverage`
- `quality_self_check`

Use empty strings or arrays when a field is not supported by the extracted text.

The process agent must read the complete supplied `extracted_text` field. The task's `text_truncated_for_task` flag is authoritative. If it is false, the agent must not claim that the pipeline truncated the text.

`agent-context` exports the full retained extracted text by default. Use `--max-chars <N>` only when a harness or model needs a smaller paper-processing task; `--max-chars 0` keeps the default no task-level cap behavior.

## Edge Objects

Graph edge objects use:

```json
{
  "relation": "uses_method",
  "node_type": "method",
  "label": "Mixed-effects models",
  "slug": "mixed-effects-models",
  "evidence": "p. 7, Methods",
  "uncertainty": ""
}
```

Prefer relation labels from the vault schema:

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

Prefer `node_type` values `concept`, `variable`, `method`, or `community`.

## Safety Rules

- Use only the extracted text and metadata in the task JSON.
- Never overwrite researcher-reviewed Markdown directly.
- Never write into the installed skill directory.
- Do not add external papers or treat web search as KB evidence.
- Preserve uncertainty and extraction limits in the JSON.

## Node Curator Contract

Input files are emitted by:

```bash
python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault build-jobs export-curator --batch-size 20
# or, for harnesses with their own queue:
python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault curator-context
```

Each task describes one non-paper node and includes:

- `agent`: `research-kb.node-curator`
- `primary_goal`: `enrich_node_and_preserve_graph_integrity`
- `node_path`, `node_type`, `node_status`, `node_title`
- `existing_node_content`
- `inbound_papers`
- `stale_key_papers`
- `related_nodes`
- `expected_json_schema`
- `result_path`

The curator writes one JSON file per task to the task's `result_path`. Job-aware exports usually place results under `.research-kb/curator-results/jobs/`; lower-level exports may use `.research-kb/curator-results/`.

Curator results may update the target node, create active synthesis notes when evidence is strong, and propose high-confidence merge plans. The CLI applies the result with:

```bash
python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault build-jobs apply-curator
# or, for harnesses with their own queue:
python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault apply-curation .research-kb/curator-results/*.json
```
