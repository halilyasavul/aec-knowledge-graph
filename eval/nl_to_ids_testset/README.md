# eval/ — natural-language -> IDS test set and scorer

Three steps. Only step 2 needs your machine.

| step | script | needs | where |
|---|---|---|---|
| 1. build the test set | `extract_testset.py` | nothing (public .ids files) | anywhere — already done, outputs committed |
| 2. generate candidate IDS | your own code | Gemini key, `.env`, live Neo4j graph | **your machine** |
| 3. score | `harness.py` + `score.py` | ifctester + IFC models | anywhere |

## 1 — test set (done)

    python extract_testset.py refs/

`spec_tasks.jsonl` — one item per specification. `prompt` = the applicable entity plus
every requirement written in plain language; `target` = the full list of facets expected.
This is the realistic authoring task.

`facet_tasks.jsonl` — one item per requirement. Single description in, single facet out.
A precise diagnostic of whether schema lookup works.

`leak` / `any_leak` marks items whose description text names the property set or property
it is meant to elicit. **Filter these out** — they turn the task into copying a string.

Reference specifications are real published requirements (City of Vienna building permit
via TU Wien, CC BY 4.0; buildingSMART Occupant Movement Analysis, CC BY-ND 4.0; Dutch
RVB/ILS; Austrian and Italian academic sets). Not the synthetic conformance fixtures.

## 2 — generation (your machine)

For each item, feed `prompt` to the system and write out the IDS it produces. Keep one
file per item id. Log the model id, the full prompt, the tool-call trace, tokens and cost.
Pin the model version — unpinned is not reproducible.

## 3 — scoring

    python score.py generated/ spec_tasks.jsonl models/

Reports two things per item:
  - facet-level precision / recall / F1 against `target`   (what the field measures)
  - pass/fail verdict agreement over element GUIDs when both the reference and the
    candidate IDS are executed against the same IFC model  (what actually matters)

The models are only a surface for detecting disagreement — they do not have to be the
buildings the requirements were written for.
