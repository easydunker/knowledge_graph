# Installation Guideline for Agent Harnesses

This guide is for installing and operating the `research-kb` skill from any agent harness on macOS. The harness may be Codex, another local agent runtime, or a custom orchestration layer. The core requirement is that the harness can read files, run shell commands, and optionally delegate model work to subagents or skills.

## Concepts

Keep these locations separate:

- **Skill directory:** reusable tooling, prompts, templates, and scripts.
- **Vault root:** the user's Obsidian knowledge-base content.

Example:

```text
~/.codex/skills/research-kb/          # installed skill/tooling
~/Documents/research-kb-vault/        # user-selected vault content
```

The skill directory must not store user PDFs or generated KB content. The vault root stores `raw/papers/`, `papers/`, `authors/`, graph nodes, `.research-kb/`, `index.md`, `log.md`, and vault-local templates.

## 1. Check macOS Prerequisites

Check Python:

```bash
python3 --version
python3 - <<'PY'
import sys
print(sys.executable)
print(sys.version)
PY
```

Recommended: Python 3.10 or newer.

If `python3` is missing or too old, install it with Homebrew:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python
python3 --version
```

Check `git`:

```bash
git --version
```

If macOS prompts for command line developer tools, install them and rerun the check.

## 2. Create a Python Environment

The CLI is dependency-light, but real PDF extraction should use `pymupdf4llm`. `pypdf` remains a compatibility fallback.

```bash
python3 -m venv ~/.venvs/research-kb
source ~/.venvs/research-kb/bin/activate
python -m pip install --upgrade pip
python -m pip install pymupdf4llm pypdf
python - <<'PY'
import pymupdf4llm
import pypdf
print("pymupdf4llm ok")
print("pypdf ok", pypdf.__version__)
PY
```

Harnesses should prefer this Python executable when running the skill:

```bash
~/.venvs/research-kb/bin/python
```

Metadata reconciliation uses only Python standard-library HTTP clients, so it does not require extra Python packages. It does require network access when Crossref, OpenAlex, or Semantic Scholar lookups are enabled.

Optional provider configuration:

```bash
# Optional but recommended for polite Crossref/OpenAlex usage.
export RESEARCH_KB_MAILTO="you@example.com"

