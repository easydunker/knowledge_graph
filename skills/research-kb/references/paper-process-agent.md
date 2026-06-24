# Paper Process Agent

Use this reference when Codex can spawn a worker/subagent to process Research KB paper-analysis tasks. The worker handles exactly one `.research-kb/agent-tasks/*.agent-task.json` file and writes exactly one analysis result JSON.

## Mission

Understand and summarize one input research paper from the supplied extracted PDF text. Produce source-grounded metadata, a one-paragraph summary, research questions, data/participants, variables, social factors, methods, findings, limitations, useful quotes, and candidate graph edges for the KB.

## Inputs

The task JSON is the authority. Read these fields first:

- `task`: must be `research_kb_paper_analysis`.
- `agent`: expected `research-kb.paper-process`.
- `note_path`, `raw_pdf_path`, and `pdf_sha256`: preserve these identifiers.
- `text_extraction_status`: use it to calibrate confidence.
- `source_text_chars`, `extracted_text_chars`, and `text_truncated_for_task`: use these to identify whether the task contains the whole extracted paper text or a capped excerpt.
- `existing_metadata`: use as starting metadata, but correct it only when the extracted text clearly supports the correction.
- `known_nodes`: prefer these existing graph nodes when substantively relevant.
- `expected_json_schema`: the required analysis object schema.
- `extracted_text` and `prompt`: the only evidence for paper content.
- `result_path`: where to write the result JSON when available.

Do not use web search, prior knowledge of the paper, DOI lookup, Zotero, or any source outside the task JSON.

## Procedure

1. Verify the task is for one paper and has extracted text. If text is missing, extraction is poor, or `text_truncated_for_task` is true, return conservative fields and list the limitation in `uncertain_fields`.
2. Identify the paper's purpose, research question, data/participants, methods, variables, social factors, and main findings from the extracted text only.
3. Make `one_paragraph_summary` the strongest part of the output: summarize what the paper studies, what evidence/data it uses, how it analyzes the evidence, and what it concludes.
4. Attach evidence anchors wherever possible. Convert `@@PAGE:N@@` markers to anchors such as `p. N`, `p. N, Table 2`, or `p. N, section heading`.
5. For graph links, prefer existing nodes from `known_nodes`. Create new slugs only for substantive concepts, variables, methods, or communities that would be useful KB nodes. Use lowercase hyphen-case slugs.
6. Mark weak or inferred claims in `uncertain_fields` or edge `uncertainty`. Do not smooth over contradictions, missing methods, or extraction gaps.
7. Return all fields required by `expected_json_schema`. Use empty strings or empty arrays rather than omitting required keys.
8. Write the result JSON to `result_path` if provided. Do not edit Markdown notes, indexes, PDFs, or other vault files.

## Output Envelope

Prefer this wrapper so `apply-analysis` can record agent provenance:

```json
{
  "note_path": "papers/example.md",
  "agent_source": "research-kb.paper-process",
  "agent_model": "codex",
  "analysis": {
    "title": "",
    "authors": [],
    "year": "",
    "doi": "",
    "publication": "",
    "one_paragraph_summary": "",
    "research_question": [],
    "data_and_participants": [],
    "linguistic_variables": [],
    "social_factors": [],
    "methods_and_measures": [],
    "graph_edges": [],
    "key_findings": [],
    "theoretical_contribution": [],
    "limitations": [],
    "useful_quotes": [],
    "uncertain_fields": []
  }
}
```

The `analysis` object must match the task's `expected_json_schema` exactly.

## Quality Bar

- The summary should be useful to a researcher who has not read the paper yet.
- Findings must be distinguishable from background claims.
- Evidence anchors should point back to pages, sections, tables, examples, or short quotes in the extracted text.
- Candidate graph edges should be sparse and meaningful, not keyword dumps.
- Uncertainty is a feature, not a failure; preserve it clearly.
