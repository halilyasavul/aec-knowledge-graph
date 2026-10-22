# Run 7: Claude Sonnet 5.5 through Claude Code and the ifc MCP server

Run 7 sent the same 47 requests as Runs 5 and 6, byte for byte, to Claude Code. Claude Code had
only the five tools of `aec_kg.mcp_server`. The generated files were scored by the same scorer,
against the same references, annotations and test models. The graph snapshot is identical to
Run 6's: 2047 classes, 746 property sets, 2501 properties. There were three repeats, matching
Run 5. Generation and scoring ran on 21 Oct 2026, 21:53–22:18, on the subscription login.

Short version: every one of the 141 item-runs produced a file. Under determined-only scoring on
the probe object set, Run 7 has S1 = 111/132 (0.841), against 0.762 for Run 6 and 0.538 for
Run 5. With the request's own Status values counted, Run 7 has 123/132 (0.932). The request
checks inside `generate_ids` never fired. Under strict scoring Run 7 is no better than Run 6: it
declines to invent values the request does not give, and strict scoring counts that as a miss.

## 1. Run facts

| | rep1 | rep2 | rep3 | all |
| --- | --- | --- | --- | --- |
| model served (`init.model`) | claude-sonnet-5-5 | claude-sonnet-5-5 | claude-sonnet-5-5 | `--model sonnet` |
| Claude Code | 2.1.296 | 2.1.296 | 2.1.296 | `apiKeySource: none` (subscription) |
| tools listed | 5 × `mcp__ifc__*` | same | same | no built-ins |
| items attempted / ok / no_file / error | 47 / 47 / 0 / 0 | 47 / 47 / 0 / 0 | 47 / 47 / 0 / 0 | 141 / 141 / 0 / 0 |
| `generate_ids` calls (rejected) | 49 (2) | 48 (1) | 49 (2) | 146 (5), all Vienna#25 |
| wall time, first start → last end | 12.2 min | 13.2 min | 12.9 min | 25 min; repeats overlapped |
| per item: median / max | 14.5 s / 37.7 s | 15.5 s / 34.9 s | 14.4 s / 40.1 s | 14.8 s / 40.1 s |
| `input_tokens` as logged: median / total | 31,186 / 1,798,745 | 31,275 / 1,756,164 | 31,302 / 1,850,320 | see note |
| input tokens, each API call counted once: median / total | 29,813 / 1,376,431 | 29,711 / 1,340,051 | 30,758 / 1,393,281 | 77% cache reads |
| API calls per item: median (total) | 4 (176) | 4 (173) | 4 (177) | |
| largest single tool result | 7,674 chars | 7,674 | 7,674 | Runs 5/6: median 86.8k, max 98.6k |
| hit `max_turns` (14) | 0 | 0 | 0 | turns: median 4, max 8 |
| Claude Code's reported cost | $1.85 | $1.78 | $1.80 | $5.44, ≈ $0.04 per item |

**Note on tokens.** Claude Code's stream-json output repeats a message's usage on every content
block, so the `input_tokens` field the runner logged during Run 7 counts each API call 2–3
times. The second row collapses those duplicates. The runner is fixed for later runs (see §7).

The per-event `output_tokens` are stream-start snapshots, so Run 7's output and thinking tokens
were not recorded. After the fix, the probe shows Sonnet 5.5 thinks by default: 848 output
tokens, 576 of them thinking, on a two-call prompt. The cost figure comes from Claude Code's
result event and is not affected.

For scale: Run 5 logged a median of about 87.7k input tokens per item, and Run 6 86.6k–89.0k
(`scores*.csv` → `input_tokens`). The tokenizers differ, so read that as "about a third", not an
exact ratio.

## 2. Headline: S1 exact over item-runs, 95% bootstrap interval over items

Taken from `e2_headline_three_scorings.csv`. The interval resamples the 44 verifiable items and
carries their repeats (B = 2000, the v8/v9 seed).

