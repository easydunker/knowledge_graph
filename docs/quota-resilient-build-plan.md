# Quota-Resilient Build Plan

This spec makes Research KB initial and incremental builds robust when the agent harness has quota limits, context limits, interruptions, or partial subagent failures. The goal is not merely smaller batches. The goal is a resumable build pipeline where the vault itself records what is complete, what is pending, what failed, and what can safely be retried.

## Design Position

Use quality-first completion semantics:

> A paper is considered processed only after its paper-process result has been applied to Markdown and `quality-guard` has passed.

This is stricter than treating a task JSON or result JSON as complete. A result that exists but was not applied is not processed. A result that was applied but failed quality guard is not processed for downstream curation. Quality-failed papers remain searchable, but curation, synthesis creation, and auto-merge evidence must ignore them unless a human explicitly reprocesses or reviews them.

The workflow should optimize for high-quality notes over lower model cost. Do not reintroduce a default paper text cap to save quota. If a user later needs cheaper processing, `agent-context --max-chars <N>` remains an explicit override, not the default.

## Current Capabilities

The existing CLI already provides useful primitives:

- `process --limit` creates draft paper notes from a bounded number of PDFs.
- `agent-context --limit` exports bounded paper-process tasks.
- Paper-process tasks include stable `result_path` fields.
- `apply-analysis` can apply one or more returned result JSON files.
- `quality-guard --limit` records pass/fail state.
- `curator-context --limit --max-papers` exports bounded node-curator tasks.
- `apply-curation` applies returned curator JSON.
- `build-report`, `review`, `lint`, and `index` expose build health.

The missing piece is a durable job layer that joins these commands into a resumable state machine.

## Proposed Job Model

Add generated job ledgers under the selected vault:

```text
.research-kb/jobs/
  paper-process.jsonl
  node-curation.jsonl
  build-runs.jsonl
```

These files are vault-local machine state. They are not skill code, not evidence, and not source-of-truth content. They can be regenerated from Markdown notes, raw PDFs, task files, result files, quality reports, and reconciliation reports, but should be kept during active builds to make resumes cheap and explicit.

### Paper Process Job

Each paper-process job represents one paper note and one version of the paper-process contract.

```json
{
  "job_id": "paper:<pdf_sha256>:paper-process-v1",
  "job_type": "paper_process",
  "note_path": "papers/example.md",
  "raw_pdf_path": "raw/papers/example.pdf",
  "pdf_sha256": "",
  "extracted_text_sha256": "",
  "agent_name": "research-kb.paper-process",
  "agent_contract_version": 1,
  "prompt_version": "paper-process-v1",
  "status": "pending",
  "attempts": 0,
  "max_attempts": 1,
  "task_path": ".research-kb/agent-tasks/paper/<job_id>.agent-task.json",
  "result_path": ".research-kb/agent-results/paper/<job_id>.agent-result.json",
  "quality_report_path": ".research-kb/quality-reports/<paper-id>.json",
  "last_error": "",
  "created_at": "",
  "updated_at": ""
}
```

### Node Curation Job

Each curator job represents one non-paper node and one version of the curator contract.

```json
{
  "job_id": "curator:<node_path_sha256>:node-curator-v1",
  "job_type": "node_curation",
  "node_path": "concepts/example.md",
  "node_type": "concept",
  "agent_name": "research-kb.node-curator",
  "agent_contract_version": 1,
  "prompt_version": "node-curator-v1",
  "status": "pending",
  "attempts": 0,
  "max_attempts": 1,
  "task_path": ".research-kb/curator-tasks/<job_id>.curator-task.json",
  "result_path": ".research-kb/curator-results/<job_id>.curator-result.json",
  "evidence_fingerprint": "",
  "last_error": "",
  "created_at": "",
  "updated_at": ""
}
```

## Job Statuses

Use a small explicit state machine:

```text
pending
  -> exported
  -> running
  -> result_written
  -> applied
  -> quality_passed

pending/exported/running/result_written/applied
  -> failed

applied
  -> quality_failed

quality_failed
  -> retry_pending
```

Meaning:

- `pending`: job exists but no current task was exported.
- `exported`: task JSON exists and can be assigned to a subagent.
- `running`: harness has dispatched the job. This is advisory because most harnesses cannot guarantee callback state.
- `result_written`: result JSON exists and passes basic JSON/schema validation.
- `applied`: result JSON was applied to Markdown.
- `quality_passed`: paper note passed `quality-guard`; this is the completion state for paper jobs.
- `quality_failed`: result was applied, but automatic quality checks failed.
- `failed`: task/result/export/apply crashed or returned invalid output.
- `retry_pending`: user or harness explicitly selected a failed job for another attempt.

