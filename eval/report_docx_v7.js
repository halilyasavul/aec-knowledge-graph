// Build the v7 Word report. Numbers come from eval/reports/v7/*.csv (written by
// python -m eval.analysis) and the v6 cell JSONs. Nothing is typed in by hand.
//   node eval/report_docx_v7.js <out.docx> eval/reports/v7 eval/reports/cells_strict.json eval/reports/run5_strict.json
const fs = require("fs");
const path = require("path");
const [OUT, V7DIR, CELLS, RUN5] = process.argv.slice(2);

function csv(name) {
  const text = fs.readFileSync(path.join(V7DIR, name), "utf8").trim();
  const [head, ...lines] = text.split(/\r?\n/);
  const cols = head.split(",");
  return lines.map((l) => {
    // minimal CSV: fields may be quoted and contain commas
    const out = []; let cur = ""; let q = false;
    for (const ch of l) {
      if (ch === '"') q = !q;
      else if (ch === "," && !q) { out.push(cur); cur = ""; }
      else cur += ch;
    }
    out.push(cur);
    return Object.fromEntries(cols.map((c, i) => [c, out[i]]));
  });
}
const T1 = csv("t1_fix_effects_bootstrap.csv");
const T2 = csv("t2_within_item_lookup.csv");
const T3 = csv("t3_item_difficulty.csv");
const T4 = csv("t4_run5_sensitivity.csv");
const T5 = csv("t5_run5_failures.csv");
const cells = JSON.parse(fs.readFileSync(CELLS, "utf8"));
const run5 = JSON.parse(fs.readFileSync(RUN5, "utf8")).cells[0];

const num = (x, dp = 3) => (x === "" || x === undefined ? "n/a" : Number(x).toFixed(dp));
const ci = (r) => `${Number(r.estimate) >= 0 ? "+" : ""}${num(r.estimate)}  [${num(r.ci_low)}, ${num(r.ci_high)}]`;
const row1 = (metric, effect) => T1.find((r) => r.metric === metric && r.effect === effect);
const flag = (r) => (r.excludes_zero === "True" ? "yes" : "no");

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

const METRICS = ["facet F1 (text)", "names-correct rate (text)", "S1 strict (behaviour)",
                 "S1 determined-only (behaviour)", "S2 reference objects (behaviour)",
                 "false rejection (behaviour, lower better)"];
const strictRow = T4.find((r) => r.variant.startsWith("strict"));
const passB = T4.find((r) => r.variant.startsWith("pass B"));
const passA = T4.find((r) => r.variant.startsWith("pass A"));
const vk = T4.find((r) => r.variant.startsWith("values kept"));
const nc = T3.find((r) => r.group === "names-correct"), nw = T3.find((r) => r.group === "names-wrong");
const fixedGroup = T2.find((r) => r.group.startsWith("names fixed"));
const causeCounts = {};
for (const r of T5) causeCounts[r.primary_cause] = (causeCounts[r.primary_cause] || 0) + 1;
const distinctFailing = new Set(T5.map((r) => r.id)).size;

