# Agent Harness Installation

This document is for an agent harness, not for the researcher. The researcher
only needs to paste the repository URL and ask to install, create, or migrate.

## Install

1. Prefer the harness's plugin installer and the repository's Git-backed
   `.agents/plugins/marketplace.json`. In Codex, an agent can add the supplied
   GitHub repository as a marketplace and install `research-kb` from it; the
   researcher does not run these commands.
2. Validate that the installed plugin resolves its
   `.codex-plugin/plugin.json` manifest before use.
3. If the harness only installs standalone skills, install the repository path
   `skills/research-kb/` with its GitHub-skill installer.
4. Keep the installed package outside any user vault. Do not copy the whole
   repository into a vault.
5. Ensure Python 3.10+ is available. `pymupdf4llm` and `pypdf` are optional
   extraction enhancements; the CLI remains usable without them.

## Create a New Vault

Choose an external user-owned folder, then run the bundled CLI with that path:

```bash
python3 <installed-skill>/scripts/research_kb.py --vault <user-vault> init
```

The CLI never defaults to the current directory. It rejects a vault located in
the installed package.

## Migrate a Legacy Vault

For a user who asked to migrate, choose a new empty external destination.
First run the no-change plan, then apply it:

```bash
python3 <installed-skill>/scripts/research_kb.py --vault <new-vault> migrate --source <old-vault>
python3 <installed-skill>/scripts/research_kb.py --vault <new-vault> migrate --source <old-vault> --apply
python3 <installed-skill>/scripts/research_kb.py --vault <new-vault> lint
python3 <installed-skill>/scripts/research_kb.py --vault <new-vault> index
python3 <installed-skill>/scripts/research_kb.py --vault <new-vault> build-report
```

Migration copies only vault material, skips package/developer files and
symlinks, and never changes the source. See the bundled
[`migration workflow`](skills/research-kb/references/migration.md).
