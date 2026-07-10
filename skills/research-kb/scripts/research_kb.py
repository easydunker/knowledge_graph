#!/usr/bin/env python3
"""
Local-first Obsidian research KB helper.

The script is intentionally dependency-light. It uses only the Python standard
library by default and opportunistically uses pypdf when it is installed.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable


RELATIONS = {
    "studies_variable",
    "has_variant",
    "measured_by",
    "uses_method",
    "uses_dataset",
    "samples_community",
    "tests_social_factor",
    "finding",
    "supports",
    "complicates",
    "contradicts",
    "extends",
    "relevant_to",
    "evidence",
    "authored_by",
    "coauthored_with",
    "works_on",
    "uncertainty",
}

QUERY_RELATIONS = RELATIONS - {"uncertainty"}

NODE_FOLDERS = {
    "paper": "papers",
    "author": "authors",
    "concept": "concepts",
    "variable": "variables",
    "method": "methods",
    "community": "communities",
    "research_question": "questions",
    "synthesis": "syntheses",
}

MACHINE_DIR = ".research-kb"
MACHINE_CONFIG = f"{MACHINE_DIR}/config.yaml"
MACHINE_INDEX = f"{MACHINE_DIR}/index.json"
MACHINE_SEARCH_DIR = f"{MACHINE_DIR}/search"
QUALITY_REPORT_DIR = f"{MACHINE_DIR}/quality-reports"
CURATOR_TASK_DIR = f"{MACHINE_DIR}/curator-tasks"
CURATOR_RESULT_DIR = f"{MACHINE_DIR}/curator-results"
JOBS_DIR = f"{MACHINE_DIR}/jobs"
PAPER_JOBS_FILE = f"{JOBS_DIR}/paper-process.jsonl"
CURATOR_JOBS_FILE = f"{JOBS_DIR}/node-curation.jsonl"
BUILD_RUNS_FILE = f"{JOBS_DIR}/build-runs.jsonl"
JOBS_STATUS_FILE = f"{JOBS_DIR}/status.json"
METADATA_CACHE_DIR = f"{MACHINE_DIR}/metadata-cache"
METADATA_RECONCILIATION_DIR = f"{MACHINE_DIR}/reconciliation"
ARCHIVE_MERGED_DIR = "archive/merged"
ARCHIVE_INVALID_DIR = "archive/invalid"
DEFAULT_AGENT_MAX_CHARS = 0
DEFAULT_PDF_TEXT_MAX_CHARS = 500000
PAPER_PROCESS_PROMPT_VERSION = "paper-process-v1"
NODE_CURATOR_PROMPT_VERSION = "node-curator-v1"
PAPER_PROCESS_AGENT_NAME = "research-kb.paper-process"
PAPER_PROCESS_AGENT_PROFILE = "agents/paper-process.yaml"
PAPER_PROCESS_AGENT_REFERENCE = "references/paper-process-agent.md"
NODE_CURATOR_AGENT_NAME = "research-kb.node-curator"
NODE_CURATOR_AGENT_PROFILE = "agents/node-curator.yaml"
NODE_CURATOR_AGENT_REFERENCE = "references/node-curator-agent.md"
ENRICHMENT_HEADINGS = [
    "Authors",
    "One-Paragraph Summary",
    "Research Question",
    "Data and Participants",
    "Linguistic Variables",
    "Social Factors",
    "Methods and Measures",
    "Graph Edges",
    "Key Findings",
    "Theoretical Contribution",
    "Limitations",
    "Useful Quotes",
    "Extraction Notes",
    "Links",
]

REQUIRED_DIRS = [
    MACHINE_DIR,
    MACHINE_SEARCH_DIR,
    QUALITY_REPORT_DIR,
    CURATOR_TASK_DIR,
    CURATOR_RESULT_DIR,
    METADATA_CACHE_DIR,
    METADATA_RECONCILIATION_DIR,
    "raw/papers",
    "raw/processed",
    "raw/failed",
    "papers",
    "authors",
    "concepts",
    "variables",
    "methods",
    "communities",
    "questions",
    "syntheses",
    "archive/merged",
    "archive/invalid",
    "templates",
    "plugins/zotero",
]

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "given",
    "how",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "method",
    "methods",
    "paper",
    "papers",
    "research",
    "study",
    "studies",
    "what",
    "when",
    "which",
    "with",
}

GENERIC_PDF_TITLES = {
    "r graphics output",
    "untitled",
    "unknown",
    "microsoft word",
}

TERM_RULES = [
    {
        "pattern": r"\brhoticity\b|post-?vocalic\s*/?r\b|vocalic\s*/?r\b",
        "folder": "variables",
        "slug": "rhoticity",
        "title": "Rhoticity",
        "relation": "studies_variable",
        "aliases": ["postvocalic r", "vocalic r"],
    },
    {
        "pattern": r"\bdialect feature[s]?\b|phonological feature[s]?",
        "folder": "variables",
        "slug": "dialect-features",
        "title": "Dialect features",
        "relation": "studies_variable",
        "aliases": [],
    },
    {
        "pattern": r"\btone normalization\b|\btonal acoustic\b|\btone\b",
        "folder": "variables",
        "slug": "tone-realization",
        "title": "Tone realization",
        "relation": "studies_variable",
        "aliases": ["tonal acoustic features"],
    },
    {
        "pattern": r"\bformant[s]?\b|\bF[123]\b|vowel quality",
        "folder": "methods",
        "slug": "formant-measurement",
        "title": "Formant measurement",
        "relation": "measured_by",
        "aliases": ["F1", "F2", "F3"],
    },
    {
        "pattern": r"\bneural network[s]?\b|\bdeep learning\b|\bGRU\b|\bLSTM\b|recurrent neural",
        "folder": "methods",
        "slug": "neural-networks",
        "title": "Neural networks",
        "relation": "uses_method",
        "aliases": ["deep learning", "recurrent neural networks"],
    },
    {
        "pattern": r"\bautomatic speech recognition\b|\bASR\b",
        "folder": "methods",
        "slug": "automatic-speech-recognition",
        "title": "Automatic speech recognition",
        "relation": "uses_method",
        "aliases": ["ASR"],
    },
    {
        "pattern": r"\bforced alignment\b|forced align",
        "folder": "methods",
        "slug": "forced-alignment",
        "title": "Forced alignment",
        "relation": "uses_method",
        "aliases": [],
    },
    {
        "pattern": r"\bPOS tagg(?:er|ing)\b|part-of-speech",
        "folder": "methods",
        "slug": "pos-tagging",
        "title": "POS tagging",
        "relation": "uses_method",
        "aliases": ["part-of-speech tagging"],
    },
    {
        "pattern": r"\btone normalization\b|\bnormalization method[s]?\b|\bLobanov\b|\bNearey\b|\bz-?score\b",
        "folder": "methods",
        "slug": "tone-normalization",
        "title": "Tone normalization",
        "relation": "uses_method",
        "aliases": ["Lobanov normalization", "Nearey normalization", "z-score normalization"],
    },
    {
        "pattern": r"\bweb application\b|online end-to-end web application",
        "folder": "methods",
        "slug": "web-application-for-analysis",
        "title": "Web application for analysis",
        "relation": "uses_method",
        "aliases": [],
    },
    {
        "pattern": r"\bsociophonetic[s]?\b",
        "folder": "concepts",
        "slug": "sociophonetics",
        "title": "Sociophonetics",
        "relation": "supports",
        "aliases": [],
    },
    {
        "pattern": r"\bcomputational sociolinguistic[s]?\b",
        "folder": "concepts",
        "slug": "computational-sociolinguistics",
        "title": "Computational sociolinguistics",
        "relation": "supports",
        "aliases": [],
    },
    {
        "pattern": r"\blanguage variation\b|\bsociolinguistic variation\b|variation research",
        "folder": "concepts",
        "slug": "language-variation",
        "title": "Language variation",
        "relation": "supports",
        "aliases": ["sociolinguistic variation"],
    },
    {
        "pattern": r"\b(?:place|social|online|speaker|community|ethnic|gender|regional)\s+identity\b|\bidentity\s+(?:construction|work|formation|performance)\b|\bconstruct(?:ion|ing)? of (?:place|social) identity\b",
        "folder": "concepts",
        "slug": "identity",
        "title": "Identity",
        "relation": "tests_social_factor",
        "aliases": ["place identity"],
    },
    {
        "pattern": r"\bgender\b",
        "folder": "concepts",
        "slug": "gender",
        "title": "Gender",
        "relation": "tests_social_factor",
        "aliases": [],
    },
    {
        "pattern": r"\bethnicity\b|ethnic",
        "folder": "concepts",
        "slug": "ethnicity",
        "title": "Ethnicity",
        "relation": "tests_social_factor",
        "aliases": [],
    },
    {
        "pattern": r"\bAfrican American Vernacular English\b|\bAAVE\b",
        "folder": "communities",
        "slug": "african-american-vernacular-english",
        "title": "African American Vernacular English",
        "relation": "samples_community",
        "aliases": ["AAVE"],
    },
    {
        "pattern": r"\bTwitter\b|tweets\b|social media",
        "folder": "communities",
        "slug": "social-media-users",
        "title": "Social media users",
        "relation": "samples_community",
        "aliases": ["Twitter users", "tweet authors"],
    },
    {
        "pattern": r"\bMandarin\b|Chinese tone|Chinese Language",
        "folder": "communities",
        "slug": "mandarin-chinese-speakers",
        "title": "Mandarin Chinese speakers",
        "relation": "samples_community",
        "aliases": ["Chinese speakers"],
    },
]


TEMPLATES = {
    "paper.md": """---
type: paper
paper_id: "{{paper_id}}"
intake_source: raw_pdf
raw_pdf_path: "{{raw_pdf_path}}"
pdf_sha256: "{{pdf_sha256}}"
title: "{{title}}"
authors: {{authors}}
year: {{year}}
doi: "{{doi}}"
publication: "{{publication}}"
kb_status: needs_review
review_state: agent_draft
aliases: []
created: "{{date}}"
updated: "{{date}}"
---

# {{title}}

## Source

- PDF: {{raw_pdf_path}}
- DOI: {{doi}}

## Authors

{{author_links}}

## One-Paragraph Summary

Needs researcher/agent review.

## Research Question

## Data and Participants

## Linguistic Variables

- studies_variable::

## Social Factors

- tests_social_factor::

## Methods and Measures

- uses_method::
- measured_by::

## Graph Edges

- studies_variable::
- tests_social_factor::
- samples_community::
- uses_method::
- measured_by::
- uses_dataset::

## Key Findings

- finding::
  - evidence::
  - supports::
  - complicates::
  - contradicts::

## Theoretical Contribution

## Limitations

## Useful Quotes

## Extraction Notes

- metadata_confidence:
- text_extraction_status:
- uncertain_fields:

## Links

- Concepts:
- Variables:
- Methods:
- Authors:
- Communities:
- Related papers:
""",
    "author.md": """---
type: author
aliases: []
status: candidate
orcid:
created: "{{date}}"
updated: "{{date}}"
---

# {{title}}

## Papers

## Topics

## Coauthors

## Notes

- uncertainty:: Local KB author node; verify identity before merging names, affiliations, or ORCID data.
""",
    "concept.md": """---
type: concept
aliases: []
status: working
created: "{{date}}"
updated: "{{date}}"
---

# {{title}}

## Working Definition

## Why It Matters

## Key Papers

## Competing Views

## Related Variables

## Related Methods

## Open Questions
""",
    "variable.md": """---
type: variable
aliases: []
level:
language_variety:
status: working
created: "{{date}}"
updated: "{{date}}"
---

# {{title}}

## Description

## Variants or Realizations

## Measures

## Social Factors

## Key Papers

## Open Questions
""",
    "method.md": """---
type: method
aliases: []
status: working
created: "{{date}}"
updated: "{{date}}"
---

# {{title}}

## Description

## When It Is Used

## Measures or Outputs

## Key Papers

## Related Variables

## Caveats
""",
    "community.md": """---
type: community
aliases: []
language_variety:
location:
status: working
created: "{{date}}"
updated: "{{date}}"
---

# {{title}}

## Description

## Language Variety

## Social Context

## Key Papers

## Related Variables

## Open Questions
""",
    "research-question.md": """---
type: research_question
status: active
created_from:
related_concepts: []
related_variables: []
created: "{{date}}"
updated: "{{date}}"
---

# {{title}}

## Prompt

## Why This Seems Interesting

## Relevant Papers in KB

## Evidence Paths

## Possible Directions

## Gaps in the KB

## Next Reading From Existing KB
""",
    "synthesis.md": """---
type: synthesis
topic:
status: working
created: "{{date}}"
updated: "{{date}}"
---

# {{title}}

## Scope

## Short Synthesis

## Main Claims

## Supporting Papers

## Tensions or Contradictions

## Methods and Data Patterns

## Gaps

## Useful Citations
""",
}

AGENTS_TEXT = """# Agent Rules

## Authority

- Raw PDFs enter through `raw/papers/`.
- Do not add external papers unless the user supplies the PDF.
- Zotero is optional plugin data, not v1 core authority.
- Do not modify Zotero.
- Do not treat external search results as trusted KB evidence.

## Paper Notes

- Keep paper notes source-grounded.
- Always preserve `raw_pdf_path` and `pdf_sha256`.
- Preserve build-only `kb_build` provenance for maintenance, but do not treat it as query evidence.
- Mark uncertain metadata and summaries clearly.
- Preserve researcher-reviewed content.
- Prefer evidence with page, section, table, or quote information when available.

## Paper-Process Quality

- The paper-process agent must read the entire supplied `extracted_text`.
- The task's `text_truncated_for_task` flag is authoritative.
- If `text_truncated_for_task` is false, do not claim pipeline truncation.
- Quality-failed paper notes remain searchable, but must be checked against full extracted/source text before being used as evidence.
- Skip quality-failed papers for curator enrichment, automatic synthesis creation, and auto-merge evidence.

## Graph Links

- Notes are graph nodes.
- Typed wikilinks are graph edges.
- Link authors, concepts, variables, methods, and communities only when substantively relevant.
- Use author nodes for author-based queries; mark uncertain identity merges as candidate.
- Do not create duplicate pages; search first.
- If a new page is useful but uncertain, create it with `status: candidate`.

## Relation Labels

Use these relation labels when possible:

```text
studies_variable::
has_variant::
measured_by::
uses_method::
uses_dataset::
samples_community::
tests_social_factor::
authored_by::
coauthored_with::
works_on::
finding::
supports::
complicates::
contradicts::
extends::
relevant_to::
evidence::
```

## Synthesis

- Synthesis notes may compare, generalize, and identify gaps.
- Distinguish supported claims from hypotheses.
- Include paper links and source evidence for claims.
- Surface contradictions and methodological differences rather than smoothing them away.
- Curator-created synthesis notes should be `status: active` only when evidence is strong.

## Curator

- Curator agents may update full author, concept, variable, method, and community note bodies.
- Curator agents should read all supplied quality-passed paper evidence for a node.
- Curator agents may propose high-confidence duplicate merges.
- Merged notes move to `archive/merged/`; do not delete merged content.
- Archive notes are maintenance history, not live query evidence.

## Updates

- Append important actions to `log.md`.
- Keep `index.md` useful and brief.
- Prefer small, reviewable edits.
"""

INDEX_TEXT = """# Research KB Index

## Current KB Content

- No paper notes have been created yet.
- No source PDFs are present in `raw/papers/`.
- The KB-only graph will be empty until paper notes, concept notes, or synthesis notes exist in the KB folders.

## Start Here

- [[log]]
- [[templates/paper]]
- [[templates/author]]
- [[templates/concept]]
- [[templates/variable]]
- [[templates/method]]
- [[templates/community]]
- [[templates/research-question]]
- [[templates/synthesis]]

## Current Focus

- Add current research themes here.
- Add active questions under `questions/`.
- Add cross-paper notes under `syntheses/`.
"""

LOG_TEXT = """# KB Log

Record important ingest, review, synthesis, and cleanup actions here.
"""

MACHINE_CONFIG_TEXT = """# Research KB tool config

schema_version: 1
human_index: index.md
machine_state_dir: .research-kb
machine_index: .research-kb/index.json
search_index_dir: .research-kb/search
quality_report_dir: .research-kb/quality-reports
curator_task_dir: .research-kb/curator-tasks
curator_result_dir: .research-kb/curator-results
jobs_dir: .research-kb/jobs
metadata_cache_dir: .research-kb/metadata-cache
metadata_reconciliation_dir: .research-kb/reconciliation
archive_merged_dir: archive/merged
archive_invalid_dir: archive/invalid
raw_pdf_dir: raw/papers
source_of_truth: markdown_notes
metadata_reconciliation:
  enabled: true
  crossref:
    enabled: true
    mailto: ""
  openalex:
    enabled: true
    mailto: ""
    api_key_env: OPENALEX_API_KEY
  semantic_scholar:
    enabled: true
    api_key_env: SEMANTIC_SCHOLAR_API_KEY
node_folders:
  paper: papers
  author: authors
  concept: concepts
  variable: variables
  method: methods
  community: communities
  research_question: questions
  synthesis: syntheses
"""

README_TEXT = """# Sociolinguistics and Sociophonetics KB Vault

This folder is the user-selected Obsidian vault that stores KB content. The
Codex skill and helper scripts are reusable tooling and may live elsewhere,
such as `~/.codex/skills/research-kb/`.

Open this folder as an Obsidian vault. Drop researcher-selected PDFs into
`raw/papers/`, then use the KB helper with `--vault /path/to/this-vault` to
process, query, lint, and repair the Markdown knowledge base.

```bash
python3 scripts/kb.py init
python3 scripts/kb.py index
python3 scripts/kb.py process
python3 scripts/kb.py query "rhotics, gender, and identity"
python3 scripts/kb.py lint
```

`index.md` is the human-facing Obsidian entry point. `.research-kb/index.json`
is generated vault-local tool state and can be rebuilt with the helper's
`index` command.
"""


@dataclass
class ExtractionResult:
    metadata: dict[str, str]
    text: str
    status: str
    backend: str
    backend_version: str
    extracted_format: str
    extracted_text_sha256: str
    extracted_text_chars: int


@dataclass
class PdfInfo:
    path: Path
    sha256: str
    title: str
    authors: list[str]
    year: str
    doi: str
    publication: str
    text_preview: str
    extraction_status: str
    uncertain_fields: list[str]
    extraction_backend: str = ""
    extraction_backend_version: str = ""
    extracted_format: str = "text"
    extracted_text_sha256: str = ""
    extracted_text_chars: int = 0


@dataclass
class AgentAnalysisResult:
    analysis: dict[str, Any]
    source: str
    model: str = ""


@dataclass
class Edge:
    relation: str
    target: str
    line_no: int
    heading: str


@dataclass
class Note:
    path: Path
    rel_path: str
    frontmatter: dict[str, object]
    body: str
    text: str
    title: str
    note_type: str
    aliases: list[str]
    links: list[str] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)


@dataclass
class Issue:
    severity: str
    code: str
    path: str
    message: str
    fix: str = ""


def today() -> str:
    return date.today().isoformat()


def rel_to(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def append_log(root: Path, message: str) -> None:
    log_path = root / "log.md"
    if not log_path.exists():
        log_path.write_text(LOG_TEXT, encoding="utf-8")
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"\n- {today()}: {message}\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def slugify(value: str, fallback: str = "untitled") -> str:
    value = value.translate(str.maketrans({"ø": "o", "Ø": "O", "đ": "d", "Đ": "D", "ł": "l", "Ł": "L", "ı": "i"}))
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = re.sub(r"['`]", "", value)
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or fallback


def titleize_slug(slug: str) -> str:
    return re.sub(r"[-_]+", " ", slug).strip().title() or "Untitled"


def yaml_string(value: str) -> str:
    escaped = (value or "").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def yaml_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def yaml_list(values: Iterable[str]) -> str:
    items = [yaml_string(str(value)) for value in values if str(value).strip()]
    return "[" + ", ".join(items) + "]" if items else "[]"


def parse_list_value(value: str) -> list[str]:
    value = value.strip()
    if not value or value == "[]":
        return []
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        try:
            return [item.strip() for item in next(csv.reader([inner], skipinitialspace=True))]
        except Exception:
            return [part.strip().strip('"').strip("'") for part in inner.split(",") if part.strip()]
    return [value.strip().strip('"').strip("'")]


def parse_scalar(value: str) -> object:
    value = value.strip()
    if value.startswith("{") and value.endswith("}"):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    if value.startswith("["):
        return parse_list_value(value)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    return value


def update_frontmatter_fields(text: str, updates: dict[str, str]) -> str:
    if not updates:
        return text
    if not text.startswith("---"):
        frontmatter = "---\n" + "\n".join(f"{key}: {value}" for key, value in updates.items()) + "\n---\n\n"
        return frontmatter + text
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.S)
    if not match:
        return text
    lines: list[str] = []
    seen: set[str] = set()
    for line in match.group(1).splitlines():
        key = line.split(":", 1)[0].strip() if ":" in line else ""
        if key in updates:
            lines.append(f"{key}: {updates[key]}")
            seen.add(key)
        else:
            lines.append(line)
    for key, value in updates.items():
        if key not in seen:
            lines.append(f"{key}: {value}")
    body = text[match.end() :]
    return "---\n" + "\n".join(lines) + "\n---\n" + body


def split_note_text(text: str) -> tuple[str, str]:
    if not text.startswith("---"):
        return "", text
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.S)
    if not match:
        return "", text
    return text[: match.end()], text[match.end() :]


def kb_build_data(note_or_text: Note | str) -> dict[str, Any]:
    if isinstance(note_or_text, Note):
        value = note_or_text.frontmatter.get("kb_build")
    else:
        frontmatter, _body = split_frontmatter(note_or_text)
        value = frontmatter.get("kb_build")
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip().startswith("{"):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {}


def set_kb_build_data(text: str, data: dict[str, Any]) -> str:
    return update_frontmatter_fields(text, {"kb_build": yaml_json(data)})


def deep_merge_dict(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge_dict(merged[key], value)  # type: ignore[arg-type]
        else:
            merged[key] = value
    return merged


def analysis_object_schema(properties: dict[str, object], required: list[str]) -> dict[str, object]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def analysis_string_array_schema() -> dict[str, object]:
    return {"type": "array", "items": {"type": "string"}}


def paper_analysis_schema() -> dict[str, object]:
    edge_ref = analysis_object_schema(
        {
            "relation": {"type": "string"},
            "node_type": {"type": "string"},
            "label": {"type": "string"},
            "slug": {"type": "string"},
            "evidence": {"type": "string"},
            "uncertainty": {"type": "string"},
        },
        ["relation", "node_type", "label", "slug", "evidence", "uncertainty"],
    )
    finding = analysis_object_schema(
        {
            "finding": {"type": "string"},
            "evidence": {"type": "string"},
            "supports": {"type": "array", "items": edge_ref},
            "complicates": {"type": "array", "items": edge_ref},
            "contradicts": {"type": "array", "items": edge_ref},
        },
        ["finding", "evidence", "supports", "complicates", "contradicts"],
    )
    section_coverage = analysis_object_schema(
        {
            "methods": {"type": "string"},
            "data": {"type": "string"},
            "results": {"type": "string"},
            "discussion": {"type": "string"},
            "conclusion": {"type": "string"},
        },
        ["methods", "data", "results", "discussion", "conclusion"],
    )
    quality_self_check = analysis_object_schema(
        {
            "read_full_extracted_text": {"type": "boolean"},
            "evidence_anchors_present": {"type": "boolean"},
            "truncation_claim_matches_task": {"type": "boolean"},
        },
        ["read_full_extracted_text", "evidence_anchors_present", "truncation_claim_matches_task"],
    )
    return analysis_object_schema(
        {
            "title": {"type": "string"},
            "authors": analysis_string_array_schema(),
            "year": {"type": "string"},
            "doi": {"type": "string"},
            "publication": {"type": "string"},
            "one_paragraph_summary": {"type": "string"},
            "research_question": analysis_string_array_schema(),
            "data_and_participants": analysis_string_array_schema(),
            "linguistic_variables": {"type": "array", "items": edge_ref},
            "social_factors": {"type": "array", "items": edge_ref},
            "methods_and_measures": {"type": "array", "items": edge_ref},
            "graph_edges": {"type": "array", "items": edge_ref},
            "key_findings": {"type": "array", "items": finding},
            "theoretical_contribution": analysis_string_array_schema(),
            "limitations": analysis_string_array_schema(),
            "useful_quotes": analysis_string_array_schema(),
            "uncertain_fields": analysis_string_array_schema(),
            "text_truncated_for_task_acknowledged": {"type": "boolean"},
            "section_coverage": section_coverage,
            "quality_self_check": quality_self_check,
        },
        [
            "title",
            "authors",
            "year",
            "doi",
            "publication",
            "one_paragraph_summary",
            "research_question",
            "data_and_participants",
            "linguistic_variables",
            "social_factors",
            "methods_and_measures",
            "graph_edges",
            "key_findings",
            "theoretical_contribution",
            "limitations",
            "useful_quotes",
            "uncertain_fields",
            "text_truncated_for_task_acknowledged",
            "section_coverage",
            "quality_self_check",
        ],
    )


def parse_json_text(value: str) -> dict[str, Any]:
    text = value.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fence:
        text = fence.group(1).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Agent analysis was not a JSON object.")
    return data


def known_node_context(root: Path, limit: int = 200) -> str:
    lines: list[str] = []
    for note in load_notes(root):
        if note.note_type == "paper":
            continue
        aliases = f"; aliases: {', '.join(note.aliases)}" if note.aliases else ""
        lines.append(f"- {note.rel_path[:-3]} ({note.note_type}): {note.title}{aliases}")
        if len(lines) >= limit:
            break
    return "\n".join(lines) if lines else "- none yet"


def paper_agent_instructions() -> str:
    return (
        "Act as the research-kb paper process agent. Your primary job is to understand "
        "and summarize one research paper for an Obsidian Markdown knowledge base. "
        "Use only the supplied extracted PDF text and existing note metadata. "
        "Read the entire `extracted_text` field before writing conclusions. "
        "Treat `text_truncated_for_task` as authoritative; if it is false, do not claim "
        "pipeline truncation. Do not use outside knowledge. Preserve uncertainty. If evidence is weak, "
        "say so in `uncertain_fields` or edge `uncertainty`. Use page markers like "
        "@@PAGE:3@@ to produce evidence anchors such as `p. 3` when possible. "
        f"Use these relation labels when possible: {', '.join(sorted(RELATIONS - {'uncertainty'}))}. "
        "For graph nodes, prefer node_type values: author, concept, variable, method, community. "
        "For graph edge slugs, use lowercase hyphen-case and avoid duplicate labels from the known nodes list. "
        "Report section coverage and set `quality_self_check.read_full_extracted_text` truthfully. "
        "Return exactly one JSON object matching `expected_json_schema`."
    )


def task_text_window(text: str, max_chars: int = DEFAULT_AGENT_MAX_CHARS) -> tuple[str, bool]:
    if max_chars <= 0:
        return text, False
    excerpt = text[:max_chars]
    return excerpt, len(text) > len(excerpt)


def build_agent_prompt(root: Path, info: PdfInfo | None, note: Note | None, text: str, extraction_status: str, max_chars: int = DEFAULT_AGENT_MAX_CHARS) -> str:
    title = note.title if note else (info.title if info else "")
    authors = note.frontmatter.get("authors", []) if note else (info.authors if info else [])
    year = str(note.frontmatter.get("year", "")) if note else (info.year if info else "")
    doi = str(note.frontmatter.get("doi", "")) if note else (info.doi if info else "")
    publication = str(note.frontmatter.get("publication", "")) if note else (info.publication if info else "")
    extracted_text, text_truncated_for_task = task_text_window(text, max_chars=max_chars)
    excerpt_chars = len(extracted_text)
    truncation_note = "yes" if text_truncated_for_task else "no"
    return f"""Act as the research-kb paper process agent.