| scoring | object set | Run 5 (2.5 Flash, ×3) | Run 6 (3.8 Flash, ×2) | Run 7 (Sonnet 5.5, ×3) |
| --- | --- | --- | --- | --- |
| strict | standard | 24/132 = 0.182 [0.083, 0.288] | 19/80 = 0.237 [0.120, 0.367] | 36/132 = 0.273 [0.136, 0.409] |
| strict | probe | 9/132 = 0.068 [0.023, 0.121] | 16/80 = 0.200 [0.086, 0.329] | 24/132 = 0.182 [0.068, 0.296] |
| determined-only | standard | 86/132 = 0.651 [0.523, 0.773] | 64/80 = 0.800 [0.682, 0.911] | 123/132 = 0.932 [0.841, 1.000] |
| determined-only | probe | 71/132 = 0.538 [0.409, 0.667] | 61/80 = 0.762 [0.626, 0.887] | 111/132 = 0.841 [0.727, 0.932] |
| determined-only + faithful extras excused | standard | 88/132 = 0.667 [0.538, 0.780] | 67/80 = 0.838 [0.722, 0.947] | 123/132 = 0.932 [0.841, 1.000] |
| determined-only + faithful extras excused | probe | 73/132 = 0.553 [0.424, 0.674] | 62/80 = 0.775 [0.645, 0.899] | 111/132 = 0.841 [0.727, 0.932] |
| request-determined (+PDF Status values) + excused | standard | 88/132 = 0.667 [0.545, 0.788] | 67/80 = 0.838 [0.718, 0.947] | 123/132 = 0.932 [0.841, 1.000] |
| request-determined (+PDF Status values) + excused | probe | 73/132 = 0.553 [0.432, 0.682] | 66/80 = 0.825 [0.706, 0.928] | 123/132 = 0.932 [0.841, 1.000] |

The intervals overlap with Run 6's in every row. The paired view is sharper. Per item, under
determined-only + excused + probe, Run 7 is never worse than Run 6 on any of the 44 items, and
better on 2: IDS4ALL#2 and NL_BIM#1. Against Run 5 it is better on 18 and worse on none. Under
request-determined + probe it is better than Run 6 on 5 items and worse on none.

Under strict + probe, Run 7 is worse than Run 6 on one item and better on none. That item is
NL_BIM#1, "Verdiepingsnaam moet beginnen met niveau-aanduiding". Run 6 invented a regex for the
level prefix, and on the test objects it agreed with the reference's pattern. Run 7 required
`Name` with no pattern, because the request states none. That is the trade the study is about:
determined-only up, strict not up.

Excusing faithful extras changes nothing for Run 7 (`item_runs_with_excused` = 0). None of
Run 7's documents contains a labelled faithful extra, and none has any extra requirement at all
(`err_extra_requirement` = 0 on every item). Its false-positive facets are value, cardinality or
dataType differences on facets the reference also has.

**Repeats.** The three repeats agree on facet content for 46 of 47 items; titles and facet order
vary. The exception is ArcDox#1, which is unverifiable: rep3 added a custom
`Project_Information.FunctionalUnit`. Even without temperature control, Run 7 behaves almost
deterministically, so its 132 item-runs carry about the information of 44. The interval
resamples items, so it is not narrowed by the repeats. The repeats just add little beyond rep1.

## 3. Facet F1 next to S1 (probe object set)

| scoring | Run 5 S1 | Run 5 F1 | Run 6 S1 | Run 6 F1 | Run 7 S1 | Run 7 F1 |
| --- | --- | --- | --- | --- | --- | --- |
| strict | 0.068 | 0.067 | 0.200 | 0.219 | 0.182 | 0.241 |
| determined-only | 0.538 | 0.399 | 0.762 | 0.778 | 0.841 | 0.850 |
| determined-only + faithful extras excused | 0.553 | 0.403 | 0.775 | 0.784 | 0.841 | 0.850 |
| request-determined (+PDF Status values) + excused | 0.553 | 0.403 | 0.825 | 0.814 | 0.932 | 0.905 |

Facet F1 is the mean over all item-runs. S1 is behaviour-exact over the verifiable ones. Run 7
leads on F1 in every scoring, strict included (0.241 against 0.219), even where its strict S1
does not lead.

The text-versus-behaviour gap is smallest for Run 7. Where its text differs from the reference,
it is mostly on values the behaviour also catches, such as the Status enumerations below. Run 5
is the opposite: text F1 (0.40) sits well under S1 (0.54), because many textual misses do not
change verdicts.

## 4. Failure directions, Run 7, determined-only + faithful extras excused + probe

Over 141 item-runs, from `scores_relaxed_excused_probe.csv`:

