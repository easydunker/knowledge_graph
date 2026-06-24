# Public PDF Quality Evaluation

This is a repeatable, test-only evaluation for the research KB workflow. It downloads public ACL PDFs into a temporary vault and does not add them to the curated KB.

The harness runs deterministic `process` and `enrich --create-nodes` so the quality baseline is reproducible and does not require any model provider. Agent-assisted paper understanding is tested separately through the model-agnostic `agent-context` / `apply-analysis` contract.

## Test Corpus

- `N19-3013.pdf`: Deep Learning and Sociophonetics: Automatic Coding of Rhoticity Using Neural Networks
- `N15-3015.pdf`: A Web Application for Automated Dialect Analysis
- `J16-3007.pdf`: Computational Sociolinguistics: A Survey
- `W15-4302.pdf`: Challenges of studying and processing dialects in social media
- `Y18-1095.pdf`: A Comparison of Tone Normalization Methods for Language Variation

## Full-Cycle Test Cases

1. Intake: `process` creates five paper notes with stable hashes and clean paper IDs.
2. Enrichment: `enrich --create-nodes` fills summaries, graph edges, findings, useful quotes, and candidate node pages.
3. Health: `lint` returns no issues after enrichment.
4. Review: `review` keeps all five paper notes in the review queue.
5. Query quality:
   - `rhoticity neural networks sociophonetics` ranks the Gupta and DiPadova rhoticity paper first.
   - `dialect features in social media and AAVE` ranks the Jørgensen, Hovy, and Søgaard social-media dialect paper first.
   - `tone normalization methods for language variation` ranks the Zhang tone-normalization paper first.
6. Graph quality: candidate concept, variable, method, and community nodes are created and linked from paper notes.
7. Evidence quality: extracted findings and useful quotes include approximate page anchors when `pypdf` extraction provides page boundaries.
8. Hygiene: internal page markers and common PDF line-break artifacts must not leak into generated notes.

## Run

Use a Python environment with `pypdf` installed for the quality run:

```bash
python3 scripts/evaluate_public_pdfs.py --python /path/to/python-with-pypdf
```

The script creates a temporary vault, downloads the public PDFs, runs `init`, `process`, `enrich --create-nodes`, `lint`, `review`, and the query tests, then prints a JSON summary with timing information.

## Latest Result

The current workflow passes the full-cycle checks with the bundled Codex Python runtime:

- Papers: 5
- Concepts: 6
- Variables: 3
- Methods: 7
- Communities: 3
- Machine-index graph: 24 notes, 126 typed edges, 56 wikilinks
- Lint: no issues
- Review queue: 5 draft paper notes
- Query first results: rhoticity -> Gupta/DiPadova 2019; dialect/AAVE -> Jørgensen/Hovy/Søgaard 2015; tone normalization -> Zhang 2018
- Performance, latest kept run: downloads 10.697s; `init` 0.057s; `process` 0.398s; `enrich --create-nodes` 0.537s; `lint` 0.043s; each tested query about 0.055s; total 11.925s.
- Agent-contract smoke coverage: `agent-context` exports portable task JSON, and `apply-analysis` applies a model-agnostic analysis JSON, records `agent_source` / `agent_model`, and creates candidate graph nodes from returned links.
- Codex process-agent smoke coverage: one `J16-3007.pdf` task was processed by a `research-kb.paper-process` worker subagent, applied with `apply-analysis --create-nodes`, linted cleanly, created 40 candidate graph nodes, and was retrievable by a query for computational sociolinguistics, social identity, and social media.

## Improvements from Review

- Added page-boundary markers during `pypdf` extraction and converted them into `evidence:: p. N` anchors in generated findings and quotes.
- Cleaned common PDF extraction artifacts such as split short words, suffix hyphenation, ligatures, and leaked page markers.
- Added a fallback abstract extractor for papers without a clear `Abstract` heading, reducing title/author/affiliation leakage into summaries.
- Narrowed the `identity` candidate-node trigger so phrases like "identity of the stressed vowel" do not become social-identity graph edges.
- Excluded `uncertainty::` lines from query scoring and evidence paths so caveats do not behave like positive evidence.
- Extended the public evaluation harness with timing, page-anchor, marker-leak, and text-artifact checks.
- Added a bundled `research-kb.paper-process` agent contract and increased PDF extraction/task text coverage so the process agent can summarize from later paper sections, not only the opening pages.

## Remaining Limitations

- The deterministic evaluation covers heuristic enrichment; agent-assisted enrichment is source-grounded but still not researcher-reviewed.
- Page anchors are approximate because they come from extracted text page boundaries; researchers should still verify against the PDF.
- Candidate nodes may need merging or relabeling.
- Scanned/OCR-poor PDFs need a separate OCR path.
- Some line-break artifacts remain possible in hard PDFs; the current cleaner handles common ACL-style extraction artifacts but is not a full OCR/layout repair system.
