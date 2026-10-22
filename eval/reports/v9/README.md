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

## B. Generator changes (not yet run; no model calls made)

`aec_kg/ids/request_checks.py`, called from `generate_ids`, rejects content the request does
not support, so the model repairs it in the same turn the way it repairs a validation error:

| check | v8 defect it answers |
| --- | --- |
| baseName with whitespace; name absent from a looked-up `Pset_`/`Qto_` set (with suggestions) | `Pset_ColumnCommon.Fire Rating`, 7 item-runs |
| Boolean pinned without a directive in the request ("must be TRUE", "muss WAHR sein", "= TRUE") | `FireExit = TRUE` on "Angabe, ob ..." / "Indication whether ...", the most common invented constraint |
| exact value / enumeration member / numeric bound neither in the request nor in the property's IFC values | `REI 90`, `ND, NE, REI 30 ...`, `RequiredSlope <= 0.06` |
| enumeration that is a strict subset of the IFC enumeration while the request names no subset | `Status` without OTHER/NOTKNOWN/UNSET (the 4-of-7 case is *not* caught: the request names those four in parentheses; the prompt rule covers it) |
| generate_ids refuses a fifth attempt in a turn; a reply that claims an attachment after no success gets a correction appended | 5 "every attempt rejected" item-runs; "attached" with no file on disk |

The system prompt gains matching rules (names, record vs. require, values, complete
enumerations, coverage, the retry cap). `eval/generate.py --no-request-checks` turns both off
and reproduces the Run 5/6 prompt exactly (sha `11f3d84b…`), so Run 6 rep2 can still be
finished with its own prompt.

Expected direction once rerun: determined-only up, strict down (more omissions where the
request gives no value) — the trade the study is about. 21 offline tests in
`tests/test_v9_request_checks.py`, including the agent loop against a scripted client.

### Replay of the checks over the recorded runs (`e4`, `e5`)

Every `generate_ids` call of Run 5 and Run 6 is in `log.jsonl` with the JSON the model sent
and the `query_class` results before it, so the checks can be replayed with no model calls
(`python -m eval.replay_checks`). On the documents the runs accepted:

| | accepted documents | checks fire | of those, behaviour-exact | of those, failing |
| --- | --- | --- | --- | --- |
| Run 5 (2.5 Flash) | 130 | 33 | 0 | 33 |
| Run 6 (3.8 Flash) | 83 | 3 | 0 | 2 (+1 unverified) |

Against the probe-set verdict the checks have no false positives: not one behaviour-exact
item-run would have been sent back. They reach 33 of Run 5's 51 failing item-runs (24 Boolean
pins, 7 `Fire Rating`, 4 invented bounds) and 2 of Run 6's 15. What they do not reach: the
no-file item-runs, the 4-of-7 `Status` truncation (the request names the four), and missing
requirements. Whether the model repairs a rejected document correctly is what the rerun measures.
