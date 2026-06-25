# PDF Parser Comparison for Research KB

Tested 2026-06-24 on 6 academic papers (single-column arXiv + multi-column ACL/NAACL).

## Results

| Library | Speed | Single-col | Multi-col | Artifacts | License |
|---------|-------|-----------|-----------|-----------|---------|
| **pymupdf4llm** `to_markdown()` | ~30K c/s | Structured MD | Structured MD | None | AGPL |
| **pymupdf** (fitz) `get_text()` | ~1000K c/s | Clean | Clean | None | AGPL |
| **pypdf** (current) | ~240K c/s | Clean | Minor ("V arious") | Spurious intra-word spaces | BSD |
| **pdfplumber** | ~70K c/s | **Broken** | **Broken** | Drops spaces: "widespreadinterest" | MIT |

pdfplumber is unusable — the word-merging bug is consistent across all paper formats.

## Recommendation: pymupdf4llm

Switch from pypdf to pymupdf4llm (`pymupdf4llm.to_markdown()`). Rationale:

1. **Structured Markdown output** — section headers become explicit `## Methods`, `## Results` markers. The paper-process agent can navigate reliably instead of guessing layout from raw text.
2. **Speed is fine** — 0.5-1.5s per paper vs. 85-220s agent time; extraction is noise in the pipeline.
3. **License is fine** — AGPL, same as pymupdf. The research-kb skill is open-source and doesn't distribute or embed the library; no commercial license needed.
4. **Tables preserved** — pymupdf4llm converts PDF tables to Markdown tables, which the agent can read as structured data.

### What changes in research_kb.py

The `extract_text_from_pdf()` function currently uses pypdf's `PdfReader`. Replace with:

```python
import pymupdf4llm

def extract_text_from_pdf(path, max_chars=500000):
    md = pymupdf4llm.to_markdown(path)
    return md[:max_chars]
```

The Markdown output is plain text compatible — the agent context and index pipeline don't need changes. The `@@PAGE:N@@` markers in the current extraction are a pypdf artifact; pymupdf4llm doesn't produce them, but page number context isn't critical for the agent (the paper note's `evidence::` lines use section/table references anyway).

### Fallback

If pymupdf4llm is not installed, fall back to raw pymupdf `fitz.open(path)` → `page.get_text()`. Remove the pypdf fallback — pymupdf is faster and cleaner.

## Test Papers

| Paper | Format | Pages | pymupdf4llm chars | pypdf chars | Notes |
|-------|--------|-------|-------------------|-------------|-------|
| Gupta & DiPadova (NAACL 2019) | 2-column | 5 | 19,468 | 17,967 | Short workshop paper |
| Jørgensen et al. (WNUT 2015) | 2-column | 10 | — | 31,260 | |
| Nguyen et al. (CL 2016) | 2-column | 57 | — | 228,479 | Survey, long |
| Zhang (PACLIC 2018) | 2-column | 9 | — | 38,520 | |
| Vaswani et al. (NeurIPS 2017) | 1-column | 15 | 40,900 | 39,597 | arXiv preprint |
| Touvron et al. (arXiv 2023) | 1-column | 77 | — | 88,176 | LLaMA paper |

## Cost

Both pymupdf and pymupdf4llm are dual-licensed (AGPL / Artifex Commercial). AGPL is fine for open-source, non-distributed use. The commercial license is only needed for proprietary products that embed pymupdf and don't want to open-source.
