# Research KB

Research KB is a distributable Codex plugin for creating and maintaining a
private, Obsidian-first research knowledge base from researcher-supplied PDFs.
It is tooling, not a knowledge-base vault: every researcher keeps notes, PDFs,
indexes, and settings in a separate folder they own.

## For Researchers

Give your agent harness this repository URL and one request. You do not need to
run commands, copy files, or edit configuration.

```text
Install Research KB from https://github.com/easydunker/knowledge_graph and
create a new research knowledge base for me.
```

To move an older KB or a previous copy of this repository that was used as a
vault:

```text
Install Research KB from https://github.com/easydunker/knowledge_graph and
migrate my existing Research KB. Preserve all notes and PDFs, keep the old
folder unchanged, and tell me where the new vault is.
```

The agent installs the plugin or skill, chooses or asks for a vault location,
creates a non-destructive migration plan, performs the copy, verifies the new
vault, and reports the result. The original folder remains untouched.

## What Is Installed

The plugin manifest is [`.codex-plugin/plugin.json`](.codex-plugin/plugin.json).
Its bundled skill is [`skills/research-kb`](skills/research-kb), containing the
instructions, deterministic CLI, templates, and worker contracts. The CLI
requires an explicit vault path and refuses to write inside the installed skill.
For Codex, [`.agents/plugins/marketplace.json`](.agents/plugins/marketplace.json)
also exposes the repository as a Git-backed plugin marketplace, so an agent can
install it directly from this URL without a hand-built local configuration.

The user vault is created separately and contains material such as:

```text
index.md
log.md
raw/papers/
papers/
authors/
concepts/
.research-kb/
```

## Maintainers

- Keep reusable package material under `skills/research-kb/`.
- Never add researcher PDFs, notes, Obsidian settings, or generated vault state
  to this repository.
- Run `python3 -m unittest discover -s tests -v` before release.
- Validate the plugin manifest with the bundled plugin validator when available.

See [INSTALL.md](INSTALL.md) for the harness protocol and
[migration workflow](skills/research-kb/references/migration.md) for the
agent-facing safety contract.
