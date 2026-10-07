# v8 result tables

Every CSV here is regenerated from the run directories by a read-only script. No model calls,
nothing typed in by hand. The Word report (`eval/reports/NL_to_IDS_report_v8.docx`, git-ignored)
is built from these files by `node eval/report_docx_v8.js <out.docx> eval/reports/v8`.

Runs used: **Run 5** = `gemini-2.5-flash`, 47 items x 3 repeats. **Run 6** = `gemini-3.8-flash`,
47 items x 2 repeats, repeat 2 stopping at 39 items when the prepaid credit ran out. **2x2** =
21 items x 3 repeats in each of four cells (`run6-lk{0,1}dt{0,1}-rep{1,2,3}`).

## Scoring variants

| suffix | meaning |
| --- | --- |
| `scores.csv` | strict: every reference requirement counts |
| `scores_relaxed.csv` | determined-only: requirements and values not derivable from the request are set aside (`eval/annotations/determinacy.jsonl`) |
| `scores_relaxed_j8.csv` | determined-only, but the 8 judgement-call value labels kept (`determinacy_minus_judgement.jsonl`) |
| `*_probe.csv` | same scoring, test model extended with probe objects (see below) |

Probe objects come from `eval/witness.py:_emit_probes`. They close two blind spots of the
standard test model: a value in the symmetric difference of two enumerations (reference allows
{A,B,C}, candidate {A,B,D} -> one object with C, one with D), and a value outside a constraint
the candidate adds where the reference has none (reference leaves the value free, candidate pins
it to TRUE -> one object with another value). Each probe is accepted by exactly one of the two
files, so no value disagreement can stay invisible.

## Files

| file | written by | what it holds |
| --- | --- | --- |
| `p1_probe_vs_standard.csv` | `eval.analysis_probe` | S1 and S2 under both object sets, with bootstrap intervals |
| `p2_probe_flips.csv` | `eval.analysis_probe` | the item-runs whose verdict changes when probes are added |
| `m1_text_class_x_behaviour.csv` | `eval.analysis_pairs` | three text classes x behaviour-exact, both scorings, both object sets, with intervals |
| `m2_disagreement_rate.csv` | `eval.analysis_pairs` | how often the text and behaviour verdicts disagree, by how discriminating the model is (real buildings / standard / probe) |
| `l1_like_for_like_effects.csv` | `eval.analysis_likeforlike` | the 2x2 fix effects on facet F1 and on S1, matched pair by pair |
| `l2_field_effects_for_comparison.csv` | `eval.analysis_likeforlike` | the same fixes measured on the field each one targets |
| `f1`-`f5` | `eval.analysis_fixes` | per-field fix effects, worked examples, text-vs-behaviour contingency, v5 reconciliation |
| `j1_judgement_call_labels.csv` | `eval.analysis_judgement` | the 8 determinacy labels that rest on a judgement call |
| `j2_headline_both_ways.csv` | `eval.analysis_judgement` | determined-only headline with those 8 dropped and kept |
| `j3_affected_item_runs.csv` | `eval.analysis_judgement` | the item-runs whose verdict depends on them |
| `r1_run6_vs_run5_paired.csv` | `eval.analysis_models` | Run 6 against Run 5, paired by item, with intervals on the difference |
| `r2_run6_both_ways.csv` | `eval.analysis_models` | Run 6 with the 3 token-ceiling failures counted and set aside |
| `r3_value_omission_by_determinacy.csv` | `eval.analysis_models` | value omission split by whether the reference value is derivable |
| `r4_cost_per_item.csv` | `eval.analysis_models` | cost and tokens per item-run, per model |
| `i1_ishigaki_facetf1.csv` | `eval.analysis_ishigaki` | FacetF1 computed the IDS-Bench way, with and without the IFC-version block |
| `i2_declared_versions.csv` | `eval.analysis_ishigaki` | which ifcVersion each run declared |
| `i3_clarification_questions.csv` | `eval.analysis_ishigaki` | the clarification questions against the determinacy labels |
| `s1`-`s6` | `eval.analysis_strict` | strict headline, failure directions, no-file detail, per-facet evidence, annotation methods |
| `v1`-`v8` | `eval.analysis_values` | matched-pair value analysis, field table, verbatim disagreements |
| `x1_spend_by_run.csv` | `eval.spend --csv` | tokens and cost per run, thinking share included |

## Caveats that must travel with these numbers

* **The headline depends on the test model.** Probe objects are adversarial by construction; real
  buildings exercise almost nothing. Both are reported; neither alone is "the" answer.
* **Run 6 is 47 + 39 item-runs, not 47 + 47**, and 3 item-runs hit the 267,000-token ceiling.
  `r2_run6_both_ways.csv` reports the headline with them counted and excluded.
* **The IDS-Bench column is not a like-for-like leaderboard entry.** Our reference declares all
  three IFC versions so that it is never version-filtered, so the version block never matches a
  generated file that declares one version. Use the "version block excluded" column for
  comparison, and say so.
* **The determinacy labels are machine-made.** 37 of 45 follow a stated rule; 8 are judgement
  calls, listed in `j1` and scored both ways in `j2`.
