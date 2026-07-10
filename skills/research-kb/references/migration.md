# Migration Workflow

Use this workflow when a researcher asks to migrate an existing Research KB or
an older checkout that doubled as a KB vault. The researcher should not run
commands or edit configuration.

## Agent Procedure

1. Identify the existing vault path and choose a new, empty vault path outside
   the installed skill and outside the source folder. Ask one short location
   question only if either path is genuinely unknown.
2. Run `research_kb.py --vault <new-vault> migrate --source <old-vault>` and
   inspect the no-change plan. It reports the selected content and confirms
   that the source remains untouched.
3. Because the researcher requested migration, run the same command with
   `--apply`. Do not delete, move, or modify the source folder.
4. Run `lint`, `index`, and `build-report` against the new vault. Explain any
   remaining lint errors or review exceptions in plain language.
5. Tell the researcher the new vault location and that the old folder is still
   available as a fallback. Do not ask the researcher to copy files, run a
   terminal command, edit a config file, or choose a queue command.

## Safety Contract

- `migrate` only copies allowlisted vault material: notes, PDFs, templates,
  Obsidian settings, archive, and vault-local tool state.
- It excludes Git data, symlinks, installed skill source, developer docs, and
  scripts from a legacy checkout.
- For a legacy checkout, it preserves the old root `AGENTS.md`, `index.md`, and
  `log.md` under `archive/migration/`, then creates current vault scaffold
  files so stale package links and rules do not become the active vault setup.
- The destination must be empty and must not nest inside the source. This
  prevents accidental merging or recursive copies.
- The source is never changed. The copied destination and the original source
  together provide the recovery path; migration also writes
  `.research-kb/reports/migration-report.json` in the new vault.
