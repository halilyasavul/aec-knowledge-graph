# Ishigaki-IDS-Bench (vendored copy)

`data/test.jsonl` and `data/README.md` are an unchanged copy of
https://huggingface.co/datasets/ONESTRUCTION/Ishigaki-IDS-Bench (DOI 10.57967/hf/8873),
fetched 2026-10-22, licence CC BY 4.0. Kanazawa et al., "Ishigaki-IDS-Bench: A Benchmark
for Generating Information Delivery Specification from BIM Information Requirements",
arXiv:2605.22079.

166 rows, 83 English. Each row: `messages` (the last assistant message is the gold IDS),
`language`, `input_format` (natural_language | csv), `turn_type`, `domain`, `ifc_versions`.

Why it is here: the requests were written first and adjusted until the gold IDS is uniquely
determined by them — the property our own test set lacks (see `eval/reports/v9/README.md`).

What it does not test: of ~290 property facets in the English gold, 9 use a standard
`Pset_`/`Qto_` set; 227 use the benchmark's "any user-defined pset" convention
`^(?!(Pset_|Qto_)).+` and the rest named custom psets. It exercises transcription, IDS syntax
and value constraints, not mapping to IFC vocabulary. 24/83 gold files have more than one
specification; 43/128 specifications use attribute or property facets in applicability.

Held-out discipline: do not read the gold files while changing the generator.
