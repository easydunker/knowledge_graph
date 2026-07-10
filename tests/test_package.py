from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / ".codex-plugin" / "plugin.json"
MARKETPLACE = REPO / ".agents" / "plugins" / "marketplace.json"
SKILL = REPO / "skills" / "research-kb"
CLI = SKILL / "scripts" / "research_kb.py"


def run_cli(skill: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(skill / "scripts" / "research_kb.py"), *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def load_cli_module():
    spec = importlib.util.spec_from_file_location("research_kb_test_module", CLI)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PackageTests(unittest.TestCase):
    def test_plugin_manifest_points_to_the_bundled_skill(self) -> None:
        manifest = json.loads(PLUGIN.read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "research-kb")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertTrue((REPO / manifest["skills"] / "research-kb" / "SKILL.md").is_file())

    def test_marketplace_exposes_this_git_backed_plugin(self) -> None:
        marketplace = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], "research-kb")
        self.assertEqual(entry["source"]["source"], "url")
        self.assertEqual(entry["source"]["url"], "https://github.com/easydunker/knowledge_graph.git")

    def test_root_has_no_tracked_vault_content(self) -> None:
        forbidden = [
            "index.md",
            "log.md",
            ".obsidian",
            ".research-kb",
            "raw",
            "papers",
            "authors",
            "concepts",
            "variables",
            "methods",
            "communities",
            "questions",
            "syntheses",
            "templates",
        ]
        for name in forbidden:
            self.assertFalse((REPO / name).exists(), name)

    def test_clean_installed_skill_requires_an_external_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            installed = temp_path / "research-kb"
            shutil.copytree(SKILL, installed)

            missing = run_cli(installed, "init", cwd=installed)
            self.assertNotEqual(missing.returncode, 0)
            self.assertFalse((installed / "index.md").exists())

            inside = run_cli(installed, "--vault", str(installed), "init")
            self.assertNotEqual(inside.returncode, 0)
            self.assertFalse((installed / "index.md").exists())

            contains_skill = run_cli(installed, "--vault", str(temp_path), "init")
            self.assertNotEqual(contains_skill.returncode, 0)
            self.assertFalse((temp_path / "index.md").exists())

            vault = temp_path / "researcher-vault"
            for command in ("init", "lint", "index"):
                result = run_cli(installed, "--vault", str(vault), command)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            vault_readme = (vault / "README.md").read_text(encoding="utf-8")
            self.assertNotIn("scripts/kb.py", vault_readme)
            self.assertTrue((vault / "index.md").is_file())
            self.assertFalse((vault / "plugins" / "zotero").exists())

            escaped_save = run_cli(installed, "--vault", str(vault), "query", "missing", "--save", ".")
            self.assertNotEqual(escaped_save.returncode, 0)
            self.assertFalse((temp_path / "researcher-vault.md").exists())

    def test_migration_is_non_destructive_and_excludes_package_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            source = temp_path / "legacy"
            destination = temp_path / "migrated"
            (source / "papers").mkdir(parents=True)
            (source / "raw" / "papers").mkdir(parents=True)
            (source / "skills" / "research-kb").mkdir(parents=True)
            (source / "skills" / "research-kb" / "SKILL.md").write_text("legacy package", encoding="utf-8")
            (source / "index.md").write_text("# My KB", encoding="utf-8")
            (source / "log.md").write_text("# My Log", encoding="utf-8")
            (source / "AGENTS.md").write_text("# Package Contributor Rules", encoding="utf-8")
            (source / "papers" / "one.md").write_text("# One", encoding="utf-8")
            (source / "raw" / "papers" / "one.pdf").write_bytes(b"researcher supplied PDF")
            (source / "docs").mkdir()
            (source / "docs" / "developer.md").write_text("do not copy", encoding="utf-8")

            plan = run_cli(SKILL, "--vault", str(destination), "migrate", "--source", str(source))
            self.assertEqual(plan.returncode, 0, plan.stdout + plan.stderr)
            self.assertFalse(destination.exists())

            applied = run_cli(SKILL, "--vault", str(destination), "migrate", "--source", str(source), "--apply")
            self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
            self.assertEqual((source / "papers" / "one.md").read_text(encoding="utf-8"), "# One")
            self.assertTrue((destination / "papers" / "one.md").is_file())
            self.assertTrue((destination / "raw" / "papers" / "one.pdf").is_file())
            self.assertFalse((destination / "skills").exists())
            self.assertFalse((destination / "docs").exists())
            self.assertTrue((destination / "archive" / "migration" / "legacy-index.md").is_file())
            self.assertFalse((destination / "archive" / "migration" / "legacy-AGENTS.md").exists())
            self.assertIn("Research KB Index", (destination / "index.md").read_text(encoding="utf-8"))
            self.assertTrue((destination / ".research-kb" / "reports" / "migration-report.json").is_file())
            for command in ("lint", "index", "build-report"):
                verified = run_cli(SKILL, "--vault", str(destination), command)
                self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)

    def test_migration_never_merges_into_a_nonempty_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            source = temp_path / "source"
            destination = temp_path / "destination"
            source.mkdir()
            destination.mkdir()
            (destination / "keep.md").write_text("do not overwrite", encoding="utf-8")
            result = run_cli(SKILL, "--vault", str(destination), "migrate", "--source", str(source), "--apply")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((destination / "keep.md").read_text(encoding="utf-8"), "do not overwrite")

            destination_file = temp_path / "destination-file"
            destination_file.write_text("not a vault", encoding="utf-8")
            file_result = run_cli(SKILL, "--vault", str(destination_file), "migrate", "--source", str(source), "--apply")
            self.assertNotEqual(file_result.returncode, 0)
            self.assertEqual(destination_file.read_text(encoding="utf-8"), "not a vault")

    def test_migration_cleans_staging_after_a_copy_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            source = temp_path / "source"
            destination = temp_path / "destination"
            source.mkdir()
            (source / "papers").mkdir()
            module = load_cli_module()
            args = SimpleNamespace(source=str(source), vault=str(destination), apply=True, json=False)

            with patch.object(module, "copy_migration_item", side_effect=OSError("forced copy failure")):
                with self.assertRaisesRegex(OSError, "forced copy failure"):
                    module.command_migrate(args)

            self.assertFalse(destination.exists())
            self.assertEqual(list(temp_path.glob(".destination.migration-*")), [])

    def test_default_worker_globs_match_job_export_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp) / "vault"
            self.assertEqual(run_cli(SKILL, "--vault", str(vault), "init").returncode, 0)
            (vault / "raw" / "papers" / "demo.pdf").write_bytes(b"plain text extraction fallback")
            self.assertEqual(run_cli(SKILL, "--vault", str(vault), "process").returncode, 0)
            self.assertEqual(run_cli(SKILL, "--vault", str(vault), "build-jobs", "export-paper", "--batch-size", "1").returncode, 0)

            paper_task = next((vault / ".research-kb" / "agent-tasks" / "paper").glob("*.agent-task.json"))
            paper_pattern = re.search(r'input_glob: "([^"]+)"', (SKILL / "agents" / "paper-process.yaml").read_text(encoding="utf-8"))
            assert paper_pattern
            self.assertTrue(PurePosixPath(paper_task.relative_to(vault).as_posix()).match(paper_pattern.group(1)))

            self.assertEqual(run_cli(SKILL, "--vault", str(vault), "new-node", "variable", "Demo").returncode, 0)
            paper_path = next((vault / "papers").glob("*.md"))
            paper_text = paper_path.read_text(encoding="utf-8")
            paper_text = paper_text.replace('"quality":{"state":"pending"}', '"quality":{"state":"passed"}')
            paper_text = paper_text.replace("- studies_variable::\n", "- studies_variable:: [[variables/demo]]\n", 1)
            paper_path.write_text(paper_text, encoding="utf-8")
            self.assertEqual(run_cli(SKILL, "--vault", str(vault), "build-jobs", "export-curator", "--batch-size", "1").returncode, 0)

            curator_task = next((vault / ".research-kb" / "curator-tasks" / "jobs").glob("*.curator-task.json"))
            curator_pattern = re.search(r'input_glob: "([^"]+)"', (SKILL / "agents" / "node-curator.yaml").read_text(encoding="utf-8"))
            assert curator_pattern
            self.assertTrue(PurePosixPath(curator_task.relative_to(vault).as_posix()).match(curator_pattern.group(1)))


if __name__ == "__main__":
    unittest.main()
