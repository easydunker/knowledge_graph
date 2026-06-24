#!/usr/bin/env python3
"""
Local-first Obsidian research KB helper.

The script is intentionally dependency-light. It uses only the Python standard
library by default and opportunistically uses pypdf when it is installed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
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
DEFAULT_AGENT_MAX_CHARS = 120000
DEFAULT_PDF_TEXT_MAX_CHARS = 500000
PAPER_PROCESS_AGENT_NAME = "research-kb.paper-process"
PAPER_PROCESS_AGENT_PROFILE = "agents/paper-process.yaml"
PAPER_PROCESS_AGENT_REFERENCE = "references/paper-process-agent.md"
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
- Mark uncertain metadata and summaries clearly.
- Preserve researcher-reviewed content.
- Prefer evidence with page, section, table, or quote information when available.

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
raw_pdf_dir: raw/papers
source_of_truth: markdown_notes
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
    if value.startswith("["):
        return parse_list_value(value)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    return value


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
        "Do not use outside knowledge. Preserve uncertainty. If evidence is weak, "
        "say so in `uncertain_fields` or edge `uncertainty`. Use page markers like "
        "@@PAGE:3@@ to produce evidence anchors such as `p. 3` when possible. "
        f"Use these relation labels when possible: {', '.join(sorted(RELATIONS - {'uncertainty'}))}. "
        "For graph nodes, prefer node_type values: author, concept, variable, method, community. "
        "For graph edge slugs, use lowercase hyphen-case and avoid duplicate labels from the known nodes list. "
        "Return exactly one JSON object matching `expected_json_schema`."
    )


def build_agent_prompt(root: Path, info: PdfInfo | None, note: Note | None, text: str, extraction_status: str, max_chars: int = DEFAULT_AGENT_MAX_CHARS) -> str:
    title = note.title if note else (info.title if info else "")
    authors = note.frontmatter.get("authors", []) if note else (info.authors if info else [])
    year = str(note.frontmatter.get("year", "")) if note else (info.year if info else "")
    doi = str(note.frontmatter.get("doi", "")) if note else (info.doi if info else "")
    publication = str(note.frontmatter.get("publication", "")) if note else (info.publication if info else "")
    excerpt_chars = min(len(text), max_chars)
    truncation_note = "yes" if len(text) > max_chars else "no"
    return f"""Act as the research-kb paper process agent.

Understand and summarize this research paper for an Obsidian Markdown knowledge base.

Use only the supplied extracted PDF text. Do not use outside knowledge.
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
"""


def paper_agent_task(root: Path, note: Note, max_chars: int = DEFAULT_AGENT_MAX_CHARS) -> dict[str, Any]:
    text, extraction_status = extract_note_pdf_text(root, note)
    extracted_text = text[:max_chars]
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
        "source_text_chars": len(text),
        "extracted_text_chars": len(extracted_text),
        "text_truncated_for_task": len(text) > len(extracted_text),
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


def extract_pdf_text(path: Path) -> tuple[dict[str, str], str, str]:
    metadata, text, status = try_extract_with_pypdf(path)
    if not metadata:
        metadata = regex_pdf_metadata(path)
    if not text:
        text, fallback_status = fallback_pdf_text(path)
        status = fallback_status if status == "pypdf_not_available" else f"{status}; {fallback_status}"
    return metadata, clean_extracted_text(text), status


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
    metadata, text, status = extract_pdf_text(path)
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
    )


def extract_note_pdf_text(root: Path, note: Note) -> tuple[str, str]:
    raw_pdf_path = str(note.frontmatter.get("raw_pdf_path", "")).strip()
    if not raw_pdf_path:
        return "", "missing_raw_pdf_path"
    pdf_path = root / raw_pdf_path
    if not pdf_path.exists():
        return "", "missing_pdf_file"
    _metadata, text, status = extract_pdf_text(pdf_path)
    return text, status


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
        "doi": info.doi,
        "publication": info.publication,
        "author_links": author_link_lines(info.authors),
        "date": today(),
    }
    note = render_template("paper.md", values, root=root)
    if "- DOI: {{doi}}" in note:
        note = note.replace("- DOI: {{doi}}", f"- DOI: {info.doi}")
    elif "- DOI:" in note:
        note = re.sub(r"^- DOI:.*$", f"- DOI: {info.doi}", note, count=1, flags=re.M)
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


def apply_agent_analysis_to_note(root: Path, note: Note, analysis: dict[str, Any], source: str, model: str, force: bool, create_nodes: bool) -> tuple[bool, str]:
    if note.note_type != "paper":
        return False, f"skipped non-paper {note.rel_path}"
    if note_is_researcher_reviewed(note) and not force:
        return False, f"skipped researcher-reviewed {note.rel_path}"
    _text, extraction_status = extract_note_pdf_text(root, note)
    result = AgentAnalysisResult(analysis=analysis, source=source, model=model)
    updated = update_frontmatter_from_analysis(note.text, analysis)
    updated = replace_sections(updated, agent_analysis_to_sections(result, extraction_status), force=True)
    changed = updated != note.text
    if changed:
        note.path.write_text(updated, encoding="utf-8")
    if create_nodes:
        created = create_candidate_notes_from_text(root, updated, note)
        changed = changed or bool(created)
    return changed, f"applied agent analysis to {note.rel_path}" if changed else f"unchanged {note.rel_path}"


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
    for note in notes:
        for link in note.links:
            resolved = resolve_link(link, notes)
            if resolved:
                incoming[resolved.rel_path] = incoming.get(resolved.rel_path, 0) + 1
            else:
                issues.append(issue("warn", "broken-wikilink", note.rel_path, f"Cannot resolve wikilink [[{link}]].", "Create a candidate note or fix the link path."))

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
        elif note.note_type in {"concept", "variable", "method", "community"}:
            outgoing_to_papers = 0
            for link in note.links:
                resolved = resolve_link(link, notes)
                if resolved and resolved.note_type == "paper":
                    outgoing_to_papers += 1
            if incoming.get(note.rel_path, 0) == 0 and outgoing_to_papers == 0:
                issues.append(issue("info", "orphan-node", note.rel_path, "Node has no backlinks and no paper links."))
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
            or str(note.frontmatter.get("review_state", "")) in {"agent_draft", "needs_review"}
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
    agent_context_parser.add_argument("--max-chars", type=int, default=DEFAULT_AGENT_MAX_CHARS, help="Maximum extracted PDF text characters to include.")
    agent_context_parser.add_argument("--limit", type=int, default=0, help="Maximum number of paper tasks to export.")
    agent_context_parser.add_argument("--all", action="store_true", help="Export all paper notes, including notes whose sections are already filled.")
    agent_context_parser.set_defaults(func=command_agent_context)

    apply_analysis_parser = sub.add_parser("apply-analysis", help="Apply model-agnostic paper-analysis JSON returned by an external agent or subagent.")
    apply_analysis_parser.add_argument("input", nargs="+", help="Analysis JSON file(s). Each should include note_path or use --note.")
    apply_analysis_parser.add_argument("--note", help="Paper note path, stem, or wikilink when the JSON file does not include note_path.")
    apply_analysis_parser.add_argument("--force", action="store_true", help="Overwrite non-empty sections and reviewed notes.")
    apply_analysis_parser.add_argument("--create-nodes", action="store_true", help="Create or update candidate concept/variable/method/community nodes for returned links.")
    apply_analysis_parser.set_defaults(func=command_apply_analysis)

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
