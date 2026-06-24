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

The CLI is dependency-light, but real PDF extraction should use `pypdf`.

```bash
python3 -m venv ~/.venvs/research-kb
source ~/.venvs/research-kb/bin/activate
python -m pip install --upgrade pip
python -m pip install pypdf
python - <<'PY'
import pypdf
print("pypdf ok", pypdf.__version__)
PY
```

Harnesses should prefer this Python executable when running the skill:

```bash
~/.venvs/research-kb/bin/python
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

Export tasks:

```bash
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" agent-context
```

The harness should process each file under:

```text
$VAULT/.research-kb/agent-tasks/*.agent-task.json
```

For each task:

1. Read `references/paper-process-agent.md`.
2. Read `references/agent-contract.md`.
3. Use only the task JSON's extracted text and metadata.
4. Write exactly one result JSON to the task's `result_path`.
5. Do not edit Markdown notes directly from the subagent.

Apply results:

```bash
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" \
  --vault "$VAULT" \
  apply-analysis "$VAULT/.research-kb/agent-results/"*.json \
  --create-nodes
```

Then refresh and check:

```bash
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" index
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" lint
```

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
- Do not modify Zotero.
- Do not write user content into the installed skill directory.
- Preserve `raw_pdf_path` and `pdf_sha256`.
- Preserve researcher-reviewed notes unless the user explicitly requests changes.
- Mark uncertain metadata, summaries, links, and author identity merges.

## 10. Minimal End-to-End Check

After adding one PDF to `raw/papers/`:

```bash
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" process --limit 1
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" agent-context --limit 1
find "$VAULT/.research-kb/agent-tasks" -name '*.json' -maxdepth 1
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" query "author name or paper topic" --mode idea
~/.venvs/research-kb/bin/python "$SKILL/scripts/research_kb.py" --vault "$VAULT" lint
```

If `agent-context` includes extracted text and the query can find the paper by title, topic, or author, the harness has the basic integration working.
