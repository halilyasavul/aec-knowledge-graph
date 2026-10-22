# v9 result tables

Regenerated from the run directories by read-only scripts; no model calls. Builds on
`eval/reports/v8/` (same runs, same bootstrap).

## A. Extras: requirements the generator emitted that the reference lacks

The prompts are the IDS files' own description text. For the Vienna set that is modelling
guidance the authors never encoded as facets, so the request often says more than the
reference. Every (item, requirement) pair that appears in a generated file of Run 5 or Run 6
and not in the determined-only reference was read against the request and labelled in
`eval/annotations/extras.jsonl`:

- **faithful** — the request supports it (e.g. `MaxPolygonCount <= 10000` for "maximalen
  Polygonanzahl beschränkt auf 10.000"; `PredefinedType` for "Typen gemäss
  IfcSanitaryTerminalTypeEnum"; NRF/UGF area properties for the ÖNORM B 1800 room rules);
- **defect** — it does not (`Pset_ColumnCommon.Fire Rating` with a space in the name; a duplicate
  `Slope`; `IsExternal` read off a descriptive sentence; `PredefinedType` pinned without cause).

`python -m eval.score --relaxed --excuse-extras` removes the faithful ones from the candidate
before scoring: the mirror image of `--relaxed`, which removes undetermined facets from the
reference. Both trims make the comparison "the part of the request the reference encodes".

A second, value-level case: five Vienna `Status` requests say the German PDF values
(Neu, Bestand, Abbruch, Temporär) may be used alongside the IFC values; the reference has the
seven IFC values only. `eval/annotations/determinacy_plus_request_values.jsonl` adds them
(`scope=value_extend`); scored with `--tag _rv`. 3.8 Flash emitted them in 6 of 8 item-runs
and was scored too lenient for it; 2.5 Flash never did (it truncated to 4 values instead).

| file | written by | what it holds |
| --- | --- | --- |
| `e1_extras_labels.csv` | `eval.analysis_extras` | the 30 labels with reasons and the runs each was seen in |
| `e2_headline_three_scorings.csv` | `eval.analysis_extras` | S1 under strict / determined-only / + faithful extras excused / + request Status values, both object sets, with intervals |
| `e3_excused_item_runs.csv` | `eval.analysis_extras` | the item-runs the excusal touches, verdict before and after |

Headline (probe object set): Run 5 determined-only 71/132 -> 73/132 excused -> 73/132 with
request values; Run 6 61/80 -> 62/80 -> 66/80. The correction moves 3.8 Flash from 76% to 82.5%;
it does not move 2.5 Flash, whose remaining failures are omissions and truncations.

The labels are the author's reading, like the determinacy labels. The 14 defect labels are
system faults and stay counted.
