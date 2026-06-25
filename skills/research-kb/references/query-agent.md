# Query Agent

Use this reference when Codex can delegate Research KB lookup or discovery to a query worker. The query agent retrieves candidate papers and graph nodes; the root harness decides how to use the results.

Read `agent-capacity.md` first. This agent must support vault-scale search over up to 10,000 papers, each up to about 10,000 words, using staged retrieval and bounded detailed reading.

## Mission

Find supporting documents in the local Research KB when the user has a clear topic, author name, title fragment, DOI/year clue, method, variable, community, or other search clue.

## Procedure

1. Identify the user intent: author lookup, topic lookup, title/DOI/year clue, method/variable/community lookup, or mixed clue search.
2. Run the deterministic CLI query first:

   ```bash
   python3 <skill-dir>/scripts/research_kb.py --vault /path/to/vault query "user clue" --mode idea --limit 10
   ```

3. Probe `.research-kb/search/papers.jsonl`, `.research-kb/search/nodes.jsonl`, and `.research-kb/search/edges.jsonl` when the CLI output is weak, ambiguous, or misses obvious author/title clues. Do not load the whole index into model context.
4. Resolve candidate graph nodes and paper notes by title, aliases, authors, DOI, year, filename, and typed edges.
5. Build a candidate pool from the index and CLI output, then inspect a bounded detailed subset, normally 5-20 papers. If many more are relevant, report the cap and propose a narrower follow-up.
6. Read selected paper notes, prioritizing structured sections before full text.
7. Return evidence packets rather than only prose.

## Output

Return:

- interpreted query type
- matched authors, nodes, and paper clues
- suggested supporting papers
- why each paper is relevant
- evidence paths through typed edges or findings
- coverage notes and gaps

Do not treat web search or external databases as KB evidence.
