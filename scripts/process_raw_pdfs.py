#!/usr/bin/env python3
"""
Create Obsidian paper notes from PDFs in raw/papers/.

This v1 script is intentionally conservative:
- it does not call external services
- it does not require Zotero
- it does not overwrite existing notes
- it uses pypdf when available, but can still create notes from filenames
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW_PAPERS = ROOT / "raw" / "papers"
RAW_PROCESSED = ROOT / "raw" / "processed"
RAW_FAILED = ROOT / "raw" / "failed"
PAPERS = ROOT / "papers"
LOG = ROOT / "log.md"


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def slugify(value: str, fallback: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or fallback


def yaml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def yaml_list(values: list[str]) -> str:
    if not values:
        return "[]"
    return "[" + ", ".join(yaml_string(value) for value in values) + "]"


def try_extract_with_pypdf(path: Path) -> tuple[dict[str, str], str, str]:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        return {}, "", "pypdf_not_available"

    try:
        reader = PdfReader(str(path))
        metadata = {}
        if reader.metadata:
            for key, value in reader.metadata.items():
                clean_key = str(key).lstrip("/")
                metadata[clean_key] = str(value or "").strip()

        pages = []
        for page in reader.pages[:5]:
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                pages.append("")
        text = "\n".join(pages).strip()
        return metadata, text, "ok"
    except Exception as exc:
        return {}, "", f"pdf_extract_failed: {exc}"


def infer_year(*values: str) -> str:
    for value in values:
        match = re.search(r"\b(19|20)\d{2}\b", value or "")
        if match:
            return match.group(0)
    return ""


def infer_doi(text: str) -> str:
    match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", text, re.I)
    return match.group(0).rstrip(".,);]") if match else ""


def split_authors(value: str) -> list[str]:
    value = value.strip()
    if not value:
        return []
    parts = re.split(r"\s*(?:;|\band\b|,)\s*", value)
    return [part.strip() for part in parts if part.strip()]


def infer_title(path: Path, metadata: dict[str, str], text: str) -> str:
    meta_title = metadata.get("Title", "").strip()
    if meta_title and meta_title.lower() not in {"untitled", "unknown"}:
        return re.sub(r"\s+", " ", meta_title)

    for line in text.splitlines()[:20]:
        clean = re.sub(r"\s+", " ", line).strip()
        if 12 <= len(clean) <= 180 and not clean.lower().startswith(("abstract", "keywords")):
            return clean

    return path.stem.replace("_", " ").replace("-", " ").strip().title()


def build_paper_id(info: PdfInfo) -> str:
    author = "unknown"
    if info.authors:
        author = info.authors[0].split()[-1]
    title_slug = slugify(info.title, "paper")
    short_title = "-".join(title_slug.split("-")[:5])
    year = info.year or "nd"
    return slugify(f"{author}-{year}-{short_title}", f"paper-{info.sha256[:8]}")


def existing_hashes() -> set[str]:
    hashes: set[str] = set()
    for note in PAPERS.glob("*.md"):
        try:
            text = note.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for match in re.finditer(r"^pdf_sha256:\s*\"?([a-fA-F0-9]{64})\"?", text, re.M):
            hashes.add(match.group(1).lower())
    return hashes


def unique_note_path(paper_id: str) -> Path:
    candidate = PAPERS / f"{paper_id}.md"
    if not candidate.exists():
        return candidate

    index = 2
    while True:
        candidate = PAPERS / f"{paper_id}-{index}.md"
        if not candidate.exists():
            return candidate
        index += 1


def collect_pdf_info(path: Path) -> PdfInfo:
    sha = sha256_file(path)
    metadata, text, status = try_extract_with_pypdf(path)
    title = infer_title(path, metadata, text)
    authors = split_authors(metadata.get("Author", ""))
    year = infer_year(metadata.get("CreationDate", ""), metadata.get("ModDate", ""), text, path.name)
    doi = infer_doi(text)
    publication = metadata.get("Subject", "").strip()
    uncertain = []
    if not authors:
        uncertain.append("authors")
    if not year:
        uncertain.append("year")
    if not doi:
        uncertain.append("doi")
    if status != "ok":
        uncertain.append("text_extraction")

    preview = re.sub(r"\s+", " ", text).strip()
    if len(preview) > 1200:
        preview = preview[:1200].rstrip() + "..."

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


def render_note(info: PdfInfo, relative_pdf_path: str, paper_id: str) -> str:
    today = date.today().isoformat()
    title = info.title or paper_id
    uncertain = ", ".join(info.uncertain_fields) if info.uncertain_fields else "none"
    preview = info.text_preview or "No text preview extracted. Review the PDF manually."

    return f"""---
