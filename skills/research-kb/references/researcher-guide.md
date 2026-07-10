# Researcher Guide: Build a Literature KB

This guide is for researchers. You do not need to run commands or inspect task files.

## Your Three Steps

1. Put only the PDFs you want to use in your vault's `raw/papers/` folder.
2. Ask Codex: **"Build my research knowledge base from the PDFs in `raw/papers/`. Continue until the build is complete, then give me the researcher check."**
3. When Codex finishes, open the small **Researcher Spot Check** sample in the build report. Verify that each sampled note accurately reflects its PDF and that its evidence anchors point to the right page, table, or section. Read every item in **Exceptions To Review**; you do not need to read all other notes.

For a new collection of around 60 papers, expect the work to run in batches and resume safely if it is interrupted. The result is not complete merely because graph nodes have appeared.

## What Codex Does Automatically

Codex creates source-tracked paper drafts, processes every paper in bounded batches, checks each result against its extracted source text, reconciles high-confidence bibliographic metadata, and then curates the shared concept, method, variable, community, and author notes.

It should report completion only after every paper job has either passed the quality guard or been placed in the exception list, and after curation jobs have been applied. It preserves the original PDF path and hash, does not add outside papers, and marks uncertainty instead of presenting it as fact.

## What You Will Be Asked To Decide

Only these cases need your judgment:

- A PDF cannot be read well enough to make a trustworthy note.
- The system finds two possible versions of the same paper or two nodes that may be duplicates.
- A quality check cannot resolve a weak or contradictory summary after a retry.
- A sampled note misstates the paper or its evidence anchor.

When this happens, respond with the paper or node you want corrected. Codex should retry or revise that item without changing researcher-reviewed notes unless you explicitly ask it to.

## How To Read The Final Report

- **Ready for researcher spot check:** automation finished without unresolved job failures. Review the short sample, then start using the vault.
- **Researcher attention needed:** the build ran, but at least one note is still marked as a draft or needs review. Read the listed exceptions before relying on those notes.
- **Build incomplete:** work remains in the queue. Codex should continue the queue rather than presenting the graph as finished.

The report lists at most ten paths in the terminal view so it remains readable. Its JSON version retains the full exception list for the harness.
