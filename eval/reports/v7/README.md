# v7 analysis tables

Produced by `python -m eval.analysis` (read-only over existing run directories).
Code commit: see `git log -1` on branch `eval-v7`; the tables below were generated at the
commit that adds `eval/analysis.py`.

| file | what it holds | source run directories |
|---|---|---|
| `t1_fix_effects_bootstrap.csv` | effect of each fix on each metric, with 95% bootstrap CIs (2000 resamples of items, all three repeats of an item carried together), plus the lookup × dataType interaction | `eval/runs/run6-{lk0dt0,lk1dt0,lk0dt1,lk1dt1}-rep{1,2,3}` (`scores.csv`, `scores_relaxed.csv`) |
| `t2_within_item_lookup.csv` | within-item change when the lookup fix is switched on with the dataType fix already on, grouped by what happened to the item's names | `run6-lk0dt1-rep{1,2,3}` vs `run6-lk1dt1-rep{1,2,3}` |
| `t3_item_difficulty.csv` | difficulty of names-correct vs names-wrong items: requirement count, facet mix, share of undetermined facets | `run6-lk1dt1-rep{1,2,3}`, `eval/annotations/determinacy.jsonl`, `eval/nl_to_ids_testset/spec_tasks.jsonl` |
| `t4_run5_sensitivity.csv` | Run 5 exact-match headline under four annotation variants, with the 3/3, 2/3, 1/3, 0/3 repeat breakdown | `run5-rep{1,2,3}`: `scores.csv`, `scores_relaxed.csv`, `scores_relaxed_passA.csv`, `scores_relaxed_valueskept.csv` |
| `t5_run5_failures.csv` | every item that still fails under the determined-only reference, one row per (repeat, item), with its cause | `run5-rep{1,2,3}` (`scores_relaxed.csv`) |

## Definitions used in these tables

- **S1** — the generated and reference specifications give an identical verdict on every test object.
- **S2 (reference objects)** — fraction of reference-derived test objects judged the same way. Only
  the reference-derived population is identical across runs, so cross-run comparisons use this.
- **false rejection** — of objects the reference accepts, the fraction the candidate rejects.
- **names-correct** — every property-set and property name matches the reference (the text-check proxy).
- **determined-only** — scored against a reference with unrecoverable requirements removed and
  unrecoverable value constraints dropped (`eval/annotations/determinacy.jsonl`).

## Annotation variants in `t4`

- `scores.csv` — strict, no annotations.
- `scores_relaxed.csv` — pass B, the final annotation (mechanical value rule + author's reading).
- `scores_relaxed_passA.csv` — pass A, the earlier text heuristics. A and B flag exactly the same
  45 facets with the same scopes, so the "worst case where A and B disagree" is empty by construction
  and equals pass B.
- `scores_relaxed_valueskept.csv` — only unmentioned requirements dropped, every value constraint
  retained. This is the informative bound: it shows how much of the headline rests on the 31
  value-scope annotations.