# Optional. The command works without these keys using unauthenticated requests.
export OPENALEX_API_KEY=""
export SEMANTIC_SCHOLAR_API_KEY=""
```

## 3. Install the Skill

From a cloned repository:

```bash
mkdir -p ~/.codex/skills
rsync -a --delete /path/to/knowledge_graph/skills/research-kb/ ~/.codex/skills/research-kb/
```

Check expected files:

```bash
test -f ~/.codex/skills/research-kb/SKILL.md
test -x ~/.codex/skills/research-kb/scripts/research_kb.py
test -f ~/.codex/skills/research-kb/templates/paper.md
test -f ~/.codex/skills/research-kb/references/paper-process-agent.md
```

If the script is not executable:

```bash
chmod +x ~/.codex/skills/research-kb/scripts/research_kb.py
```

## 4. Choose and Initialize a Vault

Let the user choose the vault path. Do not default to the installed skill directory.

```bash
export SKILL="$HOME/.codex/skills/research-kb"
export VAULT="$HOME/Documents/research-kb-vault"
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" init
```

This creates scaffold folders and copies canonical templates from the skill into the vault:

```text
raw/papers/
papers/
authors/
concepts/
variables/
methods/
communities/
questions/
syntheses/
templates/
.research-kb/
```

Template resolution order during note generation:

1. vault-local `templates/*.md`
2. installed skill `templates/*.md`
3. embedded fallback in the script

## 5. Smoke-Test the CLI

Run:

```bash
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" index
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" lint
```

Expected result for a fresh vault: no fatal errors. The vault may have no papers yet.

Check generated search indexes:

```bash
ls "$VAULT/.research-kb"
ls "$VAULT/.research-kb/search"
```

## 6. Process PDFs

The user supplies PDFs by placing them in:

```text
$VAULT/raw/papers/
```

Then run deterministic intake:

```bash
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" process
```

This creates paper-note drafts with:

- `raw_pdf_path`
- `pdf_sha256`
- extracted metadata when available
- `authored_by:: [[authors/...]]` links
- candidate author nodes

## 7. Use Model-Assisted Paper Processing

The CLI never calls an LLM provider directly. The harness owns model execution.

Create or refresh the resumable job ledger:

```bash
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" build-jobs refresh
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" build-jobs status
```

Export a quota-friendly batch:

```bash
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" build-jobs export-paper --batch-size 10
```

The harness should process each file under:

```text
$VAULT/.research-kb/agent-tasks/paper/*.agent-task.json
```

For each task:

1. Read `references/paper-process-agent.md`.
2. Read `references/agent-contract.md`.
3. Use only the task JSON's extracted text and metadata.
4. Write exactly one result JSON to the task's `result_path`.
5. Do not edit Markdown notes directly from the subagent.

Apply results:

```bash
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" build-jobs apply-paper
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" build-jobs status
```

`build-jobs apply-paper` applies returned results, creates candidate graph nodes by default, runs quality guard for touched papers, and marks a paper job complete only when quality passed. Repeat `export-paper`, subagent processing, and `apply-paper` until no paper jobs remain pending/exported/running/result_written.

Then reconcile, curate, refresh, and check:

```bash
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" reconcile-metadata --apply --mailto "$RESEARCH_KB_MAILTO"
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" build-jobs export-curator --batch-size 20
# Run node curator subagents on "$VAULT/.research-kb/curator-tasks/jobs/"*.curator-task.json.
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" build-jobs apply-curator
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" index
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" lint
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" build-report
```

The lower-level commands `agent-context`, `apply-analysis`, `quality-guard`, `curator-context`, and `apply-curation` remain available for harnesses that already have their own queue system.

`reconcile-metadata` writes provider caches and audit reports under:

```text
$VAULT/.research-kb/metadata-cache/
$VAULT/.research-kb/reconciliation/
```

By default it does not rewrite Markdown. Add `--apply` only when the harness should write high-confidence paper metadata updates to frontmatter. Provider metadata is for bibliographic cleanup and duplicate/stale-node detection only; it must not be used as evidence for scholarly claims.

## 8. Query Harness Contract

For small vaults, the harness may run:

```bash
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" \
  --vault "$VAULT" \
  query "Dong Nguyen computational sociolinguistics" \
  --mode idea \
  --limit 8
```

For large vaults, do not load all of `.research-kb/index.json` or all paper summaries into the model. Probe generated JSONL indexes first:

```bash
rg -i "Dong Nguyen" "$VAULT/.research-kb/search/papers.jsonl" "$VAULT/.research-kb/search/nodes.jsonl"
rg -i "tone normaliz|Lobanov|semitone" "$VAULT/.research-kb/search/"*.jsonl
```

Then read only the selected candidate notes.

Query-side harness roles:

- `research-kb.query`: topic, author, title, DOI/year, method, variable, community, and clue-based lookup.
- `research-kb.claim-support`: suggest supporting, complicating, contradictory, or missing KB evidence for user prose. Suggest only; do not rewrite unless asked.
- `research-kb.synthesis`: discuss previous studies from the current KB, with coverage notes and gaps.

Capacity target:

- up to 10,000 paper notes in the vault
- up to about 10,000 words per paper note
- index/probe first
- detailed reading of a bounded candidate subset, normally 5-20 papers

## 9. Harness Safety Rules

Any harness integrating this skill should enforce:

- Do not add external papers unless the user supplies PDFs into `raw/papers/`.
- Do not treat web search as KB evidence.
- Treat Crossref, OpenAlex, and Semantic Scholar as metadata authorities only, not claim evidence.
- Do not modify Zotero.
- Do not write user content into the installed skill directory.
- Preserve `raw_pdf_path` and `pdf_sha256`.
- Preserve researcher-reviewed notes unless the user explicitly requests changes.
- Mark uncertain metadata, summaries, links, and author identity merges.

## 10. Minimal End-to-End Check

After adding one PDF to `raw/papers/`:

```bash
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" process --limit 1
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" build-jobs refresh
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" build-jobs export-paper --batch-size 1
find "$VAULT/.research-kb/agent-tasks/paper" -type f -name '*.agent-task.json' -print | head -n 1
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" build-jobs status
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" reconcile-metadata --apply --limit 1 --mailto "$RESEARCH_KB_MAILTO"
test -f "$VAULT/.research-kb/reconciliation/summary.json"
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" query "author name or paper topic" --mode idea
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" lint
```

If the exported paper task includes extracted text, `build-jobs status` reports the expected pending/exported state, and the query can find the paper by title, topic, or author, the harness has the basic integration working.