Understand and summarize this research paper for an Obsidian Markdown knowledge base.

Use only the supplied extracted PDF text. Do not use outside knowledge.
Read the entire `extracted_text` field before writing conclusions.
The task field `text_truncated_for_task` is authoritative. If it is false, do not claim the pipeline truncated the paper; if results or methods are absent, say the section was not identifiable in the supplied text.
Preserve uncertainty. If evidence is weak, say so in `uncertain_fields` or the edge `uncertainty`.
Use page markers like @@PAGE:3@@ to produce evidence anchors such as "p. 3" when possible.
Use only these relation labels when possible: {', '.join(sorted(RELATIONS - {'uncertainty'}))}.
For graph nodes, prefer node_type values: author, concept, variable, method, community.
For graph edge slugs, use lowercase hyphen-case and avoid duplicate labels from the known nodes list.

Known existing nodes:
{known_node_context(root)}

Existing metadata:
- title: {title}
- authors: {authors}
- year: {year}
- doi: {doi}
- publication: {publication}
- text_extraction_status: {extraction_status}
- extracted_text_chars: {excerpt_chars}
- text_truncated_for_task: {truncation_note}

Extracted PDF text is provided in this task JSON's `extracted_text` field. Analyze that field as the only evidence for the paper's content.
The result must include `text_truncated_for_task_acknowledged`, `section_coverage`, and `quality_self_check`.
"""


def paper_agent_task(root: Path, note: Note, max_chars: int = DEFAULT_AGENT_MAX_CHARS) -> dict[str, Any]:
    extraction = extract_note_pdf_payload(root, note)
    text, extraction_status = extraction.text, extraction.status
    extracted_text, text_truncated_for_task = task_text_window(text, max_chars=max_chars)
    result_path = f"{MACHINE_DIR}/agent-results/{note.path.stem}.agent-result.json"
    return {
        "schema_version": 1,
        "task": "research_kb_paper_analysis",
        "agent": PAPER_PROCESS_AGENT_NAME,
        "agent_profile": PAPER_PROCESS_AGENT_PROFILE,
        "agent_reference": PAPER_PROCESS_AGENT_REFERENCE,
        "primary_goal": "understand_and_summarize_input_paper",
        "note_path": note.rel_path,
        "raw_pdf_path": str(note.frontmatter.get("raw_pdf_path", "")),
        "pdf_sha256": str(note.frontmatter.get("pdf_sha256", "")),
        "text_extraction_status": extraction_status,
        "extraction_backend": extraction.backend,
        "extraction_backend_version": extraction.backend_version,
        "extracted_format": extraction.extracted_format,
        "extracted_text_sha256": extraction.extracted_text_sha256,
        "source_text_chars": len(text),
        "extracted_text_chars": len(extracted_text),
        "text_truncated_for_task": text_truncated_for_task,
        "result_path": result_path,
        "result_envelope": {
            "note_path": note.rel_path,
            "agent_source": PAPER_PROCESS_AGENT_NAME,
            "agent_model": "<model name or harness label>",
            "analysis": "<object matching expected_json_schema>",
        },
        "instructions": paper_agent_instructions(),
        "known_nodes": known_node_context(root),
        "existing_metadata": {
            "title": note.title,
            "authors": note.frontmatter.get("authors", []),
            "year": str(note.frontmatter.get("year", "")),
            "doi": str(note.frontmatter.get("doi", "")),
            "publication": str(note.frontmatter.get("publication", "")),
        },
        "expected_json_schema": paper_analysis_schema(),
        "prompt": build_agent_prompt(root, None, note, text, extraction_status, max_chars=max_chars),
        "extracted_text": extracted_text,
    }


def split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    if not text.startswith("---"):
        return {}, text
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.S)
    if not match:
        return {}, text
    raw = match.group(1)
    frontmatter: dict[str, object] = {}
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = parse_scalar(value)
    return frontmatter, text[match.end() :]


def first_heading(body: str) -> str:
    match = re.search(r"^#\s+(.+?)\s*$", body, re.M)
    return match.group(1).strip() if match else ""


def wikilinks(text: str) -> list[str]:
    values: list[str] = []
    for match in re.finditer(r"\[\[([^\]]+)\]\]", text):
        target = match.group(1).split("|", 1)[0].split("#", 1)[0].strip()
        if target:
            values.append(target)
    return values


def parse_edges(body: str) -> list[Edge]:
    edges: list[Edge] = []
    heading = ""
    for i, line in enumerate(body.splitlines(), start=1):
        h = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if h:
            heading = h.group(2).strip()
            continue
        match = re.match(r"^\s*-\s*([a-z_]+)::\s*(.*?)\s*$", line)
        if match:
            relation = match.group(1).strip()
            target = match.group(2).strip()
            edges.append(Edge(relation=relation, target=target, line_no=i, heading=heading))
    return edges


def note_title(path: Path, frontmatter: dict[str, object], body: str) -> str:
    for key in ("title", "topic"):
        value = frontmatter.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    heading = first_heading(body)
    return heading or titleize_slug(path.stem)


def iter_note_paths(root: Path) -> Iterable[Path]:
    graph_folders = set(NODE_FOLDERS.values())
    for path in root.rglob("*.md"):
        parts = path.relative_to(root).parts
        if not parts or parts[0] not in graph_folders:
            continue
        yield path


def load_notes(root: Path) -> list[Note]:
    notes: list[Note] = []
    for path in sorted(iter_note_paths(root)):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        frontmatter, body = split_frontmatter(text)
        aliases_value = frontmatter.get("aliases", [])
        aliases = aliases_value if isinstance(aliases_value, list) else parse_list_value(str(aliases_value))
        note = Note(
            path=path,
            rel_path=rel_to(path, root),
            frontmatter=frontmatter,
            body=body,
            text=text,
            title=note_title(path, frontmatter, body),
            note_type=str(frontmatter.get("type", "")),
            aliases=[str(alias) for alias in aliases],
            links=wikilinks(text),
            edges=parse_edges(body),
        )
        notes.append(note)
    return notes


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def skill_template_dir() -> Path:
    return skill_root() / "templates"


def template_names() -> list[str]:
    names = set(TEMPLATES)
    directory = skill_template_dir()
    if directory.exists():
        names.update(path.name for path in directory.glob("*.md"))
    return sorted(names)


def load_template_text(name: str, root: Path | None = None, prefer_vault: bool = True) -> str:
    if prefer_vault and root is not None:
        vault_template = root / "templates" / name
        if vault_template.exists():
            return vault_template.read_text(encoding="utf-8")
    skill_template = skill_template_dir() / name
    if skill_template.exists():
        return skill_template.read_text(encoding="utf-8")
    if name in TEMPLATES:
        return TEMPLATES[name]
    raise KeyError(f"unknown template: {name}")


def render_template(name: str, values: dict[str, object], root: Path | None = None) -> str:
    text = load_template_text(name, root=root)
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


def write_if_missing(path: Path, content: str, force: bool = False) -> bool:
    if path.exists() and not force:
        return False
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")
    return True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def init_vault(root: Path, force: bool = False) -> list[str]:
    changed: list[str] = []
    for folder in REQUIRED_DIRS:
        target = root / folder
        if not target.exists():
            ensure_dir(target)
            changed.append(f"created {folder}/")

    for name in template_names():
        content = load_template_text(name, root=None, prefer_vault=False)
        target = root / "templates" / name
        if write_if_missing(target, content, force=force):
            changed.append(f"wrote templates/{name}")

    for rel, content in {
        "AGENTS.md": AGENTS_TEXT,
        "index.md": INDEX_TEXT,
        "log.md": LOG_TEXT,
        "README.md": README_TEXT,
        MACHINE_CONFIG: MACHINE_CONFIG_TEXT,
        "plugins/zotero/README.md": "# Zotero Plugin Placeholder\n\nZotero is optional plugin data, not v1 core authority.\n",
    }.items():
        if write_if_missing(root / rel, content, force=force):
            changed.append(f"wrote {rel}")
    return changed


def compact_for_index(value: str, max_chars: int = 2000) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "..."
    return text


def probe_section(body: str, heading: str, max_chars: int = 2000) -> str:
    pattern = r"^##\s+" + re.escape(heading) + r"\s*$"
    match = re.search(pattern, body, flags=re.M)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^##\s+.+?\s*$", body[start:], flags=re.M)
    end = start + next_match.start() if next_match else len(body)
    return compact_for_index(body[start:end], max_chars=max_chars)


def probe_findings(body: str, max_items: int = 8, max_chars: int = 2500) -> list[str]:
    findings: list[str] = []
    for line in body.splitlines():
        if "finding::" not in line:
            continue
        finding = line.split("finding::", 1)[1].strip()
        if finding:
            findings.append(compact_for_index(finding, max_chars=400))
        if len(findings) >= max_items:
            break
    joined = compact_for_index(" | ".join(findings), max_chars=max_chars)
    return [item for item in joined.split(" | ") if item] if joined else []


def frontmatter_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def safe_file_key(value: str, fallback: str = "item") -> str:
    return slugify(value, fallback)[:140]


def normalize_doi(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text)
    text = re.sub(r"^doi:\s*", "", text)
    return text.strip().rstrip(".")


def normalize_match_text(value: object) -> str:
    text = str(value or "").lower()
    text = re.sub(r"['`’]", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def text_similarity(left: object, right: object) -> float:
    a = normalize_match_text(left)
    b = normalize_match_text(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def author_display_name(value: dict[str, Any]) -> str:
    given = str(value.get("given", "") or "").strip()
    family = str(value.get("family", "") or "").strip()
    name = " ".join(part for part in [given, family] if part)
    return name or str(value.get("name", "") or value.get("display_name", "") or "").strip()


def note_authors(note: Note) -> list[str]:
    authors = frontmatter_list(note.frontmatter.get("authors"))
    if authors:
        return authors
    values: list[str] = []
    for edge in note.edges:
        if edge.relation == "authored_by":
            for link in relation_target_links(edge):
                values.append(titleize_slug(Path(normalize_link_target(link)).name))
    return values


def first_author_similarity(note: Note, candidate_authors: list[str]) -> float:
    authors = note_authors(note)
    if not authors or not candidate_authors:
        return 0.0
    return max(text_similarity(authors[0], candidate_authors[0]), text_similarity(authors[0].split()[-1], candidate_authors[0].split()[-1]))


def metadata_cache_path(root: Path, provider: str, key: str) -> Path:
    return root / METADATA_CACHE_DIR / provider / f"{safe_file_key(key)}.json"


def fetch_json_cached(root: Path, provider: str, key: str, url: str, headers: dict[str, str] | None = None, refresh: bool = False, timeout: int = 25) -> dict[str, Any]:
    path = metadata_cache_path(root, provider, key)
    if path.exists() and not refresh:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass
    request = urllib.request.Request(url, headers=headers or {"User-Agent": "research-kb/1.0"})
    payload: dict[str, Any]
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            payload = {
                "ok": True,
                "status": getattr(response, "status", 200),
                "url": url,
                "fetched_at": utc_timestamp(),
                "data": json.loads(raw),
            }
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        payload = {
            "ok": False,
            "url": url,
            "fetched_at": utc_timestamp(),
            "error": str(exc),
        }
        if isinstance(exc, urllib.error.HTTPError):
            payload["status"] = exc.code
    write_json(path, payload)
    return payload


def crossref_candidates(root: Path, note: Note, mailto: str = "", refresh: bool = False) -> list[dict[str, Any]]:
    doi = normalize_doi(note.frontmatter.get("doi"))
    headers = {"User-Agent": f"research-kb/1.0{f' (mailto:{mailto})' if mailto else ''}"}
    if doi:
        url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
        payload = fetch_json_cached(root, "crossref", f"doi-{doi}", url, headers=headers, refresh=refresh)
        items = [payload.get("data", {}).get("message", {})] if payload.get("ok") else []
    else:
        params = {"query.title": note.title, "rows": "3"}
        if mailto:
            params["mailto"] = mailto
        url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
        payload = fetch_json_cached(root, "crossref", f"title-{note.rel_path}-{note.title}", url, headers=headers, refresh=refresh)
        message = payload.get("data", {}).get("message", {}) if payload.get("ok") else {}
        items = message.get("items", []) if isinstance(message.get("items"), list) else []
    candidates: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = item.get("title", [""])
        container = item.get("container-title", [""])
        year = ""
        for key in ("published-print", "published-online", "published", "created"):
            parts = item.get(key, {}).get("date-parts") if isinstance(item.get(key), dict) else None
            if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
                year = str(parts[0][0])
                break
        authors = [author_display_name(author) for author in item.get("author", []) if isinstance(author, dict)]
        candidates.append(
            {
                "provider": "crossref",
                "title": str(title[0] if isinstance(title, list) and title else title or ""),
                "year": year,
                "doi": normalize_doi(item.get("DOI")),
                "venue": str(container[0] if isinstance(container, list) and container else container or ""),
                "authors": [author for author in authors if author],
                "external_ids": {"doi": normalize_doi(item.get("DOI"))},
                "raw_id": normalize_doi(item.get("DOI")),
            }
        )
    return candidates


def openalex_candidates(root: Path, note: Note, mailto: str = "", api_key_env: str = "OPENALEX_API_KEY", refresh: bool = False) -> list[dict[str, Any]]:
    doi = normalize_doi(note.frontmatter.get("doi"))
    params: dict[str, str] = {}
    if mailto:
        params["mailto"] = mailto
    api_key = os.environ.get(api_key_env, "").strip() if api_key_env else ""
    if api_key:
        params["api_key"] = api_key
    if doi:
        url = "https://api.openalex.org/works/https://doi.org/" + urllib.parse.quote(doi, safe="")
        if params:
            url += "?" + urllib.parse.urlencode(params)
        payload = fetch_json_cached(root, "openalex", f"doi-{doi}", url, refresh=refresh)
        items = [payload.get("data", {})] if payload.get("ok") else []
    else:
        params.update({"search": note.title, "per-page": "3"})
        url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
        payload = fetch_json_cached(root, "openalex", f"title-{note.rel_path}-{note.title}", url, refresh=refresh)
        data = payload.get("data", {}) if payload.get("ok") else {}
        items = data.get("results", []) if isinstance(data.get("results"), list) else []
    candidates: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        authors = []
        author_ids = []
        for authorship in item.get("authorships", []) if isinstance(item.get("authorships"), list) else []:
            author = authorship.get("author", {}) if isinstance(authorship, dict) else {}
            if isinstance(author, dict):
                name = str(author.get("display_name", "") or "").strip()
                if name:
                    authors.append(name)
                aid = str(author.get("id", "") or "").strip()
                if aid:
                    author_ids.append(aid)
        venue = ""
        source = item.get("primary_location", {}).get("source") if isinstance(item.get("primary_location"), dict) else None
        if isinstance(source, dict):
            venue = str(source.get("display_name", "") or "")
        candidates.append(
            {
                "provider": "openalex",
                "title": str(item.get("display_name", "") or ""),
                "year": str(item.get("publication_year", "") or ""),
                "doi": normalize_doi(item.get("doi")),
                "venue": venue,
                "authors": authors,
                "external_ids": {
                    "doi": normalize_doi(item.get("doi")),
                    "openalex_work_id": str(item.get("id", "") or ""),
                    "openalex_author_ids": author_ids,
                },
                "raw_id": str(item.get("id", "") or ""),
            }
        )
    return candidates


def semantic_scholar_candidates(root: Path, note: Note, api_key_env: str = "SEMANTIC_SCHOLAR_API_KEY", refresh: bool = False) -> list[dict[str, Any]]:
    fields = "title,year,authors,venue,externalIds,publicationVenue"
    doi = normalize_doi(note.frontmatter.get("doi"))
    headers = {"User-Agent": "research-kb/1.0"}
    api_key = os.environ.get(api_key_env, "").strip() if api_key_env else ""
    if api_key:
        headers["x-api-key"] = api_key
    if doi:
        url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{urllib.parse.quote(doi, safe='')}?fields={urllib.parse.quote(fields)}"
        payload = fetch_json_cached(root, "semantic-scholar", f"doi-{doi}", url, headers=headers, refresh=refresh)
        items = [payload.get("data", {})] if payload.get("ok") else []
    else:
        params = {"query": note.title, "limit": "3", "fields": fields}
        url = "https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode(params)
        payload = fetch_json_cached(root, "semantic-scholar", f"title-{note.rel_path}-{note.title}", url, headers=headers, refresh=refresh)
        data = payload.get("data", {}) if payload.get("ok") else {}
        items = data.get("data", []) if isinstance(data.get("data"), list) else []
    candidates: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        authors = []
        author_ids = []
        for author in item.get("authors", []) if isinstance(item.get("authors"), list) else []:
            if isinstance(author, dict):
                name = str(author.get("name", "") or "").strip()
                if name:
                    authors.append(name)
                aid = str(author.get("authorId", "") or "").strip()
                if aid:
                    author_ids.append(aid)
        external = item.get("externalIds", {}) if isinstance(item.get("externalIds"), dict) else {}
        venue = str(item.get("venue", "") or "")
        candidates.append(
            {
                "provider": "semantic_scholar",
                "title": str(item.get("title", "") or ""),
                "year": str(item.get("year", "") or ""),
                "doi": normalize_doi(external.get("DOI")),
                "venue": venue,
                "authors": authors,
                "external_ids": {
                    "doi": normalize_doi(external.get("DOI")),
                    "semantic_scholar_paper_id": str(item.get("paperId", "") or ""),
                    "semantic_scholar_author_ids": author_ids,
                },
                "raw_id": str(item.get("paperId", "") or ""),
            }
        )
    return candidates


def score_metadata_candidate(note: Note, candidate: dict[str, Any]) -> dict[str, Any]:
    note_doi = normalize_doi(note.frontmatter.get("doi"))
    cand_doi = normalize_doi(candidate.get("doi"))
    title_score = text_similarity(note.title, candidate.get("title"))
    year_note = str(note.frontmatter.get("year", "") or "").strip()
    year_candidate = str(candidate.get("year", "") or "").strip()
    year_match = bool(year_note and year_candidate and year_note == year_candidate)
    author_score = first_author_similarity(note, [str(item) for item in candidate.get("authors", []) if str(item).strip()])
    doi_match = bool(note_doi and cand_doi and note_doi == cand_doi)
    score = max(title_score * 0.65 + author_score * 0.2 + (0.15 if year_match else 0), 1.0 if doi_match else 0)
    confidence = "none"
    if doi_match or (title_score >= 0.94 and (year_match or author_score >= 0.88)):
        confidence = "high"
    elif title_score >= 0.86 and (year_match or author_score >= 0.75):
        confidence = "medium"
    elif title_score >= 0.78:
        confidence = "low"
    return {
        **candidate,
        "score": round(score, 4),
        "confidence": confidence,
        "signals": {
            "doi_match": doi_match,
            "title_similarity": round(title_score, 4),
            "year_match": year_match,
            "first_author_similarity": round(author_score, 4),
        },
    }


def merged_external_ids(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    ids: dict[str, Any] = {}
    for candidate in candidates:
        if candidate.get("confidence") not in {"high", "medium"}:
            continue
        ext = candidate.get("external_ids")
        if not isinstance(ext, dict):
            continue
        for key, value in ext.items():
            if not value:
                continue
            if isinstance(value, list):
                current = ids.setdefault(key, [])
                if isinstance(current, list):
                    for item in value:
                        if item and item not in current:
                            current.append(item)
            elif key not in ids:
                ids[key] = value
    return ids


def paper_match_report(root: Path, note: Note, args: argparse.Namespace) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    if not args.no_crossref:
        candidates.extend(crossref_candidates(root, note, mailto=args.mailto or "", refresh=args.refresh))
        time.sleep(args.delay)
    if not args.no_openalex:
        candidates.extend(openalex_candidates(root, note, mailto=args.mailto or "", api_key_env=args.openalex_api_key_env, refresh=args.refresh))
        time.sleep(args.delay)
    if not args.no_semantic_scholar:
        candidates.extend(semantic_scholar_candidates(root, note, api_key_env=args.semantic_scholar_api_key_env, refresh=args.refresh))
        time.sleep(args.delay)
    scored = [score_metadata_candidate(note, candidate) for candidate in candidates if candidate.get("title")]
    scored.sort(key=lambda item: float(item.get("score", 0)), reverse=True)
    best = scored[0] if scored else {}
    confidence = str(best.get("confidence", "none") or "none")
    return {
        "schema_version": 1,
        "generated_at": utc_timestamp(),
        "paper_path": note.rel_path,
        "paper_title": note.title,
        "paper_year": str(note.frontmatter.get("year", "") or ""),
        "paper_doi": normalize_doi(note.frontmatter.get("doi")),
        "paper_authors": note_authors(note),
        "state": "matched" if confidence in {"high", "medium", "low"} else "unmatched",
        "confidence": confidence,
        "best_match": best,
        "candidates": scored[:10],
        "provider_policy": "metadata only; not KB claim evidence",
    }


def apply_paper_metadata_match(note: Note, report: dict[str, Any], force: bool = False) -> bool:
    if report.get("confidence") != "high":
        return False
    if note_is_researcher_reviewed(note) and not force:
        return False
    best = report.get("best_match")
    if not isinstance(best, dict):
        return False
    updates: dict[str, str] = {
        "updated": yaml_string(today()),
        "metadata_reconciliation": yaml_json(
            {
                "state": "matched",
                "confidence": "high",
                "checked_at": utc_timestamp(),
                "providers": sorted({str(item.get("provider")) for item in report.get("candidates", []) if isinstance(item, dict) and item.get("confidence") in {"high", "medium"}}),
                "note": "External metadata is for bibliographic cleanup only, not KB claim evidence.",
            }
        ),
    }
    title = as_string(best.get("title"))
    if title and (force or not str(note.frontmatter.get("title", "")).strip() or text_similarity(note.title, title) < 0.98):
        updates["title"] = yaml_string(title)
    year = as_string(best.get("year"))
    if year and (force or not str(note.frontmatter.get("year", "")).strip()):
        updates["year"] = year
    doi = normalize_doi(best.get("doi"))
    if doi and (force or not str(note.frontmatter.get("doi", "")).strip()):
        updates["doi"] = yaml_string(doi)
    venue = as_string(best.get("venue"))
    if venue and (force or not str(note.frontmatter.get("publication", "")).strip()):
        updates["publication"] = yaml_string(venue)
    authors = [str(item).strip() for item in best.get("authors", []) if str(item).strip()]
    if authors and (force or not frontmatter_list(note.frontmatter.get("authors"))):
        updates["authors"] = yaml_list(authors)
    ids = merged_external_ids(report.get("candidates", []) if isinstance(report.get("candidates"), list) else [])
    if ids:
        updates["external_ids"] = yaml_json(ids)
    updated = update_frontmatter_fields(note.text, updates)
    if updated != note.text:
        note.path.write_text(updated, encoding="utf-8")
        return True
    return False


def note_key_paper_links(note: Note) -> set[str]:
    return {normalize_link_target(link) for link in wikilinks(section_body(note.body, "Key Papers")) if normalize_link_target(link).startswith("papers/")}


def inbound_live_links(root: Path, node: Note, notes: list[Note]) -> list[str]:
    target_no_ext = node.rel_path[:-3] if node.rel_path.endswith(".md") else node.rel_path
    target_name = Path(target_no_ext).name
    refs: list[str] = []
    for source in notes:
        if source.rel_path == node.rel_path:
            continue
        for link in source.links:
            normalized = normalize_link_target(link)
            if normalized in {target_no_ext, node.rel_path, target_name}:
                refs.append(source.rel_path)
                break
    return sorted(set(refs))


def author_name_core(title: str) -> str:
    parts = normalize_match_text(title).split()
    filtered = [part for part in parts if len(part) > 1]
    return " ".join(filtered) or " ".join(parts)


def phrase_like_author(title: str) -> bool:
    words = normalize_match_text(title).split()
    bad_starts = {"one", "previous", "methodological", "result", "results", "study", "paper", "section", "table", "figure"}
    if words and words[0] in bad_starts:
        return True
    phrase_terms = {"method", "methods", "normalization", "variation", "acoustic", "issue", "previously", "mainly"}
    return len(words) >= 3 and len(set(words) & phrase_terms) >= 2


def node_duplicate_score(left: Note, right: Note) -> tuple[float, list[str]]:
    signals: list[str] = []
    if left.note_type == "author" and right.note_type == "author":
        title_score = text_similarity(author_name_core(left.title), author_name_core(right.title))
    else:
        title_score = text_similarity(left.title, right.title)
    if title_score >= 0.86:
        signals.append(f"title_similarity={title_score:.3f}")
    left_papers = note_key_paper_links(left)
    right_papers = note_key_paper_links(right)
    shared_papers = left_papers & right_papers
    if shared_papers:
        signals.append("shared_key_papers=" + ",".join(sorted(shared_papers)[:5]))
    alias_score = 0.0
    for alias in left.aliases:
        alias_score = max(alias_score, text_similarity(alias, right.title))
    for alias in right.aliases:
        alias_score = max(alias_score, text_similarity(alias, left.title))
    if alias_score >= 0.9:
        signals.append(f"alias_similarity={alias_score:.3f}")
    score = max(title_score, alias_score)
    if shared_papers and score >= 0.72:
        score += 0.12
    return min(score, 1.0), signals


def duplicate_merge_rank(root: Path, note: Note, notes: list[Note]) -> tuple[int, int, int, int]:
    status = str(note.frontmatter.get("status", "")).strip()
    status_rank = {"reviewed": 5, "active": 4, "working": 3, "candidate": 1, "": 0}.get(status, 2)
    curated_rank = 1 if str(note.frontmatter.get("curated_by", "")).strip() else 0
    inbound_rank = len(inbound_live_links(root, note, notes))
    return (status_rank, curated_rank, inbound_rank, len(note.text))


def choose_duplicate_merge_nodes(root: Path, left: Note, right: Note, notes: list[Note]) -> tuple[Note, Note]:
    left_rank = duplicate_merge_rank(root, left, notes)
    right_rank = duplicate_merge_rank(root, right, notes)
    if left_rank >= right_rank:
        return right, left
    return left, right


def duplicate_node_clusters(root: Path, notes: list[Note]) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    node_notes = [note for note in notes if note.note_type in {"author", "concept", "variable", "method", "community"}]
    for i, left in enumerate(node_notes):
        for right in node_notes[i + 1 :]:
            if left.note_type != right.note_type:
                continue
            score, signals = node_duplicate_score(left, right)
            if score < 0.82:
                continue
            left_refs = inbound_live_links(root, left, notes)
            right_refs = inbound_live_links(root, right, notes)
            confidence = "high" if score >= 0.93 or (score >= 0.84 and set(left_refs) & set(right_refs)) else "medium"
            source, target = choose_duplicate_merge_nodes(root, left, right, notes)
            clusters.append(
                {
                    "schema_version": 1,
                    "generated_at": utc_timestamp(),
                    "cluster_type": "duplicate_node_candidate",
                    "confidence": confidence,
                    "suggested_action": "merge" if confidence == "high" else "needs_human_review",
                    "source_node": source.rel_path,
                    "target_node": target.rel_path,
                    "node_type": left.note_type,
                    "score": round(score, 4),
                    "signals": signals,
                    "nodes": [
                        {
                            "path": left.rel_path,
                            "title": left.title,
                            "status": str(left.frontmatter.get("status", "")),
                            "aliases": left.aliases,
                            "key_papers": sorted(note_key_paper_links(left)),
                            "inbound_refs": left_refs,
                        },
                        {
                            "path": right.rel_path,
                            "title": right.title,
                            "status": str(right.frontmatter.get("status", "")),
                            "aliases": right.aliases,
                            "key_papers": sorted(note_key_paper_links(right)),
                            "inbound_refs": right_refs,
                        },
                    ],
                    "provider_policy": "metadata only; curator must not use this as claim evidence",
                }
            )
    return clusters


def invalid_candidate_reports(root: Path, notes: list[Note]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for note in notes:
        if note.note_type not in {"author", "concept", "variable", "method", "community"}:
            continue
        if str(note.frontmatter.get("status", "")).strip() not in {"candidate", ""}:
            continue
        refs = inbound_live_links(root, note, notes)
        reasons: list[str] = []
        confidence = "low"
        if note.note_type == "author" and phrase_like_author(note.title):
            reasons.append("author title looks phrase-like rather than a person name")
            confidence = "high" if not refs else "medium"
        if not refs and not note_key_paper_links(note):
            reasons.append("candidate has no live inbound links or key papers")
            confidence = "medium" if confidence == "low" else confidence
        if not reasons:
            continue
        reports.append(
            {
                "schema_version": 1,
                "generated_at": utc_timestamp(),
                "cluster_type": "invalid_or_stale_candidate",
                "confidence": confidence,
                "suggested_action": "archive_invalid" if confidence == "high" else "needs_human_review",
                "source_node": note.rel_path,
                "node_type": note.note_type,
                "title": note.title,
                "status": str(note.frontmatter.get("status", "")),
                "reasons": reasons,
                "inbound_refs": refs,
                "key_papers": sorted(note_key_paper_links(note)),
                "provider_policy": "maintenance metadata only; not KB claim evidence",
            }
        )
    return reports


def write_reconciliation_clusters(root: Path, clusters: list[dict[str, Any]], invalids: list[dict[str, Any]]) -> None:
    duplicate_dir = root / METADATA_RECONCILIATION_DIR / "duplicate-clusters"
    invalid_dir = root / METADATA_RECONCILIATION_DIR / "invalid-candidates"
    ensure_dir(duplicate_dir)
    ensure_dir(invalid_dir)
    for old in list(duplicate_dir.glob("*.json")) + list(invalid_dir.glob("*.json")):
        old.unlink()
    for index, cluster in enumerate(clusters, start=1):
        source = safe_file_key(str(cluster.get("source_node", f"cluster-{index}")))
        write_json(duplicate_dir / f"{index:04d}-{source}.json", cluster)
    for index, item in enumerate(invalids, start=1):
        source = safe_file_key(str(item.get("source_node", f"invalid-{index}")))
        write_json(invalid_dir / f"{index:04d}-{source}.json", item)


def reconciliation_records_for_node(root: Path, node: Note, limit: int = 10) -> dict[str, list[dict[str, Any]]]:
    result = {"duplicate_clusters": [], "invalid_candidates": [], "author_matches": []}
    source_values = {node.rel_path}

    def payload_mentions_node(payload: dict[str, Any]) -> bool:
        for key in ("source_node", "target_node", "node_path"):
            if payload.get(key) in source_values:
                return True
        nodes = payload.get("nodes")
        if isinstance(nodes, list):
            for item in nodes:
                if isinstance(item, dict) and item.get("path") in source_values:
                    return True
        authors = payload.get("authors")
        if isinstance(authors, list) and node.note_type == "author":
            for item in authors:
                if isinstance(item, dict) and item.get("suggested_slug") == Path(node.rel_path).stem:
                    return True
        return False

    for folder, key in [
        ("duplicate-clusters", "duplicate_clusters"),
        ("invalid-candidates", "invalid_candidates"),
        ("author-matches", "author_matches"),
    ]:
        base = root / METADATA_RECONCILIATION_DIR / folder
        if not base.exists():
            continue
        for path in sorted(base.glob("*.json")):
            if len(result[key]) >= limit:
                break
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if payload_mentions_node(payload):
                result[key].append(payload)
    return result


def has_reconciliation_work(root: Path, node: Note) -> bool:
    records = reconciliation_records_for_node(root, node, limit=1)
    return any(records.get(key) for key in records)


def write_probe_indexes(root: Path, notes: list[Note]) -> None:
    search_dir = root / MACHINE_SEARCH_DIR
    ensure_dir(search_dir)
    paper_rows: list[dict[str, object]] = []
    node_rows: list[dict[str, object]] = []
    edge_rows: list[dict[str, object]] = []

    for note in notes:
        edge_labels = [f"{edge.relation}::{edge.target}" for edge in note.edges if edge.relation in QUERY_RELATIONS and edge.target]
        link_targets = sorted(set(normalize_link_target(link) for link in note.links))
        if note.note_type == "paper":
            authors = frontmatter_list(note.frontmatter.get("authors"))
            summary = probe_section(note.body, "One-Paragraph Summary", max_chars=1400)
            research_question = probe_section(note.body, "Research Question", max_chars=1200)
            findings = probe_findings(note.body)
            paper_rows.append(
                {
                    "path": note.rel_path,
                    "type": note.note_type,
                    "title": note.title,
                    "authors": authors,
                    "year": str(note.frontmatter.get("year", "")),
                    "doi": str(note.frontmatter.get("doi", "")),
                    "publication": str(note.frontmatter.get("publication", "")),
                    "kb_status": str(note.frontmatter.get("kb_status", "")),
                    "review_state": str(note.frontmatter.get("review_state", "")),
                    "raw_pdf_path": str(note.frontmatter.get("raw_pdf_path", "")),
                    "pdf_sha256": str(note.frontmatter.get("pdf_sha256", "")),
                    "summary": summary,
                    "research_question": research_question,
                    "key_findings": findings,
                    "links": link_targets[:80],
                    "edges": edge_labels[:120],
                    "search_text": compact_for_index(
                        " ".join([note.rel_path, note.title, " ".join(authors), summary, research_question, " ".join(findings), " ".join(edge_labels)]),
                        max_chars=6000,
                    ),
                }
            )
        else:
            key_papers = probe_section(note.body, "Key Papers", max_chars=1200)
            node_rows.append(
                {
                    "path": note.rel_path,
                    "type": note.note_type,
                    "title": note.title,
                    "aliases": note.aliases,
                    "status": str(note.frontmatter.get("status", "")),
                    "links": link_targets[:80],
                    "edges": edge_labels[:120],
                    "key_papers": key_papers,
                    "search_text": compact_for_index(
                        " ".join([note.rel_path, note.title, " ".join(note.aliases), key_papers, " ".join(edge_labels)]),
                        max_chars=4000,
                    ),
                }
            )

        for edge in note.edges:
            if edge.relation not in QUERY_RELATIONS or not edge.target:
                continue
            edge_rows.append(
                {
                    "source_path": note.rel_path,
                    "source_type": note.note_type,
                    "source_title": note.title,
                    "relation": edge.relation,
                    "target": edge.target,
                    "heading": edge.heading,
                    "line_no": edge.line_no,
                    "search_text": compact_for_index(f"{note.rel_path} {note.title} {edge.relation} {edge.target} {edge.heading}", max_chars=2000),
                }
            )

    write_jsonl(search_dir / "papers.jsonl", paper_rows)
    write_jsonl(search_dir / "nodes.jsonl", node_rows)
    write_jsonl(search_dir / "edges.jsonl", edge_rows)
    manifest = {
        "schema_version": 1,
        "generated_at": utc_timestamp(),
        "purpose": "search-friendly probe index; regenerate from Markdown and do not treat as source of truth",
        "files": {
            "papers": f"{MACHINE_SEARCH_DIR}/papers.jsonl",
            "nodes": f"{MACHINE_SEARCH_DIR}/nodes.jsonl",
            "edges": f"{MACHINE_SEARCH_DIR}/edges.jsonl",
        },
        "limits": {
            "target_corpus_papers": 10000,
            "expected_max_words_per_paper_note": 10000,
        },
    }
    (search_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def write_machine_index(root: Path, notes: list[Note], counts: dict[str, int], recent_papers: list[str]) -> None:
    target = root / MACHINE_INDEX
    ensure_dir(target.parent)
    raw_pdf_dir = root / "raw" / "papers"
    raw_pdfs = sorted(rel_to(path, root) for path in raw_pdf_dir.glob("*.pdf")) if raw_pdf_dir.exists() else []
    payload = {
        "schema_version": 1,
        "generated_at": utc_timestamp(),
        "human_index": "index.md",
        "source_of_truth": "markdown_notes",
        "raw_pdf_dir": "raw/papers",
        "node_folders": NODE_FOLDERS,
        "counts": counts,
        "raw_pdfs": raw_pdfs,
        "recent_papers": recent_papers,
        "notes": [
            {
                "path": note.rel_path,
                "type": note.note_type,
                "title": note.title,
                "aliases": note.aliases,
                "status": str(note.frontmatter.get("status", "")),
                "kb_status": str(note.frontmatter.get("kb_status", "")),
                "review_state": str(note.frontmatter.get("review_state", "")),
                "raw_pdf_path": str(note.frontmatter.get("raw_pdf_path", "")),
                "pdf_sha256": str(note.frontmatter.get("pdf_sha256", "")),
                "links": sorted(set(normalize_link_target(link) for link in note.links)),
                "edges": [
                    {
                        "relation": edge.relation,
                        "target": edge.target,
                        "heading": edge.heading,
                        "line_no": edge.line_no,
                    }
                    for edge in note.edges
                ],
            }
            for note in notes
        ],
    }
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    write_probe_indexes(root, notes)


def update_index(root: Path) -> None:
    index_path = root / "index.md"
    if not index_path.exists():
        index_path.write_text(INDEX_TEXT, encoding="utf-8")
    text = index_path.read_text(encoding="utf-8")
    notes = load_notes(root)
    counts = {folder: 0 for folder in NODE_FOLDERS.values()}
    recent_paper_notes: list[Note] = []
    for note in notes:
        parts = Path(note.rel_path).parts
        if parts and parts[0] in counts:
            counts[parts[0]] += 1
        if note.note_type == "paper":
            recent_paper_notes.append(note)
    recent_papers = recent_paper_notes[-10:]
    recent_paper_links = [f"- [[{note.rel_path[:-3]}]]" for note in recent_papers]
    recent_paper_paths = [note.rel_path for note in recent_papers]

    block = [
        "<!-- BEGIN KB AUTO INDEX -->",
        "## Auto Index",
        "",
        f"- Papers: {counts['papers']}",
        f"- Authors: {counts['authors']}",
        f"- Concepts: {counts['concepts']}",
        f"- Variables: {counts['variables']}",
        f"- Methods: {counts['methods']}",
        f"- Communities: {counts['communities']}",
        f"- Questions: {counts['questions']}",
        f"- Syntheses: {counts['syntheses']}",
        "",
        "## Recent Paper Notes",
        "",
        *(recent_paper_links or ["- None yet."]),
        "<!-- END KB AUTO INDEX -->",
        "",
    ]
    replacement = "\n".join(block)
    if "<!-- BEGIN KB AUTO INDEX -->" in text and "<!-- END KB AUTO INDEX -->" in text:
        text = re.sub(
            r"<!-- BEGIN KB AUTO INDEX -->.*?<!-- END KB AUTO INDEX -->\n?",
            replacement,
            text,
            flags=re.S,
        )
    else:
        text = text.rstrip() + "\n\n" + replacement
    index_path.write_text(text, encoding="utf-8")
    write_machine_index(root, notes, counts, recent_paper_paths)


def decode_pdf_literal(raw: bytes) -> str:
    if raw.startswith(b"(") and raw.endswith(b")"):
        inner = raw[1:-1]
        if inner.startswith(b"\xfe\xff") or inner.count(b"\x00") > max(2, len(inner) // 8):
            try:
                return inner.decode("utf-16-be", errors="ignore").lstrip("\ufeff")
            except Exception:
                pass
        text = inner.decode("latin1", errors="ignore")
        text = re.sub(r"\\([nrtbf()\\])", lambda m: {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "(": "(", ")": ")", "\\": "\\"}[m.group(1)], text)
        text = re.sub(r"\\([0-7]{1,3})", lambda m: chr(int(m.group(1), 8)), text)
        if text.startswith("þÿ") or text.count("\x00") > max(2, len(text) // 8):
            try:
                return text.encode("latin1", errors="ignore").decode("utf-16-be", errors="ignore").lstrip("\ufeff")
            except Exception:
                pass
        return text
    if raw.startswith(b"<") and raw.endswith(b">") and not raw.startswith(b"<<"):
        try:
            data = bytes.fromhex(raw[1:-1].decode("ascii", errors="ignore"))
            for encoding in ("utf-16-be", "utf-8", "latin1"):
                try:
                    return data.decode(encoding).lstrip("\ufeff")
                except UnicodeDecodeError:
                    pass
        except ValueError:
            return ""
    return ""


def clean_extracted_text(value: str) -> str:
    value = value.replace("\ufeff", "").replace("\x00", "")
    value = value.replace("þÿ", "")
    value = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def clean_generated_text(value: str) -> str:
    value = value.replace("\ufb01", "fi").replace("\ufb02", "fl")
    value = value.replace("\u00ad", "").replace("\u02d8", "")
    value = re.sub(r"(?:\[\[PAGE:\d+\]\]|@@PAGE:\d+@@)", " ", value)
    value = re.sub(r"\b([A-Za-z]{2,3})-\s+([a-z]{2,})\b", r"\1\2", value)
    value = re.sub(r"\bi\s+nherent\b", "inherent", value, flags=re.I)
    value = re.sub(r"\bs\s+ocial\b", "social", value, flags=re.I)
    value = re.sub(r"\ban\s+d\b", "and", value, flags=re.I)

    def join_suffix_break(match: re.Match[str]) -> str:
        left, right = match.group(1), match.group(2)
        suffixes = (
            "able",
            "ably",
            "al",
            "ally",
            "ance",
            "cation",
            "calic",
            "ed",
            "ence",
            "ences",
            "er",
            "ers",
            "ical",
            "ically",
            "icant",
            "icantly",
            "ible",
            "ibly",
            "ing",
            "ion",
            "ions",
            "ity",
            "ive",
            "ively",
            "ment",
            "ments",
            "ness",
            "ology",
            "ous",
            "tion",
            "tions",
        )
        if right.lower().startswith(suffixes):
            return f"{left}{right}"
        return f"{left}-{right}"

    value = re.sub(r"\b([A-Za-z]{4,})-\s+([a-z]{2,})\b", join_suffix_break, value)
    value = re.sub(r"([A-Za-z])-\s+([A-Za-z])", r"\1-\2", value)
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def printable_ratio(value: bytes) -> float:
    if not value:
        return 0.0
    printable = sum(1 for byte in value if byte in b"\n\r\t" or 32 <= byte <= 126)
    return printable / len(value)


def looks_like_bad_title(value: str) -> bool:
    clean = clean_extracted_text(value).strip()
    if not clean:
        return True
    low = clean.lower().strip()
    if low in GENERIC_PDF_TITLES or any(low.startswith(item) for item in GENERIC_PDF_TITLES):
        return True
    if re.fullmatch(r"[a-z]{2,}\d+\.dvi", low) or low.endswith(".dvi"):
        return True
    if low.startswith("/") or "headers/footers" in low or re.search(r"\b(tf|helv)\b", low):
        return True
    if len(clean) < 8:
        return True
    letters = sum(1 for char in clean if char.isalpha())
    weird = sum(1 for char in clean if not (char.isalnum() or char.isspace() or char in ".,:;!?/&'()-–—"))
    if letters < 4 or weird / max(1, len(clean)) > 0.25:
        return True
    return False


def clean_person_name(value: str) -> str:
    value = clean_extracted_text(value)
    value = value.replace("∗", "").replace("*", "")
    value = value.replace("P .", "P.")
    value = re.sub(r"\S+@\S+", "", value)
    value = re.sub(r"\s+", " ", value).strip(" ,;")
    return value


def regex_pdf_metadata(path: Path) -> dict[str, str]:
    data = path.read_bytes()
    metadata: dict[str, str] = {}
    for key in ("Title", "Author", "Subject", "Creator", "Producer", "CreationDate", "ModDate"):
        pattern = rb"/" + key.encode("ascii") + rb"\s*(\((?:\\.|[^\\)])*\)|<[^<>]+>)"
        match = re.search(pattern, data, re.S)
        if match:
            metadata[key] = re.sub(r"\s+", " ", clean_extracted_text(decode_pdf_literal(match.group(1)))).strip()
    return metadata


def fallback_pdf_text(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    chunks: list[bytes] = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        stream = match.group(1).strip(b"\r\n")
        try:
            chunks.append(zlib.decompress(stream))
        except Exception:
            if printable_ratio(stream) > 0.70:
                chunks.append(stream)
    if not chunks and printable_ratio(data) > 0.55:
        chunks = [data]

    values: list[str] = []
    for chunk in chunks:
        for literal in re.finditer(rb"\((?:\\.|[^\\()])*\)", chunk, re.S):
            decoded = decode_pdf_literal(literal.group(0))
            decoded = re.sub(r"\s+", " ", clean_extracted_text(decoded)).strip()
            if len(decoded) >= 2 and re.search(r"[A-Za-z0-9]", decoded):
                values.append(decoded)
        for literal in re.finditer(rb"<[0-9A-Fa-f\s]{4,}>", chunk):
            decoded = decode_pdf_literal(literal.group(0))
            decoded = re.sub(r"\s+", " ", clean_extracted_text(decoded)).strip()
            if len(decoded) >= 2 and re.search(r"[A-Za-z0-9]", decoded):
                values.append(decoded)
    text = clean_extracted_text("\n".join(values))
    status = "fallback_literal_extraction" if text else "no_text_extracted"
    return text, status


def try_extract_with_pypdf(path: Path, max_chars: int = DEFAULT_PDF_TEXT_MAX_CHARS) -> tuple[dict[str, str], str, str]:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        return {}, "", "pypdf_not_available"

    try:
        reader = PdfReader(str(path))
        metadata = {}
        if reader.metadata:
            for key, value in reader.metadata.items():
                metadata[str(key).lstrip("/")] = str(value or "").strip()

        pages: list[str] = []
        total_chars = 0
        truncated = False
        for index, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""
            if page_text.strip():
                page_chunk = f"@@PAGE:{index}@@\n{page_text}"
                if max_chars and total_chars + len(page_chunk) > max_chars:
                    remaining = max_chars - total_chars
                    if remaining > 0:
                        pages.append(page_chunk[:remaining])
                    truncated = True
                    break
                pages.append(page_chunk)
                total_chars += len(page_chunk)
        text = "\n".join(pages).strip()
        if truncated:
            text = text.rstrip() + f"\n\n@@TRUNCATED: extracted first {max_chars} characters@@"
            return metadata, text, f"ok_truncated_{max_chars}_chars"
        return metadata, text, "ok"
    except Exception as exc:
        return {}, "", f"pdf_extract_failed: {exc}"


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return ""


def cap_extracted_text(text: str, max_chars: int, status: str) -> tuple[str, str]:
    if max_chars and len(text) > max_chars:
        return text[:max_chars].rstrip() + f"\n\n@@TRUNCATED: extracted first {max_chars} characters@@", f"{status}_truncated_{max_chars}_chars"
    return text, status


def try_extract_with_pymupdf4llm(path: Path, max_chars: int = DEFAULT_PDF_TEXT_MAX_CHARS) -> tuple[dict[str, str], str, str, str]:
    try:
        import pymupdf4llm  # type: ignore
    except Exception:
        return {}, "", "pymupdf4llm_not_available", ""
    try:
        markdown = pymupdf4llm.to_markdown(str(path))
        if isinstance(markdown, list):
            markdown = "\n\n".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in markdown)
        text, status = cap_extracted_text(str(markdown or ""), max_chars, "ok")
        return {}, text, status, package_version("pymupdf4llm")
    except Exception as exc:
        return {}, "", f"pymupdf4llm_extract_failed: {exc}", package_version("pymupdf4llm")


def try_extract_with_pymupdf(path: Path, max_chars: int = DEFAULT_PDF_TEXT_MAX_CHARS) -> tuple[dict[str, str], str, str, str]:
    try:
        import fitz  # type: ignore
    except Exception:
        try:
            import pymupdf as fitz  # type: ignore
        except Exception:
            return {}, "", "pymupdf_not_available", ""
    try:
        doc = fitz.open(str(path))
        metadata = {str(k): str(v or "").strip() for k, v in (doc.metadata or {}).items() if str(v or "").strip()}
        chunks: list[str] = []
        total_chars = 0
        truncated = False
        for index, page in enumerate(doc, start=1):
            try:
                page_text = page.get_text("text") or ""
            except Exception:
                page_text = ""
            if not page_text.strip():
                continue
            page_chunk = f"@@PAGE:{index}@@\n{page_text}"
            if max_chars and total_chars + len(page_chunk) > max_chars:
                remaining = max_chars - total_chars
                if remaining > 0:
                    chunks.append(page_chunk[:remaining])
                truncated = True
                break
            chunks.append(page_chunk)
            total_chars += len(page_chunk)
        text = "\n".join(chunks)
        if truncated:
            text = text.rstrip() + f"\n\n@@TRUNCATED: extracted first {max_chars} characters@@"
            return metadata, text, f"ok_truncated_{max_chars}_chars", package_version("PyMuPDF") or package_version("pymupdf")
        return metadata, text, "ok", package_version("PyMuPDF") or package_version("pymupdf")
    except Exception as exc:
        return {}, "", f"pymupdf_extract_failed: {exc}", package_version("PyMuPDF") or package_version("pymupdf")


def extract_pdf_payload(path: Path, max_chars: int = DEFAULT_PDF_TEXT_MAX_CHARS) -> ExtractionResult:
    attempts: list[str] = []
    metadata, text, status, version = try_extract_with_pymupdf4llm(path, max_chars=max_chars)
    attempts.append(status)
    backend = "pymupdf4llm"
    extracted_format = "markdown"
    if not text:
        metadata, text, status, version = try_extract_with_pymupdf(path, max_chars=max_chars)
        attempts.append(status)
        backend = "pymupdf"
        extracted_format = "text"
    if not text:
        metadata, text, status = try_extract_with_pypdf(path, max_chars=max_chars)
        attempts.append(status)
        backend = "pypdf"
        version = package_version("pypdf")
        extracted_format = "text"
    if not metadata:
        metadata = regex_pdf_metadata(path)
    if not text:
        text, fallback_status = fallback_pdf_text(path)
        attempts.append(fallback_status)
        status = fallback_status
        backend = "literal"
        version = ""
        extracted_format = "text"
    cleaned = clean_extracted_text(text)
    if backend == "literal" and len(attempts) > 1:
        status = "; ".join(attempts)
    digest = hashlib.sha256(cleaned.encode("utf-8")).hexdigest() if cleaned else ""
    return ExtractionResult(
        metadata=metadata,
        text=cleaned,
        status=status,
        backend=backend,
        backend_version=version,
        extracted_format=extracted_format,
        extracted_text_sha256=digest,
        extracted_text_chars=len(cleaned),
    )


def extract_pdf_text(path: Path) -> tuple[dict[str, str], str, str]:
    payload = extract_pdf_payload(path)
    return payload.metadata, payload.text, payload.status


def infer_year(*values: str) -> str:
    for value in values:
        acl_match = re.search(r"\b[A-Z](\d{2})-\d{3,5}\b", value or "")
        if acl_match:
            year = int(acl_match.group(1))
            return str(2000 + year if year < 70 else 1900 + year)
        match = re.search(r"\b(19|20)\d{2}\b", value or "")
        if match:
            return match.group(0)
    return ""


def infer_doi(text: str) -> str:
    match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", text, re.I)
    return match.group(0).rstrip(".,);]") if match else ""


def split_authors(value: str) -> list[str]:
    value = clean_extracted_text(value).strip()
    if not value:
        return []
    parts = re.split(r"\s*(?:;|\band\b|,)\s*", value)
    return [clean_person_name(part) for part in parts if clean_person_name(part)]


def looks_like_person_line(line: str) -> bool:
    clean = clean_person_name(line)
    if not clean or len(clean) > 90:
        return False
    low = clean.lower()
    if clean.startswith("/") or re.search(r"\d", clean) or re.search(r"\b(tf|helv)\b", low):
        return False
    affiliation_words = {
        "advanced",
        "avenida",
        "association",
        "center",
        "centre",
        "china",
        "college",
        "computer",
        "college",
        "department",
        "humanities",
        "institute",
        "laboratory",
        "language",
        "literature",
        "macau",
        "netherlands",
        "school",
        "science",
        "sciences",
        "study",
        "universidade",
        "university",
        "proceedings",
        "abstract",
        "pages",
        "workshop",
    }
    if any(word in low for word in affiliation_words) or "@" in clean:
        return False
    words = [word for word in re.split(r"\s+", clean) if word]
    if not 2 <= len(words) <= 6:
        return False
    alpha_words = [word for word in words if re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", word)]
    if len(alpha_words) < 2:
        return False
    return sum(1 for word in alpha_words if word[:1].isupper()) >= 1


def line_is_title_candidate(line: str) -> bool:
    low = line.lower()
    if not 10 <= len(line) <= 180:
        return False
    if len(tokens(line)) < 2:
        return False
    bad_prefixes = (
        "abstract",
        "keywords",
        "proceedings",
        "copyright",
        "doi",
        "http",
        "www.",
        "association for computational linguistics",
    )
    if low.startswith(bad_prefixes) or "@" in line:
        return False
    if re.fullmatch(r"\d+", line):
        return False
    return not looks_like_bad_title(line)


def infer_title_from_text(text: str) -> str:
    lines = [clean_extracted_text(line) for line in text.splitlines()[:50]]
    lines = [line for line in lines if line]
    for index, line in enumerate(lines):
        if not line_is_title_candidate(line):
            continue
        title = line
        if index + 1 < len(lines):
            next_line = lines[index + 1]
            if (
                line.endswith((':', 'of', 'for', 'and'))
                or (len(next_line) <= 90 and line_is_title_candidate(next_line) and not looks_like_person_line(next_line))
            ):
                combined = f"{line} {next_line}".strip()
                if len(combined) <= 180 and not looks_like_bad_title(combined):
                    title = combined
        return re.sub(r"\s+", " ", title).strip()
    return ""


def infer_authors_from_text(text: str, title: str) -> list[str]:
    lines = [clean_extracted_text(line) for line in text.splitlines()[:80]]
    lines = [line for line in lines if line]
    if not lines:
        return []
    title_tokens = set(tokens(title))
    start = 0
    if title_tokens:
        for index, line in enumerate(lines):
            line_tokens = set(tokens(line))
            if len(title_tokens & line_tokens) >= max(2, min(4, len(title_tokens))):
                start = index + 1
                break
    authors: list[str] = []
    checked = 0
    for line in lines[start : start + 20]:
        checked += 1
        low = line.lower()
        if low.startswith(("abstract", "keywords", "introduction")):
            break
        if looks_like_person_line(line):
            for part in re.split(r"\s*(?:,|\band\b|;)\s*", line):
                name = clean_person_name(part)
                if looks_like_person_line(name) and name not in authors:
                    authors.append(name)
        if len(authors) >= 6 or (authors and checked >= 10):
            break
    return authors


def infer_title(path: Path, metadata: dict[str, str], text: str) -> str:
    meta_title = clean_extracted_text(metadata.get("Title", ""))
    text_title = infer_title_from_text(text)
    if meta_title and not looks_like_bad_title(meta_title):
        return re.sub(r"\s+", " ", meta_title)
    if text_title:
        return text_title
    for line in text.splitlines()[:30]:
        clean = re.sub(r"\s+", " ", clean_extracted_text(line)).strip()
        if line_is_title_candidate(clean):
            return clean
    return path.stem.replace("_", " ").replace("-", " ").strip().title()


def collect_pdf_info(path: Path) -> PdfInfo:
    sha = sha256_file(path)
    extraction = extract_pdf_payload(path)
    metadata, text, status = extraction.metadata, extraction.text, extraction.status
    title = infer_title(path, metadata, text)
    authors = split_authors(metadata.get("Author", ""))
    if not authors:
        authors = infer_authors_from_text(text, title)
    year = infer_year(path.name, text[:5000], metadata.get("CreationDate", ""), metadata.get("ModDate", ""))
    doi = infer_doi(text)
    publication = clean_extracted_text(metadata.get("Subject", "")).strip()
    uncertain = []
    if not authors:
        uncertain.append("authors")
    if not year:
        uncertain.append("year")
    if not doi:
        uncertain.append("doi")
    if status != "ok":
        uncertain.append("text_extraction")

    preview = re.sub(r"\s+", " ", clean_generated_text(text)).strip()
    if len(preview) > 1600:
        preview = preview[:1600].rstrip() + "..."

    return PdfInfo(
        path=path,
        sha256=sha,
        title=title,
        authors=authors,
        year=year,
        doi=doi,
        publication=publication,
        text_preview=preview,
        extraction_status=status,
        uncertain_fields=uncertain,
        extraction_backend=extraction.backend,
        extraction_backend_version=extraction.backend_version,
        extracted_format=extraction.extracted_format,
        extracted_text_sha256=extraction.extracted_text_sha256,
        extracted_text_chars=extraction.extracted_text_chars,
    )


def extract_note_pdf_text(root: Path, note: Note) -> tuple[str, str]:
    payload = extract_note_pdf_payload(root, note)
    return payload.text, payload.status


def extract_note_pdf_payload(root: Path, note: Note) -> ExtractionResult:
    raw_pdf_path = str(note.frontmatter.get("raw_pdf_path", "")).strip()
    if not raw_pdf_path:
        return ExtractionResult({}, "", "missing_raw_pdf_path", "", "", "text", "", 0)
    pdf_path = root / raw_pdf_path
    if not pdf_path.exists():
        return ExtractionResult({}, "", "missing_pdf_file", "", "", "text", "", 0)
    return extract_pdf_payload(pdf_path)


def split_sentences(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return []
    pieces = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", compact)
    sentences = []
    for piece in pieces:
        piece = clean_generated_text(piece)
        if 35 <= len(piece) <= 360 and not looks_like_bad_title(piece):
            sentences.append(piece)
    return sentences


def line_looks_like_front_matter(line: str, title: str) -> bool:
    clean = clean_generated_text(line)
    if not clean:
        return True
    low = clean.lower()
    if title and slugify(clean) == slugify(title):
        return True
    if re.fullmatch(r"\d+", clean) or re.fullmatch(r"@@PAGE:\d+@@", clean):
        return True
    if "@" in clean or low.startswith(("proceedings", "copyright", "doi", "http", "www.")):
        return True
    if looks_like_person_line(clean):
        return True
    affiliation_words = {
        "avenida",
        "association for computational linguistics",
        "carnegie mellon",
        "college",
        "department",
        "humanities",
        "institute",
        "laboratory",
        "linguistics and cognitive science",
        "macau",
        "neukom",
        "netherlands",
        "pages",
        "school",
        "science",
        "social sciences",
        "tilburg",
        "university",
        "workshop",
    }
    return any(word in low for word in affiliation_words)


def extract_front_matter_abstract(text: str, title: str = "") -> str:
    intro = re.search(r"\n\s*(?:\d+\.?\s+)?(?:Introduction|INTRODUCTION)\b", text)
    segment = text[: intro.start()] if intro else text[:2200]
    lines = [clean_generated_text(line) for line in segment.splitlines()]
    kept: list[str] = []
    for line in lines:
        if not line or line_looks_like_front_matter(line, title):
            continue
        if line.lower() in {"abstract", "keywords"}:
            continue
        kept.append(line)
    candidate = clean_extracted_text(" ".join(kept))
    sentences = split_sentences(candidate)
    if sentences:
        return " ".join(sentences[:4])
    return candidate


def extract_abstract(text: str, title: str = "") -> str:
    if not text:
        return ""
    match = re.search(
        r"\bAbstract\b\s*(.*?)(?=\n\s*(?:1\.?\s+)?(?:Introduction|INTRODUCTION|Background|Related Work)\b)",
        text,
        re.S,
    )
    if match:
        return clean_extracted_text(match.group(1))
    match = re.search(r"\bAbstract\b\s*(.{300,1600})", text, re.S)
    if match:
        return clean_extracted_text(match.group(1))
    front_matter = extract_front_matter_abstract(text, title)
    return front_matter or clean_extracted_text(text[:1600])


def select_sentences(text: str, patterns: list[str], limit: int = 3, exclude_patterns: list[str] | None = None) -> list[str]:
    selected: list[str] = []
    exclude_patterns = exclude_patterns or []
    for sentence in split_sentences(text):
        if any(re.search(pattern, sentence, re.I) for pattern in exclude_patterns):
            continue
        if any(re.search(pattern, sentence, re.I) for pattern in patterns):
            if sentence not in selected:
                selected.append(sentence)
        if len(selected) >= limit:
            break
    return selected


def sentence_page(text: str, sentence: str) -> str:
    normalized_sentence = " ".join(tokens(sentence)[:10])
    if not normalized_sentence:
        return ""
    sections = re.split(r"@@PAGE:(\d+)@@", text)
    current_page = ""
    for item in sections:
        if item.isdigit():
            current_page = item
            continue
        normalized_section = " ".join(tokens(clean_generated_text(item)))
        if normalized_sentence in normalized_section:
            return current_page
    return ""


def evidence_anchor(text: str, sentence: str) -> str:
    page = sentence_page(text, sentence)
    if page:
        return f"p. {page}, extracted text; verify against PDF"
    return "extracted text; verify page number in PDF"


def detected_term_rules(text: str) -> list[dict[str, object]]:
    seen: set[tuple[str, str]] = set()
    found: list[dict[str, object]] = []
    for rule in TERM_RULES:
        pattern = str(rule["pattern"])
        if re.search(pattern, text, re.I):
            key = (str(rule["folder"]), str(rule["slug"]))
            if key not in seen:
                found.append(rule)
                seen.add(key)
    return found


def rule_wikilink(rule: dict[str, object]) -> str:
    return f"[[{rule['folder']}/{rule['slug']}]]"


def section_text(text: str, heading: str) -> str:
    match = re.search(rf"^##\s+{re.escape(heading)}\s*$", text, re.M)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^##\s+", text[start:], re.M)
    end = start + next_match.start() if next_match else len(text)
    return text[start:end].strip()


def section_is_draft(text: str, heading: str) -> bool:
    current = section_text(text, heading)
    if not current:
        return True
    low = current.lower()
    if "needs researcher/agent review" in low or "no text preview extracted" in low:
        return True
    if heading == "Links":
        link_lines = [line.strip() for line in current.splitlines() if line.strip()]
        if link_lines and all(re.fullmatch(r"-\s+[^:]+:\s*", line) for line in link_lines):
            return True
    if heading == "Extraction Notes":
        note_lines = [line.strip() for line in current.splitlines() if line.strip()]
        if note_lines and all(re.fullmatch(r"-\s+[^:]+:\s*", line) for line in note_lines):
            return True
    meaningful = [
        line.strip()
        for line in current.splitlines()
        if line.strip() and not re.fullmatch(r"-\s*[a-z_]+::\s*", line.strip())
    ]
    return not meaningful


def replace_markdown_section(text: str, heading: str, content: str, force: bool = False) -> str:
    if not force and not section_is_draft(text, heading):
        return text
    replacement = f"## {heading}\n\n{content.strip()}\n\n"
    pattern = rf"^##\s+{re.escape(heading)}\s*$.*?(?=^##\s+|\Z)"
    if re.search(pattern, text, re.S | re.M):
        return re.sub(pattern, replacement, text, count=1, flags=re.S | re.M)
    return text.rstrip() + "\n\n" + replacement


def bullet_lines(items: list[str], fallback: str) -> str:
    if not items:
        return fallback
    return "\n".join(f"- {item}" for item in items)


def as_string(value: object) -> str:
    return clean_generated_text(str(value or "")).strip()


def as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = as_string(item)
        if text:
            items.append(text)
    return items


def normalized_node_type(value: str) -> str:
    clean = value.strip().lower().replace("-", "_")
    aliases = {
        "question": "research_question",
        "research-question": "research_question",
        "paper_note": "paper",
    }
    clean = aliases.get(clean, clean)
    return clean if clean in NODE_FOLDERS else "concept"


def edge_ref_wikilink(edge: dict[str, Any]) -> str:
    node_type = normalized_node_type(as_string(edge.get("node_type")))
    folder = NODE_FOLDERS[node_type]
    slug = slugify(as_string(edge.get("slug")) or as_string(edge.get("label")) or "candidate")
    return f"[[{folder}/{slug}]]"


def normalized_relation(value: str, fallback: str = "relevant_to") -> str:
    relation = value.strip().lower().replace("-", "_")
    return relation if relation in RELATIONS and relation != "uncertainty" else fallback


def render_edge_refs(edges: object, fallback_relation: str = "relevant_to") -> list[str]:
    if not isinstance(edges, list):
        return []
    lines: list[str] = []
    seen: set[str] = set()
    for item in edges:
        if not isinstance(item, dict):
            continue
        relation = normalized_relation(as_string(item.get("relation")), fallback=fallback_relation)
        target = edge_ref_wikilink(item)
        line = f"- {relation}:: {target} #candidate"
        uncertainty = as_string(item.get("uncertainty"))
        evidence = as_string(item.get("evidence"))
        if line not in seen:
            lines.append(line)
            if evidence:
                lines.append(f"  - evidence:: {evidence}")
            if uncertainty:
                lines.append(f"  - uncertainty:: {uncertainty}")
            seen.add(line)
    return lines


def merge_graph_edges(*edge_groups: object) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for group in edge_groups:
        if not isinstance(group, list):
            continue
        for item in group:
            if not isinstance(item, dict):
                continue
            key = (
                normalized_relation(as_string(item.get("relation"))),
                normalized_node_type(as_string(item.get("node_type"))),
                slugify(as_string(item.get("slug")) or as_string(item.get("label"))),
            )
            if key not in seen:
                merged.append(item)
                seen.add(key)
    return merged


def links_from_edges(edges: list[dict[str, Any]]) -> str:
    grouped = {
        "author": [],
        "concept": [],
        "variable": [],
        "method": [],
        "community": [],
    }
    for edge in edges:
        node_type = normalized_node_type(as_string(edge.get("node_type")))
        if node_type in grouped:
            link = edge_ref_wikilink(edge)
            if link not in grouped[node_type]:
                grouped[node_type].append(link)
    return "\n".join(
        [
            "- Concepts: " + ", ".join(grouped["concept"]) if grouped["concept"] else "- Concepts:",
            "- Variables: " + ", ".join(grouped["variable"]) if grouped["variable"] else "- Variables:",
            "- Methods: " + ", ".join(grouped["method"]) if grouped["method"] else "- Methods:",
            "- Authors: " + ", ".join(grouped["author"]) if grouped["author"] else "- Authors:",
            "- Communities: " + ", ".join(grouped["community"]) if grouped["community"] else "- Communities:",
            "- Related papers:",
        ]
    )


def author_link_lines(authors: list[str]) -> str:
    if not authors:
        return "- authored_by::"
    return "\n".join(f"- authored_by:: [[authors/{slugify(author)}]]" for author in authors if author.strip()) or "- authored_by::"


def agent_analysis_to_sections(result: AgentAnalysisResult, extraction_status: str) -> dict[str, str]:
    analysis = result.analysis
    variable_edges = analysis.get("linguistic_variables", [])
    social_edges = analysis.get("social_factors", [])
    method_edges = analysis.get("methods_and_measures", [])
    graph_edges = merge_graph_edges(analysis.get("graph_edges", []), variable_edges, social_edges, method_edges)

    summary = as_string(analysis.get("one_paragraph_summary"))
    if summary:
        summary = f"Agent-drafted from extracted text; verify against the PDF. {summary}"
    else:
        summary = "Agent analysis did not return a reliable summary. Review the PDF manually before using this note as evidence."

    findings: list[str] = []
    key_findings = analysis.get("key_findings", [])
    if isinstance(key_findings, list):
        for item in key_findings:
            if not isinstance(item, dict):
                continue
            finding = as_string(item.get("finding"))
            if not finding:
                continue
            findings.append(f"- finding:: {finding}")
            evidence = as_string(item.get("evidence")) or "Agent-selected extracted text; verify against PDF"
            findings.append(f"  - evidence:: {evidence}")
            for relation, field in [("supports", "supports"), ("complicates", "complicates"), ("contradicts", "contradicts")]:
                for line in render_edge_refs(item.get(field, []), fallback_relation=relation):
                    if line.startswith("- "):
                        findings.append("  " + line)
    if not findings:
        findings = ["- finding:: unknown", "  - evidence:: Agent analysis did not return key findings; review PDF manually."]

    extraction = [
        "- metadata_confidence: agent_assisted",
        f"- text_extraction_status: {extraction_status}",
        f"- enrichment_source: agent",
        f"- agent_source: {result.source}",
        f"- agent_model: {result.model or 'unspecified'}",
        "- uncertain_fields: " + (", ".join(as_string_list(analysis.get("uncertain_fields"))) or "none"),
        "- enrichment_note: Agent output is source-grounded from extracted text but still requires researcher review.",
    ]

    return {
        "Authors": author_link_lines(as_string_list(analysis.get("authors"))),
        "One-Paragraph Summary": summary,
        "Research Question": bullet_lines(as_string_list(analysis.get("research_question")), "- Research question not confidently extracted; inspect the paper manually."),
        "Data and Participants": bullet_lines(as_string_list(analysis.get("data_and_participants")), "- Data/participants not confidently extracted; inspect methods/data sections manually."),
        "Linguistic Variables": "\n".join(render_edge_refs(variable_edges, "studies_variable")) or "- studies_variable:: unknown\n  - uncertainty:: Agent analysis did not identify a linguistic variable.",
        "Social Factors": "\n".join(render_edge_refs(social_edges, "tests_social_factor")) or "- tests_social_factor:: unknown\n  - uncertainty:: Agent analysis did not identify a social factor.",
        "Methods and Measures": "\n".join(render_edge_refs(method_edges, "uses_method")) or "- uses_method:: unknown\n  - uncertainty:: Agent analysis did not identify methods/measures.",
        "Graph Edges": "\n".join(render_edge_refs(graph_edges, "relevant_to")) or "- relevant_to:: review needed\n  - uncertainty:: Agent analysis did not return candidate graph edges.",
        "Key Findings": "\n".join(findings),
        "Theoretical Contribution": bullet_lines(as_string_list(analysis.get("theoretical_contribution")), "- Contribution not confidently extracted; review introduction/conclusion manually."),
        "Limitations": bullet_lines(as_string_list(analysis.get("limitations")), "- Limitations not confidently extracted; review discussion/conclusion manually."),
        "Useful Quotes": bullet_lines(as_string_list(analysis.get("useful_quotes")), "- No reliable quote extracted."),
        "Extraction Notes": "\n".join(extraction),
        "Links": links_from_edges(graph_edges),
    }


def replace_sections(text: str, sections: dict[str, str], force: bool = False) -> str:
    updated = text
    for heading, content in sections.items():
        updated = replace_markdown_section(updated, heading, content, force=force)
    return updated


def build_enrichment(root: Path, note: Note, text: str, extraction_status: str) -> dict[str, str]:
    title = note.title
    abstract = extract_abstract(text, title)
    abstract_sentences = split_sentences(abstract)
    full_sentences = split_sentences(text[:16000])
    rules = detected_term_rules(" ".join([title, abstract, text[:12000]]))

    summary_sentences = abstract_sentences[:3] or full_sentences[:3]
    if summary_sentences:
        summary = " ".join(summary_sentences)
        summary = f"Agent-drafted from extracted text; verify against the PDF. {summary}"
    else:
        summary = "Agent could not extract a reliable abstract. Review the PDF manually before using this note as evidence."

    rq_sentences = select_sentences(
        abstract + "\n" + text[:8000],
        [r"\bask", r"\binvestigat", r"\bstud", r"\bfocus", r"\bpropos", r"\bpresent", r"\bexamin"],
        limit=2,
    )
    research_question = bullet_lines(rq_sentences, f"- What does `{title}` contribute to the current KB? #candidate")

    data_sentences = select_sentences(
        abstract + "\n" + text[:12000],
        [r"\bdata\b", r"\bcorpus\b", r"\btweet", r"\bspeech\b", r"\brecord", r"\bspeaker", r"\baudio", r"\bexperiment", r"\btoken"],
        limit=4,
    )
    data = bullet_lines(data_sentences, "- Data/participants not confidently extracted; inspect methods/data sections manually.")

    variable_rules = [rule for rule in rules if rule["folder"] == "variables"]
    method_rules = [rule for rule in rules if rule["folder"] == "methods"]
    concept_rules = [rule for rule in rules if rule["folder"] == "concepts"]
    community_rules = [rule for rule in rules if rule["folder"] == "communities"]
    social_rules = [rule for rule in concept_rules if rule["relation"] == "tests_social_factor"]

    variables = "\n".join(f"- studies_variable:: {rule_wikilink(rule)} #candidate" for rule in variable_rules)
    if not variables:
        variables = "- studies_variable:: unknown\n  - uncertainty:: No linguistic variable was confidently detected from extracted text."

    social = "\n".join(f"- tests_social_factor:: {rule_wikilink(rule)} #candidate" for rule in social_rules)
    if not social:
        social = "- tests_social_factor:: unknown\n  - uncertainty:: No social factor was confidently detected from extracted text."

    method_lines: list[str] = []
    for rule in method_rules:
        relation = str(rule["relation"])
        method_lines.append(f"- {relation}:: {rule_wikilink(rule)} #candidate")
    if not method_lines:
        method_lines = ["- uses_method:: unknown", "  - uncertainty:: No method was confidently detected from extracted text."]
    methods = "\n".join(method_lines)

    graph_lines: list[str] = []
    for rule in rules:
        relation = str(rule["relation"])
        graph_lines.append(f"- {relation}:: {rule_wikilink(rule)} #candidate")
    if not graph_lines:
        graph_lines = ["- relevant_to:: review needed", "  - uncertainty:: No candidate graph edges were detected."]
    graph = "\n".join(graph_lines)

    finding_sentences = select_sentences(
        abstract + "\n" + text[:18000],
        [r"\bshow", r"\bfind", r"\bfound", r"\bresult", r"\bsuggest", r"\bdemonstrat", r"\boutperform", r"\baccuracy", r"\bperform"],
        limit=4,
        exclude_patterns=[r"^\s*(?:to what|how|why|whether|can|does|do)\b", r"^\s*(?:\d+(?:\.\d+)*|section\s+\d+)\b", r"\?$"],
    )
    if not finding_sentences:
        finding_sentences = summary_sentences[:2]
    findings: list[str] = []
    support_targets = concept_rules[:2] or variable_rules[:1]
    for sentence in finding_sentences[:4]:
        findings.append(f"- finding:: {sentence}")
        findings.append(f"  - evidence:: {evidence_anchor(text, sentence)}")
        for target in support_targets[:2]:
            relation = "supports" if target["folder"] == "concepts" else "relevant_to"
            findings.append(f"  - {relation}:: {rule_wikilink(target)} #candidate")
    key_findings = "\n".join(findings) if findings else "- finding:: unknown\n  - evidence:: review PDF manually"

    contribution_sentences = select_sentences(
        abstract + "\n" + text[:14000],
        [r"\bcontribut", r"\bpropos", r"\bpresent", r"\bintroduc", r"\benable", r"\bprovide"],
        limit=3,
    )
    contribution = bullet_lines(contribution_sentences, "- Contribution not confidently extracted; review introduction/conclusion manually.")

    limitation_sentences = select_sentences(
        text[:22000],
        [r"\blimit", r"\bchallenge", r"\bfuture work", r"\bnot feasible", r"\berror", r"\bmanual", r"\bnoisy"],
        limit=3,
    )
    limitations = bullet_lines(limitation_sentences, "- Limitations not confidently extracted; review discussion/conclusion manually.")

    quote_lines = abstract_sentences[:3] or full_sentences[:3]
    useful_quotes = "\n".join(f"- \"{sentence}\" - {evidence_anchor(text, sentence)}" for sentence in quote_lines)
    if not useful_quotes:
        useful_quotes = "- No reliable quote extracted."

    links = [
        "- Concepts: " + ", ".join(rule_wikilink(rule) for rule in concept_rules) if concept_rules else "- Concepts:",
        "- Variables: " + ", ".join(rule_wikilink(rule) for rule in variable_rules) if variable_rules else "- Variables:",
        "- Methods: " + ", ".join(rule_wikilink(rule) for rule in method_rules) if method_rules else "- Methods:",
        "- Communities: " + ", ".join(rule_wikilink(rule) for rule in community_rules) if community_rules else "- Communities:",
        "- Related papers:",
    ]

    extraction = [
        "- metadata_confidence: heuristic_enrichment",
        f"- text_extraction_status: {extraction_status}",
        "- uncertain_fields: graph_edges, findings, page_numbers",
        "- enrichment_note: Candidate summaries and edges were inferred from extracted text; researcher review required.",
    ]

    return {
        "One-Paragraph Summary": summary,
        "Research Question": research_question,
        "Data and Participants": data,
        "Linguistic Variables": variables,
        "Social Factors": social,
        "Methods and Measures": methods,
        "Graph Edges": graph,
        "Key Findings": key_findings,
        "Theoretical Contribution": contribution,
        "Limitations": limitations,
        "Useful Quotes": useful_quotes,
        "Extraction Notes": "\n".join(extraction),
        "Links": "\n".join(links),
    }


def note_is_researcher_reviewed(note: Note) -> bool:
    return (
        str(note.frontmatter.get("kb_status", "")).strip() == "reviewed"
        or str(note.frontmatter.get("review_state", "")).strip() == "researcher_reviewed"
    )


def create_or_update_candidate_node(root: Path, rule: dict[str, object], paper_note: Note) -> bool:
    folder = str(rule["folder"])
    slug = str(rule["slug"])
    title = str(rule["title"])
    note_type = {value: key for key, value in NODE_FOLDERS.items()}.get(folder, "concept")
    path = root / folder / f"{slug}.md"
    paper_target = note_link(paper_note)
    changed = False
    aliases = yaml_list([str(alias) for alias in rule.get("aliases", [])])
    if not path.exists():
        ensure_dir(path.parent)
        content = f"""---
