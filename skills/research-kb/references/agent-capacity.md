# Agent Capacity

Use this reference for Research KB agents that operate over large vaults.

## Standard Workload

Agents should handle a Research KB vault containing up to 10,000 paper notes. Each paper note or supplied paper excerpt may be up to about 10,000 words.

This is a corpus-scale requirement, not a permission to load the whole vault into context. Use staged retrieval:

1. Do not load a 10,000-paper index or all paper summaries into the root harness context.
2. Use generated query output, note filenames, and `.research-kb/search/*.jsonl` as the first-pass map. These probe indexes contain paper identity, authors, summaries, findings, typed edges, and graph links in search-friendly records.
3. Probe the search index and note filenames for candidate authors, topics, title clues, DOI/year clues, methods, variables, communities, and relation labels.
4. Build a candidate pool before reading full paper notes. Prefer reviewed notes, exact metadata matches, author-node matches, and typed-edge paths.
5. Select a bounded subset for detailed inspection. A normal answer should inspect 5-20 paper notes in detail, depending on task complexity and harness context.
6. Read detailed paper notes in batches when needed. Prefer sections that answer the task: summary, research question, data, variables, methods, findings, limitations, useful quotes, and extraction notes.
7. Track which papers were found by index/probe search, which were inspected in detail, and which were left as uninspected candidates.
8. If hundreds or thousands of papers are relevant, report the coverage limit and suggest a narrowed follow-up query rather than silently collapsing them into a false synthesis.

## Limits

- Maximum corpus size target: 10,000 paper notes.
- Maximum expected text per paper note or excerpt: 10,000 words.
- Normal detailed-reading target per agent pass: 5-20 papers after index/probe narrowing.
- The root harness should search `.research-kb/search/papers.jsonl`, `.research-kb/search/nodes.jsonl`, and `.research-kb/search/edges.jsonl`; it should not read all records into the model at once.
- If a paper note or excerpt is longer than expected, summarize the first pass from structured sections and only inspect additional sections that are needed for the user's query.
- If the active harness/model cannot safely hold the full workload, process papers in batches and merge the intermediate notes into a final answer.

## Required Coverage Notes

Every multi-paper agent output should state:

- corpus/index scope searched
- candidate papers found
- papers inspected in detail
- entry points tried, such as topic, author, title clue, graph node, or claim
- evidence paths used
- relevant papers or graph areas not inspected because of detailed-reading limits
- gaps in the current KB

## Suggest-Only Rule

For paragraph enrichment and citation support, suggest supporting, complicating, or missing evidence. Do not rewrite the user's paragraph unless the user explicitly asks for a rewrite.
