# Package Contributor Rules

- This repository is a reusable plugin package, never a researcher vault.
- Keep all reusable skill content under `skills/research-kb/`.
- Do not add PDFs, notes, Obsidian settings, `.research-kb/` state, or mutable
  `index.md`/`log.md` content at the repository root.
- Preserve the explicit external-vault guard and non-destructive migration
  contract when changing the CLI.
- Update tests whenever the installation, migration, task-path, or scaffold
  contract changes.
