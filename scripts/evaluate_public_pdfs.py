#!/usr/bin/env python3
"""Run a test-only full-cycle evaluation with public ACL PDFs.

This script downloads public PDFs into a temporary vault. It does not add papers
to the user's curated KB.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KB = ROOT / "scripts" / "kb.py"
PUBLIC_PDFS = [
    "https://aclanthology.org/N19-3013.pdf",
    "https://aclanthology.org/N15-3015.pdf",
    "https://aclanthology.org/J16-3007.pdf",
    "https://aclanthology.org/W15-4302.pdf",
    "https://aclanthology.org/Y18-1095.pdf",
]

EXPECTED_PAPERS = {
    "rhoticity": "papers/gupta-2019-deep-learning-and-sociophonetics-automatic-coding.md",
    "dialect": "papers/jrgensen-2015-challenges-of-studying-and-processing-dialects.md",
    "tone": "papers/zhang-2018-a-comparison-of-tone-normalization-methods.md",
}

QUERIES = {
    "rhoticity": ("rhoticity neural networks sociophonetics", "idea"),
    "dialect": ("dialect features in social media and AAVE", "question"),
    "tone": ("tone normalization methods for language variation", "question"),
}


def run(cmd: list[str], cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, check=False)


def run_timed(cmd: list[str], cwd: Path = ROOT) -> tuple[subprocess.CompletedProcess[str], float]:
    started = time.perf_counter()
    result = run(cmd, cwd)
    return result, time.perf_counter() - started


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def download_pdfs(vault: Path) -> None:
    raw = vault / "raw" / "papers"
    raw.mkdir(parents=True, exist_ok=True)
    for url in PUBLIC_PDFS:
        target = raw / Path(url).name
        with urllib.request.urlopen(url, timeout=60) as response:
            target.write_bytes(response.read())
        require(target.stat().st_size > 50_000, f"Downloaded file is unexpectedly small: {url}")


def first_paper_from_query(output: str) -> str:
    match = re.search(r"^- \[\[(papers/[^\]]+)\]\]", output, re.M)
    return f"{match.group(1)}.md" if match else ""


def count_files(vault: Path, folder: str) -> int:
    return len(list((vault / folder).glob("*.md")))


def paper_quality_checks(vault: Path) -> list[str]:
    failures: list[str] = []
    for note in sorted((vault / "papers").glob("*.md")):
        text = note.read_text(encoding="utf-8")
        if "Needs researcher/agent review" in text:
            failures.append(f"{note.name}: summary placeholder remains")
        if "## Graph Edges" not in text or "#candidate" not in text:
            failures.append(f"{note.name}: candidate graph edges missing")
        if "## Key Findings" not in text or "- finding::" not in text:
            failures.append(f"{note.name}: findings missing")
        if "  - evidence:: p." not in text:
            failures.append(f"{note.name}: page-aware evidence anchors missing")
        if "## Links" not in text or "[[" not in text.split("## Links", 1)[1]:
            failures.append(f"{note.name}: links section not populated")
        if "@@PAGE:" in text or "[[PAGE:" in text:
            failures.append(f"{note.name}: internal page marker leaked into note")
        for artifact in ("hu- man", "fo- cus", "signif- icantly", "postvo- calic"):
            if artifact in text:
                failures.append(f"{note.name}: PDF text artifact remains: {artifact}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate full KB cycle with public ACL PDFs in a temp vault.")
    parser.add_argument("--python", default=sys.executable, help="Python executable to run the KB CLI. Use an environment with pypdf for quality tests.")
    parser.add_argument("--keep", action="store_true", help="Keep the temporary vault after the run.")
    args = parser.parse_args()

    vault = Path(tempfile.mkdtemp(prefix="research-kb-public-eval."))
    summary: dict[str, object] = {"vault": str(vault), "python": args.python, "public_pdfs": PUBLIC_PDFS}
    total_started = time.perf_counter()
    try:
        download_started = time.perf_counter()
        download_pdfs(vault)
        summary["download_duration_sec"] = round(time.perf_counter() - download_started, 3)
        steps = {}
        for step in (["init"], ["process"], ["enrich", "--create-nodes"]):
            result, duration = run_timed([args.python, str(KB), "--vault", str(vault), *step])
            steps[" ".join(step)] = {
                "returncode": result.returncode,
                "duration_sec": round(duration, 3),
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
            require(result.returncode == 0, f"`{' '.join(step)}` failed: {result.stderr or result.stdout}")

        lint, lint_duration = run_timed([args.python, str(KB), "--vault", str(vault), "lint"])
        steps["lint"] = {
            "returncode": lint.returncode,
            "duration_sec": round(lint_duration, 3),
            "stdout": lint.stdout.strip(),
            "stderr": lint.stderr.strip(),
        }
        require(lint.returncode == 0 and "No lint issues found." in lint.stdout, f"lint failed: {lint.stdout}\n{lint.stderr}")

        query_results = {}
        for name, (query, mode) in QUERIES.items():
            result, duration = run_timed([args.python, str(KB), "--vault", str(vault), "query", query, "--mode", mode, "--limit", "5"])
            require(result.returncode == 0, f"query failed for {name}: {result.stderr}")
            first = first_paper_from_query(result.stdout)
            query_results[name] = {"query": query, "first_paper": first, "duration_sec": round(duration, 3)}
            require(first == EXPECTED_PAPERS[name], f"{name} query expected {EXPECTED_PAPERS[name]}, got {first}")

        review, review_duration = run_timed([args.python, str(KB), "--vault", str(vault), "review", "--limit", "10"])
        require(review.returncode == 0, f"review failed: {review.stderr}")
        review_count = len(re.findall(r"^- \[\[papers/", review.stdout, re.M))
        require(review_count == 5, f"expected 5 papers in review queue, got {review_count}")

        quality_failures = paper_quality_checks(vault)
        require(not quality_failures, "paper quality failures: " + "; ".join(quality_failures))

        counts = {folder: count_files(vault, folder) for folder in ["papers", "concepts", "variables", "methods", "communities", "questions", "syntheses"]}
        require(counts["papers"] == 5, f"expected 5 papers, got {counts['papers']}")
        require(counts["concepts"] >= 5, f"expected at least 5 concepts, got {counts['concepts']}")
        require(counts["variables"] >= 3, f"expected at least 3 variables, got {counts['variables']}")
        require(counts["methods"] >= 5, f"expected at least 5 methods, got {counts['methods']}")
        require(counts["communities"] >= 3, f"expected at least 3 communities, got {counts['communities']}")

        summary.update(
            {
                "status": "passed",
                "counts": counts,
                "queries": query_results,
                "review_queue_count": review_count,
                "review_duration_sec": round(review_duration, 3),
                "steps": steps,
                "total_duration_sec": round(time.perf_counter() - total_started, 3),
            }
        )
        print(json.dumps(summary, indent=2))
        return 0
    except Exception as exc:
        summary["status"] = "failed"
        summary["error"] = str(exc)
        print(json.dumps(summary, indent=2), file=sys.stderr)
        return 1
    finally:
        if not args.keep:
            shutil.rmtree(vault, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