For paper jobs, only `quality_passed` counts as complete. For curator jobs, `applied` counts as complete, because curation is already downstream of quality-passed paper evidence and `apply-curation` validates merge/archive confidence.

## Stable Paths

Task and result filenames should be stable by job identity, not only by note stem:

```text
.research-kb/agent-tasks/paper/<job_id>.agent-task.json
.research-kb/agent-results/paper/<job_id>.agent-result.json
.research-kb/curator-tasks/<job_id>.curator-task.json
.research-kb/curator-results/<job_id>.curator-result.json
```

This prevents collisions when note slugs change and makes resume behavior deterministic. Existing flat folders can remain supported for compatibility, but the job-aware commands should prefer the typed subfolders.

## CLI Additions

Add a small build-job command family. Names can be refined during implementation, but the behavior should stay explicit.

```bash
python3 research_kb.py --vault "$VAULT" build-jobs refresh
python3 research_kb.py --vault "$VAULT" build-jobs status
python3 research_kb.py --vault "$VAULT" build-jobs export-paper --batch-size 10
python3 research_kb.py --vault "$VAULT" build-jobs apply-paper
python3 research_kb.py --vault "$VAULT" build-jobs export-curator --batch-size 20
python3 research_kb.py --vault "$VAULT" build-jobs apply-curator
python3 research_kb.py --vault "$VAULT" build-jobs retry-failed --limit 5
```

### `build-jobs refresh`

Reconstruct or update ledgers from current vault state:

- raw PDFs and paper notes
- `pdf_sha256` and `raw_pdf_path`
- `kb_build.extraction`
- existing task/result files
- paper-process provenance in `kb_build.paper_process`
- quality reports and `review_state`
- curator task/result files
- archived merge/invalid records

This command should be safe to run repeatedly.

### `build-jobs status`

Print a compact build dashboard:

```text
Paper process jobs:
- quality_passed: 82
- pending: 13
- exported: 10
- result_written: 4
- quality_failed: 3
- failed: 1

Next suggested command:
python3 ... build-jobs export-paper --batch-size 10
```

Also write a machine-readable status file:

```text
.research-kb/jobs/status.json
```

### `build-jobs export-paper --batch-size N`

Select up to `N` paper jobs whose status is `pending` or `retry_pending`, export task JSON, and mark them `exported`.

Selection order should be stable:

1. unprocessed supplied PDFs with draft paper notes
2. jobs with no result JSON
3. jobs explicitly marked `retry_pending`

Do not export jobs whose paper already has `quality_passed` for the same `pdf_sha256`, `extracted_text_sha256`, `agent_contract_version`, and `prompt_version`.

### `build-jobs apply-paper`

Find result JSON files for `exported`, `running`, or `result_written` jobs, validate them, apply them with the existing `apply-analysis` behavior, then run quality guard for those notes.

Status transitions:

- valid result applied and quality passed: `quality_passed`
- valid result applied but quality failed: `quality_failed`
- invalid JSON/schema or apply crash: `failed`
- missing result: leave status unchanged

This command should be idempotent. Re-running it should not duplicate graph edges, overwrite researcher-reviewed notes, or reapply already-applied equivalent results.

### `build-jobs export-curator --batch-size N`

Run after paper jobs have quality-passed and metadata reconciliation has completed.

Select up to `N` curator jobs for affected non-paper nodes. Evidence must come only from quality-passed paper notes and reconciliation clusters. Quality-failed papers must not feed curation evidence.

### `build-jobs apply-curator`

Find returned curator results, validate them, apply them with existing `apply-curation` behavior, and mark curator jobs `applied` or `failed`.

High-confidence merge/archive behavior remains unchanged:

- non-paper duplicate nodes can be auto-merged when confidence is high
- paper duplicate notes require very strong identity evidence
- merged notes move to `archive/merged/`
- invalid/stale candidate nodes move to `archive/invalid/`

### `build-jobs retry-failed`

Move selected `failed` or `quality_failed` jobs to `retry_pending` and increment attempt tracking.

Defaults:

- do not retry automatically
- do not retry beyond `max_attempts` unless `--force` is passed
- do not retry researcher-reviewed notes unless `--force` is passed

This matches the current quality policy: failures are recorded for manual retry rather than hidden by automatic loops.

## Harness Workflow

The harness should use small batches, but the batch size is only a scheduling knob. The ledger is the source of resume truth.

```bash
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" init
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" process
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" build-jobs refresh
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" build-jobs status
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" build-jobs export-paper --batch-size 10
```

Then the harness dispatches only the exported paper-process tasks. If quota runs out, the next run resumes:

