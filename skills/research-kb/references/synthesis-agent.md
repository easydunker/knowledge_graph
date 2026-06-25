# Synthesis Agent

Use this reference when a researcher asks to discuss previous studies on a topic, author, method, variable, community, or theoretical issue.

Read `agent-capacity.md` first. This agent must support vault-scale search over up to 10,000 papers, each up to about 10,000 words, using staged retrieval and bounded detailed reading.

## Mission

Produce a source-grounded discussion of previous studies represented in the local KB. Organize what the selected studies do, how they relate, where they agree or differ, and what gaps remain.

## Procedure

1. Resolve the topic into candidate graph nodes, authors, methods, variables, communities, and title clues.
2. Query the KB and probe `.research-kb/search/*.jsonl` to build a candidate set. Do not load the whole index into model context.
3. Build a candidate pool, then select a bounded detailed subset, normally 5-20 papers for synthesis. Prefer researcher-reviewed notes, stronger evidence anchors, and papers connected by typed edges.
4. Read structured sections first, then inspect details needed to compare studies.
5. Cluster papers by the dimension most useful for the user request:
   - author or research group
   - topic/concept
   - variable or phenomenon
   - method or measure
   - community/data
   - finding or disagreement
   - chronology
6. Surface contradictions, methodological differences, and missing evidence rather than smoothing them into a single story.

## Output

Return:

- brief answer
- grouped previous studies
- key findings by group
- methods/data comparison
- contradictions or complications
- gaps in the KB
- corpus/index scope searched
- candidate papers considered
- papers inspected in detail

Use only KB papers and source-grounded paper notes. Mark candidate/agent-draft evidence clearly.
