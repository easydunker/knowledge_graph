# Node Curator Agent

Use this reference when Codex can spawn a worker/subagent to curate Research KB non-paper nodes. The worker handles exactly one `.research-kb/curator-tasks/*.curator-task.json` file and writes exactly one result JSON.

## Mission

Improve the knowledge graph after papers have been processed. Use quality-passed paper-note evidence to enrich concept, variable, method, community, and author nodes. Surface contradictions, update key paper lists, propose strong synthesis notes, and propose only high-confidence duplicate merges or invalid-node archive actions.

## Inputs

The task JSON is the authority. Read these fields first:

- `task`: must be `research_kb_curate_node`.
- `agent`: expected `research-kb.node-curator`.
- `node_path`, `node_type`, `node_status`, `node_title`, and `node_aliases`.
- `existing_node_content`: the current Markdown note.
- `inbound_papers`: quality-passed paper evidence packets.
- `stale_key_papers`: inbound papers not yet listed in the node's Key Papers section.
- metadata reconciliation fields or duplicate/stale candidate clusters, when present.
- `related_nodes`: adjacent graph nodes for context.
- `expected_json_schema`: the expected output shape.
- `result_path`: where to write the result JSON when available.

Do not use web search, prior knowledge, DOI lookup, Zotero, or any source outside the task JSON. If the task JSON includes Crossref, OpenAlex, or Semantic Scholar reconciliation records, treat them only as bibliographic identity hints for metadata cleanup, duplicate detection, and stale-node cleanup. They are not evidence for scholarly claims.

## Procedure

1. Verify the task is for one non-paper node.
2. Read every inbound paper evidence packet before writing conclusions.
3. Rewrite the node body when that would improve the KB. The curator may update the full body, not only a managed block.
4. Preserve source-grounded paper links and evidence anchors. Mark uncertainty directly.
5. Surface competing views and methodological differences instead of smoothing them away.
6. For author nodes, summarize only papers and patterns present in this KB. Do not invent biography, affiliation, or identity merges.
7. Create synthesis notes only when evidence is strong: 3+ quality-passed papers around a theme, 2+ papers that clearly contradict/complicate one another, or a local cluster that answers a likely researcher query better than any single node.
8. Propose merges only when the nodes are high-confidence duplicates. Do not merge merely related broad/narrow concepts.
9. Propose invalid-node archive actions only when a candidate node is clearly stale, phrase-like, OCR-corrupted, or unsupported by live paper links.
10. Write the result JSON to `result_path` if provided. Do not edit Markdown notes, indexes, PDFs, or other vault files directly.

## Output Envelope

Use this wrapper:

```json
{
  "node_path": "concepts/gender.md",
  "agent_source": "research-kb.node-curator",
  "agent_model": "codex",
  "action": "update_node",
  "new_status": "active",
  "body_markdown": "# Gender\n\n## Working Definition\n\n...",
  "coverage": {
    "inbound_papers_total": 12,
    "papers_read": 12,
    "coverage_limited": false
  },
  "synthesis_notes": [],
  "merge_plans": [],
  "uncertain_fields": []
}
```

`body_markdown` should include the Markdown body after frontmatter, starting with the `#` title. If using `sections` instead, keys should be human section names or snake_case names that map cleanly to Markdown headings.

## Synthesis Output

When evidence is strong, include synthesis notes:

```json
{
  "title": "Gender Prediction in Computational Sociolinguistics",
  "evidence_strength": "strong",
  "body_markdown": "## Claim\n\n...",
  "papers_considered": 8,
  "papers_used": [
    "papers/nguyen-2016.md",
    "papers/example-2020.md"
  ],
  "coverage_limited": false
}
```

The CLI creates these notes with `type: synthesis` and `status: active`.

If evidence is weak, do not ask the CLI to create a synthesis note. Record the opportunity in the target node's open questions or uncertainty instead. The CLI skips synthesis items that do not provide strong evidence, 3+ papers, or a clear 2-paper contradiction/complication.

## Merge Output

For high-confidence duplicates, include merge plans:

```json
{
  "confidence": "high",
  "source_node": "methods/svm.md",
  "target_node": "methods/support-vector-machine.md",
  "reason": "SVM is an acronym alias for support vector machine; source is a stub with no conflicting reviewed content."
}
```

Paper-note merges require very strong identity evidence such as same `pdf_sha256`, same normalized DOI, or same normalized title plus first author plus year.

Author merges require strong local and metadata-backed evidence. Prefer merges when the task shows the same matched paper, same author position, and a clear OCR/diacritic/name-initial variant. Do not merge two active or researcher-reviewed author nodes when identity is uncertain.

For invalid stale candidates, include archive plans:

```json
{
  "confidence": "high",
  "source_node": "authors/previous-tone-normalization-methods-mainly.md",
  "target_node": "",
  "action": "archive_invalid",
  "reason": "The node title is a phrase from the paper text, not an author name, and the task shows no live inbound paper link or provider-backed author match."
}
```

## Quality Bar

- The node should be more useful to a researcher after curation.
- Key claims must be linked to paper evidence.
- Contradictions and caveats should be visible.
- Synthesis notes should be rare and valuable.
- Merge proposals should be boringly obvious.
- Invalid-node archive proposals should be boringly obvious and reversible.
- Uncertainty is a feature, not a failure.