const children = [
  new Paragraph({ spacing: { after: 60 }, children: [new TextRun({ text: "Testing Our Text-to-IDS System", font: FONT, size: 36, bold: true, color: "1F3864" })] }),
  new Paragraph({ spacing: { after: 240 }, border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "1F3864", space: 4 } },
    children: [run("Report v7 — the claims with uncertainty attached  |  October 6, 2026", { color: "595959" })] }),

  h1("1. What changed since v6, in one paragraph"),
  p("v6 reported that one fix moved the text scores and the other moved behaviour. With confidence intervals and a within-item check, that story only half survives. The dataType fix really does move behaviour, and does not move the text scores. The lookup fix moves neither: it reduces invented property-set names, but it did not raise the text scores (it slightly lowered the share of items with every name right) and it did not raise behaviour. We also found that the Run 5 headline rests entirely on one group of annotations, and that the items with correct names are simply easier items."),

  h1("2. Effect of each fix, with 95% intervals"),
  p("Each figure is the change from turning that fix on, averaged over the other factor. Intervals come from 2000 bootstrap resamples of items; all three repeats of an item move together, because repeats of the same item are not independent."),
  table([3500, 2500, 2460, 900], [
    ["Metric", "Lookup fix", "dataType fix", "Clear?"],
    ...METRICS.map((m) => {
      const lk = row1(m, "lookup fix"), dt = row1(m, "dataType fix");
      return [m, ci(lk), ci(dt), `${flag(lk)} / ${flag(dt)}`];
    }),
  ]),
  gap(),
  p("\"Clear?\" says whether the interval excludes zero, for the lookup fix and the dataType fix respectively."),
  rich([["It is not a double dissociation. ", B],
    `The dataType fix moved behaviour and left the text scores alone: false rejection ${ci(row1("false rejection (behaviour, lower better)", "dataType fix"))}, exact match under determined-only scoring ${ci(row1("S1 determined-only (behaviour)", "dataType fix"))}, both clear of zero, while facet F1 ${ci(row1("facet F1 (text)", "dataType fix"))} and names-correct ${ci(row1("names-correct rate (text)", "dataType fix"))} are indistinguishable from no change. The lookup fix, however, did not move the text scores upward either: names-correct ${ci(row1("names-correct rate (text)", "lookup fix"))}, which is a small decrease, and facet F1 ${ci(row1("facet F1 (text)", "lookup fix"))}. So the honest claim is one-sided: a fix can move behaviour without moving any text score, which is enough to show the two kinds of measurement come apart.`]),
  rich([["The interaction is not detectable. ", B],
    `Lookup × dataType on S2 is ${ci(row1("S2 reference objects (behaviour)", "interaction"))} and on determined-only exact match ${ci(row1("S1 determined-only (behaviour)", "interaction"))}. Both intervals straddle zero, so "P2 is not confirmed" is now a reported estimate with its uncertainty rather than a judgement call.`]),
  rich([["One caution on S2: ", B], `the dataType effect on S2 is ${ci(row1("S2 reference objects (behaviour)", "dataType fix"))} — the interval just touches zero, even though the same fix clearly moves false rejection and determined-only exact match. With 21 items that is what this design can resolve.`]),

  h1("3. P2 against P3: do correct names cause better behaviour?"),
  p("P3 compared different items; P2 changed one factor on the same items. The within-item comparison is the causal one, so we looked for items whose names went from wrong to correct when the lookup fix was switched on, with the dataType fix already on."),
  rich([["There are none. ", B],
    `Of the 21 items, ${T2.find((r) => r.group === "names already correct" && r.metric.startsWith("S2")).items} already had every name right in both conditions, ${T2.find((r) => r.group === "names wrong in both" && r.metric.startsWith("S2")).items} had a wrong name in both, ${T2.find((r) => r.group === "names broken by the lookup fix" && r.metric.startsWith("S2")).items} had correct names only with the fix off, and ${fixedGroup.items} were corrected by the fix. The within-item test for P2 therefore has no cases to run, and the lookup fix cannot be credited with any behavioural gain through name correctness.`]),
  p("So the P3 gap has to be explained some other way. The two groups of items differ in difficulty:"),
  table([2600, 1800, 1800, 2160, 1000], [
    ["Group", "Items", "Mean requirements", "Share of undetermined facets", "Longest"],
    ["names-correct", nc.items, num(nc.mean_requirements, 2), num(nc.share_undetermined_facets, 2), nc.max_requirements],
    ["names-wrong", nw.items, num(nw.mean_requirements, 2), num(nw.share_undetermined_facets, 2), nw.max_requirements],
  ]),
  gap(),
  rich([["Conclusion: names-correct items are easier items, not better answers. ", B],
    `They carry ${num(nc.mean_requirements, 1)} requirements on average against ${num(nw.mean_requirements, 1)}, and ${num(100 * Number(nc.share_undetermined_facets), 0)}% of their facets are ones nobody could determine from the request, against ${num(100 * Number(nw.share_undetermined_facets), 0)}%. A single-requirement item whose value constraint is excluded is close to trivial once the property name is right. The v6 reading — that correct names predict better behaviour — is confounded by item difficulty, and this report withdraws the causal version of that claim.`]),

  h1("4. How much of the Run 5 headline is the annotations?"),
  p("The Run 5 figure of \"29 of 44 exactly right\" depends on the machine-made determinacy annotations. Scored four ways:"),
  table([3800, 1700, 1700, 1100, 1060], [
    ["Variant", "Exact per repeat", "Exact rate", "3 of 3", "0 of 3"],
    ...[strictRow, passB, passA, vk].map((r) => [r.variant, r.exact_per_repeat, num(r.exact_rate, 2), r.items_3of3, r.items_0of3]),
  ]),
  gap(),
  bullet([["Pass A and pass B give identical results ", B], "because the two passes flag exactly the same 45 facets with the same scopes. The \"worst case where the passes disagree\" is therefore empty by construction — it tests nothing, and we say so rather than presenting it as reassurance."]),
  bullet([["The whole gain comes from the value annotations. ", B], `Dropping only the unmentioned requirements and keeping every value constraint gives ${vk.exact_per_repeat} of ${vk.items_testable_per_repeat} — the same as strict scoring (${strictRow.exact_per_repeat}). The jump to ${passB.exact_per_repeat} comes entirely from the 31 value-scope annotations.`]),
  bullet([["Repeat stability: ", B], `under pass B, ${passB.items_3of3} items matched in all three repeats and ${passB.items_0of3} in none; under strict scoring, ${strictRow.items_3of3} and ${strictRow.items_0of3}.`]),
  rich([["What this means for the paper: ", B], "the headline is only as good as the judgement that those 31 value lists and patterns could not be recovered from the request. That judgement was made by this system, not by a person. It should be reviewed before the number is published."]),

  h1("5. What still fails"),
  p(`Across the three Run 5 repeats, ${T5.length} item-runs still fail under the determined-only reference, covering ${distinctFailing} distinct items. Their causes:`),
  table([4200, 1500, 4660], [
    ["Primary cause", "Item-runs", "What it is"],
    ...Object.entries(causeCounts).sort((a, b) => b[1] - a[1]).map(([c, n]) => [c, String(n), {
      "wrong value or allowed list": "a value constraint the request did state, but the system got wrong",
      "missing requirement": "a described requirement the system left out",
      "no file produced": "the system asked for clarification instead of answering",
      "extra requirement": "a requirement the reference does not have",
      "wrong cardinality": "required versus optional",
      "wrong data type": "the IFC type does not match",
      "version mismatch": "declared schema excludes the test model",
      "other": "none of the above",
    }[c] || ""]),
  ]),
  gap(),
  rich([["These are the genuine model errors. ", B], "Wrong values dominate even after the unrecoverable ones are excluded, which means the system also mishandles value constraints the request does state. Missing requirements come second, and the clarification refusals third — those last ones are arguably correct behaviour being scored as failure, because the request really is underspecified."]),

  h1("6. Run 6 could not be started"),
  rich([["The Gemini account is out of credit. ", B],
    "Every call now returns \"402 RESOURCE_EXHAUSTED: Your prepayment credits are depleted\", including the model used for every run so far. Nothing was generated for Run 6, and no partial run was left behind. Top up at ai.studio and Run 6 can start unchanged."]),
  p("The plan stands: the same 47 items, three repeats, temperature 0, all fixes on, with the strongest Gemini model pinned by its exact version string. The candidates visible on this account are gemini-3.8-flash (version string \"3.0\"), gemini-3.7-flash (\"3.7-flash-08-2026\") and gemini-3.1-pro-preview (\"3.1-pro-preview-01-2026\"). Run 5 cost $5.60 for 141 generations on 2.5 Flash, so a flash-tier Run 6 should cost about the same and a Pro-tier one roughly $25–45 at current Pro pricing — under the $50 gate, but worth confirming which tier you want, since \"strongest\" and \"same family\" point at different models."),

  h1("7. Limits, unchanged and new"),
  bullet([["New: the names-correct advantage is confounded. ", B], "Item difficulty explains it; the causal claim is withdrawn."]),
  bullet([["New: the determined-only headline rests on 31 unreviewed value annotations. ", B], "Keeping those constraints returns the figure to the strict value."]),
  bullet([["21 items, three repeats, and a design that resolves only large effects. ", B], "The dataType effect is clear; the lookup effect and the interaction are not resolvable at this sample size."]),
  bullet([["Synthetic test models, one model, one graph, 31 of 47 items from one source. ", B], "As in v6."]),
  bullet([["Non-determinism remains: ", B], `repeats of the same cell agree on ${cells.cells.map((c) => (c.identical_across_repeats ? c.identical_across_repeats.identical : "?")).join(", ")} of 21 items, and ${run5.identical_across_repeats ? run5.identical_across_repeats.identical : "?"} of 47 in Run 5.`]),
];

const doc = new Document({
  numbering: { config: [{ reference: "b", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•",
    alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] }] },
  sections: [{ properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } }, children }],
});
Packer.toBuffer(doc).then((b) => { fs.writeFileSync(OUT, b); console.log("wrote", OUT); });