```bash
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" build-jobs apply-paper
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" build-jobs status
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" build-jobs export-paper --batch-size 10
```

When paper jobs are quality-passed:

```bash
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" reconcile-metadata --apply
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" build-jobs refresh
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" build-jobs export-curator --batch-size 20
```

After curator subagents return:

```bash
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" build-jobs apply-curator
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" lint
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" index
python3 <skill-dir>/scripts/research_kb.py --vault "$VAULT" build-report
```

## Skill Guidance Updates

Update `SKILL.md` and `references/workflows.md` so future harnesses do not try to process the whole vault in one burst.

Default guidance:

- prefer `build-jobs` commands for Codex or any quota-constrained harness
- use batches of 5-20 paper tasks for normal subscriptions
- after every batch, run `build-jobs apply-paper` and `build-jobs status`
- stop cleanly when quota is low; the next run resumes from the ledger
- do not feed curation until papers are quality-passed

The skill should still expose the lower-level commands (`agent-context`, `apply-analysis`, `curator-context`, `apply-curation`) for harnesses that already have their own job system.

## Query-Stage Boundary

Build job ledgers and `kb_build` provenance are maintenance data. Query agents should not use them as scholarly evidence.

Allowed query-stage uses:

- warn that a paper is `quality_failed`
- decide to load full extracted/source text before using a quality-failed paper
- answer user questions about build status or provenance

Disallowed query-stage uses:

- cite `kb_build` as evidence for a scholarly claim
- treat provider metadata as evidence
- treat job status as a relevance signal except for quality/trust filtering

## Open Design Questions

1. Should `running` jobs expire back to `exported` after a timeout?
   - Recommendation: yes. Harnesses can die after dispatch. A stale `running` job should become exportable again after a configurable interval.

2. Should job ledgers be append-only or rewritten snapshots?
   - Recommendation: keep JSONL event history in `build-runs.jsonl`, but rewrite `paper-process.jsonl` and `node-curation.jsonl` as current-state snapshots for simple tooling.

3. Should `build-jobs apply-paper` run quality guard internally?
   - Recommendation: yes. Quality-passed is the completion boundary, so applying without checking quality creates an unsafe halfway state.

4. Should metadata reconciliation be represented as jobs?
   - Recommendation: not in v1. It is deterministic/API-backed, cacheable, and already resumable through provider caches. Add jobs later only if provider quota/rate limits become painful.

5. Should curator jobs be blocked until all paper jobs are done?
   - Recommendation: no. For incremental builds, curator jobs may run for nodes affected by the current batch, but only using quality-passed papers. A final curator pass should run after all intended paper batches complete.

## Implementation Plan

### Phase 1: Ledger foundation

- Add job record helpers to `research_kb.py`.
- Add `.research-kb/jobs/` constants and config entries.
- Implement `build-jobs refresh`.
- Implement `build-jobs status`.
- Test refresh/status on the sample vault and an empty vault.

### Phase 2: Paper queue

- Add stable paper job IDs from `pdf_sha256`, `extracted_text_sha256`, and prompt version.
- Add job-aware task/result paths.
- Implement `build-jobs export-paper --batch-size`.
- Implement `build-jobs apply-paper`.
- Run quality guard inside `apply-paper`.
- Ensure `quality_passed` is the only paper completion state.
- Test interruption cases:
  - task exported, no result
  - result exists, not applied
  - result invalid
  - result applied, quality failed
  - rerun after success

### Phase 3: Curator queue

- Add curator job IDs from node path, evidence fingerprint, and prompt version.
- Implement `build-jobs export-curator --batch-size`.
- Implement `build-jobs apply-curator`.
- Ensure only quality-passed paper evidence is included.
- Test duplicate/stale-node reports and high-confidence merge/archive plans.

### Phase 4: Skill workflow docs

- Update `SKILL.md` quick start to prefer resumable `build-jobs`.
- Update `references/workflows.md` with quota-resilient batch/resume workflow.
- Update installation guide with a smoke test for `build-jobs status`.

### Phase 5: Optimization and reporting

- Add `--json` output to `build-jobs status`.
- Add `--batch-size` recommendations based on average extracted text length.
- Add a build-report section for incomplete jobs and suggested next command.
- Add stale `running` job recovery.

## Acceptance Criteria

- A user can stop after any batch and rerun later without losing state.
- Completed quality-passed papers are not reprocessed unless source hash or prompt/contract version changes.
- Result JSON files can arrive out of order and still be applied safely.
- Quality-failed papers are recorded, searchable, and excluded from curator/synthesis evidence.
- The harness can ask for the next batch without loading all task/result files into context.
- The system provides a clear next command when work remains.
- Low-level commands remain available for non-Codex harnesses with their own queue systems.
