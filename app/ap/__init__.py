"""AP English Language & Composition scoring (rubric-grounded, multi-agent).

Implements the official College Board 6-point ANALYTIC rubric — Row A (Thesis,
0-1), Row B (Evidence & Commentary, 0-4), Row C (Sophistication, 0-1) — for all
three free-response question (FRQ) types: Synthesis, Rhetorical Analysis,
Argument.

This is NOT a fine-tuned model. It is a rubric-decomposed, sample-anchored,
self-consistent LLM scorer whose accuracy is measured against official
human-scored sample essays via Quadratic Weighted Kappa (see app/ap/eval.py).
Source of truth for the rubric text: data/ap/scoring_guidelines_2024_set1_raw.txt
"""
