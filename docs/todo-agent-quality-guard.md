# TODO: Paper-Process Agent Quality Guard

## Bug

The paper-process sub-agent can report "no results available" / "text truncated" even when the full extracted text IS present in the task JSON. This happened with gupta-2019 (NAACL SRW): the agent only read the first chunk of 18K chars and stopped, missing methods (MFCCs, grid search), results (AUC 0.892, 81.1% accuracy), and discussion on pages 2-5.

## Root cause

The agent does not verify that it has consumed the entire `extracted_text` field before concluding content is missing. The task JSON provides an authoritative flag (`text_truncated_for_task: true/false`) but the agent ignores it and makes its own incorrect determination.

## Required fixes

### 1. Contract update (references/paper-process-agent.md)

Add to the Procedure section:

```markdown
- Before concluding text is truncated or missing, verify you have read the
  ENTIRE extracted_text field. The task's `text_truncated_for_task` field is
  authoritative — if it says false, the full extracted text is available and
  you must find and analyze all sections (methods, results, discussion,
  conclusion) that appear in it.
- If text_truncated_for_task is false and you cannot find results, report
  "results section not identifiable in extracted text" in uncertain_fields
  rather than claiming the text was truncated.
```

### 2. Quality gate (curator agent, future)

When the curator reads a paper note that claims "no results available" or that extraction was truncated:

1. Check the original task JSON — if `text_truncated_for_task: false`, the agent claim is suspect
2. Optionally scan the extracted text for obvious result indicators (numbers, percentages, "accuracy", "AUC", "Table", "Figure")
3. If results appear to exist, flag the paper note as needing re-processing rather than accepting the bad analysis

### 3. CLI change (optional, nice-to-have)

`lint` could warn when a paper note has `text_truncated_for_task: false` in its task JSON but the note body contains phrases like "no results available" or "text truncated" — indicating the agent contradicted the pipeline's own determination.

## Concrete reproduction

```
PDF: raw/papers/N19-3013.pdf (Gupta & DiPadova, NAACL 2019 SRW)
Task JSON: gupta-2019-...agent-task.json
  text_truncated_for_task: false
  extracted_text_chars: 18021
  Actual content: 5 pages, methods (MFCCs, grid search), results (AUC 0.892, 81.1% accuracy), discussion
Paper note: gupta-2019-...md
  Claims: "no results available", "text truncated in Introduction"
  Reality: results ARE present on pages 3-4 of extracted text
```
