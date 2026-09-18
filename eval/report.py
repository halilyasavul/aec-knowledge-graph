"""Print the study summary for a scored run.

    python -m eval.report <run_dir>

All items count. `leak` (the request text contains a target property name) is not a filter;
block 1 only shows it as a breakdown.
Surfaces (see eval/score.py): wit = witness models built from each reference (primary);
vf0 = sample buildings, ifcVersion ignored; vf1 = sample buildings, version-filtered.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from collections import Counter

from eval.score import ERROR_COLS, FACET_KINDS, prf

MIN_DISTINCT_F1 = 10


def pct(x, n):
    return f"{x}/{n} = {100 * x / n:.1f}%" if n else f"{x}/0 = n/a"


def hr(title):
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


SURFACES = ("wit", "vf0", "vf1")
LABEL = {"wit": "witness models", "vf0": "sample buildings", "vf1": "sample buildings, version-filtered"}


def outcome_block(df: pd.DataFrame, mode: str) -> float | None:
    col = f"{mode}_outcome_equiv"
    ext = df[df[col].notna()]
    n, k = len(ext), int(ext[col].sum()) if len(ext) else 0
    if mode == "wit":
        ver = int(df.get("wit_verified", pd.Series(dtype=float)).fillna(0).sum())
        extra = f"items with a usable witness: {n}/{len(df)}; witness verified against its reference: {ver}"
    else:
        skipped = int(df[f"{mode}_models_skipped"].sum())
        pairs = int(df[f"{mode}_models_used"].sum() + skipped)
        extra = (f"items with >=1 usable model: {n}/{len(df)}; (item,model) pairs skipped because the "
                 f"reference applies to 0 elements: {skipped}/{pairs}")
    print(f"  [{mode:<3}] outcome equivalence: {pct(k, n):<18} {LABEL[mode]}  ({extra})")
    return k / n if n else None


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1:
        sys.exit(__doc__)
    run_dir = Path(argv[0])
    df = pd.read_csv(run_dir / "scores.csv")
    items = df
    print(f"run: {run_dir}   items scored: {len(df)}   (property name appears in request text: {int(df.leak.sum())})")

    # ------------------------------------------------------------------ 1
    hr("1. OUTCOME EQUIVALENCE")
    rates = {m: outcome_block(items, m) for m in SURFACES}
    for m, r in rates.items():
        if r is not None and r in (0.0, 1.0):
            print(f"\n  !!! STOP: [{m}] outcome equivalence is {r:.0%}. The corpus or the applicability filter "
                  f"is driving this, not the models. Do not interpret it.")
    for flag, lab in ((0, "name NOT in request text"), (1, "name appears in request text")):
        sub = df[(df.leak == flag) & df.wit_outcome_equiv.notna()]
        if len(sub):
            print(f"  breakdown [wit], {lab:<30}: equivalent {pct(int(sub.wit_outcome_equiv.sum()), len(sub))}, "
                  f"mean facet-F1 {sub.facet_f1.mean():.2f}")
    ex = items[items.vf0_outcome_equiv.notna()]
    if len(ex):
        allfail = ex[ex.vf0_n_ref_pass == 0]
        print(f"  surface check [vf0]: reference FAILS EVERY applicable element in {pct(len(allfail), len(ex))} items "
              f"-> equivalence there {pct(int(allfail.vf0_outcome_equiv.sum()), len(allfail))}; "
              f"where the reference passes >=1 element: "
              f"{pct(int(ex[ex.vf0_n_ref_pass > 0].vf0_outcome_equiv.sum()), int((ex.vf0_n_ref_pass > 0).sum()))}")
        print("  (a reference that fails everything cannot see property-level errors: any candidate that also\n"
              "   requires something the model lacks is 'equivalent'. Read the headline against this line.)")
        print("  divergence direction [vf0]: " +
              ", ".join(f"{k}={v}" for k, v in ex.vf0_direction.value_counts().items()))
        acc = ex.vf0_verdict_acc.dropna()
        kap = ex.vf0_verdict_kappa.dropna()
        print(f"  applicability Jaccard [vf0] mean={ex.vf0_app_jaccard.mean():.3f}   "
              f"verdict accuracy on intersection mean={acc.mean():.3f} (n={len(acc)})   "
              f"Cohen kappa mean={kap.mean():.3f} (defined for n={len(kap)}; undefined when both sides "
              f"give one verdict to every element)")

    ew = items[items.wit_outcome_equiv.notna()] if "wit_outcome_equiv" in items else items.iloc[0:0]
    if len(ew):
        print("  divergence direction [wit]: " +
              ", ".join(f"{k}={v}" for k, v in ew.wit_direction.value_counts().items()))
        acc, kap = ew.wit_verdict_acc.dropna(), ew.wit_verdict_kappa.dropna()
        print(f"  applicability Jaccard [wit] mean={ew.wit_app_jaccard.mean():.3f}   verdict accuracy on "
              f"intersection mean={acc.mean():.3f} (n={len(acc)})   Cohen kappa mean={kap.mean():.3f} (n={len(kap)})")
        kinds = Counter(v.split(":")[0] for d in ew.wit_diverging.dropna() for v in str(d).split())
        print("  witness variants where candidate and reference disagree: " +
              ", ".join(f"{k}={v}" for k, v in kinds.most_common()))
        print("  (full/altvalue/edge = candidate rejects a conforming element; missing/badvalue/badtype = accepts\n"
              "   a broken one; decoy = applies where the reference does not)")

    # ------------------------------------------------------------------ intensional summary
    hr("A. FACET-LEVEL (intensional)")
    gen = items[items.status == "ok"]
    tp, fp, fn = items.facet_tp.sum(), items.facet_fp.sum(), items.facet_fn.sum()
    p, r, f = prf(tp, fp, fn)
    print(f"  micro P={p:.3f} R={r:.3f} F1={f:.3f}   macro F1={items.facet_f1.mean():.3f}   "
          f"(name-level 'loose' macro F1={items.loose_f1.mean():.3f})")
    print(f"  items with an IDS: {pct(len(gen), len(items))}   XSD-valid: {pct(int(gen.xsd_valid.sum()), len(gen))}   "
          f"ifcVersion in XSD set: {pct(int(gen.ifcversion_xsd_ok.sum()), len(gen))}   "
          f"ifcVersion covers IFC4X3_ADD2: {pct(int(gen.ifcversion_covers_models.sum()), len(gen))}")
    print(f"  ifcVersion emitted: " + ", ".join(f"{k}={v}" for k, v in gen.ifc_version.value_counts().items()))
    print(f"  applicability entity/predefinedType exact match: {pct(int(gen.app_match.sum()), len(gen))}")
    print(f"  {'facet type':<16}{'TP':>5}{'FP':>5}{'FN':>5}{'P':>8}{'R':>8}{'F1':>8}")
    for k in FACET_KINDS:
        a, b, c = (int(items[f"{k}_{x}"].sum()) for x in ("tp", "fp", "fn"))
        if a + b + c:
            p, r, f = prf(a, b, c)
            print(f"  {k:<16}{a:>5}{b:>5}{c:>5}{p:>8.3f}{r:>8.3f}{f:>8.3f}")
    if "ref_psets_not_in_graph" in items:
        n_ref = int(items.ref_psets_not_in_graph.sum())
        print(f"  reference property facets whose pset is not in the graph (ungroundable): {n_ref}")

    # ------------------------------------------------------------------ 2
    hr("2. THE TWO NUMBERS (items with extensional signal)")
    for m in SURFACES:
        e = items[items[f"{m}_outcome_equiv"].notna()]
        hi, lo = e[e.facet_f1 >= 0.9], e[e.facet_f1 < 0.7]
        print(f"  [{m}] P(divergent | facet-F1 >= 0.9) = {pct(int((hi[f'{m}_outcome_equiv'] == 0).sum()), len(hi))}")
        print(f"  [{m}] P(equivalent | facet-F1 <  0.7) = {pct(int((lo[f'{m}_outcome_equiv'] == 1).sum()), len(lo))}")

    # ------------------------------------------------------------------ 3
    S = "wit"
    hr(f"3. FACET-F1 vs OUTCOME EQUIVALENCE [{S}: {LABEL[S]}]")
    e = items[items[f"{S}_outcome_equiv"].notna()]
    vals = e.facet_f1.round(4)
    distinct = vals.nunique()
    print(f"  distinct facet-F1 values: {distinct}  -> {sorted(vals.unique().tolist())}")
    tab = e.groupby(vals)[f"{S}_outcome_equiv"].agg(["count", "sum"])
    print(f"  {'facet-F1':>9} {'n':>4} {'equiv':>6}  scatter (x = F1 bucket, #=equivalent, .=divergent)")
    for f1, row in tab.iterrows():
        print(f"  {f1:>9.3f} {int(row['count']):>4} {int(row['sum']):>6}  "
              + "#" * int(row["sum"]) + "." * int(row["count"] - row["sum"]))
    if distinct < MIN_DISTINCT_F1:
        print(f"\n  Only {distinct} distinct facet-F1 values (< {MIN_DISTINCT_F1}). Spearman rho NOT reported: "
              f"with this few values it is a range-restriction artifact, not a finding.")
    else:
        rho = e.facet_f1.corr(e[f"{S}_outcome_equiv"], method="spearman")
        print(f"\n  Spearman rho(facet-F1, outcome equivalence) = {rho:.3f}  (n={len(e)})")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        rng = np.random.default_rng(0)
        fig, ax = plt.subplots(figsize=(6, 3.2))
        ax.scatter(e.facet_f1, e[f"{S}_outcome_equiv"] + rng.uniform(-0.06, 0.06, len(e)), s=18, alpha=0.7, color="#3b6ea5")
        ax.set_yticks([0, 1], ["divergent", "equivalent"])
        ax.set_xlabel("facet-level F1 (intensional)")
        ax.set_xlim(-0.05, 1.05)
        ax.set_title(f"Facet F1 vs execution outcome, n={len(e)} items ({LABEL[S]})", fontsize=10)
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        fig.savefig(run_dir / "f1_vs_equivalence.png", dpi=150)
        print(f"  scatter -> {run_dir / 'f1_vs_equivalence.png'}")
    except Exception as ex_:
        print(f"  (scatter PNG skipped: {ex_})")

    # ------------------------------------------------------------------ 4
    hr("4. ERROR FREQUENCY ")
    print(f"  {'error':<28}{'occurrences':>12}{'items':>8}")
    for c in ERROR_COLS:
        col = f"err_{c}"
        if col in items:
            print(f"  {c:<28}{int(items[col].sum()):>12}{int((items[col] > 0).sum()):>8}")
    print("  (hallucinated_pset = pset not in graph; applicability_* from executed element sets [wit, else vf0];\n"
          "   empty_restriction = constraint the pipeline silently dropped; bad_ifcversion = not in XSD set)")

    # ------------------------------------------------------------------ 5
    hr("5. COST AND LATENCY PER ITEM (all generated items)")
    for col, lab, fmt in (("wall_ms", "wall-clock s", lambda v: f"{v / 1000:.1f}"),
                          ("cost_usd", "cost USD", lambda v: f"{v:.4f}"),
                          ("input_tokens", "input tokens", lambda v: f"{v:,.0f}"),
                          ("output_tokens", "output tokens (+thinking)", lambda v: f"{v:,.0f}"),
                          ("n_tool_calls", "tool calls", lambda v: f"{v:.1f}"),
                          ("generate_ids_attempts", "generate_ids attempts", lambda v: f"{v:.1f}")):
        s = df[col].dropna()
        if len(s):
            print(f"  {lab:<28} mean {fmt(s.mean()):>9}  median {fmt(s.median()):>9}  "
                  f"p90 {fmt(s.quantile(0.9)):>9}  total {fmt(s.sum()):>10}")


if __name__ == "__main__":
    main()
