# Agent Contract

Use this reference when implementing or validating Research KB agent/subagent outputs. The CLI remains model-agnostic: agents write JSON, and `research_kb.py apply-analysis` validates and applies it to Markdown notes.

## Paper Process Contract

Input files are emitted by:

```bash
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

The process agent writes one JSON file per task under `.research-kb/agent-results/`.

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

Use empty strings or arrays when a field is not supported by the extracted text.

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
