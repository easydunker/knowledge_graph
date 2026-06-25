#!/usr/bin/env python3
"""Compatibility wrapper for the bundled research KB skill CLI."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skills" / "research-kb" / "scripts" / "research_kb.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("research_kb_tool", TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {TOOL}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    tool = load_tool()
    args = sys.argv[1:]
    has_explicit_vault = any(arg == "--vault" or arg.startswith("--vault=") for arg in args)
    if has_explicit_vault:
        raise SystemExit(tool.main(args))
    raise SystemExit(tool.main(["--vault", str(ROOT), *args]))