| `wit_direction` | item-runs |
| --- | --- |
| equivalent | 108 |
| over_strict | 9 (3 items × 3; one of them is behaviour-exact, see IDS4ALL#2 below) |
| under_strict | 15 (5 items × 3) |
| over_strict + under_strict | 0 |
| no_file | 0 |
| witness_unverified | 3 (ArcDox#1 × 3) |
| not executable, no direction | 6 (ArcDox#3, #4 × 3) |

The 9 unverifiable item-runs are the same 3 items that are unverifiable in Runs 5 and 6.
ArcDox#3 and #4 have reference entities that are not concrete IfcRoot classes (IFCUNITASSIGNMENT,
IFCPOSTALADDRESS). For ArcDox#1 the witness cannot type `UnitsInContext`. S1 = 111/132.

Every failing item fails in all three repeats:

| item | direction | F1 | first differing objects (`wit_diverging`) / reason |
| --- | --- | --- | --- |
| IDS_oma_input#10 (ramp) | over_strict | 0.60 | `ref:missing:2 ref:missing:4`. Requires `HandicapAccessible` and `FireExit` where the reference has them optional. The request says "Indication that / whether ...", and server rule 3 says to require such properties with no value. |
| Vienna#7 (IFCMEMBER) | under_strict | 0.57 | `probe:3:*:cand_only`. `Status` = the 7 IFC values plus Neu, Bestand, Abbruch, Temporär, which the request allows ("können auch weiterhin die Werte aus der PDF-Datei verwendet werden"). |
| Vienna#18 (IFCSOLARDEVICE) | under_strict | 0.00 | `probe:1:*:cand_only`. Same Status extension. |
| Vienna#19 (IFCPIPESEGMENT) | under_strict | 0.00 | `probe:1:*:cand_only`. Same Status extension. |
| Vienna#22 (IFCSANITARYTERMINAL) | under_strict | 0.00 | `probe:1:*:cand_only`. Same Status extension. |
| Vienna#9 (IFCRAILING) | under_strict | 0.29 | `ref:badtype:1 cand:full:IFCRAILING` plus the Status extension. `Pset_RailingCommon.Height` has no `ifc_type` in the graph, so the model omitted `dataType` as the instructions say. The reference has IFCPOSITIVELENGTHMEASURE. A graph gap, not a model error. |
| Vienna#25 (IFCSPACE) | labelled over_strict | 0.00 | `cand:full:IFCSPACE`. The document has applicability only. The model tried to encode "Alle Räume sind geschossweise zu modellieren" as a `partOf IFCBUILDINGSTOREY` requirement. The generator's document model accepts only property and attribute requirements, so it rejected `partOf` twice. The model then wrote a requirement-less spec and said so in its reply. Behaviourally it is under-strict: it accepts a space the reference rejects, because the reference's PredefinedType enumeration excludes it. |

Under request-determined scoring, the five Status items become exact. Sonnet emitted the PDF
values in 15 of 15 Status item-runs; 3.8 Flash did in 6 of 8 and 2.5 Flash in none. What remains
is oma_input#10, Vienna#9 and Vienna#25 (9 item-runs; S1 = 123/132).

**A scorer note, metric code untouched.** `wit_direction` comes from `compare()` in
`eval/score.py`, which takes the executor's raw passed set, so an applicable object the candidate
does not pass counts as failed. S1 (`wit_s1`, via `verdicts()`) counts an applicable object as
passing unless the IDS fails it. A spec with no requirements passes nothing and fails nothing. So IDS4ALL#2
("A slab is a structural component ...", a purely descriptive request) is labelled
`over_strict` but is behaviour-exact, S1 = 1. Its reference requirement (entity IFCSLAB on
IFCSLAB applicability) cannot fail, and Run 7's file has the same applicability and no
requirements: neither file rejects anything. Vienna#25 gets the same `over_strict` label while
being behaviourally lenient. The direction labels for requirement-less candidates should be read
with this in mind.

## 5. The request checks during generation

The checks did not fire once: 0 of 146 `generate_ids` calls in 141 item-runs returned
`request_errors`. So the question of whether the model repairs a rejected document did not
arise. The 5 rejected calls were all Pydantic `validation_errors` on Vienna#25's `partOf`
requirement (see §4). Each was followed by a successful call without it.

Replaying the checks over Run 7's logged calls (`python -m eval.replay_checks`, now also reading
the MCP logs) agrees: 0 of 146 calls, 0 of 141 accepted documents. Every server config carried
`IDS_REQUEST_FILE`, so the value checks were active. Sonnet's documents simply contain none of
the defects the checks target: no whitespace names, no Boolean pins, no invented values or
bounds, no truncated enumerations. For comparison, the replay fires on 33 of 130 accepted
documents in Run 5 and 3 of 83 in Run 6 (`e4`, `e5`, regenerated with the Run 7 rows added; the
Run 5/6 rows are unchanged).

So in Run 7 the checks were a safety net that never caught anything. Whatever moved the result
came from the model and the instructions, not from the checks.

## 6. What is not like-for-like with Runs 5/6

The comparison is "the same 47 requests, the same scorer". Everything that produced the
documents differs:

- **Model family.** Claude Sonnet 5.5 against Gemini 2.5 Flash and 3.8 Flash.
- **Sampling.** Runs 5/6 ran at temperature 0. Claude Code exposes no temperature, top-p or
  thinking budget, so Run 7 ran at its defaults, which were not recorded. Effort was Claude
  Code's default for the model; the desktop session's `CLAUDE_EFFORT` was deliberately not
  passed on (§7).
- **Instructions.** Run 7 used `eval/claude_system_prompt.md` plus the server's `INSTRUCTIONS`
  (sha256 `c561fcaa…` and `8688df60…` in `run.json`). These carry the v9 rules: record vs.
  require, values only from the request or `allowed_values`, complete enumerations, coverage.
  Runs 5/6 used the v8 prompt (sha `11f3d84b…`).
- **Retrieval.** Two-step: `query_class` returns codes only, then `query_pset` returns one set in
  full. Runs 5/6 got every property set of the class in full from `query_class`. Tool results
  were ≤ 7.7k characters, against a median largest result of 86.8k.
- **Checks.** The request checks were on in `generate_ids`; Runs 5/6 had none. They never fired
  (§5).
- **Agent loop.** Claude Code's own loop (max 14 turns, none reached) replaced the Gemini
  function-calling loop in `eval/generate.py`. The v9 server refuses a fifth failing
  `generate_ids` call; Runs 5/6 had no such cap. It never came into play: no item-run failed
  more than twice.
- **Repeats.** Three, like Run 5. Run 6 has 47 + 39.

Identical across runs: the 47 user messages (byte-compared against Runs 5 and 6), the item list,
`spec_tasks.jsonl`, the annotation files, `eval/score.py` and `eval/witness.py`, the test models,
and the graph content (the `graph_psets.json` and `graph_ptypes.json` snapshots equal Run 6's).

## 7. Problems hit and what changed

1. **Neo4j credentials.** `docker inspect aeckg-eval-neo4j` gave the password, and the container
   was up on 7687 with the full graph. The stale `eval.win_run` driver was no longer running, and
   no `run7-*` directories existed.
2. **Hidden CLI flags.** Claude Code 2.1.296 accepts `--system-prompt-file` and `--max-turns` but
   leaves them out of `--help`, so the runner refused to start. `cli_flags()` now confirms flags
   missing from the help text with a fail-fast call: a nonexistent prompt file errors before any
   model call, and an unknown option would say "unknown option".
3. **Environment leaking from the parent session.** This run was driven from a Claude Code desktop
   session, whose environment carries `CLAUDECODE`, `CLAUDE_CODE_*` (entrypoint, session id,
   messaging socket, extra tools), `CLAUDE_EFFORT=xhigh` and `ANTHROPIC_BASE_URL`. The child
   `claude -p` would have inherited all of it. `child_env()` now drops `CLAUDE*` and
   `ANTHROPIC_*` variables, keeping `CLAUDE_CONFIG_DIR`; that also keeps an API key from billing
   the run. The probe passed with this: only the five `mcp__ifc__*` tools, the file read and the
   shell command impossible, `apiKeySource: none`.
4. **Token accounting.** See the note in §1. `digest()` now counts each message id once and the
   entry stores the result event's `usage` and `modelUsage`. `output_tokens` and
   `thinking_tokens` come from the result. All three Run 7 repeats were generated before this
   fix; their figures above are de-duplicated after the fact.
5. **Scoring without the graph.** The first scoring of rep1 ran in a shell without the `NEO4J_*`
   variables. `eval.common.graph_psets` fell back to the `.env` Aura URI, failed, and left
   `ifc_only` empty, so every analysis would have dropped Run 7. The graph snapshots were then
   written from the live container (they equal Run 6's) and rep1 was rescored. Nothing else in
   the scores depends on the graph.
6. **`replay_checks` and the MCP log shape.** It read only the Gemini argument names
   (`ids_json_string`) and learned property sets only from `query_class`. It now reads `ids` and
   learns from `query_pset` the way the server does. Rerun over Runs 5/6, it reproduces the
   committed `e4`/`e5` rows exactly, apart from the pydantic version in error-message URLs.
7. **The `_rv` standard-object-set scoring.** The handover's list and `win_run.py` had only the
   probe variant, but `analysis_extras` reads both, as Runs 5/6 have. The standard variant was
   scored too, and `win_run.py` now includes it.
8. **`GROUPS`.** `analysis_extras` imports `GROUPS` from `analysis_probe`, so the one entry
   added there covers both tables.
9. **Three repeats instead of two.** At ≈ $0.04 and 15 s per item, the usage window allowed it,
   and it matches Run 5. Repeats ran partly in parallel (rep2 alongside rep1 and rep3). Each
   item is its own `claude -p` process with its own server, so they do not interact.

Files: `eval/runs/run7-claude-rep{1,2,3}/` (not committed). New rows in
`eval/reports/v8/p1_probe_vs_standard.csv`, `p2_probe_flips.csv`,
`eval/reports/v9/e2_headline_three_scorings.csv`, `e4_replay_checks.csv` and
`e5_replay_vs_verdict.csv`.
