---
license: cc-by-4.0
task_categories:
- text-generation
language:
- ja
- en
tags:
- ids
- ifc
- bim
- construction
- buildingSMART
pretty_name: Ishigaki-IDS-Bench
configs:
- config_name: default
  data_files:
  - split: test
    path: data/test.jsonl
---

# Ishigaki-IDS-Bench

Ishigaki-IDS-Bench is a bilingual benchmark for generating buildingSMART IDS 1.0 XML from user-facing building requirements.

## Data Format

Each row uses the common conversational `messages` format:

```json
{
  "id": "row-0001",
  "messages": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "language": "ja",
  "input_format": "natural_language",
  "turn_type": "single_turn",
  "domain": "architectural",
  "ifc_versions": ["IFC4"]
}
```

The final assistant message is the gold IDS XML. The evaluation input is `messages[:-1]`.

## Fields

- `id`: example identifier.
- `messages`: multi-turn conversation in `role`/`content` format.
- `language`: `ja` or `en`.
- `input_format`: `natural_language` or `csv`.
- `turn_type`: `single_turn` or `multi_turn`.
- `domain`: `architectural`, `structural`, `mep`, or `general`.
- `ifc_versions`: target IFC version labels.

## Citation

```bibtex
@misc{kanazawa2026ishigakiidsbench,
  title = {Ishigaki-IDS-Bench: A Benchmark for Generating Information Delivery Specification from BIM Information Requirements},
  author = {Ryo Kanazawa and Koyo Hidaka and Teppei Miyamoto and Takayuki Kato and Tomoki Ando and Chenguang Wang and Dayuan Jiang and Naofumi Fujita and Shuhei Saitoh and Atomu Kondo and Koki Arakawa and Daiho Nishioka},
  year = {2026},
  eprint = {2605.22079},
  archivePrefix = {arXiv},
  primaryClass = {cs.CL},
  doi = {10.48550/arXiv.2605.22079},
  url = {https://arxiv.org/abs/2605.22079}
}
```
