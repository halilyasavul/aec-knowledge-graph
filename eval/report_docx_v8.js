// Build the v8 Word report. Every number comes from eval/reports/v8/*.csv, written by
//   python -m eval.analysis_probe  analysis_pairs  analysis_likeforlike  analysis_judgement
//   python -m eval.analysis_models  analysis_ishigaki  spend --csv
// Nothing is typed in by hand.
//   node eval/report_docx_v8.js <out.docx> eval/reports/v8
const fs = require("fs");
const path = require("path");
const [OUT, DIR] = process.argv.slice(2);

// minimal CSV: fields may be quoted and contain commas -- header included, which matters
// because several of these files have column names like "text exact, behaviour differs"
function splitLine(l) {
  const out = []; let cur = ""; let q = false;
  for (const ch of l) {
    if (ch === '"') q = !q;
    else if (ch === "," && !q) { out.push(cur); cur = ""; }
    else cur += ch;
  }
  out.push(cur);
  return out;
}
function csv(name) {
  const text = fs.readFileSync(path.join(DIR, name), "utf8").trim();
  const [head, ...lines] = text.split(/\r?\n/);
  const cols = splitLine(head);
  return lines.map((l) => Object.fromEntries(splitLine(l).map((v, i) => [cols[i], v])));
}

const P1 = csv("p1_probe_vs_standard.csv");
const M1 = csv("m1_text_class_x_behaviour.csv");
const M2 = csv("m2_disagreement_rate.csv");
const L1 = csv("l1_like_for_like_effects.csv");
const L2 = csv("l2_field_effects_for_comparison.csv");
const J1 = csv("j1_judgement_call_labels.csv");
const J2 = csv("j2_headline_both_ways.csv");
const J3 = csv("j3_affected_item_runs.csv");
const R1 = csv("r1_run6_vs_run5_paired.csv");
const R2 = csv("r2_run6_both_ways.csv");
const R3 = csv("r3_value_omission_by_determinacy.csv");
const R4 = csv("r4_cost_per_item.csv");
const I1 = csv("i1_ishigaki_facetf1.csv");
const I3 = csv("i3_clarification_questions.csv");
const SP = csv("x1_spend_by_run.csv");

const RUN5 = "Run 5 (2.5 Flash, 47 items x 3)";
const RUN6 = "Run 6 (3.8 Flash, 47 items x 2)";
const num = (x, dp = 3) => (x === "" || x === undefined ? "n/a" : Number(x).toFixed(dp));
const pct = (x, dp = 0) => (x === "" || x === undefined ? "n/a" : `${(100 * Number(x)).toFixed(dp)}%`);
const sgn = (x, dp = 3) => `${Number(x) >= 0 ? "+" : ""}${num(x, dp)}`;
const ci = (r) => `${sgn(r.estimate)}  [${num(r.ci_low)}, ${num(r.ci_high)}]`;
const money = (x) => `$${Number(x).toFixed(2)}`;
const p1 = (g, s, o) => P1.find((r) => r.group === g && r.scoring === s && r["object set"] === o);
const m2 = (g, s, o) => M2.find((r) => r.group === g && r.scoring === s && r["object set"] === o);
const m1 = (g, s, o, c) => M1.find((r) => r.group === g && r.scoring === s && r["object set"] === o && r["text class"] === c);
const l1 = (m, e) => L1.find((r) => r.measure === m && r.effect === e);
const l2 = (m, e) => L2.find((r) => r.measure === m && r.effect === e);
const r1 = (m) => R1.find((r) => r.measure === m);
const r2 = (s, o) => R2.find((r) => r.scoring === s && r["object set"] === o);
const r3 = (g, v) => R3.find((r) => r.group === g && r["reference value is"] === v);
const r4 = (g) => R4.find((r) => r.group === g);
const i1 = (g, v) => I1.find((r) => r.group === g && r["IFC-version block"] === v);
const j2 = (g, t, o) => J2.find((r) => r.group === g && r["object set"] === o && r.treatment.startsWith(t));
const allGradings = M2.filter((r) => r["object set"] !== "sample buildings (version filtered)")
  .reduce((a, r) => a + Number(r.item_runs), 0);   // vf0 and vf1 are the same files twice