type: {note_type}
aliases: {aliases}
status: candidate
created: "{today()}"
updated: "{today()}"
---

# {title}

## Working Definition

Candidate node created during PDF enrichment. Review terminology and merge with an existing note if duplicated.

## Key Papers

- {paper_target}

## Open Questions

- Confirm whether this node is the best label for the linked evidence.
"""
        path.write_text(content, encoding="utf-8")
        return True

    text = path.read_text(encoding="utf-8")
    if paper_target not in text:
        if re.search(r"^##\s+Key Papers\s*$", text, re.M):
            text = re.sub(r"(^##\s+Key Papers\s*$)", rf"\1\n\n- {paper_target}", text, count=1, flags=re.M)
        else:
            text = text.rstrip() + f"\n\n## Key Papers\n\n- {paper_target}\n"
        path.write_text(text, encoding="utf-8")
        changed = True
    return changed


def enrich_note(root: Path, note: Note, force: bool, create_nodes: bool) -> tuple[bool, str]:
    if note.note_type != "paper":
        return False, f"skipped non-paper {note.rel_path}"
    if note_is_researcher_reviewed(note) and not force:
        return False, f"skipped researcher-reviewed {note.rel_path}"
    needs_sections = force or any(section_is_draft(note.text, heading) for heading in ENRICHMENT_HEADINGS)
    if not needs_sections and not create_nodes:
        return False, f"unchanged {note.rel_path}"

    original = note.text
    updated = original
    text, extraction_status = extract_note_pdf_text(root, note)
    if not text and needs_sections:
        return False, f"skipped {note.rel_path}: {extraction_status}"

    if needs_sections:
        enrichment = build_enrichment(root, note, text, extraction_status)
        updated = replace_sections(updated, enrichment, force=force)

    changed = updated != original
    if changed:
        note.path.write_text(updated, encoding="utf-8")
    if create_nodes:
        rules = detected_term_rules(" ".join([note.title, extract_abstract(text, note.title), text[:12000]]))
        for rule in rules:
            if create_or_update_candidate_node(root, rule, note):
                changed = True
        created_from_links = create_candidate_notes_from_text(root, updated, note)
        if created_from_links:
            changed = True
    return changed, f"enriched {note.rel_path}" if changed else f"unchanged {note.rel_path}"


def build_paper_id(info: PdfInfo) -> str:
    author = "unknown"
    if info.authors:
        author = re.sub(r"[^A-Za-z0-9-]", "", info.authors[0].split()[-1]) or "unknown"
    title_slug = slugify(info.title, "paper")
    short_title = "-".join(title_slug.split("-")[:6])
    return slugify(f"{author}-{info.year or 'nd'}-{short_title}", f"paper-{info.sha256[:8]}")


def existing_hashes(notes: list[Note]) -> set[str]:
    hashes: set[str] = set()
    for note in notes:
        value = note.frontmatter.get("pdf_sha256")
        if isinstance(value, str) and re.fullmatch(r"[a-fA-F0-9]{64}", value.strip()):
            hashes.add(value.strip().lower())
    return hashes


def unique_note_path(root: Path, paper_id: str) -> Path:
    candidate = root / "papers" / f"{paper_id}.md"
    if not candidate.exists():
        return candidate
    index = 2
    while True:
        candidate = root / "papers" / f"{paper_id}-{index}.md"
        if not candidate.exists():
            return candidate
        index += 1


def render_paper_note(root: Path, info: PdfInfo, relative_pdf_path: str, paper_id: str) -> str:
    uncertain = ", ".join(info.uncertain_fields) if info.uncertain_fields else "none"
    preview = info.text_preview or "No text preview extracted. Review the PDF manually."
    doi = info.doi or ""
    metadata_confidence = "low"
    if info.title and info.year and info.authors and info.extraction_status == "ok":
        metadata_confidence = "high"
    elif info.title and info.year and (info.authors or info.extraction_status == "ok"):
        metadata_confidence = "medium"
    values = {
        "paper_id": paper_id,
        "raw_pdf_path": relative_pdf_path,
        "pdf_sha256": info.sha256,
        "title": info.title or paper_id,
        "authors": yaml_list(info.authors),
        "year": info.year,
        "doi": doi,
        "publication": info.publication,
        "author_links": author_link_lines(info.authors),
        "date": today(),
    }
    note = render_template("paper.md", values, root=root)
    if "- DOI: {{doi}}" in note:
        note = note.replace("- DOI: {{doi}}", f"- DOI: {doi}")
    elif "- DOI:" in note:
        note = re.sub(r"^- DOI:.*$", f"- DOI: {doi}", note, count=1, flags=re.M)
    kb_build = {
        "extraction": {
            "backend": info.extraction_backend,
            "backend_version": info.extraction_backend_version,
            "extracted_format": info.extracted_format,
            "extracted_text_sha256": info.extracted_text_sha256,
            "extracted_text_chars": info.extracted_text_chars,
            "text_truncated_for_task": False,
        },
        "quality": {"state": "pending"},
    }
    note = update_frontmatter_fields(note, {"kb_build": yaml_json(kb_build)})
    note = note.replace("- metadata_confidence:", f"- metadata_confidence: {metadata_confidence}")
    note = note.replace("- text_extraction_status:", f"- text_extraction_status: {info.extraction_status}")
    note = note.replace("- uncertain_fields:", f"- uncertain_fields: {uncertain}\n- text_preview: {preview}")
    return note


def process_pdf(root: Path, path: Path, move: bool, dry_run: bool, known_hashes: set[str]) -> str:
    info = collect_pdf_info(path)
    if info.sha256.lower() in known_hashes:
        return f"skipped existing PDF hash: {rel_to(path, root)}"

    paper_id = build_paper_id(info)
    note_path = unique_note_path(root, paper_id)
    target_pdf_path = path
    if move:
        processed = root / "raw" / "processed"
        ensure_dir(processed)
        target_pdf_path = processed / path.name
        if target_pdf_path.exists():
            target_pdf_path = processed / f"{path.stem}-{info.sha256[:8]}{path.suffix}"

    relative_pdf_path = rel_to(target_pdf_path, root)
    if dry_run:
        return f"would create {rel_to(note_path, root)} from {rel_to(path, root)}"

    ensure_dir(note_path.parent)
    if move:
        shutil.move(str(path), str(target_pdf_path))
    note_text = render_paper_note(root, info, relative_pdf_path, note_path.stem)
    note_path.write_text(note_text, encoding="utf-8")
    paper_note = Note(path=note_path, rel_path=rel_to(note_path, root), frontmatter={}, body="", text=note_text, title=info.title or note_path.stem, note_type="paper", aliases=[], links=[], edges=[])
    create_candidate_notes_from_text(root, note_text, paper_note)
    known_hashes.add(info.sha256.lower())
    append_log(root, f"Processed raw PDF `{relative_pdf_path}` into `{rel_to(note_path, root)}`.")
    return f"created {rel_to(note_path, root)}"


def command_process(args: argparse.Namespace) -> int:
    root = Path(args.vault).resolve()
    init_vault(root)
    pdf_dir = root / "raw" / "papers"
    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if args.limit:
        pdfs = pdfs[: args.limit]
    if not pdfs:
        print("No PDFs found in raw/papers/.")
        return 0
    notes = load_notes(root)
    hashes = existing_hashes(notes)
    had_error = False
    for pdf in pdfs:
        try:
            print(process_pdf(root, pdf, args.move, args.dry_run, hashes))
        except Exception as exc:
            had_error = True
            failed = root / "raw" / "failed" / pdf.name
            if args.move and not args.dry_run:
                ensure_dir(failed.parent)
                shutil.move(str(pdf), str(failed))
            print(f"failed {rel_to(pdf, root)}: {exc}")
            if not args.dry_run:
                append_log(root, f"Failed to process raw PDF `{rel_to(pdf, root)}`: {exc}.")
    if not args.dry_run:
        update_index(root)
    return 1 if had_error else 0


def command_enrich(args: argparse.Namespace) -> int:
    root = Path(args.vault).resolve()
    notes = [note for note in load_notes(root) if note.note_type == "paper"]
    if args.limit:
        notes = notes[: args.limit]
    if not notes:
        print("No paper notes found to enrich.")
        return 0
    changed_count = 0
    for note in notes:
        changed, message = enrich_note(root, note, args.force, args.create_nodes)
        if changed:
            changed_count += 1
        print(message)
    if changed_count:
        update_index(root)
        append_log(root, f"Enriched {changed_count} paper note(s) from extracted PDF text.")
    return 0


def find_note_arg(root: Path, value: str) -> Note | None:
    clean = normalize_link_target(value.strip())
    if clean.endswith(".md"):
        clean = clean[:-3]
    notes = load_notes(root)
    for note in notes:
        rel = note.rel_path[:-3] if note.rel_path.endswith(".md") else note.rel_path
        if clean in {rel, note.rel_path, Path(rel).name, note.path.stem}:
            return note
    return resolve_link(clean, notes)


def agent_task_path(root: Path, output_dir: str, note: Note) -> Path:
    base = Path(output_dir)
    if not base.is_absolute():
        base = root / base
    return base / f"{note.path.stem}.agent-task.json"


def command_agent_context(args: argparse.Namespace) -> int:
    root = Path(args.vault).resolve()
    init_vault(root)
    if args.note:
        note = find_note_arg(root, args.note)
        notes = [note] if note and note.note_type == "paper" else []
    else:
        notes = [note for note in load_notes(root) if note.note_type == "paper"]
        if not args.all:
            notes = [
                note
                for note in notes
                if any(section_is_draft(note.text, heading) for heading in ENRICHMENT_HEADINGS)
            ]
    if args.limit:
        notes = notes[: args.limit]
    if not notes:
        print("No paper notes found for agent context export.")
        return 1 if args.note else 0

    written = 0
    for note in notes:
        task = paper_agent_task(root, note, max_chars=args.max_chars)
        target = agent_task_path(root, args.output_dir, note)
        ensure_dir(target.parent)
        target.write_text(json.dumps(task, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {rel_to(target, root)}")
        written += 1
    append_log(root, f"Exported {written} paper analysis agent task(s).")
    return 0


def load_analysis_payload(path: Path) -> tuple[str, dict[str, Any], str, str]:
    raw = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = parse_json_text(raw)
    if not isinstance(payload, dict):
        raise ValueError("analysis file must contain a JSON object")
    analysis_value = payload.get("analysis")
    if isinstance(analysis_value, dict):
        analysis = analysis_value
    else:
        analysis = payload
    note_path = as_string(payload.get("note_path") or analysis.get("note_path"))
    source = as_string(payload.get("agent_source") or payload.get("source")) or "external_agent"
    model = as_string(payload.get("agent_model") or payload.get("model"))
    return note_path, analysis, source, model


def analysis_quality_warnings(analysis: dict[str, Any], note: Note, text: str) -> list[str]:
    warnings: list[str] = []
    task_truncated = analysis.get("text_truncated_for_task_acknowledged")
    if not isinstance(task_truncated, bool):
        warnings.append("missing boolean text_truncated_for_task_acknowledged")
    self_check = analysis.get("quality_self_check")
    if not isinstance(self_check, dict):
        warnings.append("missing quality_self_check")
    else:
        if self_check.get("read_full_extracted_text") is not True:
            warnings.append("quality_self_check.read_full_extracted_text is not true")
        if self_check.get("truncation_claim_matches_task") is not True:
            warnings.append("quality_self_check.truncation_claim_matches_task is not true")
    coverage = analysis.get("section_coverage")
    if not isinstance(coverage, dict):
        warnings.append("missing section_coverage")
    findings = analysis.get("key_findings")
    if len(text) > 10000 and (not isinstance(findings, list) or not findings):
        warnings.append("substantial extracted text but no key_findings returned")
    uncertain = " ".join(as_string_list(analysis.get("uncertain_fields"))).lower()
    if "truncat" in uncertain and task_truncated is False:
        warnings.append("analysis claims truncation but task/provenance does not")
    return warnings


def update_frontmatter_from_analysis(text: str, analysis: dict[str, Any]) -> str:
    if not text.startswith("---"):
        return text
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.S)
    if not match:
        return text
    updates: dict[str, str] = {}
    for key in ("title", "year", "doi", "publication"):
        value = as_string(analysis.get(key))
        if value:
            updates[key] = yaml_string(value)
    authors = as_string_list(analysis.get("authors"))
    if authors:
        updates["authors"] = yaml_list(authors)
    if not updates:
        return text

    lines: list[str] = []
    seen: set[str] = set()
    for line in match.group(1).splitlines():
        key = line.split(":", 1)[0].strip() if ":" in line else ""
        if key in updates:
            lines.append(f"{key}: {updates[key]}")
            seen.add(key)
        else:
            lines.append(line)
    body = text[match.end() :]
    frontmatter = "---\n" + "\n".join(lines) + "\n---\n"
    return frontmatter + body


def apply_build_provenance(text: str, note: Note, analysis: dict[str, Any], source: str, model: str, warnings: list[str], extraction: ExtractionResult) -> str:
    build = kb_build_data(text)
    task_truncated = False
    if isinstance(build.get("extraction"), dict):
        task_truncated = bool(build["extraction"].get("text_truncated_for_task", False))  # type: ignore[index]
    if "text_truncated_for_task_acknowledged" in analysis:
        task_truncated = bool(analysis.get("text_truncated_for_task_acknowledged"))
    extraction_data = {
        "backend": extraction.backend,
        "backend_version": extraction.backend_version,
        "extracted_format": extraction.extracted_format,
        "extracted_text_sha256": extraction.extracted_text_sha256,
        "extracted_text_chars": extraction.extracted_text_chars,
        "text_truncated_for_task": task_truncated,
    }
    build = deep_merge_dict(
        build,
        {
            "extraction": extraction_data,
            "paper_process": {
                "source": source,
                "model_capability": model or "unspecified",
                "result_sha256": hashlib.sha256(json.dumps(analysis, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
                "applied_at": utc_timestamp(),
                "validation_warnings": warnings,
            },
            "quality": {"state": "pending"},
        },
    )
    updates = {"kb_build": yaml_json(build)}
    if warnings and str(note.frontmatter.get("review_state", "")) != "quality_failed":
        updates["review_state"] = "needs_review"
    return update_frontmatter_fields(text, updates)


def apply_agent_analysis_to_note(root: Path, note: Note, analysis: dict[str, Any], source: str, model: str, force: bool, create_nodes: bool) -> tuple[bool, str]:
    if note.note_type != "paper":
        return False, f"skipped non-paper {note.rel_path}"
    if note_is_researcher_reviewed(note) and not force:
        return False, f"skipped researcher-reviewed {note.rel_path}"
    extraction = extract_note_pdf_payload(root, note)
    text, extraction_status = extraction.text, extraction.status
    warnings = analysis_quality_warnings(analysis, note, text)
    result = AgentAnalysisResult(analysis=analysis, source=source, model=model)
    updated = update_frontmatter_from_analysis(note.text, analysis)
    updated = replace_sections(updated, agent_analysis_to_sections(result, extraction_status), force=True)
    updated = apply_build_provenance(updated, note, analysis, source, model, warnings, extraction)
    changed = updated != note.text
    if changed:
        note.path.write_text(updated, encoding="utf-8")
    if create_nodes:
        created = create_candidate_notes_from_text(root, updated, note)
        changed = changed or bool(created)
    warning_note = f" ({len(warnings)} quality warning(s))" if warnings else ""
    return changed, (f"applied agent analysis to {note.rel_path}{warning_note}" if changed else f"unchanged {note.rel_path}{warning_note}")


def command_apply_analysis(args: argparse.Namespace) -> int:
    root = Path(args.vault).resolve()
    changed_count = 0
    had_error = False
    for input_value in args.input:
        path = Path(input_value)
        if not path.is_absolute():
            path = root / path
        try:
            note_path, analysis, source, model = load_analysis_payload(path)
            note_arg = args.note or note_path
            if not note_arg:
                raise ValueError("analysis JSON must include `note_path`, or pass --note")
            note = find_note_arg(root, note_arg)
            if not note:
                raise ValueError(f"cannot find note `{note_arg}`")
            changed, message = apply_agent_analysis_to_note(root, note, analysis, source, model, args.force, args.create_nodes)
            if changed:
                changed_count += 1
            print(message)
        except Exception as exc:
            had_error = True
            print(f"failed {rel_to(path, root)}: {exc}", file=sys.stderr)
    if changed_count:
        update_index(root)
        append_log(root, f"Applied {changed_count} external agent paper analysis result(s).")
    return 1 if had_error else 0


RESULT_INDICATOR_RE = re.compile(r"\b(accuracy|auc|f1|precision|recall|significant|p\s*[<=>]|result|results|table|figure|outperform|improv(?:e|ed|ement)|percent|%)\b", re.I)


def note_claims_truncation(note: Note) -> bool:
    _frontmatter, body = split_note_text(note.text)
    low = body.lower()
    return "truncated" in low or "truncation" in low


def note_claims_no_results(note: Note) -> bool:
    low = note.text.lower()
    return any(phrase in low for phrase in ["no results available", "no key findings", "no results were", "results not available"])


def note_has_substantive_findings(note: Note) -> bool:
    for line in section_body(note.body, "Key Findings").splitlines():
        low = line.lower()
        if "finding::" in low and "unknown" not in low and "did not return key findings" not in low:
            return True
    return False


def quality_report_for_note(root: Path, note: Note) -> dict[str, Any]:
    extraction = extract_note_pdf_payload(root, note)
    build = kb_build_data(note)
    extraction_build = build.get("extraction") if isinstance(build.get("extraction"), dict) else {}
    text_truncated_for_task = bool(extraction_build.get("text_truncated_for_task", False)) if isinstance(extraction_build, dict) else False
    checks: dict[str, dict[str, object]] = {}

    truncation_claim = note_claims_truncation(note)
    checks["truncation_claim_valid"] = {
        "passed": not (truncation_claim and not text_truncated_for_task),
        "detail": "Paper note claims truncation while build provenance says text_truncated_for_task=false."
        if truncation_claim and not text_truncated_for_task
        else "No contradiction between note and build truncation provenance.",
    }

    has_result_indicators = bool(RESULT_INDICATOR_RE.search(extraction.text))
    no_results_claim = note_claims_no_results(note)
    checks["results_present"] = {
        "passed": not (has_result_indicators and no_results_claim),
        "detail": "Extracted text contains result-like indicators, but the note claims no results are available."
        if has_result_indicators and no_results_claim
        else "No obvious contradiction between extracted text and result claims.",
    }

    has_findings = note_has_substantive_findings(note)
    checks["finding_count"] = {
        "passed": not (extraction.extracted_text_chars > 10000 and not has_findings),
        "detail": "Substantial extracted text produced no substantive finding lines."
        if extraction.extracted_text_chars > 10000 and not has_findings
        else "Finding count is plausible for extracted text length.",
    }

    evidence_lines = [line for line in section_body(note.body, "Key Findings").splitlines() if "evidence::" in line]
    weak_evidence = [line for line in evidence_lines if "verify" in line.lower() or "agent analysis did not" in line.lower()]
    checks["evidence_anchors"] = {
        "passed": bool(evidence_lines) and len(weak_evidence) < len(evidence_lines),
        "detail": "Evidence anchors are missing or only generic verification placeholders."
        if not evidence_lines or len(weak_evidence) == len(evidence_lines)
        else "Evidence anchors are present.",
    }

    missing_sections = []
    for heading in ["Data and Participants", "Methods and Measures", "Key Findings"]:
        body = section_body(note.body, heading).lower()
        if not body or "not confidently extracted" in body or "unknown" in body:
            missing_sections.append(heading)
    checks["key_sections_present"] = {
        "passed": not (extraction.extracted_text_chars > 10000 and len(missing_sections) >= 2),
        "detail": f"Major paper sections appear incomplete: {', '.join(missing_sections)}."
        if extraction.extracted_text_chars > 10000 and len(missing_sections) >= 2
        else "Major sections are present or extraction is too short for a strict check.",
    }

    failed = [name for name, item in checks.items() if not item["passed"]]
    verdict = "failed" if failed else "passed"
    return {
        "schema_version": 1,
        "note_path": note.rel_path,
        "checked_at": utc_timestamp(),
        "extraction": {
            "backend": extraction.backend,
            "backend_version": extraction.backend_version,
            "extracted_text_chars": extraction.extracted_text_chars,
            "extracted_text_sha256": extraction.extracted_text_sha256,
            "text_truncated_for_task": text_truncated_for_task,
        },
        "checks": checks,
        "verdict": verdict,
        "failed_checks": failed,
        "recommendation": "Manual retry or researcher review is needed before this paper is used for curation."
        if failed
        else "Paper note passed automatic quality guard.",
    }


def apply_quality_state(note: Note, report: dict[str, Any]) -> bool:
    build = kb_build_data(note)
    build = deep_merge_dict(
        build,
        {
            "quality": {
                "state": "failed" if report.get("verdict") == "failed" else "passed",
                "checked_at": str(report.get("checked_at", "")),
                "failed_checks": report.get("failed_checks", []),
            }
        },
    )
    updates = {"kb_build": yaml_json(build)}
    if report.get("verdict") == "failed":
        updates["review_state"] = "quality_failed"
    elif str(note.frontmatter.get("review_state", "")) == "quality_failed":
        updates["review_state"] = "needs_review"
    updated = update_frontmatter_fields(note.text, updates)
    if updated != note.text:
        note.path.write_text(updated, encoding="utf-8")
        return True
    return False


def command_quality_guard(args: argparse.Namespace) -> int:
    root = Path(args.vault).resolve()
    init_vault(root)
    if args.note:
        note = find_note_arg(root, args.note)
        notes = [note] if note and note.note_type == "paper" else []
    else:
        notes = [note for note in load_notes(root) if note.note_type == "paper"]
    if args.limit:
        notes = notes[: args.limit]
    if not notes:
        print("No paper notes found for quality guard.")
        return 1 if args.note else 0
    report_dir = root / QUALITY_REPORT_DIR
    ensure_dir(report_dir)
    failed = 0
    changed = 0
    for note in notes:
        report = quality_report_for_note(root, note)
        target = report_dir / f"{note.path.stem}.quality-report.json"
        target.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        if apply_quality_state(note, report):
            changed += 1
        if report["verdict"] == "failed":
            failed += 1
        print(f"{report['verdict']} {note.rel_path} -> {rel_to(target, root)}")
    if changed:
        update_index(root)
    append_log(root, f"Quality guard checked {len(notes)} paper note(s); {failed} failed.")
    return 1 if failed and args.fail_on_quality_failed else 0


PAPER_JOB_COMPLETE = "quality_passed"
CURATOR_JOB_COMPLETE = "applied"
JOB_STATUSES = [
    "pending",
    "exported",
    "running",
    "result_written",
    "applied",
    "quality_passed",
    "quality_failed",
    "failed",
    "retry_pending",
]


def now_job_timestamp() -> str:
    return utc_timestamp()


def safe_job_part(value: str, fallback: str = "unknown") -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return clean or fallback


def job_sha(value: str, length: int = 16) -> str:
    if not value:
        return "unknown"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def read_jsonl_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def write_jsonl_records(path: Path, records: list[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    lines = [json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def job_ledger_path(root: Path, kind: str) -> Path:
    if kind == "paper":
        return root / PAPER_JOBS_FILE
    if kind == "curator":
        return root / CURATOR_JOBS_FILE
    raise ValueError(f"unknown job ledger kind `{kind}`")


def load_job_ledger(root: Path, kind: str) -> dict[str, dict[str, Any]]:
    return {as_string(record.get("job_id")): record for record in read_jsonl_records(job_ledger_path(root, kind)) if as_string(record.get("job_id"))}


def save_job_ledger(root: Path, kind: str, jobs: dict[str, dict[str, Any]]) -> None:
    ordered = sorted(jobs.values(), key=lambda item: (as_string(item.get("note_path") or item.get("node_path")), as_string(item.get("job_id"))))
    write_jsonl_records(job_ledger_path(root, kind), ordered)


def append_build_run(root: Path, event: dict[str, Any]) -> None:
    path = root / BUILD_RUNS_FILE
    ensure_dir(path.parent)
    record = {"timestamp": now_job_timestamp(), **event}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def job_rel_path(*parts: str) -> str:
    return "/".join(part.strip("/") for part in parts if part)


def paper_job_id(note: Note, extraction_hash: str) -> str:
    pdf_hash = safe_job_part(str(note.frontmatter.get("pdf_sha256", ""))[:16], "no-pdf")
    text_hash = safe_job_part(extraction_hash[:16], "no-text")
    stem = safe_job_part(note.path.stem)
    return f"paper-{pdf_hash}-{text_hash}-{PAPER_PROCESS_PROMPT_VERSION}-{stem}"


def curator_job_id(node: Note, evidence_fingerprint: str) -> str:
    node_hash = job_sha(node.rel_path, 12)
    evidence_hash = safe_job_part(evidence_fingerprint[:16], "no-evidence")
    stem = safe_job_part(node.path.stem)
    return f"curator-{node_hash}-{evidence_hash}-{NODE_CURATOR_PROMPT_VERSION}-{stem}"


def paper_job_task_path(job: dict[str, Any]) -> str:
    return job_rel_path(MACHINE_DIR, "agent-tasks", "paper", f"{job['job_id']}.agent-task.json")


def paper_job_result_path(job: dict[str, Any]) -> str:
    return job_rel_path(MACHINE_DIR, "agent-results", "paper", f"{job['job_id']}.agent-result.json")


def curator_job_task_path(job: dict[str, Any]) -> str:
    return job_rel_path(MACHINE_DIR, "curator-tasks", "jobs", f"{job['job_id']}.curator-task.json")


def curator_job_result_path(job: dict[str, Any]) -> str:
    return job_rel_path(MACHINE_DIR, "curator-results", "jobs", f"{job['job_id']}.curator-result.json")


def quality_report_path_for_note(note: Note) -> str:
    return job_rel_path(QUALITY_REPORT_DIR, f"{note.path.stem}.quality-report.json")


def preserve_job_state(previous: dict[str, Any] | None, default_status: str) -> tuple[str, int, str]:
    if not previous:
        return default_status, 0, ""
    status = as_string(previous.get("status")) or default_status
    attempts_value = previous.get("attempts", 0)
    attempts = int(attempts_value) if isinstance(attempts_value, int) else 0
    last_error = as_string(previous.get("last_error"))
    return status, attempts, last_error


def applied_result_matches(note: Note, result_path: Path) -> bool:
    if not result_path.exists():
        return False
    build = kb_build_data(note)
    paper_process = build.get("paper_process") if isinstance(build.get("paper_process"), dict) else {}
    applied_hash = as_string(paper_process.get("result_sha256")) if isinstance(paper_process, dict) else ""
    try:
        _note_path, analysis, _source, _model = load_analysis_payload(result_path)
    except Exception:
        return False
    result_hash = hashlib.sha256(json.dumps(analysis, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return bool(applied_hash and applied_hash == result_hash)


def infer_paper_job_status(root: Path, note: Note, job: dict[str, Any], previous: dict[str, Any] | None) -> str:
    quality_state = paper_quality_state(note)
    if quality_state == "passed":
        return PAPER_JOB_COMPLETE
    if quality_state == "failed":
        return "quality_failed"
    task_path = root / as_string(job.get("task_path"))
    result_path = root / as_string(job.get("result_path"))
    if applied_result_matches(note, result_path):
        return "applied"
    if result_path.exists():
        return "result_written"
    if task_path.exists():
        previous_status = as_string(previous.get("status")) if previous else ""
        return previous_status if previous_status == "running" else "exported"
    return "pending"


def build_paper_job(root: Path, note: Note, previous: dict[str, Any] | None = None) -> dict[str, Any]:
    extraction_hash = ""
    build = kb_build_data(note)
    extraction_build = build.get("extraction") if isinstance(build.get("extraction"), dict) else {}
    if isinstance(extraction_build, dict):
        extraction_hash = as_string(extraction_build.get("extracted_text_sha256"))
    if not extraction_hash:
        try:
            extraction_hash = extract_note_pdf_payload(root, note).extracted_text_sha256
        except Exception:
            extraction_hash = ""
    job_id = paper_job_id(note, extraction_hash)
    status, attempts, last_error = preserve_job_state(previous, "pending")
    job = {
        "schema_version": 1,
        "job_id": job_id,
        "job_type": "paper_process",
        "note_path": note.rel_path,
        "raw_pdf_path": as_string(note.frontmatter.get("raw_pdf_path")),
        "pdf_sha256": as_string(note.frontmatter.get("pdf_sha256")),
        "extracted_text_sha256": extraction_hash,
        "agent_name": PAPER_PROCESS_AGENT_NAME,
        "agent_contract_version": 1,
        "prompt_version": PAPER_PROCESS_PROMPT_VERSION,
        "status": status,
        "attempts": attempts,
        "max_attempts": int(previous.get("max_attempts", 2)) if previous and isinstance(previous.get("max_attempts"), int) else 2,
        "task_path": "",
        "result_path": "",
        "quality_report_path": quality_report_path_for_note(note),
        "last_error": last_error,
        "created_at": as_string(previous.get("created_at")) if previous else now_job_timestamp(),
        "updated_at": now_job_timestamp(),
    }
    job["task_path"] = paper_job_task_path(job)
    job["result_path"] = paper_job_result_path(job)
    job["status"] = infer_paper_job_status(root, note, job, previous)
    return job


def refresh_paper_jobs(root: Path) -> dict[str, dict[str, Any]]:
    previous = load_job_ledger(root, "paper")
    previous_by_note = {as_string(job.get("note_path")): job for job in previous.values() if as_string(job.get("note_path"))}
    jobs: dict[str, dict[str, Any]] = {}
    for note in load_notes(root):
        if note.note_type != "paper":
            continue
        job = build_paper_job(root, note, previous_by_note.get(note.rel_path))
        prior = previous.get(job["job_id"])
        if prior and prior is not previous_by_note.get(note.rel_path):
            job = build_paper_job(root, note, prior)
        jobs[job["job_id"]] = job
    save_job_ledger(root, "paper", jobs)
    return jobs


def paper_jobs_by_status(jobs: dict[str, dict[str, Any]], statuses: set[str]) -> list[dict[str, Any]]:
    selected = [job for job in jobs.values() if as_string(job.get("status")) in statuses]
    return sorted(selected, key=lambda item: (as_string(item.get("note_path")), as_string(item.get("job_id"))))


def set_job_status(job: dict[str, Any], status: str, error: str = "") -> None:
    job["status"] = status
    job["updated_at"] = now_job_timestamp()
    if error:
        job["last_error"] = error
    elif status not in {"failed", "quality_failed"}:
        job["last_error"] = ""


def command_build_jobs_refresh(args: argparse.Namespace) -> int:
    root = Path(args.vault).resolve()
    init_vault(root)
    paper_jobs = refresh_paper_jobs(root)
    curator_jobs = refresh_curator_jobs(root, max_papers=args.max_papers)
    append_build_run(
        root,
        {
            "event": "refresh",
            "paper_jobs": len(paper_jobs),
            "curator_jobs": len(curator_jobs),
        },
    )
    print(f"refreshed {len(paper_jobs)} paper job(s) and {len(curator_jobs)} curator job(s)")
    return 0


def summarize_jobs(jobs: dict[str, dict[str, Any]]) -> dict[str, int]:
    summary = {status: 0 for status in JOB_STATUSES}
    for job in jobs.values():
        status = as_string(job.get("status")) or "pending"
        summary[status] = summary.get(status, 0) + 1
    return {key: value for key, value in summary.items() if value}


WORK_IN_PROGRESS_JOB_STATUSES = {"pending", "retry_pending", "exported", "running", "result_written", "applied"}
FAILURE_JOB_STATUSES = {"failed", "quality_failed"}


def job_attempt_limit(job: dict[str, Any]) -> tuple[int, int]:
    attempts = int(job.get("attempts", 0)) if isinstance(job.get("attempts"), int) else 0
    max_attempts = int(job.get("max_attempts", 1)) if isinstance(job.get("max_attempts"), int) else 1
    return attempts, max_attempts


def job_failure_records(kind: str, jobs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for job in jobs.values():
        status = as_string(job.get("status"))
        if status not in FAILURE_JOB_STATUSES:
            continue
        attempts, max_attempts = job_attempt_limit(job)
        path = as_string(job.get("note_path") or job.get("node_path"))
        job_id = as_string(job.get("job_id"))
        records.append(
            {
                "kind": kind,
                "path": path,
                "job_id": job_id,
                "status": status,
                "attempts": attempts,
                "max_attempts": max_attempts,
                "retryable": attempts < max_attempts,
                "last_error": as_string(job.get("last_error")),
            }
        )
    return sorted(records, key=lambda item: (str(item["kind"]), str(item["path"]), str(item["job_id"])))


def next_job_command(paper_jobs: dict[str, dict[str, Any]], curator_jobs: dict[str, dict[str, Any]]) -> str:
    paper_summary = summarize_jobs(paper_jobs)
    curator_summary = summarize_jobs(curator_jobs)
    failures = job_failure_records("paper", paper_jobs) + job_failure_records("curator", curator_jobs)
    if paper_summary.get("result_written") or paper_summary.get("applied"):
        return "build-jobs apply-paper"
    if any(record["retryable"] for record in failures):
        return "build-jobs retry-failed"
    if paper_summary.get("pending") or paper_summary.get("retry_pending"):
        return "build-jobs export-paper --batch-size 10"
    if paper_summary.get("exported") or paper_summary.get("running"):
        return "wait for paper-process results, then run build-jobs apply-paper"
    if curator_summary.get("result_written"):
        return "build-jobs apply-curator"
    if curator_summary.get("pending") or curator_summary.get("retry_pending"):
        return "build-jobs export-curator --batch-size 20"
    if curator_summary.get("exported") or curator_summary.get("running"):
        return "wait for curator results, then run build-jobs apply-curator"
    if failures:
        return "review terminal exceptions in build-report"
    return "lint && index && build-report"


def command_build_jobs_status(args: argparse.Namespace) -> int:
    root = Path(args.vault).resolve()
    paper_jobs = refresh_paper_jobs(root)
    curator_jobs = refresh_curator_jobs(root, max_papers=args.max_papers)
    paper_summary = summarize_jobs(paper_jobs)
    curator_summary = summarize_jobs(curator_jobs)
    failures = job_failure_records("paper", paper_jobs) + job_failure_records("curator", curator_jobs)
    next_command = next_job_command(paper_jobs, curator_jobs)
    status = {
        "schema_version": 1,
        "generated_at": now_job_timestamp(),
        "paper_jobs": paper_summary,
        "curator_jobs": curator_summary,
        "retryable_failures": [record for record in failures if record["retryable"]],
        "terminal_exceptions": [record for record in failures if not record["retryable"]],
        "next_suggested_command": next_command,
    }
    target = root / JOBS_STATUS_FILE
    ensure_dir(target.parent)
    target.write_text(json.dumps(status, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(status, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print("Paper process jobs:")
        for key, value in paper_summary.items():
            print(f"- {key}: {value}")
        print("\nNode curation jobs:")
        for key, value in curator_summary.items():
            print(f"- {key}: {value}")
        print(f"\nNext suggested command:\npython3 <skill-dir>/scripts/research_kb.py --vault {root} {next_command}")
        print(f"\nwrote {rel_to(target, root)}")
    return 0


def command_build_jobs_export_paper(args: argparse.Namespace) -> int:
    root = Path(args.vault).resolve()
    init_vault(root)
    jobs = refresh_paper_jobs(root)
    selected = paper_jobs_by_status(jobs, {"pending", "retry_pending"})[: args.batch_size]
    written = 0
    for job in selected:
        note = find_note_arg(root, as_string(job.get("note_path")))
        if not note or note.note_type != "paper":
            set_job_status(job, "failed", "cannot resolve paper note")
            continue
        try:
            task = paper_agent_task(root, note, max_chars=args.max_chars)
            task["job_id"] = job["job_id"]
            task["prompt_version"] = PAPER_PROCESS_PROMPT_VERSION
            task["result_path"] = job["result_path"]
            task["result_envelope"]["job_id"] = job["job_id"]
            target = root / as_string(job.get("task_path"))
            ensure_dir(target.parent)
            target.write_text(json.dumps(task, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            job["attempts"] = int(job.get("attempts", 0)) + 1
            set_job_status(job, "exported")
            print(f"wrote {rel_to(target, root)}")
            written += 1
        except Exception as exc:
            set_job_status(job, "failed", str(exc))
            print(f"failed {job.get('note_path')}: {exc}", file=sys.stderr)
    save_job_ledger(root, "paper", jobs)
    append_log(root, f"Exported {written} resumable paper-process job task(s).")
    append_build_run(root, {"event": "export-paper", "written": written, "batch_size": args.batch_size})
    return 0 if written or not selected else 1


def apply_quality_guard_to_note(root: Path, note: Note) -> dict[str, Any]:
    report = quality_report_for_note(root, note)
    target = root / quality_report_path_for_note(note)
    ensure_dir(target.parent)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    apply_quality_state(note, report)
    return report


def command_build_jobs_apply_paper(args: argparse.Namespace) -> int:
    root = Path(args.vault).resolve()
    init_vault(root)
    jobs = refresh_paper_jobs(root)
    candidates = paper_jobs_by_status(jobs, {"exported", "running", "result_written", "applied"})
    applied = 0
    failed = 0
    changed_count = 0
    for job in candidates:
        result_path = root / as_string(job.get("result_path"))
        if not result_path.exists():
            continue
        try:
            note_path, analysis, source, model = load_analysis_payload(result_path)
            note_arg = as_string(job.get("note_path")) or note_path
            note = find_note_arg(root, note_arg)
            if not note or note.note_type != "paper":
                raise ValueError(f"cannot resolve paper note `{note_arg}`")
            changed, message = apply_agent_analysis_to_note(root, note, analysis, source, model, args.force, args.create_nodes)
            changed_count += int(changed)
            print(message)
            fresh_note = find_note_arg(root, note.rel_path)
            if not fresh_note:
                raise ValueError(f"cannot reload paper note `{note.rel_path}`")
            report = apply_quality_guard_to_note(root, fresh_note)
            if report.get("verdict") == "passed":
                set_job_status(job, PAPER_JOB_COMPLETE)
            else:
                set_job_status(job, "quality_failed", ", ".join(as_string_list(report.get("failed_checks"))))
            print(f"{report['verdict']} {fresh_note.rel_path} -> {job.get('quality_report_path')}")
            applied += 1
        except Exception as exc:
            failed += 1
            set_job_status(job, "failed", str(exc))
            print(f"failed {rel_to(result_path, root)}: {exc}", file=sys.stderr)
    save_job_ledger(root, "paper", jobs)
    if changed_count:
        update_index(root)
    append_log(root, f"Applied {applied} resumable paper-process result(s); {failed} failed.")
    append_build_run(root, {"event": "apply-paper", "applied": applied, "failed": failed})
    return 1 if failed else 0


def paper_quality_state(note: Note) -> str:
    if str(note.frontmatter.get("review_state", "")) == "quality_failed":
        return "failed"
    build = kb_build_data(note)
    quality = build.get("quality")
    if isinstance(quality, dict):
        state = str(quality.get("state", "")).strip()
        if state:
            return state
    return "unknown"


def curator_eligible_paper(note: Note) -> bool:
    # Curation turns paper-note content into shared graph knowledge.  Only
    # quality-passed notes are reliable enough for that promotion; draft,
    # pending, and failed notes must stay out of curator evidence packets.
    return note.note_type == "paper" and paper_quality_state(note) == "passed"


def edge_targets_node(edge: Edge, node: Note, notes: list[Note]) -> bool:
    for link in relation_target_links(edge):
        resolved = resolve_link(link, notes)
        if resolved and resolved.rel_path == node.rel_path:
            return True
    return False


def compact_note_sections(note: Note) -> dict[str, str]:
    sections = {}
    for heading in [
        "One-Paragraph Summary",
        "Research Question",
        "Data and Participants",
        "Methods and Measures",
        "Key Findings",
        "Theoretical Contribution",
        "Limitations",
    ]:
        sections[heading] = compact_for_index(section_body(note.body, heading), max_chars=2200)
    return sections


def inbound_paper_records(node: Note, notes: list[Note], max_papers: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for paper in notes:
        if not curator_eligible_paper(paper):
            continue
        matching_edges = [edge for edge in paper.edges if edge.relation in QUERY_RELATIONS and edge_targets_node(edge, node, notes)]
        if not matching_edges and node.rel_path[:-3] not in {normalize_link_target(link) for link in paper.links}:
            continue
        records.append(
            {
                "path": paper.rel_path,
                "title": paper.title,
                "year": str(paper.frontmatter.get("year", "")),
                "review_state": str(paper.frontmatter.get("review_state", "")),
                "quality_state": paper_quality_state(paper),
                "matching_edges": [
                    {"relation": edge.relation, "target": edge.target, "heading": edge.heading, "line_no": edge.line_no}
                    for edge in matching_edges
                ],
                "evidence_sections": compact_note_sections(paper),
            }
        )
        if len(records) >= max_papers:
            break
    return records


def related_node_records(node: Note, notes: list[Note], limit: int = 20) -> list[dict[str, str]]:
    related: list[dict[str, str]] = []
    seen: set[str] = {node.rel_path}
    for link in node.links:
        resolved = resolve_link(link, notes)
        if resolved and resolved.rel_path not in seen and resolved.note_type != "paper":
            related.append({"path": resolved.rel_path, "type": resolved.note_type, "title": resolved.title})
            seen.add(resolved.rel_path)
        if len(related) >= limit:
            break
    return related


def node_curator_schema() -> dict[str, object]:
    return {
        "type": "object",
        "required": ["node_path", "agent_source", "agent_model", "action"],
        "additionalProperties": True,
        "properties": {
            "node_path": {"type": "string"},
            "agent_source": {"type": "string"},
            "agent_model": {"type": "string"},
            "action": {"type": "string"},
            "new_status": {"type": "string"},
            "body_markdown": {"type": "string"},
            "sections": {"type": "object"},
            "synthesis_notes": {"type": "array"},
            "merge_plans": {"type": "array"},
            "coverage": {"type": "object"},
            "uncertain_fields": {"type": "array", "items": {"type": "string"}},
        },
    }


def node_curator_instructions() -> str:
    return (
        "Act as research-kb.node-curator. Use only the supplied node content and quality-passed paper-note evidence. "
        "You may rewrite the target non-paper node body to make it useful. Preserve uncertainty, surface contradictions, "
        "and keep source links/evidence anchors. You may propose active synthesis notes only when evidence is strong. "
        "You may propose high-confidence merges, but only for clear duplicates. Do not use web search or outside knowledge. "
        "Do not use quality-failed papers as curation evidence."
    )


def stale_key_papers_for_node(node: Note, inbound: list[dict[str, Any]]) -> list[str]:
    current = section_body(node.body, "Key Papers")
    missing = []
    for record in inbound:
        paper_path = str(record["path"])
        target = f"[[{paper_path[:-3] if paper_path.endswith('.md') else paper_path}]]"
        if target not in current:
            missing.append(paper_path)
    return missing


def curator_task(root: Path, node: Note, notes: list[Note], max_papers: int) -> dict[str, Any]:
    inbound = inbound_paper_records(node, notes, max_papers=max_papers)
    result_path = f"{CURATOR_RESULT_DIR}/{node.path.stem}.curator-result.json"
    return {
        "schema_version": 1,
        "task": "research_kb_curate_node",
        "agent": NODE_CURATOR_AGENT_NAME,
        "agent_profile": NODE_CURATOR_AGENT_PROFILE,
        "agent_reference": NODE_CURATOR_AGENT_REFERENCE,
        "primary_goal": "enrich_node_and_preserve_graph_integrity",
        "node_path": node.rel_path,
        "node_type": node.note_type,
        "node_status": str(node.frontmatter.get("status", "")),
        "node_title": node.title,
        "node_aliases": node.aliases,
        "existing_node_content": node.text,
        "inbound_papers_total": len(inbound),
        "inbound_papers": inbound,
        "stale_key_papers": stale_key_papers_for_node(node, inbound),
        "related_nodes": related_node_records(node, notes),
        "metadata_reconciliation": reconciliation_records_for_node(root, node),
        "result_path": result_path,
        "instructions": node_curator_instructions(),
        "expected_json_schema": node_curator_schema(),
    }


def curator_task_path(root: Path, output_dir: str, node: Note) -> Path:
    base = Path(output_dir)
    if not base.is_absolute():
        base = root / base
    return base / f"{node.path.stem}.curator-task.json"


def command_curator_context(args: argparse.Namespace) -> int:
    root = Path(args.vault).resolve()
    init_vault(root)
    notes = load_notes(root)
    selected: list[Note] = []
    if args.nodes:
        for value in args.nodes:
            note = find_note_arg(root, value)
            if note and note.note_type != "paper":
                selected.append(note)
    else:
        for note in notes:
            if note.note_type in {"author", "concept", "variable", "method", "community"}:
                inbound = inbound_paper_records(note, notes, max_papers=1)
                if inbound or has_reconciliation_work(root, note):
                    selected.append(note)
    if args.limit:
        selected = selected[: args.limit]
    if not selected:
        print("No non-paper nodes found for curator context export.")
        return 1 if args.nodes else 0
    written = 0
    for node in selected:
        task = curator_task(root, node, notes, max_papers=args.max_papers)
        target = curator_task_path(root, args.output_dir, node)
        ensure_dir(target.parent)
        target.write_text(json.dumps(task, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {rel_to(target, root)}")
        written += 1
    append_log(root, f"Exported {written} node curator task(s) for {args.mode}.")
    return 0


def selectable_curator_nodes(root: Path, notes: list[Note]) -> list[Note]:
    selected: list[Note] = []
    for note in notes:
        if note.note_type in {"author", "concept", "variable", "method", "community"}:
            inbound = inbound_paper_records(note, notes, max_papers=1)
            if inbound or has_reconciliation_work(root, note):
                selected.append(note)
    return selected


def curator_evidence_fingerprint(root: Path, node: Note, notes: list[Note], max_papers: int) -> str:
    task = curator_task(root, node, notes, max_papers=max_papers)
    evidence = {
        "node_path": node.rel_path,
        "inbound_papers": task.get("inbound_papers", []),
        "stale_key_papers": task.get("stale_key_papers", []),
        "metadata_reconciliation": task.get("metadata_reconciliation", {}),
        "prompt_version": NODE_CURATOR_PROMPT_VERSION,
    }
    return hashlib.sha256(json.dumps(evidence, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def infer_curator_job_status(root: Path, job: dict[str, Any], previous: dict[str, Any] | None) -> str:
    previous_status = as_string(previous.get("status")) if previous else ""
    if previous_status == CURATOR_JOB_COMPLETE:
        return CURATOR_JOB_COMPLETE
    result_path = root / as_string(job.get("result_path"))
    task_path = root / as_string(job.get("task_path"))
    if result_path.exists():
        return "result_written"
    if task_path.exists():
        return previous_status if previous_status == "running" else "exported"
    return previous_status if previous_status == "retry_pending" else "pending"


def build_curator_job(root: Path, node: Note, notes: list[Note], max_papers: int, previous: dict[str, Any] | None = None) -> dict[str, Any]:
    fingerprint = curator_evidence_fingerprint(root, node, notes, max_papers=max_papers)
    job_id = curator_job_id(node, fingerprint)
    status, attempts, last_error = preserve_job_state(previous, "pending")
    job = {
        "schema_version": 1,
        "job_id": job_id,
        "job_type": "node_curation",
        "node_path": node.rel_path,
        "node_type": node.note_type,
        "agent_name": NODE_CURATOR_AGENT_NAME,
        "agent_contract_version": 1,
        "prompt_version": NODE_CURATOR_PROMPT_VERSION,
        "status": status,
        "attempts": attempts,
        "max_attempts": int(previous.get("max_attempts", 1)) if previous and isinstance(previous.get("max_attempts"), int) else 1,
        "task_path": "",
        "result_path": "",
        "evidence_fingerprint": fingerprint,
        "last_error": last_error,
        "created_at": as_string(previous.get("created_at")) if previous else now_job_timestamp(),
        "updated_at": now_job_timestamp(),
    }
    job["task_path"] = curator_job_task_path(job)
    job["result_path"] = curator_job_result_path(job)
    job["status"] = infer_curator_job_status(root, job, previous)
    return job


def refresh_curator_jobs(root: Path, max_papers: int = 20) -> dict[str, dict[str, Any]]:
    previous = load_job_ledger(root, "curator")
    previous_by_node = {as_string(job.get("node_path")): job for job in previous.values() if as_string(job.get("node_path"))}
    notes = load_notes(root)
    jobs: dict[str, dict[str, Any]] = {}
    for node in selectable_curator_nodes(root, notes):
        job = build_curator_job(root, node, notes, max_papers=max_papers, previous=previous_by_node.get(node.rel_path))
        prior = previous.get(job["job_id"])
        if prior and prior is not previous_by_node.get(node.rel_path):
            job = build_curator_job(root, node, notes, max_papers=max_papers, previous=prior)
        jobs[job["job_id"]] = job
    save_job_ledger(root, "curator", jobs)
    return jobs


def curator_jobs_by_status(jobs: dict[str, dict[str, Any]], statuses: set[str]) -> list[dict[str, Any]]:
    selected = [job for job in jobs.values() if as_string(job.get("status")) in statuses]
    return sorted(selected, key=lambda item: (as_string(item.get("node_path")), as_string(item.get("job_id"))))


def command_build_jobs_export_curator(args: argparse.Namespace) -> int:
    root = Path(args.vault).resolve()
    init_vault(root)
    jobs = refresh_curator_jobs(root, max_papers=args.max_papers)
    notes = load_notes(root)
    selected = curator_jobs_by_status(jobs, {"pending", "retry_pending"})[: args.batch_size]
    written = 0
    for job in selected:
        node = find_note_arg(root, as_string(job.get("node_path")))
        if not node or node.note_type == "paper":
            set_job_status(job, "failed", "cannot resolve curator node")
            continue
        try:
            task = curator_task(root, node, notes, max_papers=args.max_papers)
            task["job_id"] = job["job_id"]
            task["prompt_version"] = NODE_CURATOR_PROMPT_VERSION
            task["result_path"] = job["result_path"]
            target = root / as_string(job.get("task_path"))
            ensure_dir(target.parent)
            target.write_text(json.dumps(task, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
            job["attempts"] = int(job.get("attempts", 0)) + 1
            set_job_status(job, "exported")
            print(f"wrote {rel_to(target, root)}")
            written += 1
        except Exception as exc:
            set_job_status(job, "failed", str(exc))
            print(f"failed {job.get('node_path')}: {exc}", file=sys.stderr)
    save_job_ledger(root, "curator", jobs)
    append_log(root, f"Exported {written} resumable curator job task(s).")
    append_build_run(root, {"event": "export-curator", "written": written, "batch_size": args.batch_size})
    return 0 if written or not selected else 1


def command_build_jobs_apply_curator(args: argparse.Namespace) -> int:
    root = Path(args.vault).resolve()
    init_vault(root)
    jobs = refresh_curator_jobs(root, max_papers=args.max_papers)
    candidates = curator_jobs_by_status(jobs, {"exported", "running", "result_written"})
    applied = 0
    failed = 0
    changed_count = 0
    for job in candidates:
        result_path = root / as_string(job.get("result_path"))
        if not result_path.exists():
            continue
        try:
            payload = load_curator_payload(result_path)
            payload_changed, messages = apply_curator_payload_actions(root, payload, force=args.force, promote=not args.no_promote)
            changed_count += payload_changed
            for message in messages:
                print(message)
            set_job_status(job, CURATOR_JOB_COMPLETE)
            applied += 1
        except Exception as exc:
            failed += 1
            set_job_status(job, "failed", str(exc))
            print(f"failed {rel_to(result_path, root)}: {exc}", file=sys.stderr)
    save_job_ledger(root, "curator", jobs)
    if changed_count:
        update_index(root)
    append_log(root, f"Applied {applied} resumable curator result(s); {failed} failed.")
    append_build_run(root, {"event": "apply-curator", "applied": applied, "failed": failed})
    return 1 if failed else 0


def command_build_jobs_retry_failed(args: argparse.Namespace) -> int:
    root = Path(args.vault).resolve()
    paper_jobs = refresh_paper_jobs(root)
    curator_jobs = refresh_curator_jobs(root, max_papers=args.max_papers)
    changed = 0
    for kind, jobs in (("paper", paper_jobs), ("curator", curator_jobs)):
        candidates = [job for job in jobs.values() if as_string(job.get("status")) in {"failed", "quality_failed"}]
        candidates = sorted(candidates, key=lambda item: (as_string(item.get("note_path") or item.get("node_path")), as_string(item.get("job_id"))))
        for job in candidates:
            if args.limit and changed >= args.limit:
                break
            attempts, max_attempts = job_attempt_limit(job)
            if attempts >= max_attempts and not args.force:
                continue
            set_job_status(job, "retry_pending")
            changed += 1
            print(f"retry_pending {kind} {job.get('note_path') or job.get('node_path')}")
    save_job_ledger(root, "paper", paper_jobs)
    save_job_ledger(root, "curator", curator_jobs)
    append_build_run(root, {"event": "retry-failed", "changed": changed})
    print(f"marked {changed} job(s) retry_pending")
    return 0


def load_curator_payload(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = parse_json_text(raw)
    if not isinstance(payload, dict):
        raise ValueError("curator result must be a JSON object")
    return payload


def replace_note_body(text: str, body_markdown: str) -> str:
    frontmatter, _body = split_note_text(text)
    body = body_markdown.strip() + "\n"
    if frontmatter:
        return frontmatter + body
    return body


def apply_sections_to_note_text(text: str, sections: dict[str, object], force: bool) -> str:
    updated = text
    for heading, content in sections.items():
        if isinstance(content, list):
            content_text = "\n".join(f"- {as_string(item)}" for item in content if as_string(item))
        else:
            content_text = as_string(content)
        if heading and content_text:
            updated = replace_markdown_section(updated, titleize_slug(str(heading).replace("_", "-")), content_text, force=force)
    return updated


def apply_node_curation(root: Path, payload: dict[str, Any], force: bool, promote: bool) -> tuple[bool, str]:
    node_path = as_string(payload.get("node_path"))
    if not node_path:
        raise ValueError("curator result missing node_path")
    note = find_note_arg(root, node_path)
    if not note:
        raise ValueError(f"cannot find node `{node_path}`")
    if note.note_type == "paper":
        raise ValueError("node curator cannot rewrite paper notes")
    if note_is_researcher_reviewed(note) and not force:
        return False, f"skipped researcher-reviewed {note.rel_path}"
    updated = note.text
    body_value = payload.get("body_markdown")
    body_markdown = body_value if isinstance(body_value, str) else ""
    if body_markdown:
        updated = replace_note_body(updated, body_markdown)
    sections = payload.get("sections")
    if isinstance(sections, dict):
        updated = apply_sections_to_note_text(updated, sections, force=True)
    updates = {
        "updated": yaml_string(today()),
        "curated_by": yaml_string(as_string(payload.get("agent_source")) or NODE_CURATOR_AGENT_NAME),
        "curated_at": yaml_string(utc_timestamp()),
    }
    new_status = as_string(payload.get("new_status"))
    if promote and new_status:
        updates["status"] = new_status
    updated = update_frontmatter_fields(updated, updates)
    if updated != note.text:
        note.path.write_text(updated, encoding="utf-8")
        return True, f"curated {note.rel_path}"
    return False, f"unchanged {note.rel_path}"


def synthesis_path_for_title(root: Path, title: str) -> Path:
    slug = slugify(title, "curator-synthesis")
    path = root / "syntheses" / f"{slug}.md"
    if not path.exists():
        return path
    index = 2
    while True:
        candidate = root / "syntheses" / f"{slug}-{index}.md"
        if not candidate.exists():
            return candidate
        index += 1


def has_strong_synthesis_evidence(item: dict[str, Any]) -> bool:
    strength = as_string(item.get("evidence_strength")).lower()
    if strength in {"strong", "high", "very_high", "very-high"}:
        return True
    papers_used = item.get("papers_used", [])
    used_count = len(papers_used) if isinstance(papers_used, list) else 0
    if used_count >= 3:
        return True
    if used_count >= 2 and bool(item.get("has_contradiction") or item.get("has_complication")):
        return True
    if used_count >= 2 and as_string(item.get("active_node_context")):
        return True
    return False


def create_synthesis_from_payload(root: Path, item: dict[str, Any], force: bool = False) -> tuple[bool, str]:
    if not force and not has_strong_synthesis_evidence(item):
        title = as_string(item.get("title")) or as_string(item.get("topic")) or "curator synthesis"
        return False, f"skipped weak synthesis evidence for {title}"
    title = as_string(item.get("title")) or as_string(item.get("topic")) or "Curator synthesis"
    path_value = as_string(item.get("path"))
    path = root / path_value if path_value else synthesis_path_for_title(root, title)
    if path.exists():
        return False, f"skipped existing synthesis {rel_to(path, root)}"
    body_value = item.get("body_markdown")
    body = body_value if isinstance(body_value, str) else ""
    if not body:
        claims = item.get("claims")
        if isinstance(claims, list):
            body = "\n".join(f"- {as_string(claim)}" for claim in claims if as_string(claim))
    if not body:
        body = "## Claim\n\n- Curator-created synthesis; review source evidence.\n"
    papers_used = item.get("papers_used", [])
    frontmatter = {
        "type": "synthesis",
        "topic": yaml_string(title),
        "status": "active",
        "created_by": yaml_string(NODE_CURATOR_AGENT_NAME),
        "created": yaml_string(today()),
        "updated": yaml_string(today()),
        "source_scope": yaml_json(
            {
                "papers_considered": item.get("papers_considered", len(papers_used) if isinstance(papers_used, list) else 0),
                "papers_used": len(papers_used) if isinstance(papers_used, list) else 0,
                "coverage_limited": bool(item.get("coverage_limited", False)),
            }
        ),
    }
    text = "---\n" + "\n".join(f"{key}: {value}" for key, value in frontmatter.items()) + "\n---\n\n"
    text += f"# {title}\n\n{body.strip()}\n"
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")
    return True, f"created synthesis {rel_to(path, root)}"


def rewrite_wikilinks(text: str, source_rel: str, target_rel: str) -> str:
    source_no_ext = source_rel[:-3] if source_rel.endswith(".md") else source_rel
    target_no_ext = target_rel[:-3] if target_rel.endswith(".md") else target_rel
    source_name = Path(source_no_ext).name

    def repl(match: re.Match[str]) -> str:
        raw = match.group(1)
        target = raw.split("|", 1)[0].split("#", 1)[0].strip()
        suffix = ""
        if "|" in raw:
            suffix = "|" + raw.split("|", 1)[1]
        elif "#" in raw:
            suffix = "#" + raw.split("#", 1)[1]
        normalized = normalize_link_target(target)
        if normalized in {source_no_ext, source_rel, source_name}:
            return "[[" + target_no_ext + suffix + "]]"
        return match.group(0)

    return re.sub(r"\[\[([^\]]+)\]\]", repl, text)


def archive_note_path(root: Path, note: Note) -> Path:
    folder = Path(note.rel_path).parts[0]
    target_dir = root / ARCHIVE_MERGED_DIR / folder
    ensure_dir(target_dir)
    candidate = target_dir / Path(note.rel_path).name
    if not candidate.exists():
        return candidate
    index = 2
    while True:
        alt = target_dir / f"{candidate.stem}-{index}{candidate.suffix}"
        if not alt.exists():
            return alt
        index += 1


def archive_invalid_note_path(root: Path, note: Note) -> Path:
    folder = Path(note.rel_path).parts[0]
    target_dir = root / ARCHIVE_INVALID_DIR / folder
    ensure_dir(target_dir)
    candidate = target_dir / Path(note.rel_path).name
    if not candidate.exists():
        return candidate
    index = 2
    while True:
        alt = target_dir / f"{candidate.stem}-{index}{candidate.suffix}"
        if not alt.exists():
            return alt
        index += 1


def apply_archive_invalid_plan(root: Path, plan: dict[str, Any], force: bool) -> tuple[bool, str]:
    confidence = as_string(plan.get("confidence")).lower()
    if confidence not in {"high", "very_high", "very-high"} and not force:
        return False, "skipped invalid archive without high confidence"
    source_value = as_string(plan.get("source_node") or plan.get("source_path"))
    if not source_value:
        raise ValueError("archive_invalid plan requires source_node")
    source = find_note_arg(root, source_value)
    if not source:
        raise ValueError(f"cannot resolve invalid archive node `{source_value}`")
    if source.note_type == "paper":
        raise ValueError("archive_invalid cannot archive paper notes")
    if note_is_researcher_reviewed(source) and not force:
        return False, f"skipped researcher-reviewed source {source.rel_path}"
    live_refs = inbound_live_links(root, source, load_notes(root))
    if live_refs and not force:
        return False, f"skipped invalid archive with live inbound links: {source.rel_path}"
    archive_path = archive_invalid_note_path(root, source)
    archived_text = update_frontmatter_fields(
        source.path.read_text(encoding="utf-8"),
        {
            "type": "archived_node",
            "archive_reason": yaml_string(as_string(plan.get("reason")) or "invalid_or_stale_candidate"),
            "archived_at": yaml_string(utc_timestamp()),
            "archived_by": yaml_string(NODE_CURATOR_AGENT_NAME),
            "original_type": source.note_type or "note",
        },
    )
    archive_path.write_text(archived_text, encoding="utf-8")
    source.path.unlink()
    append_log(root, f"Archived invalid/stale node `{source.rel_path}` at `{rel_to(archive_path, root)}`.")
    return True, f"archived invalid {source.rel_path}; moved to {rel_to(archive_path, root)}"


def apply_merge_plan(root: Path, plan: dict[str, Any], force: bool) -> tuple[bool, str]:
    confidence = as_string(plan.get("confidence")).lower()
    if confidence not in {"high", "very_high", "very-high"} and not force:
        return False, "skipped merge without high confidence"
    source_value = as_string(plan.get("source_node") or plan.get("source_path"))
    target_value = as_string(plan.get("target_node") or plan.get("target_path") or plan.get("merged_into"))
    if not source_value or not target_value:
        raise ValueError("merge plan requires source_node and target_node")
    source = find_note_arg(root, source_value)
    target = find_note_arg(root, target_value)
    if not source or not target:
        raise ValueError(f"cannot resolve merge nodes `{source_value}` -> `{target_value}`")
    if note_is_researcher_reviewed(source) and not force:
        return False, f"skipped researcher-reviewed source {source.rel_path}"
    if source.note_type == "paper" or target.note_type == "paper":
        same_hash = str(source.frontmatter.get("pdf_sha256", "")).strip() and source.frontmatter.get("pdf_sha256") == target.frontmatter.get("pdf_sha256")
        same_doi = str(source.frontmatter.get("doi", "")).strip().lower() and str(source.frontmatter.get("doi", "")).strip().lower() == str(target.frontmatter.get("doi", "")).strip().lower()
        source_authors = frontmatter_list(source.frontmatter.get("authors"))
        target_authors = frontmatter_list(target.frontmatter.get("authors"))
        same_first_author = bool(source_authors and target_authors and slugify(source_authors[0]) == slugify(target_authors[0]))
        same_title_author_year = slugify(source.title) == slugify(target.title) and same_first_author and str(source.frontmatter.get("year", "")) == str(target.frontmatter.get("year", ""))
        if not (same_hash or same_doi or same_title_author_year or force):
            return False, f"skipped paper merge without strong identity evidence: {source.rel_path}"
    source_no_ext = source.rel_path[:-3] if source.rel_path.endswith(".md") else source.rel_path
    target_no_ext = target.rel_path[:-3] if target.rel_path.endswith(".md") else target.rel_path
    changed = False
    for note in load_notes(root):
        if note.rel_path == source.rel_path:
            continue
        rewritten = rewrite_wikilinks(note.text, source.rel_path, target.rel_path)
        if rewritten != note.text:
            note.path.write_text(rewritten, encoding="utf-8")
            changed = True
    target_text = target.path.read_text(encoding="utf-8")
    if f"[[{source_no_ext}]]" not in target_text and f"[[{target_no_ext}]]" not in source.text:
        target_text = target_text.rstrip() + f"\n\n## Merged Notes\n\n- Merged from `{source.rel_path}` on {today()}; archived under `{ARCHIVE_MERGED_DIR}/`.\n"
        target.path.write_text(target_text, encoding="utf-8")
        changed = True
    archive_path = archive_note_path(root, source)
    archived_text = update_frontmatter_fields(
        source.path.read_text(encoding="utf-8"),
        {
            "type": "archived_paper" if source.note_type == "paper" else "archived_node",
            "archive_reason": "merged_duplicate",
            "merged_into": yaml_string(target.rel_path),
            "merged_at": yaml_string(utc_timestamp()),
            "merged_by": yaml_string(NODE_CURATOR_AGENT_NAME),
            "original_type": source.note_type or "note",
        },
    )
    archive_path.write_text(archived_text, encoding="utf-8")
    source.path.unlink()
    append_log(root, f"Merged `{source.rel_path}` into `{target.rel_path}` and archived old note at `{rel_to(archive_path, root)}`.")
    return True, f"merged {source.rel_path} -> {target.rel_path}; archived {rel_to(archive_path, root)}"


def apply_curator_payload_actions(root: Path, payload: dict[str, Any], force: bool, promote: bool) -> tuple[int, list[str]]:
    changed_count = 0
    messages: list[str] = []
    action = as_string(payload.get("action")) or "populate"
    if action in {"populate", "update", "update_node", "curate_node"}:
        changed, message = apply_node_curation(root, payload, force=force, promote=promote)
        messages.append(message)
        changed_count += int(changed)
        synthesis_items = payload.get("synthesis_notes")
        if isinstance(synthesis_items, list):
            for item in synthesis_items:
                if isinstance(item, dict):
                    changed, message = create_synthesis_from_payload(root, item, force=force)
                    messages.append(message)
                    changed_count += int(changed)
        merge_items = payload.get("merge_plans")
        if isinstance(merge_items, list):
            for item in merge_items:
                if isinstance(item, dict):
                    action_value = as_string(item.get("action")).lower()
                    if action_value == "archive_invalid":
                        changed, message = apply_archive_invalid_plan(root, item, force=force)
                    else:
                        changed, message = apply_merge_plan(root, item, force=force)
                    messages.append(message)
                    changed_count += int(changed)
    elif action in {"create_synthesis", "create_syntheses"}:
        items = payload.get("synthesis_notes")
        if not isinstance(items, list):
            items = [payload]
        for item in items:
            if isinstance(item, dict):
                changed, message = create_synthesis_from_payload(root, item, force=force)
                messages.append(message)
                changed_count += int(changed)
    elif action in {"merge_nodes", "merge"}:
        plans = payload.get("merge_plans")
        if not isinstance(plans, list):
            plans = [payload]
        for plan in plans:
            if isinstance(plan, dict):
                changed, message = apply_merge_plan(root, plan, force=force)
                messages.append(message)
                changed_count += int(changed)
    elif action in {"archive_invalid", "archive_stale"}:
        changed, message = apply_archive_invalid_plan(root, payload, force=force)
        messages.append(message)
        changed_count += int(changed)
    else:
        raise ValueError(f"unknown curator action `{action}`")
    return changed_count, messages


def command_apply_curation(args: argparse.Namespace) -> int:
    root = Path(args.vault).resolve()
    changed_count = 0
    had_error = False
    messages: list[str] = []
    for input_value in args.input:
        path = Path(input_value)
        if not path.is_absolute():
            path = root / path
        try:
            payload = load_curator_payload(path)
            payload_changed, payload_messages = apply_curator_payload_actions(root, payload, force=args.force, promote=not args.no_promote)
            messages.extend(payload_messages)
            changed_count += payload_changed
        except Exception as exc:
            had_error = True
            messages.append(f"failed {rel_to(path, root)}: {exc}")
    for message in messages:
        print(message)
    if changed_count:
        update_index(root)
        append_log(root, f"Applied {changed_count} curator change(s).")
    return 1 if had_error else 0


def command_init(args: argparse.Namespace) -> int:
    root = Path(args.vault).resolve()
    changed = init_vault(root, force=args.force)
    update_index(root)
    if changed:
        append_log(root, "Initialized or refreshed KB vault scaffold.")
    for item in changed:
        print(item)
    if not changed:
        print("Vault scaffold already present.")
    return 0


def command_index(args: argparse.Namespace) -> int:
    root = Path(args.vault).resolve()
    init_vault(root)
    update_index(root)
    print("refreshed index.md")
    print(f"refreshed {MACHINE_INDEX}")
    return 0


def normalize_link_target(target: str) -> str:
    target = target.split("|", 1)[0].split("#", 1)[0].strip()
    if target.endswith(".md"):
        target = target[:-3]
    return target.strip("/")


def build_note_indexes(notes: list[Note]) -> tuple[dict[str, Note], dict[str, Note]]:
    by_rel: dict[str, Note] = {}
    by_name: dict[str, Note] = {}
    for note in notes:
        rel = note.rel_path[:-3] if note.rel_path.endswith(".md") else note.rel_path
        by_rel[rel.lower()] = note
        by_rel[note.rel_path.lower()] = note
        by_name[Path(rel).name.lower()] = note
        by_name[slugify(note.title).lower()] = note
        for alias in note.aliases:
            by_name[slugify(alias).lower()] = note
    return by_rel, by_name


def resolve_link(target: str, notes: list[Note]) -> Note | None:
    by_rel, by_name = build_note_indexes(notes)
    clean = normalize_link_target(target)
    if clean.lower() in by_rel:
        return by_rel[clean.lower()]
    slug = slugify(clean)
    if slug.lower() in by_name:
        return by_name[slug.lower()]
    return None


def tokens(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}|\d{4}|10\.\d{4,9}/[-._;()/:A-Z0-9]+", text.lower())
    return [word for word in words if word not in STOPWORDS]


def token_score(needles: list[str], haystack: str) -> float:
    hay = haystack.lower()
    score = 0.0
    for token in needles:
        if token in hay:
            score += 1.0
    return score


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value not in seen:
            unique.append(value)
            seen.add(value)
    return unique


def note_link(note: Note) -> str:
    rel = note.rel_path[:-3] if note.rel_path.endswith(".md") else note.rel_path
    return f"[[{rel}]]"


def relation_target_links(edge: Edge) -> list[str]:
    return wikilinks(edge.target)


def query_vault(root: Path, query: str, mode: str, limit: int) -> str:
    notes = load_notes(root)
    q_tokens = tokens(query)
    if not q_tokens:
        q_tokens = [query.lower()]

    matched_nodes: list[tuple[float, Note]] = []
    for note in notes:
        if note.note_type == "paper":
            continue
        node_body = re.sub(r"\[\[[^\]]+\]\]", "", note.body)
        node_body = re.sub(r"^##\s+Key Papers\s*$.*?(?=^##\s+|\Z)", "", node_body, flags=re.S | re.M)
        haystack = " ".join([Path(note.rel_path).stem, note.title, " ".join(note.aliases), node_body])
        score = token_score(q_tokens, haystack)
        if score:
            if any(token in slugify(note.title) for token in q_tokens):
                score += 2
            matched_nodes.append((score, note))
    matched_nodes.sort(key=lambda item: item[0], reverse=True)
    matched_node_set = {note.rel_path for _, note in matched_nodes[:12]}

    backlinks: dict[str, list[Note]] = {}
    for note in notes:
        for link in note.links:
            resolved = resolve_link(link, notes)
            if resolved:
                backlinks.setdefault(resolved.rel_path, []).append(note)

    results: list[tuple[float, Note, list[str], list[str]]] = []
    for note in notes:
        if note.note_type != "paper":
            continue
        score = 0.0
        reasons: list[str] = []
        paths: list[str] = []
        edge_text_matches: set[str] = set()
        typed_node_matches: set[str] = set()
        plain_node_matches: set[str] = set()
        direct = min(token_score(q_tokens, " ".join([note.title, note.body])), 6.0)
        if direct:
            score += direct
            reasons.append(f"keyword overlap ({direct:.0f} terms)")
            paths.append(f"query -> keyword match -> {note_link(note)}")
        if str(note.frontmatter.get("review_state", "")) == "researcher_reviewed":
            score += 1.0
            reasons.append("researcher-reviewed note")
        if any(edge.relation == "evidence" and edge.target for edge in note.edges):
            score += 0.5
            reasons.append("has explicit evidence lines")
        for edge in note.edges:
            if edge.relation not in QUERY_RELATIONS:
                continue
            target_text = edge.target
            edge_score = token_score(q_tokens, target_text)
            edge_key = f"{edge.relation}:{target_text}"
            if edge_score and edge_key not in edge_text_matches:
                score += min(1.5 + edge_score, 4.0)
                edge_text_matches.add(edge_key)
                reasons.append(f"{edge.relation}:: matches query")
                paths.append(f"query -> {edge.relation}:: {target_text} -> {note_link(note)}")
            for link in relation_target_links(edge):
                resolved = resolve_link(link, notes)
                if resolved and resolved.rel_path in matched_node_set and resolved.rel_path not in typed_node_matches:
                    score += 8.0
                    typed_node_matches.add(resolved.rel_path)
                    reasons.append(f"typed edge to matched node {note_link(resolved)}")
                    paths.append(f"query -> {note_link(resolved)} <- {edge.relation}:: {note_link(note)}")
        for link in note.links:
            resolved = resolve_link(link, notes)
            if (
                resolved
                and resolved.rel_path in matched_node_set
                and resolved.rel_path not in typed_node_matches
                and resolved.rel_path not in plain_node_matches
            ):
                score += 2.0
                plain_node_matches.add(resolved.rel_path)
                reasons.append(f"links to matched node {note_link(resolved)}")
                paths.append(f"query -> {note_link(resolved)} <- link <- {note_link(note)}")
        if typed_node_matches:
            score += min(len(typed_node_matches), 4) * 1.5
        if "#candidate" in note.text or "uncertainty::" in note.text:
            score -= 0.5
        if score > 0:
            results.append((score, note, unique_preserve_order(reasons), unique_preserve_order(paths)))

    results.sort(key=lambda item: item[0], reverse=True)
    results = results[:limit]

    heading = {
        "idea": "Idea to Papers and Directions",
        "draft": "Draft to Supporting Citations",
        "question": "Question to Relevant Papers",
    }.get(mode, "KB Query")
    lines = [f"## {heading}", "", f"**Query:** {query}", ""]
    if matched_nodes:
        lines += ["## Interpreted KB Nodes", ""]
        for score, note in matched_nodes[:8]:
            lines.append(f"- {note_link(note)} ({note.note_type or 'note'}, score {score:.1f})")
        lines.append("")

    if results:
        lines += ["## Relevant Papers in the KB", ""]
        for score, note, reasons, paths in results:
            title = note.title or note.rel_path
            year = str(note.frontmatter.get("year", "")).strip()
            label = f"{title} ({year})" if year else title
            lines.append(f"- {note_link(note)} - {label}; score {score:.1f}.")
            if paper_quality_state(note) == "failed":
                lines.append("  - Quality: failed automatic quality guard; load full extracted/source text before using this paper as evidence.")
            if reasons:
                lines.append(f"  - Why: {'; '.join(reasons[:4])}.")
            if paths:
                best_path = next((path for path in paths if "<-" in path or "::" in path), paths[0])
                lines.append(f"  - Evidence path: {best_path}")
        lines.append("")
    else:
        lines += ["## Relevant Papers in the KB", "", "- No matching paper notes found in the current vault.", ""]

    if mode == "draft":
        lines += [
            "## Claims Needing More Support",
            "",
            "- Treat any claim without a listed paper above as unsupported by the current curated KB.",
            "",
        ]
    else:
        lines += [
            "## Possible Directions",
            "",
            "- Build from papers with explicit `finding::` and `evidence::` lines first.",
            "- Create or update synthesis notes when several papers cluster around the same concept, variable, method, or community.",
            "",
        ]

    lines += [
        "## Gaps in Current KB",
        "",
        "- Missing results may mean the vault has not processed relevant PDFs yet, not that the literature is empty.",
        "- Prefer adding researcher-selected PDFs to `raw/papers/` before relying on external discovery.",
        "",
    ]
    return "\n".join(lines)


def save_query_note(root: Path, output: str, query: str, save_path: str) -> str:
    target = root / save_path
    if target.suffix != ".md":
        target = target.with_suffix(".md")
    ensure_dir(target.parent)
    if target.exists():
        stem = target.stem
        index = 2
        while target.exists():
            target = target.with_name(f"{stem}-{index}.md")
            index += 1
    note_type = "synthesis" if "synthes" in target.parts else "research_question"
    frontmatter = [
        "---",
        f"type: {note_type}",
        f"status: {'working' if note_type == 'synthesis' else 'active'}",
        f"created_from: {yaml_string('query')}",
        f"created: {yaml_string(today())}",
        f"updated: {yaml_string(today())}",
        "---",
        "",
        f"# {query[:80].strip() or titleize_slug(target.stem)}",
        "",
    ]
    target.write_text("\n".join(frontmatter) + output, encoding="utf-8")
    append_log(root, f"Saved query result to `{rel_to(target, root)}`.")
    return rel_to(target, root)


def command_query(args: argparse.Namespace) -> int:
    root = Path(args.vault).resolve()
    output = query_vault(root, args.query, args.mode, args.limit)
    print(output)
    if args.save:
        saved = save_query_note(root, output, args.query, args.save)
        update_index(root)
        print(f"\nSaved to {saved}")
    return 0


def section_body(body: str, heading: str) -> str:
    pattern = r"^##\s+" + re.escape(heading) + r"\s*$"
    match = re.search(pattern, body, re.M)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^##\s+", body[start:], re.M)
    end = start + next_match.start() if next_match else len(body)
    return body[start:end].strip()


def issue(severity: str, code: str, path: str, message: str, fix: str = "") -> Issue:
    return Issue(severity=severity, code=code, path=path, message=message, fix=fix)


def lint_vault(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    for folder in REQUIRED_DIRS:
        if not (root / folder).exists():
            issues.append(issue("error", "missing-dir", folder, "Required folder is missing.", "Run `kb.py init` or `kb.py lint --fix`."))
    for rel in ["index.md", "log.md", "AGENTS.md", MACHINE_CONFIG, MACHINE_INDEX]:
        if not (root / rel).exists():
            severity = "warn" if rel == MACHINE_INDEX else "error"
            fix = "Run `kb.py index` or `kb.py lint --fix`." if rel == MACHINE_INDEX else "Run `kb.py init` or `kb.py lint --fix`."
            issues.append(issue(severity, "missing-file", rel, "Required scaffold file is missing.", fix))

    notes = load_notes(root)
    notes_by_hash: dict[str, list[Note]] = {}
    notes_by_doi: dict[str, list[Note]] = {}
    notes_by_title: dict[str, list[Note]] = {}
    paper_hashes = existing_hashes(notes)

    for pdf in sorted((root / "raw" / "papers").glob("*.pdf")):
        try:
            sha = sha256_file(pdf)
        except OSError as exc:
            issues.append(issue("error", "pdf-read-failed", rel_to(pdf, root), str(exc)))
            continue
        if sha.lower() not in paper_hashes:
            issues.append(issue("warn", "unprocessed-pdf", rel_to(pdf, root), "PDF has no paper note with the same sha256.", "Run `kb.py process`."))

    incoming: dict[str, int] = {note.rel_path: 0 for note in notes}
    inbound_papers_by_node: dict[str, set[str]] = {note.rel_path: set() for note in notes if note.note_type != "paper"}
    for note in notes:
        for link in note.links:
            if normalize_link_target(link).startswith("archive/"):
                issues.append(issue("warn", "live-link-to-archive", note.rel_path, f"Live note links to archived note [[{link}]].", "Rewrite the link to the active merged note."))
            resolved = resolve_link(link, notes)
            if resolved:
                incoming[resolved.rel_path] = incoming.get(resolved.rel_path, 0) + 1
                if note.note_type == "paper" and curator_eligible_paper(note) and resolved.note_type != "paper":
                    inbound_papers_by_node.setdefault(resolved.rel_path, set()).add(note.rel_path)
            else:
                issues.append(issue("warn", "broken-wikilink", note.rel_path, f"Cannot resolve wikilink [[{link}]].", "Create a candidate note or fix the link path."))
        if note.note_type == "paper" and curator_eligible_paper(note):
            for edge in note.edges:
                if edge.relation not in QUERY_RELATIONS:
                    continue
                for link in relation_target_links(edge):
                    resolved = resolve_link(link, notes)
                    if resolved and resolved.note_type != "paper":
                        inbound_papers_by_node.setdefault(resolved.rel_path, set()).add(note.rel_path)

    for note in notes:
        if not note.note_type and note.path.name not in {"README.md", "AGENTS.md", "index.md", "log.md"}:
            issues.append(issue("warn", "missing-type", note.rel_path, "Note has no frontmatter `type`."))
        if note.note_type == "paper":
            raw_pdf_path = str(note.frontmatter.get("raw_pdf_path", "")).strip()
            pdf_sha = str(note.frontmatter.get("pdf_sha256", "")).strip()
            title = str(note.frontmatter.get("title", "")).strip()
            doi = str(note.frontmatter.get("doi", "")).strip().lower()
            if not raw_pdf_path:
                issues.append(issue("error", "missing-raw-pdf-path", note.rel_path, "Paper note is missing `raw_pdf_path`."))
            elif not (root / raw_pdf_path).exists():
                issues.append(issue("warn", "missing-raw-pdf-file", note.rel_path, f"`raw_pdf_path` does not exist: {raw_pdf_path}."))
            if not pdf_sha:
                issues.append(issue("error", "missing-pdf-sha256", note.rel_path, "Paper note is missing `pdf_sha256`."))
            elif not re.fullmatch(r"[a-fA-F0-9]{64}", pdf_sha):
                issues.append(issue("error", "invalid-pdf-sha256", note.rel_path, "`pdf_sha256` is not a 64-character hex digest."))
            elif raw_pdf_path and (root / raw_pdf_path).exists():
                actual = sha256_file(root / raw_pdf_path)
                if actual.lower() != pdf_sha.lower():
                    issues.append(issue("error", "pdf-hash-mismatch", note.rel_path, "Stored `pdf_sha256` does not match the PDF file."))
            if not title:
                issues.append(issue("warn", "missing-title", note.rel_path, "Paper note is missing `title`."))
            if not str(note.frontmatter.get("year", "")).strip():
                issues.append(issue("warn", "missing-year", note.rel_path, "Paper note is missing `year`."))
            authors = note.frontmatter.get("authors", [])
            if authors in ("", [], None):
                issues.append(issue("warn", "missing-authors", note.rel_path, "Paper note is missing `authors`."))
            summary = section_body(note.body, "One-Paragraph Summary")
            if not summary or summary.lower().startswith("needs researcher"):
                issues.append(issue("warn", "missing-summary", note.rel_path, "Paper note still needs a substantive summary."))
            useful_edges = [
                edge
                for edge in note.edges
                if edge.relation in {"studies_variable", "uses_method", "measured_by", "samples_community", "tests_social_factor"}
                and "[[" in edge.target
            ]
            if not useful_edges:
                issues.append(issue("warn", "missing-graph-links", note.rel_path, "Paper note has no typed links to concepts, variables, methods, or communities."))
            empty_edges = [edge for edge in note.edges if edge.relation in RELATIONS and not edge.target]
            if empty_edges:
                relations = ", ".join(sorted({edge.relation for edge in empty_edges}))
                issues.append(issue("info", "empty-relations", note.rel_path, f"{len(empty_edges)} empty relation placeholders remain: {relations}."))
            if pdf_sha:
                notes_by_hash.setdefault(pdf_sha.lower(), []).append(note)
            if doi:
                notes_by_doi.setdefault(doi, []).append(note)
            if title:
                notes_by_title.setdefault(slugify(title), []).append(note)
        elif note.note_type in {"author", "concept", "variable", "method", "community"}:
            outgoing_to_papers = 0
            for link in note.links:
                resolved = resolve_link(link, notes)
                if resolved and resolved.note_type == "paper":
                    outgoing_to_papers += 1
            if incoming.get(note.rel_path, 0) == 0 and outgoing_to_papers == 0:
                issues.append(issue("info", "orphan-node", note.rel_path, "Node has no backlinks and no paper links."))
            inbound_papers = inbound_papers_by_node.get(note.rel_path, set())
            if inbound_papers:
                key_papers_heading = "Papers" if note.note_type == "author" else "Key Papers"
                key_papers = section_body(note.body, key_papers_heading)
                missing = []
                for paper_path in sorted(inbound_papers):
                    target = f"[[{paper_path[:-3] if paper_path.endswith('.md') else paper_path}]]"
                    if target not in key_papers:
                        missing.append(paper_path)
                if missing:
                    issues.append(issue("warn", "stale-key-papers", note.rel_path, f"{key_papers_heading} is missing {len(missing)} inbound quality-passed paper(s): {', '.join(missing[:5])}.", f"Run build-jobs export-curator and build-jobs apply-curator, or update {key_papers_heading} manually."))
        elif note.note_type == "synthesis":
            paper_links = 0
            for link in note.links:
                resolved = resolve_link(link, notes)
                if resolved and resolved.note_type == "paper":
                    paper_links += 1
            if paper_links == 0:
                issues.append(issue("warn", "synthesis-without-papers", note.rel_path, "Synthesis note does not link to any paper notes."))

    for code, mapping in {
        "duplicate-pdf-hash": notes_by_hash,
        "duplicate-doi": notes_by_doi,
        "duplicate-title": notes_by_title,
    }.items():
        for key, grouped in mapping.items():
            if key and len(grouped) > 1:
                paths = ", ".join(note.rel_path for note in grouped)
                issues.append(issue("error", code, paths, f"Duplicate paper identity: {key}."))

    return issues


def candidate_note_for_link(root: Path, target: str) -> Path | None:
    clean = normalize_link_target(target)
    if not clean or clean.startswith(("http:", "https:")):
        return None
    path = root / f"{clean}.md"
    parts = path.relative_to(root).parts if path.is_relative_to(root) else ()
    if not parts or parts[0] not in set(NODE_FOLDERS.values()):
        return None
    return path


def create_candidate_note(path: Path, root: Path) -> bool:
    if path.exists():
        return False
    folder = path.relative_to(root).parts[0]
    note_type = {value: key for key, value in NODE_FOLDERS.items()}.get(folder, "concept")
    title = titleize_slug(path.stem)
    template_name = {
        "paper": "paper.md",
        "author": "author.md",
        "concept": "concept.md",
        "variable": "variable.md",
        "method": "method.md",
        "community": "community.md",
        "research_question": "research-question.md",
        "synthesis": "synthesis.md",
    }[note_type]
    values = {
        "title": title,
        "date": today(),
        "paper_id": path.stem,
        "raw_pdf_path": "",
        "pdf_sha256": "",
        "authors": "[]",
        "author_links": "- authored_by::",
        "year": "",
        "doi": "",
        "publication": "",
    }
    content = render_template(template_name, values, root=root)
    content = re.sub(r"status: working", "status: candidate", content)
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")
    return True


def add_key_paper_link(path: Path, paper_note: Note) -> bool:
    if not path.exists():
        return False
    paper_target = note_link(paper_note)
    text = path.read_text(encoding="utf-8")
    if paper_target in text:
        return False
    if re.search(r"^##\s+Key Papers\s*$", text, re.M):
        text = re.sub(r"(^##\s+Key Papers\s*$)", rf"\1\n\n- {paper_target}", text, count=1, flags=re.M)
    else:
        text = text.rstrip() + f"\n\n## Key Papers\n\n- {paper_target}\n"
    path.write_text(text, encoding="utf-8")
    return True


def create_candidate_notes_from_text(root: Path, text: str, paper_note: Note) -> int:
    notes = load_notes(root)
    created_or_updated = 0
    for link in wikilinks(text):
        resolved = resolve_link(link, notes)
        if resolved:
            if resolved.note_type in {"author", "concept", "variable", "method", "community"} and add_key_paper_link(resolved.path, paper_note):
                created_or_updated += 1
            continue
        target = candidate_note_for_link(root, link)
        if not target:
            continue
        folder = target.relative_to(root).parts[0]
        if folder not in {"authors", "concepts", "variables", "methods", "communities"}:
            continue
        changed = create_candidate_note(target, root)
        if changed:
            created_or_updated += 1
            notes = load_notes(root)
        if add_key_paper_link(target, paper_note):
            created_or_updated += 1
    return created_or_updated


def apply_safe_fixes(root: Path, create_missing_linked_notes: bool) -> list[str]:
    changed = init_vault(root)
    if create_missing_linked_notes:
        notes = load_notes(root)
        for note in notes:
            for link in note.links:
                if resolve_link(link, notes):
                    continue
                target = candidate_note_for_link(root, link)
                if target and create_candidate_note(target, root):
                    changed.append(f"created candidate note {rel_to(target, root)}")
    update_index(root)
    if changed:
        append_log(root, "Applied safe KB lint fixes.")
    return changed


def print_issues(issues: list[Issue], as_json: bool) -> None:
    if as_json:
        print(json.dumps([issue.__dict__ for issue in issues], indent=2, ensure_ascii=False))
        return
    if not issues:
        print("No lint issues found.")
        return
    for item in issues:
        fix = f" Fix: {item.fix}" if item.fix else ""
        print(f"[{item.severity}] {item.code}: {item.path} - {item.message}{fix}")


def command_lint(args: argparse.Namespace) -> int:
    root = Path(args.vault).resolve()
    if args.fix:
        changed = apply_safe_fixes(root, args.create_missing_linked_notes)
        for item in changed:
            print(item)
        if not changed:
            print("No safe fixes needed.")
    issues = lint_vault(root)
    print_issues(issues, args.json)
    return 1 if any(item.severity == "error" for item in issues) else 0


def command_review(args: argparse.Namespace) -> int:
    root = Path(args.vault).resolve()
    notes = load_notes(root)
    papers = [
        note
        for note in notes
        if note.note_type == "paper"
        and (
            str(note.frontmatter.get("kb_status", "")) == "needs_review"
            or str(note.frontmatter.get("review_state", "")) in {"agent_draft", "needs_review", "quality_failed"}
        )
    ]
    print("## Review Queue\n")
    if not papers:
        print("- No paper notes currently marked for review.")
        return 0
    for note in papers[: args.limit]:
        uncertain = ""
        match = re.search(r"^- uncertain_fields:\s*(.+)$", note.body, re.M)
        if match:
            uncertain = match.group(1).strip()
        print(f"- {note_link(note)} - {note.title}")
        if uncertain:
            print(f"  - Uncertain fields: {uncertain}")
        print("  - Review: summary, graph links, findings, evidence, useful quotes.")
    if len(papers) > args.limit:
        print(f"\n{len(papers) - args.limit} more notes omitted by --limit.")
    return 0


def reconciliation_summary(root: Path) -> dict[str, Any]:
    summary_path = root / METADATA_RECONCILIATION_DIR / "summary.json"
    if summary_path.exists():
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass
    return {
        "paper_reports": 0,
        "high_confidence_matches": 0,
        "medium_confidence_matches": 0,
        "low_confidence_matches": 0,
        "duplicate_clusters": 0,
        "invalid_candidates": 0,
        "needs_review": 0,
    }


def command_reconcile_metadata(args: argparse.Namespace) -> int:
    root = Path(args.vault).resolve()
    init_vault(root)
    notes = load_notes(root)
    paper_notes = [note for note in notes if note.note_type == "paper"]
    if args.note:
        note = find_note_arg(root, args.note)
        paper_notes = [note] if note and note.note_type == "paper" else []
    if args.limit:
        paper_notes = paper_notes[: args.limit]
    if not paper_notes:
        print("No paper notes found for metadata reconciliation.")
        return 1 if args.note else 0

    paper_match_dir = root / METADATA_RECONCILIATION_DIR / "paper-matches"
    author_match_dir = root / METADATA_RECONCILIATION_DIR / "author-matches"
    ensure_dir(paper_match_dir)
    ensure_dir(author_match_dir)
    reports: list[dict[str, Any]] = []
    applied = 0
    for note in paper_notes:
        report = paper_match_report(root, note, args)
        reports.append(report)
        write_json(paper_match_dir / f"{safe_file_key(Path(note.rel_path).stem)}.json", report)
        print(f"{note.rel_path}: {report['confidence']} metadata match")
        if args.apply and apply_paper_metadata_match(note, report, force=args.force):
            applied += 1

    notes = load_notes(root)
    clusters = duplicate_node_clusters(root, notes)
    invalids = invalid_candidate_reports(root, notes)
    write_reconciliation_clusters(root, clusters, invalids)

    # Author match reports are lightweight hints from high-confidence paper matches.
    for report in reports:
        best = report.get("best_match")
        if not isinstance(best, dict) or report.get("confidence") != "high":
            continue
        authors = [str(item).strip() for item in best.get("authors", []) if str(item).strip()]
        if not authors:
            continue
        payload = {
            "schema_version": 1,
            "generated_at": utc_timestamp(),
            "paper_path": report.get("paper_path"),
            "provider_policy": "author names are metadata reconciliation hints only",
            "authors": [
                {
                    "position": index + 1,
                    "display_name": author,
                    "suggested_slug": slugify(author),
                }
                for index, author in enumerate(authors)
            ],
            "external_ids": best.get("external_ids", {}),
        }
        write_json(author_match_dir / f"{safe_file_key(str(report.get('paper_path', 'paper')))}.json", payload)

    high = sum(1 for report in reports if report.get("confidence") == "high")
    medium = sum(1 for report in reports if report.get("confidence") == "medium")
    low = sum(1 for report in reports if report.get("confidence") == "low")
    needs_review = medium + low + sum(1 for cluster in clusters if cluster.get("confidence") != "high") + sum(1 for item in invalids if item.get("confidence") != "high")
    summary = {
        "schema_version": 1,
        "generated_at": utc_timestamp(),
        "paper_reports": len(reports),
        "high_confidence_matches": high,
        "medium_confidence_matches": medium,
        "low_confidence_matches": low,
        "unmatched": sum(1 for report in reports if report.get("confidence") in {"none", ""}),
        "duplicate_clusters": len(clusters),
        "high_confidence_duplicate_clusters": sum(1 for cluster in clusters if cluster.get("confidence") == "high"),
        "invalid_candidates": len(invalids),
        "high_confidence_invalid_candidates": sum(1 for item in invalids if item.get("confidence") == "high"),
        "metadata_updates_applied": applied,
        "needs_review": needs_review,
        "provider_policy": "metadata only; not KB claim evidence",
    }
    write_json(root / METADATA_RECONCILIATION_DIR / "summary.json", summary)
    append_log(root, f"Reconciled metadata for {len(reports)} paper note(s); found {len(clusters)} duplicate cluster(s) and {len(invalids)} invalid/stale candidate(s).")
    if args.apply and applied:
        update_index(root)
    print(f"Duplicate clusters: {len(clusters)}")
    print(f"Invalid/stale candidates: {len(invalids)}")
    if applied:
        print(f"Applied high-confidence metadata updates: {applied}")
    return 0


def build_report(root: Path) -> dict[str, Any]:
    notes = load_notes(root)
    papers = [note for note in notes if note.note_type == "paper"]
    quality_failed = [note for note in papers if paper_quality_state(note) == "failed"]
    quality_passed = [note for note in papers if paper_quality_state(note) == "passed"]
    curated_nodes = [note for note in notes if note.note_type != "paper" and str(note.frontmatter.get("curated_by", "")).strip()]
    curator_syntheses = [
        note
        for note in notes
        if note.note_type == "synthesis" and str(note.frontmatter.get("created_by", "")).strip() == NODE_CURATOR_AGENT_NAME
    ]
    archived = sorted(rel_to(path, root) for path in (root / ARCHIVE_MERGED_DIR).rglob("*.md")) if (root / ARCHIVE_MERGED_DIR).exists() else []
    archived_invalid = sorted(rel_to(path, root) for path in (root / ARCHIVE_INVALID_DIR).rglob("*.md")) if (root / ARCHIVE_INVALID_DIR).exists() else []
    issues = lint_vault(root)
    metadata = reconciliation_summary(root)
    paper_job_ledger = load_job_ledger(root, "paper")
    curator_job_ledger = load_job_ledger(root, "curator")
    paper_jobs = summarize_jobs(paper_job_ledger)
    curator_jobs = summarize_jobs(curator_job_ledger)
    job_failures = job_failure_records("paper", paper_job_ledger) + job_failure_records("curator", curator_job_ledger)
    exceptions_by_identity: dict[str, dict[str, Any]] = {}

    def add_exception(kind: str, path: str, status: str, detail: str = "", job_id: str = "", retryable: bool | None = None) -> None:
        identity = f"{kind}:{path or job_id}"
        entry = exceptions_by_identity.setdefault(
            identity,
            {"identity": identity, "kind": kind, "path": path, "job_ids": [], "statuses": [], "details": [], "retryable": False},
        )
        if job_id and job_id not in entry["job_ids"]:
            entry["job_ids"].append(job_id)
        if status and status not in entry["statuses"]:
            entry["statuses"].append(status)
        if detail and detail not in entry["details"]:
            entry["details"].append(detail)
        if retryable is True:
            entry["retryable"] = True

    for note in papers:
        review_state = str(note.frontmatter.get("review_state", ""))
        quality = paper_quality_state(note)
        if review_state in {"needs_review", "agent_draft", "quality_failed"}:
            add_exception("paper", note.rel_path, review_state)
        if quality == "failed":
            quality_data = kb_build_data(note).get("quality")
            failed_checks = as_string_list(quality_data.get("failed_checks")) if isinstance(quality_data, dict) else []
            add_exception("paper", note.rel_path, "quality_failed", "; ".join(failed_checks))
    for failure in job_failures:
        detail = as_string(failure["last_error"])
        attempt_detail = f"attempt {failure['attempts']}/{failure['max_attempts']}"
        add_exception(
            str(failure["kind"]),
            str(failure["path"]),
            str(failure["status"]),
            "; ".join(part for part in [attempt_detail, detail] if part),
            str(failure["job_id"]),
            bool(failure["retryable"]),
        )
    attention_notes = sorted(exceptions_by_identity.values(), key=lambda item: (str(item["kind"]), str(item["path"]), str(item["identity"])))
    retryable_failures = [record for record in job_failures if record["retryable"]]
    terminal_failures = [record for record in job_failures if not record["retryable"]]
    passed_for_audit = [note for note in papers if paper_quality_state(note) == "passed"]
    audit_sample = sorted(
        passed_for_audit,
        key=lambda note: hashlib.sha256(
            str(note.frontmatter.get("pdf_sha256", "") or note.rel_path).encode("utf-8")
        ).hexdigest(),
    )[: min(8, len(passed_for_audit))]
    paper_job_blockers = sum(value for status, value in paper_jobs.items() if status in WORK_IN_PROGRESS_JOB_STATUSES)
    curator_job_blockers = sum(value for status, value in curator_jobs.items() if status in WORK_IN_PROGRESS_JOB_STATUSES)
    if paper_job_blockers or curator_job_blockers or retryable_failures or any(item.severity == "error" for item in issues):
        workflow_state = "build_incomplete"
    elif terminal_failures or attention_notes:
        workflow_state = "researcher_attention_needed"
    else:
        workflow_state = "ready_for_researcher_spot_check"
    return {
        "schema_version": 1,
        "generated_at": utc_timestamp(),
        "processed_paper_notes": len(papers),
        "quality_passed": len(quality_passed),
        "quality_failed": len(quality_failed),
        "quality_failed_notes": [note.rel_path for note in quality_failed],
        "curated_nodes": len(curated_nodes),
        "curated_node_paths": [note.rel_path for note in curated_nodes],
        "curator_created_syntheses": len(curator_syntheses),
        "curator_created_synthesis_paths": [note.rel_path for note in curator_syntheses],
        "archived_notes": len(archived),
        "archived_note_paths": archived,
        "archived_invalid_notes": len(archived_invalid),
        "archived_invalid_note_paths": archived_invalid,
        "metadata_reconciliation": metadata,
        "paper_jobs": paper_jobs,
        "curator_jobs": curator_jobs,
        "retryable_failures": retryable_failures,
        "terminal_exceptions": terminal_failures,
        "next_job_command": next_job_command(paper_job_ledger, curator_job_ledger),
        "workflow_state": workflow_state,
        "researcher_spot_check": [note.rel_path for note in audit_sample],
        "researcher_spot_check_guidance": "Read this small, deterministic sample of quality-passed notes and inspect the cited anchors in their PDFs; use the exception list for anything else.",
        "lint_errors": sum(1 for item in issues if item.severity == "error"),
        "lint_warnings": sum(1 for item in issues if item.severity == "warn"),
        "needs_user_review": attention_notes,
    }


def command_build_report(args: argparse.Namespace) -> int:
    root = Path(args.vault).resolve()
    report = build_report(root)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
        return 0
    print("## Research KB Build Report\n")
    print(f"- Processed paper notes: {report['processed_paper_notes']}")
    print(f"- Quality passed: {report['quality_passed']}")
    print(f"- Quality failed: {report['quality_failed']}")
    print(f"- Curated nodes: {report['curated_nodes']}")
    print(f"- Curator-created synthesis notes: {report['curator_created_syntheses']}")
    print(f"- Archived merged notes: {report['archived_notes']}")
    print(f"- Archived invalid notes: {report['archived_invalid_notes']}")
    metadata = report["metadata_reconciliation"]
    print(f"- Metadata matches: {metadata.get('high_confidence_matches', 0)} high / {metadata.get('medium_confidence_matches', 0) + metadata.get('low_confidence_matches', 0)} review")
    print(f"- Duplicate clusters: {metadata.get('duplicate_clusters', 0)}")
    print(f"- Invalid/stale candidates: {metadata.get('invalid_candidates', 0)}")
    print(f"- Paper jobs: {report['paper_jobs']}")
    print(f"- Curator jobs: {report['curator_jobs']}")
    print(f"- Workflow state: {report['workflow_state']}")
    print(f"- Next job command: {report['next_job_command']}")
    print(f"- Lint errors: {report['lint_errors']}")
    print(f"- Lint warnings: {report['lint_warnings']}")
    if report["retryable_failures"]:
        print(f"\n## Retryable Job Failures ({len(report['retryable_failures'])})\n")
        for item in report["retryable_failures"][:10]:
            location = item["path"] or item["job_id"]
            print(f"- {item['kind']} {location}: {item['status']} ({item['attempts']}/{item['max_attempts']}); {item['last_error'] or 'no error detail recorded'}")
        if len(report["retryable_failures"]) > 10:
            print(f"- … and {len(report['retryable_failures']) - 10} more (see --json for the complete list).")
    if report["needs_user_review"]:
        print(f"\n## Exceptions To Review ({len(report['needs_user_review'])})\n")
        for item in report["needs_user_review"][:10]:
            location = item["path"] or item["identity"]
            statuses = ", ".join(item["statuses"])
            details = "; ".join(item["details"])
            suffix = f"; {details}" if details else ""
            print(f"- {item['kind']} {location}: {statuses}{suffix}")
        if len(report["needs_user_review"]) > 10:
            print(f"- … and {len(report['needs_user_review']) - 10} more (see --json for the complete list).")
    if report["researcher_spot_check"]:
        print("\n## Researcher Spot Check\n")
        print("Read this small sample of quality-passed notes and verify their evidence anchors in the PDFs. You do not need to read every note unless it appears in the exceptions list.")
        for path in report["researcher_spot_check"]:
            print(f"- {path}")
    return 0


def command_new_node(args: argparse.Namespace) -> int:
    root = Path(args.vault).resolve()
    init_vault(root)
    folder = NODE_FOLDERS[args.type]
    slug = slugify(args.slug or args.title)
    path = root / folder / f"{slug}.md"
    if path.exists() and not args.force:
        print(f"exists {rel_to(path, root)}")
        return 0
    template_name = {
        "author": "author.md",
        "concept": "concept.md",
        "variable": "variable.md",
        "method": "method.md",
        "community": "community.md",
        "research_question": "research-question.md",
        "synthesis": "synthesis.md",
    }[args.type]
    content = render_template(
        template_name,
        {
            "title": args.title,
            "date": today(),
            "paper_id": "",
            "raw_pdf_path": "",
            "pdf_sha256": "",
            "authors": "[]",
            "author_links": "- authored_by::",
            "year": "",
            "doi": "",
            "publication": "",
        },
        root=root,
    )
    if args.status:
        content = re.sub(r"status: \w+", f"status: {args.status}", content, count=1)
    write_if_missing(path, content, force=args.force)
    append_log(root, f"Created `{rel_to(path, root)}`.")
    update_index(root)
    print(f"created {rel_to(path, root)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate a local Obsidian research knowledge base.")
    parser.add_argument("--vault", default=".", help="User-selected Obsidian vault root for KB content. Defaults to the current directory.")
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="Create the vault scaffold and templates.")
    init_parser.add_argument("--force", action="store_true", help="Overwrite scaffold files and templates.")
    init_parser.set_defaults(func=command_init)

    index_parser = sub.add_parser("index", help="Refresh the human index and machine index cache.")
    index_parser.set_defaults(func=command_index)

    process_parser = sub.add_parser("process", help="Create paper notes from PDFs in raw/papers/.")
    process_parser.add_argument("--move", action="store_true", help="Move successfully processed PDFs to raw/processed/.")
    process_parser.add_argument("--dry-run", action="store_true", help="Show what would be created without writing notes.")
    process_parser.add_argument("--limit", type=int, default=0, help="Maximum number of PDFs to process.")
    process_parser.set_defaults(func=command_process)

    enrich_parser = sub.add_parser("enrich", help="Fill draft paper-note sections from extracted PDF text.")
    enrich_parser.add_argument("--force", action="store_true", help="Overwrite non-empty sections and reviewed notes.")
    enrich_parser.add_argument("--create-nodes", action="store_true", help="Create or update candidate concept/variable/method/community nodes for inferred links.")
    enrich_parser.add_argument("--limit", type=int, default=0, help="Maximum number of paper notes to enrich.")
    enrich_parser.set_defaults(func=command_enrich)

    agent_context_parser = sub.add_parser("agent-context", help="Export model-agnostic paper-analysis task JSON for an external agent or subagent.")
    agent_context_parser.add_argument("--note", help="Paper note path, stem, or wikilink. Defaults to draft paper notes.")
    agent_context_parser.add_argument("--output-dir", default=f"{MACHINE_DIR}/agent-tasks", help="Vault-relative or absolute directory for task JSON files.")
    agent_context_parser.add_argument("--max-chars", type=int, default=DEFAULT_AGENT_MAX_CHARS, help="Maximum extracted PDF text characters to include. Use 0 for the full retained extracted text.")
    agent_context_parser.add_argument("--limit", type=int, default=0, help="Maximum number of paper tasks to export.")
    agent_context_parser.add_argument("--all", action="store_true", help="Export all paper notes, including notes whose sections are already filled.")
    agent_context_parser.set_defaults(func=command_agent_context)

    apply_analysis_parser = sub.add_parser("apply-analysis", help="Apply model-agnostic paper-analysis JSON returned by an external agent or subagent.")
    apply_analysis_parser.add_argument("input", nargs="+", help="Analysis JSON file(s). Each should include note_path or use --note.")
    apply_analysis_parser.add_argument("--note", help="Paper note path, stem, or wikilink when the JSON file does not include note_path.")
    apply_analysis_parser.add_argument("--force", action="store_true", help="Overwrite non-empty sections and reviewed notes.")
    apply_analysis_parser.add_argument("--create-nodes", action="store_true", help="Create or update candidate concept/variable/method/community nodes for returned links.")
    apply_analysis_parser.set_defaults(func=command_apply_analysis)

    quality_parser = sub.add_parser("quality-guard", help="Check paper notes against extracted source text and record quality state.")
    quality_parser.add_argument("--note", help="Paper note path, stem, or wikilink. Defaults to all paper notes.")
    quality_parser.add_argument("--limit", type=int, default=0, help="Maximum number of paper notes to check.")
    quality_parser.add_argument("--fail-on-quality-failed", action="store_true", help="Return non-zero if any paper fails quality guard.")
    quality_parser.set_defaults(func=command_quality_guard)

    reconcile_parser = sub.add_parser("reconcile-metadata", help="Use Crossref, OpenAlex, and Semantic Scholar for bibliographic reconciliation and duplicate/stale-node reports.")
    reconcile_parser.add_argument("--note", help="Paper note path, stem, or wikilink. Defaults to all paper notes.")
    reconcile_parser.add_argument("--limit", type=int, default=0, help="Maximum number of paper notes to reconcile.")
    reconcile_parser.add_argument("--apply", action="store_true", help="Apply high-confidence paper metadata updates to Markdown frontmatter.")
    reconcile_parser.add_argument("--force", action="store_true", help="Allow metadata updates to reviewed notes when used with --apply.")
    reconcile_parser.add_argument("--refresh", action="store_true", help="Refresh provider calls instead of using cached responses.")
    reconcile_parser.add_argument("--mailto", default="", help="Optional email for Crossref/OpenAlex polite API usage.")
    reconcile_parser.add_argument("--delay", type=float, default=0.15, help="Delay in seconds between provider requests.")
    reconcile_parser.add_argument("--openalex-api-key-env", default="OPENALEX_API_KEY", help="Optional environment variable name for an OpenAlex API key.")
    reconcile_parser.add_argument("--semantic-scholar-api-key-env", default="SEMANTIC_SCHOLAR_API_KEY", help="Optional environment variable name for a Semantic Scholar API key.")
    reconcile_parser.add_argument("--no-crossref", action="store_true", help="Skip Crossref.")
    reconcile_parser.add_argument("--no-openalex", action="store_true", help="Skip OpenAlex.")
    reconcile_parser.add_argument("--no-semantic-scholar", action="store_true", help="Skip Semantic Scholar.")
    reconcile_parser.set_defaults(func=command_reconcile_metadata)

    curator_context_parser = sub.add_parser("curator-context", help="Export node curator task JSON for affected non-paper nodes.")
    curator_context_parser.add_argument("--nodes", nargs="*", help="Specific node paths, stems, or wikilinks. Defaults to all nodes with inbound quality-passed papers.")
    curator_context_parser.add_argument("--mode", choices=["initial-build", "incremental-build"], default="incremental-build")
    curator_context_parser.add_argument("--output-dir", default=CURATOR_TASK_DIR, help="Vault-relative or absolute directory for curator task JSON files.")
    curator_context_parser.add_argument("--max-papers", type=int, default=20, help="Maximum inbound paper evidence packets per curator task.")
    curator_context_parser.add_argument("--limit", type=int, default=0, help="Maximum number of curator tasks to export.")
    curator_context_parser.set_defaults(func=command_curator_context)

    apply_curation_parser = sub.add_parser("apply-curation", help="Apply model-agnostic node curator JSON returned by an external agent or subagent.")
    apply_curation_parser.add_argument("input", nargs="+", help="Curator result JSON file(s).")
    apply_curation_parser.add_argument("--force", action="store_true", help="Allow rewriting researcher-reviewed source nodes and lower-confidence merges.")
    apply_curation_parser.add_argument("--no-promote", action="store_true", help="Do not apply curator-recommended status changes.")
    apply_curation_parser.set_defaults(func=command_apply_curation)

    build_jobs_parser = sub.add_parser("build-jobs", help="Manage resumable quota-safe paper processing and curation jobs.")
    build_jobs_sub = build_jobs_parser.add_subparsers(dest="build_jobs_command", required=True)

    build_jobs_refresh_parser = build_jobs_sub.add_parser("refresh", help="Refresh paper and curator job ledgers from current vault state.")
    build_jobs_refresh_parser.add_argument("--max-papers", type=int, default=20, help="Maximum inbound paper evidence packets used to fingerprint curator jobs.")
    build_jobs_refresh_parser.set_defaults(func=command_build_jobs_refresh)

    build_jobs_status_parser = build_jobs_sub.add_parser("status", help="Show resumable build job status and suggested next command.")
    build_jobs_status_parser.add_argument("--max-papers", type=int, default=20, help="Maximum inbound paper evidence packets used to fingerprint curator jobs.")
    build_jobs_status_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON status.")
    build_jobs_status_parser.set_defaults(func=command_build_jobs_status)

    build_jobs_export_paper_parser = build_jobs_sub.add_parser("export-paper", help="Export the next batch of pending paper-process tasks.")
    build_jobs_export_paper_parser.add_argument("--batch-size", type=int, default=10, help="Maximum number of paper-process tasks to export.")
    build_jobs_export_paper_parser.add_argument("--max-chars", type=int, default=DEFAULT_AGENT_MAX_CHARS, help="Maximum extracted PDF text characters to include. Use 0 for the full retained extracted text.")
    build_jobs_export_paper_parser.set_defaults(func=command_build_jobs_export_paper)

    build_jobs_apply_paper_parser = build_jobs_sub.add_parser("apply-paper", help="Apply completed paper-process results and run quality guard.")
    build_jobs_apply_paper_parser.add_argument("--force", action="store_true", help="Overwrite researcher-reviewed notes when applying analysis.")
    build_jobs_apply_paper_parser.add_argument("--create-nodes", action="store_true", default=True, help="Create or update candidate graph nodes for returned links.")
    build_jobs_apply_paper_parser.add_argument("--no-create-nodes", action="store_false", dest="create_nodes", help="Do not create candidate graph nodes while applying results.")
    build_jobs_apply_paper_parser.set_defaults(func=command_build_jobs_apply_paper)

    build_jobs_export_curator_parser = build_jobs_sub.add_parser("export-curator", help="Export the next batch of pending node-curator tasks.")
    build_jobs_export_curator_parser.add_argument("--batch-size", type=int, default=20, help="Maximum number of curator tasks to export.")
    build_jobs_export_curator_parser.add_argument("--max-papers", type=int, default=20, help="Maximum inbound paper evidence packets per curator task.")
    build_jobs_export_curator_parser.set_defaults(func=command_build_jobs_export_curator)

    build_jobs_apply_curator_parser = build_jobs_sub.add_parser("apply-curator", help="Apply completed curator results.")
    build_jobs_apply_curator_parser.add_argument("--force", action="store_true", help="Allow overwriting researcher-reviewed notes and lower-confidence curator actions.")
    build_jobs_apply_curator_parser.add_argument("--no-promote", action="store_true", help="Do not apply curator-suggested status changes.")
    build_jobs_apply_curator_parser.add_argument("--max-papers", type=int, default=20, help="Maximum inbound paper evidence packets used to fingerprint curator jobs.")
    build_jobs_apply_curator_parser.set_defaults(func=command_build_jobs_apply_curator)

    build_jobs_retry_parser = build_jobs_sub.add_parser("retry-failed", help="Mark failed or quality-failed jobs for manual retry.")
    build_jobs_retry_parser.add_argument("--limit", type=int, default=0, help="Maximum number of failed jobs to mark for retry.")
    build_jobs_retry_parser.add_argument("--force", action="store_true", help="Allow retrying jobs that reached max_attempts.")
    build_jobs_retry_parser.add_argument("--max-papers", type=int, default=20, help="Maximum inbound paper evidence packets used to fingerprint curator jobs.")
    build_jobs_retry_parser.set_defaults(func=command_build_jobs_retry_failed)

    query_parser = sub.add_parser("query", help="Query the Markdown graph and paper notes.")
    query_parser.add_argument("query", help="Idea, draft claim, or research question to search for.")
    query_parser.add_argument("--mode", choices=["idea", "draft", "question"], default="idea")
    query_parser.add_argument("--limit", type=int, default=8)
    query_parser.add_argument("--save", help="Save the answer as a Markdown note, such as questions/my-question.md.")
    query_parser.set_defaults(func=command_query)

    lint_parser = sub.add_parser("lint", help="Review vault health and optionally apply safe fixes.")
    lint_parser.add_argument("--fix", action="store_true", help="Create missing scaffold files and refresh index.")
    lint_parser.add_argument("--create-missing-linked-notes", action="store_true", help="With --fix, create candidate notes for broken typed wikilinks.")
    lint_parser.add_argument("--json", action="store_true", help="Emit JSON issues.")
    lint_parser.set_defaults(func=command_lint)

    review_parser = sub.add_parser("review", help="Print paper notes that need researcher review.")
    review_parser.add_argument("--limit", type=int, default=25)
    review_parser.set_defaults(func=command_review)

    build_report_parser = sub.add_parser("build-report", help="Summarize build quality, curation, archive, and review state.")
    build_report_parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    build_report_parser.set_defaults(func=command_build_report)

    new_node_parser = sub.add_parser("new-node", help="Create an author, concept, variable, method, community, question, or synthesis note.")
    new_node_parser.add_argument("type", choices=["author", "concept", "variable", "method", "community", "research_question", "synthesis"])
    new_node_parser.add_argument("title")
    new_node_parser.add_argument("--slug", help="Filename slug. Defaults to a slug from the title.")
    new_node_parser.add_argument("--status", choices=["working", "candidate", "active", "reviewed"])
    new_node_parser.add_argument("--force", action="store_true")
    new_node_parser.set_defaults(func=command_new_node)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