type: paper
paper_id: {yaml_string(paper_id)}
intake_source: raw_pdf
raw_pdf_path: {yaml_string(relative_pdf_path)}
pdf_sha256: {yaml_string(info.sha256)}
title: {yaml_string(title)}
authors: {yaml_list(info.authors)}
year: {info.year or ""}
doi: {yaml_string(info.doi)}
publication: {yaml_string(info.publication)}
kb_status: needs_review
review_state: agent_draft
aliases: []
created: {yaml_string(today)}
updated: {yaml_string(today)}
---

# {title}

## Source

- PDF: {relative_pdf_path}
- DOI: {info.doi or ""}

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

## Key Findings

- finding::
  - evidence::
  - supports::
  - complicates::

## Theoretical Contribution

## Limitations

## Useful Quotes

## Extraction Notes

- metadata_confidence: low
- text_extraction_status: {info.extraction_status}
- uncertain_fields: {uncertain}
- text_preview: {preview}

## Links

- Concepts:
- Variables:
- Methods:
- Communities:
- Related papers:
"""


def append_log(message: str) -> None:
    today = date.today().isoformat()
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"\n- {today}: {message}\n")


def process_pdf(path: Path, move: bool, known_hashes: set[str]) -> str:
    info = collect_pdf_info(path)
    if info.sha256.lower() in known_hashes:
        return f"skipped existing PDF hash: {path.name}"

    paper_id = build_paper_id(info)
    note_path = unique_note_path(paper_id)

    target_pdf_path = path
    if move:
        RAW_PROCESSED.mkdir(parents=True, exist_ok=True)
        target_pdf_path = RAW_PROCESSED / path.name
        if target_pdf_path.exists():
            target_pdf_path = RAW_PROCESSED / f"{path.stem}-{info.sha256[:8]}{path.suffix}"
        shutil.move(str(path), str(target_pdf_path))

    relative_pdf_path = target_pdf_path.relative_to(ROOT).as_posix()
    note = render_note(info, relative_pdf_path, note_path.stem)
    note_path.write_text(note, encoding="utf-8")
    known_hashes.add(info.sha256.lower())
    append_log(f"Processed raw PDF `{relative_pdf_path}` into `{note_path.relative_to(ROOT).as_posix()}`.")
    return f"created {note_path.relative_to(ROOT).as_posix()}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create paper notes from raw PDFs.")
    parser.add_argument("--move", action="store_true", help="Move processed PDFs to raw/processed/.")
    args = parser.parse_args()

    RAW_PAPERS.mkdir(parents=True, exist_ok=True)
    PAPERS.mkdir(parents=True, exist_ok=True)
    RAW_FAILED.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(RAW_PAPERS.glob("*.pdf"))
    if not pdfs:
        print("No PDFs found in raw/papers/.")
        return 0

    hashes = existing_hashes()
    for pdf in pdfs:
        try:
            print(process_pdf(pdf, args.move, hashes))
        except Exception as exc:
            print(f"failed {pdf.name}: {exc}")
            append_log(f"Failed to process raw PDF `{pdf.name}`: {exc}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