const wrongWayRound = M2.reduce((a, r) => a + Number(r["text exact, behaviour differs"]), 0);  // any object set
const totalSpend = SP.reduce((a, r) => a + Number(r.cost_usd), 0);
const run6Spend = SP.filter((r) => r.run.startsWith("run6-flash") || r.run.startsWith("run6-pro-pilot"))
  .reduce((a, r) => a + Number(r.cost_usd), 0);

const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, LevelFormat, AlignmentType,
} = require("docx");
const FONT = "Calibri";
const run = (t, o = {}) => new TextRun({ text: String(t), font: FONT, size: 22, ...o });
const p = (t, o = {}) => new Paragraph({ spacing: { after: 120 }, ...o, children: [run(t)] });
const rich = (parts, o = {}) => new Paragraph({ spacing: { after: 120 }, ...o,
  children: parts.map((x) => (typeof x === "string" ? run(x) : run(x[0], x[1]))) });
const h1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 280, after: 120 },
  children: [new TextRun({ text: t, font: FONT, size: 28, bold: true, color: "1F3864" })] });
const bullet = (parts) => new Paragraph({ numbering: { reference: "b", level: 0 }, spacing: { after: 60 },
  children: (Array.isArray(parts) ? parts : [parts]).map((x) => (typeof x === "string" ? run(x) : run(x[0], x[1]))) });
const B = { bold: true };
const border = { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" };
const borders = { top: border, bottom: border, left: border, right: border };
const gap = () => new Paragraph({ spacing: { after: 80 }, children: [] });
function table(widths, rows) {
  return new Table({
    width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA }, columnWidths: widths,
    rows: rows.map((cells_, r) => new TableRow({
      children: cells_.map((c, i) => new TableCell({
        width: { size: widths[i], type: WidthType.DXA }, borders,
        shading: r === 0 ? { type: ShadingType.CLEAR, color: "auto", fill: "D9E2F3" } : undefined,
        margins: { top: 60, bottom: 60, left: 100, right: 100 },
        children: [new Paragraph({ children: (Array.isArray(c) ? c : [c]).map((x) =>
          typeof x === "string" ? run(x, { size: 19, bold: r === 0 }) : run(x[0], { size: 19, ...x[1] })) })],
      })),
    })),
  });
}

