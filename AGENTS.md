# Agent Rules

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
- Link concepts, variables, methods, and communities only when substantively relevant.
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
