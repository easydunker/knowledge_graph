# Paper-Process Quality Guard

Status: implemented.

This note records the quality-guard design that replaced the original TODO. The triggering bug was a paper-process subagent reporting "no results available" or "text truncated" even when the task JSON contained the full extracted text. In the concrete Gupta and DiPadova NAACL 2019 SRW case, the task had `text_truncated_for_task: false` and about 18K characters of extracted text, but the agent stopped early and missed methods, results, and discussion.

## Implemented Safeguards

### Paper-Process Contract

`skills/research-kb/references/paper-process-agent.md` now requires the paper-process agent to:

- read the entire supplied `extracted_text` field before writing conclusions
- treat `text_truncated_for_task` as authoritative
- avoid claiming pipeline truncation when `text_truncated_for_task` is false
- report "section not identifiable in extracted text" rather than inventing truncation
- report `section_coverage`
- set `quality_self_check.read_full_extracted_text`
- set `quality_self_check.truncation_claim_matches_task`

`skills/research-kb/references/agent-contract.md` mirrors this requirement for harnesses validating paper-process outputs.

### Task Export

`agent-context` and `build-jobs export-paper` include the full retained extracted text by default. The old task-level character cap was removed as the default; `--max-chars <N>` remains an explicit opt-in for smaller harnesses, and `--max-chars 0` means no task-level cap.

Task JSON includes:

```json
{
  "source_text_chars": 18021,
  "extracted_text_chars": 18021,
  "text_truncated_for_task": false
}
```

### Apply-Time Validation

`apply-analysis` validates model outputs before applying them to Markdown. It records warnings when:

- `text_truncated_for_task_acknowledged` is missing
- `quality_self_check` is missing
- `quality_self_check.read_full_extracted_text` is not true
- `quality_self_check.truncation_claim_matches_task` is not true
- `section_coverage` is missing
- substantial extracted text returns no findings
- the analysis claims truncation while task/provenance says the task was not truncated

Warnings are stored in `kb_build.paper_process.validation_warnings`, and affected notes are marked `needs_review` unless already `quality_failed`.

### Quality Guard

`quality-guard` writes durable reports under:

```text
.research-kb/quality-reports/
```

It checks for:

- truncation claims that contradict `kb_build.extraction.text_truncated_for_task`
- "no results" claims when the extracted text contains result-like indicators
- missing substantive findings for substantial extracted text
- missing or weak evidence anchors
- missing major sections such as data, methods, or findings

Failed notes are marked:

```yaml
review_state: quality_failed
kb_build:
  quality:
    state: failed
```

Quality-failed notes remain searchable, but they are skipped for curation, synthesis creation, and automatic merge evidence.

### Resumable Build Integration

`build-jobs apply-paper` now applies returned paper-process JSON and immediately runs the quality guard for touched papers. A paper-process job is considered complete only when it reaches:

```text
quality_passed
```

This makes quality checks part of the default quota-resilient build path rather than a separate optional afterthought.

## Remaining Risk

The implemented guard catches common contradictions and incomplete outputs, but it is still not a full semantic verifier. A paper-process agent can still produce a plausible but shallow summary that passes heuristics. The intended mitigation is layered:

- paper-process agent contract
- apply-time schema and self-check validation
- automatic quality guard
- curator exclusion of quality-failed papers
- researcher review for notes marked `needs_review` or `quality_failed`

## Historical Reproduction

The original observed failure:

```text
PDF: raw/papers/N19-3013.pdf
Paper: Gupta & DiPadova, NAACL 2019 SRW
Task JSON:
  text_truncated_for_task: false
  extracted_text_chars: 18021
  actual content: methods, results, discussion
Bad paper note:
  claimed "no results available"
  claimed extracted text was truncated
Expected behavior now:
  agent must not claim truncation
  apply-analysis records self-check/coverage warnings if output is incomplete
  quality-guard flags contradictions before the paper can feed curation
```