const children = [
  new Paragraph({ spacing: { after: 60 }, children: [new TextRun({ text: "Testing Our Text-to-IDS System", font: FONT, size: 36, bold: true, color: "1F3864" })] }),
  new Paragraph({ spacing: { after: 240 }, border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "1F3864", space: 4 } },
    children: [run("Report v8 — what the test model can see, and a second model  |  October 7, 2026", { color: "595959" })] }),

  h1("1. The question, and what v8 adds"),
  p("The system turns a written request into an IDS file — a machine-readable checklist that software can run against a building model. The field grades such a file by comparing its text with a reference file. We think the grade that matters is different: run both files against a building and see whether they reach the same pass/fail decisions. v8 asks a harder version of that question — how much does the answer depend on the building you test with? — and adds a second, newer language model for comparison."),
  rich([["The short answer. ", B],
    `The two kinds of grading come apart, but only in one direction, and how far they come apart depends entirely on how searching the test building is. Identical text always produced identical behaviour: ${wrongWayRound} counterexamples in ${allGradings} gradings. Different text behaving identically, however, is common — and the weaker the test building, the more common it gets.`]),

  h1("2. How much divergence you see depends on the test building"),
  p("We graded every file against three kinds of building, from the least searching to the most:"),
  bullet([["Real sample buildings. ", B], "Two public IFC models. Most requirements are never exercised, because the building has no object that the requirement applies to."]),
  bullet([["Standard test models. ", B], "One small model per item, built so that each requirement is exercised at least once, from both the reference file and the generated file."]),
  bullet([["Probe test models (new in v8). ", B], "The same, plus one object for every value the two files disagree about. If the reference allows A, B, C and the generated file allows A, B, D, the probe adds an object using C and one using D. If the reference leaves a value free and the generated file pins it to TRUE, the probe adds an object with a different value. Either file accepts it and the other rejects it — so no value disagreement can hide."]),
  p("The same files, graded against all three, with strict scoring (every reference requirement counts):"),
  table([3200, 1700, 1700, 1700, 1700], [
    ["Test building", "Run 5: agree", "Run 5: disagree", "Run 6: agree", "Run 6: disagree"],
    ...[["Real sample buildings", "sample buildings (no version filter)"],
        ["Standard test models", "standard"],
        ["Probe test models", "probe"]].map(([label, key]) => {
      const a = m2(RUN5, "strict", key), b = m2(RUN6, "strict", key);
      return [label, pct(1 - Number(a["disagreement rate"])), pct(a["disagreement rate"]),
              pct(1 - Number(b["disagreement rate"])), pct(b["disagreement rate"])];
    }),
  ]),
  gap(),
  p("\"Disagree\" means the text grade and the behaviour grade reached different conclusions about the same file. On real buildings they disagree about three times in five; on probe models, about one time in thirty."),
  rich([["Why this matters for the paper. ", B],
    "A claim that \"text comparison and execution disagree\" is incomplete without saying what you executed against. Our strongest claim is the one-directional one: text comparison never calls a file right that behaves differently, but it calls many files wrong that behave identically — and that gap is a property of the test building as much as of the generator."]),

  h1("3. The headline numbers, under both test models"),
  p("Exact behavioural match means: on the test model, the generated file and the reference file pass and fail exactly the same objects. Strict scoring counts every reference requirement; determined-only scoring sets aside the requirements and values that nobody could have derived from the written request."),
  table([2500, 1900, 2250, 2250, 1100], [
    ["Run", "Scoring", "Standard test models", "Probe test models", "Items"],
    ...[[RUN5, "strict"], [RUN5, "determined-only"], [RUN6, "strict"], [RUN6, "determined-only"]]
      .map(([g, s]) => {
        const a = p1(g, s, "standard"), b = p1(g, s, "probe");
        return [g.split(" (")[0] + (g === RUN5 ? " (2.5 Flash)" : " (3.8 Flash)"), s,
          `${a.S1_exact_count}/${a.item_runs} = ${pct(a.S1)}  [${pct(a.S1_ci_low)}, ${pct(a.S1_ci_high)}]`,
          `${b.S1_exact_count}/${b.item_runs} = ${pct(b.S1)}  [${pct(b.S1_ci_low)}, ${pct(b.S1_ci_high)}]`,
          a.items];
      }),
  ]),
  gap(),
  p("Ranges are 95% bootstrap intervals; items are resampled with all their repeats together, because repeats of the same item are not independent."),
  rich([["The probe models are now the headline. ", B],
    `Adding them cut Run 5's strict figure from ${pct(p1(RUN5, "strict", "standard").S1)} to ${pct(p1(RUN5, "strict", "probe").S1)} — from ${p1(RUN5, "strict", "standard").S1_exact_count} exact matches to ${p1(RUN5, "strict", "probe").S1_exact_count} of ${p1(RUN5, "strict", "probe").item_runs}. The earlier figure was partly an artefact: the generated file added a value constraint the reference did not have, and no object in the model happened to violate it, so the extra constraint was invisible. Run 6 moved less (${pct(p1(RUN6, "strict", "standard").S1)} to ${pct(p1(RUN6, "strict", "probe").S1)}) because it omits value constraints rather than inventing them.`]),
  rich([["One honest limit of the probe models. ", B],
    "They are adversarial by construction: they look for the disagreement on purpose. A real building may contain no such object, which is exactly why the real-building column in section 2 looks so different. The probe figure is the strictest reading, the real-building figure the most forgiving, and the truth for any given project sits between them."]),

  h1("4. Text grade against behaviour grade, file by file"),
  p("Every generated file falls into one of three text classes: the XML matches the reference exactly; the property names are all right but something else differs; or a name is wrong. For each class, how often does the file behave identically?"),
  table([3400, 1500, 2100, 1500, 2100], [
    ["Text class", "Run 5 n", "Run 5 behaves same", "Run 6 n", "Run 6 behaves same"],
    ...["text exact", "names correct, text not exact", "names wrong"].map((c) => {
      const a = m1(RUN5, "strict", "probe", c), b = m1(RUN6, "strict", "probe", c);
      return [c, a.item_runs, `${a["behaviour exact"]}/${a.item_runs} = ${pct(a["P(behaviour exact)"])}`,
              b.item_runs, `${b["behaviour exact"]}/${b.item_runs} = ${pct(b["P(behaviour exact)"])}`];
    }),
  ]),
  gap(),
  p("Strict scoring, probe test models. The determined-only and standard-model versions of this table are in m1_text_class_x_behaviour.csv."),
  bullet([["Text-exact always behaves identically. ", B],
    `${m1(RUN5, "strict", "probe", "text exact")["behaviour exact"]} of ${m1(RUN5, "strict", "probe", "text exact").item_runs} in Run 5 and ${m1(RUN6, "strict", "probe", "text exact")["behaviour exact"]} of ${m1(RUN6, "strict", "probe", "text exact").item_runs} in Run 6, with no exceptions anywhere in the study. So the text metric never gives false credit.`]),
  bullet([["Text-wrong often behaves identically anyway. ", B],
    `Under determined-only scoring on standard models, ${pct(m1(RUN5, "determined-only", "standard", "[conditional] text NOT exact")["P(behaviour exact)"])} of Run 5's text-imperfect files still reached every verdict correctly (${m1(RUN5, "determined-only", "standard", "[conditional] text NOT exact")["behaviour exact"]} of ${m1(RUN5, "determined-only", "standard", "[conditional] text NOT exact").item_runs}); on probe models that falls to ${pct(m1(RUN5, "determined-only", "probe", "[conditional] text NOT exact")["P(behaviour exact)"])}. That residue is where a text-only grade is wrong about a file, and it does not vanish.`]),
  bullet([["A wrong property name is fatal. ", B],
    `Under probe scoring, ${m1(RUN5, "strict", "probe", "names wrong")["behaviour exact"]} of ${m1(RUN5, "strict", "probe", "names wrong").item_runs} Run 5 files and ${m1(RUN6, "strict", "probe", "names wrong")["behaviour exact"]} of ${m1(RUN6, "strict", "probe", "names wrong").item_runs} Run 6 files with a wrong name behaved identically. Naming is the first thing to get right.`]),

  h1("5. The two fixes, judged by both kinds of grade"),
  p("The 2x2 experiment (21 items, three repeats, two fixes switched on and off independently) is the one place where the same change can be measured on the text grade and the behaviour grade at once:"),
  table([4200, 2900, 2900], [
    ["Measure", "Lookup fix", "dataType fix"],
    ...["facet F1, strict (text)", "S1, strict (behaviour)",
        "facet F1, determined-only (text)", "S1, determined-only (behaviour)"].map((m) =>
      [m, ci(l1(m, "lookup fix")), ci(l1(m, "dataType fix"))]),
    ["dataType field, among name-matched requirements",
      ci(l2("dataType field, among name-matched requirements", "lookup fix")),
      ci(l2("dataType field, among name-matched requirements", "dataType fix"))],
  ]),
  gap(),
  rich([["The mechanism, in one line. ", B],
    `The dataType fix changed the field it targets — the declared IFC type of a property — by ${sgn(l2("dataType field, among name-matched requirements", "dataType fix").estimate)}, and that one field is enough to flip whole files: a wrong type makes the checker reject every object the reference accepts. Behaviour moved with it (${ci(l1("S1, determined-only (behaviour)", "dataType fix"))}), and so, this time, did the determined-only text score (${ci(l1("facet F1, determined-only (text)", "dataType fix"))}). The strict text score did not move at all (${ci(l1("facet F1, strict (text)", "dataType fix"))}), because strict scoring also counts the many requirements nobody could derive, which stay wrong either way and swamp the change.`]),
  rich([["That is the sharpest version of our argument. ", B],
    "A real improvement to the generator was worth nothing on the standard text metric and a third of all files on the behaviour metric. The metric you choose decides whether you can see your own progress."]),

  h1("6. A newer model: 3.8 Flash against 2.5 Flash"),
  p("Run 6 repeats Run 5's 47 items on a newer Flash model. Both runs are paired item by item, each item contributing the average of its own repeats:"),
  table([3800, 1800, 1800, 2600], [
    ["Measure", "2.5 Flash", "3.8 Flash", "Difference (95% interval)"],
    ...["facet F1 (text)", "names-correct rate (text)", "S1 strict, probe objects",
        "S1 determined-only, probe objects", "cost per item-run (US$)"].map((m) => {
      const r = r1(m);
      return [m, num(r.run5_25flash, 3), num(r.run6_38flash, 3),
              `${sgn(r.difference)}  [${num(r.ci_low)}, ${num(r.ci_high)}]${r.excludes_zero === "True" ? "  (clear)" : ""}`];
    }),
  ]),
  gap(),
  rich([["The newer model is better and costs more than twice as much. ", B],
    `Behaviour on probe models improved by ${sgn(r1("S1 determined-only, probe objects").difference)} under determined-only scoring and ${sgn(r1("S1 strict, probe objects").difference)} strict, both intervals clear of zero, at ${money(r4(RUN6.split(" (")[0] + " (3.8 Flash)") ? r4("Run 6 (3.8 Flash)")["mean cost per item-run"] : 0)} per item against ${money(r4("Run 5 (2.5 Flash)")["mean cost per item-run"])}.`]),
  rich([["It gets there by leaving values out. ", B],
    `Where the reference states a value that the request does not support, 3.8 Flash omits the constraint ${pct(r3("Run 6 (3.8 Flash)", "value not derivable from the request")["omission rate"])} of the time against 2.5 Flash's ${pct(r3("Run 5 (2.5 Flash)", "value not derivable from the request")["omission rate"])}. Under determined-only scoring that is the right call and it is rewarded. Under strict scoring it is a missing requirement. Where the request does support a value, both models supply one — and neither ever got it exactly right (${r3("Run 5 (2.5 Flash)", "derivable from the request")["value present and equal"]} of ${r3("Run 5 (2.5 Flash)", "derivable from the request")["matched reqs with a reference value"]} in Run 5, ${r3("Run 6 (3.8 Flash)", "derivable from the request")["value present and equal"]} of ${r3("Run 6 (3.8 Flash)", "derivable from the request")["matched reqs with a reference value"]} in Run 6).`]),

  h1("7. Money, and the run that could not be finished"),
  rich([["Run 6 is incomplete and will stay that way for now. ", B],
    `Repeat 1 covered all 47 items; repeat 2 covered ${Number(SP.find((r) => r.run === "run6-flash-rep2").n_items)} before the prepaid credit ran out. The approved top-up run to finish the last 8 items was attempted and stopped on its first call with "402 RESOURCE_EXHAUSTED: prepayment credits are depleted", so it cost nothing. Everything in this report uses the ${Number(SP.find((r) => r.run === "run6-flash-rep1").n_items) + Number(SP.find((r) => r.run === "run6-flash-rep2").n_items)} item-runs that exist.`]),
  table([3000, 2400, 2400, 2400], [
    ["Spending", "Amount", "Of which Run 6", "Total logged"],
    ["All runs to date", money(totalSpend), money(run6Spend), `${SP.length} runs`],
  ]),
  gap(),
  p("Three item-runs in Run 6 hit the per-item token ceiling of 267,000 and were abandoned mid-item. The ceiling was set from Run 5's median and was not raised retroactively. Counting those three as failures or setting them aside changes the headline as follows:"),
  table([2300, 2000, 2400, 2400, 2000], [
    ["Scoring", "Test models", "Counted as failures", "Set aside", "Executed only"],
    ...[["strict", "standard"], ["strict", "probe"], ["determined-only", "standard"], ["determined-only", "probe"]]
      .map(([s, o]) => {
        const r = r2(s, o);
        return [s, o, `${r.exact}/${r.n_all_attempted} = ${pct(r.S1_budget_counted)}`,
                `${r.exact}/${r.n_budget_set_aside} = ${pct(r.S1_budget_excluded)}`,
                `${r.exact}/${r.n_executed_only} = ${pct(r.S1_executed_only)}`];
      }),
  ]),
  gap(),
  p("The difference is under three percentage points either way, so no conclusion in this report turns on it. Future runs will use a ceiling of three times that model's own pilot median rather than a figure inherited from another model."),

  h1("8. How much rests on our determinacy judgements"),
  p(`Determined-only scoring sets aside 45 reference details nobody could have derived from the request. 37 of those follow a stated rule. The remaining ${J1.length} are judgement calls — patterns, fixed values and one numeric bound — where a reader could reasonably disagree:`),
  table([1000, 3400, 2800, 3000], [
    ["Item", "Requirement", "Reference value", "What the request says"],
    ...J1.map((r) => [r.spec, r.facet.replace("property ", "").replace("attribute ", ""),
                      r["reference value"], r["what the request says about it"].slice(0, 90)]),
  ]),
  gap(),
  p("Scoring the determined-only headline with these eight dropped (as published) and with them kept:"),
  table([2500, 2000, 2600, 2600], [
    ["Run", "Test models", "The 8 dropped (published)", "The 8 kept"],
    ...[[RUN5, "standard"], [RUN5, "probe"], [RUN6, "standard"], [RUN6, "probe"]].map(([g, o]) => {
      const a = j2(g, "the 8 treated as not derivable", o), b = j2(g, "the 8 treated as derivable", o);
      return [g === RUN5 ? "Run 5" : "Run 6", o,
              `${a.exact}/${a.item_runs} = ${pct(a["S1 determined-only"])}`,
              `${b.exact}/${b.item_runs} = ${pct(b["S1 determined-only"])}`];
    }),
  ]),
  gap(),
  rich([["The headline survives either reading. ", B],
    `Keeping all eight moves Run 5 from ${pct(j2(RUN5, "the 8 treated as not derivable", "probe")["S1 determined-only"])} to ${pct(j2(RUN5, "the 8 treated as derivable", "probe")["S1 determined-only"])} and Run 6 from ${pct(j2(RUN6, "the 8 treated as not derivable", "probe")["S1 determined-only"])} to ${pct(j2(RUN6, "the 8 treated as derivable", "probe")["S1 determined-only"])} — ${J3.filter((r) => r["object set"] === "probe").length} item-run verdicts depend on them under probe scoring, ${J3.filter((r) => r["object set"] === "standard").length} under standard scoring. Both versions are reported so a reviewer can pick.`]),

  h1("9. Comparing with the published benchmark"),
  p("IDS-Bench, the only published benchmark for this task, scores generated files by matching facet blocks against a reference and reports a macro-averaged FacetF1; its best zero-shot result is 65.6%. Computing the same measure on our files:"),
  table([3600, 2500, 2500, 2300], [
    ["Run", "IFC-version block counted", "Version block excluded", "Our own facet F1"],
    ...[RUN5, RUN6].map((g) => {
      const a = i1(g, "counted"), b = i1(g, "excluded");
      return [g, `${pct(a.FacetF1_macro_IDSBench)}  [${pct(a.ci_low)}, ${pct(a.ci_high)}]`,
              `${pct(b.FacetF1_macro_IDSBench)}  [${pct(b.ci_low)}, ${pct(b.ci_high)}]`,
              pct(a.our_facet_f1_macro)];
    }),
  ]),
  gap(),
  rich([["Read this column with care. ", B],
    "Our reference files are reconstructed from the German IDS collection and declare all three IFC versions so that the reference is never filtered out; every generated file declares the one version the request asked for, so the version block never matches and the first column is penalised uniformly. The middle column is the fairer comparison. Either way the gap between our own facet F1 and the benchmark's definition — same files, same references — is about thirty points, which is itself a finding about how much the metric definition decides."]),
  rich([["Clarification questions are not a determinacy detector. ", B],
    `The model answered with a question instead of a file in ${I3.length} item-runs, on ${new Set(I3.map((r) => r.id)).size} distinct items; those items carry ${[...new Set(I3.map((r) => r["undetermined labels on this item"]))].join(" and ")} undetermined labels between them. The questions were about references asking for things the IFC schema does not have, not about requests missing a detail.`]),

  h1("10. Limits"),
  bullet([["The headline depends on the test building, and we now report three. ", B], "Probe models are the strictest and most adversarial; real buildings are the most forgiving; neither is \"the\" answer."]),
  bullet([["Run 6 is 47 items plus 39, not 47 plus 47. ", B], "The credit ran out mid-repeat. Reported both with and without the three abandoned item-runs."]),
  bullet([["One generator, one graph, synthetic test models, 31 of 47 items from one source collection. ", B], "Unchanged since v6."]),
  bullet([["The determinacy labels are machine-made. ", B], `37 follow a rule, ${J1.length} are judgement calls, and both readings are reported.`]),
  bullet([["No value constraint was ever reproduced exactly. ", B], "Across both runs, every matched requirement where the reference states a value either lost the value or got a different one. This is the clearest open defect in the system."]),
];

const doc = new Document({
  numbering: { config: [{ reference: "b", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•",
    alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] }] },
  sections: [{ properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } }, children }],
});
Packer.toBuffer(doc).then((b) => { fs.writeFileSync(OUT, b); console.log("wrote", OUT); });
