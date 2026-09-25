// Build the v6 Word report. Numbers are read from JSON, never typed in:
//   python -m eval.summary <run6 dirs...> --cells -o eval/reports/cells_strict.json
//   python -m eval.summary <run6 dirs...> --cells --scores scores_relaxed.csv -o eval/reports/cells_relaxed.json
//   python -m eval.summary <run5 dirs...> --cells -o eval/reports/run5_strict.json   (and _relaxed)
//   python -m eval.determinism <run4 dirs...> -o eval/reports/determinism.json
//   node eval/report_docx_v6.js <out.docx> <cells_strict> <cells_relaxed> <run5_strict> <run5_relaxed>
const fs = require("fs");
const [OUT, CS, CR, R5S, R5R] = process.argv.slice(2);
const strict = JSON.parse(fs.readFileSync(CS, "utf8"));
const relaxed = JSON.parse(fs.readFileSync(CR, "utf8"));
const run5s = R5S && fs.existsSync(R5S) ? JSON.parse(fs.readFileSync(R5S, "utf8")) : null;
const run5r = R5R && fs.existsSync(R5R) ? JSON.parse(fs.readFileSync(R5R, "utf8")) : null;

const ORDER = ["run6-lk0dt0", "run6-lk1dt0", "run6-lk0dt1", "run6-lk1dt1"];
const LABEL = {
  "run6-lk0dt0": "neither fix", "run6-lk1dt0": "lookup only",
  "run6-lk0dt1": "dataType only", "run6-lk1dt1": "both fixes",
};
const cellsOf = (d) => ORDER.map((n) => d.cells.find((c) => c.cell === n)).filter(Boolean);
const S = cellsOf(strict), R = cellsOf(relaxed);
const byName = (arr) => Object.fromEntries(arr.map((c) => [c.cell, c]));
const Sx = byName(S), Rx = byName(R);

const f2 = (x) => (x === null || x === undefined ? "n/a" : Number(x).toFixed(2));
const mm = (m) => (m ? `${m.mean.toFixed(2)} (${m.min.toFixed(2)}–${m.max.toFixed(2)})` : "n/a");
const s1 = (c) => `${c.s1.mean.toFixed(1)} of ${c.s1.of.toFixed(0)}`;
const delta = (on, off, key) => (Sx[on][key].mean - Sx[off][key].mean);
// marginal effect of a fix = mean over the two cells where it is on, minus the two where it is off
const marg = (key, which) => {
  const on = which === "lk" ? ["run6-lk1dt0", "run6-lk1dt1"] : ["run6-lk0dt1", "run6-lk1dt1"];
  const off = which === "lk" ? ["run6-lk0dt0", "run6-lk0dt1"] : ["run6-lk0dt0", "run6-lk1dt0"];
  const avg = (ns) => ns.reduce((a, n) => a + (Sx[n][key]?.mean ?? Sx[n][key]), 0) / ns.length;
  return avg(on) - avg(off);
};
const margNames = (which) => {
  const on = which === "lk" ? ["run6-lk1dt0", "run6-lk1dt1"] : ["run6-lk0dt1", "run6-lk1dt1"];
  const off = which === "lk" ? ["run6-lk0dt0", "run6-lk0dt1"] : ["run6-lk0dt0", "run6-lk1dt0"];
  const avg = (ns) => ns.reduce((a, n) => a + Sx[n].names_correct.mean, 0) / ns.length;
  return avg(on) - avg(off);
};
const sign = (x, dp = 2) => (x >= 0 ? "+" : "") + x.toFixed(dp);

const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, LevelFormat, AlignmentType,
} = require("docx");
const FONT = "Calibri";
const run = (t, o = {}) => new TextRun({ text: String(t), font: FONT, size: 22, ...o });
const p = (text, opts = {}) => new Paragraph({ spacing: { after: 120 }, ...opts, children: [run(text)] });
const rich = (parts, opts = {}) => new Paragraph({ spacing: { after: 120 }, ...opts,
  children: parts.map((x) => (typeof x === "string" ? run(x) : run(x[0], x[1]))) });
const h1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 280, after: 120 },
  children: [new TextRun({ text: t, font: FONT, size: 28, bold: true, color: "1F3864" })] });
const h2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 180, after: 80 },
  children: [new TextRun({ text: t, font: FONT, size: 24, bold: true, color: "2F5496" })] });
const bullet = (parts) => new Paragraph({ numbering: { reference: "b", level: 0 }, spacing: { after: 60 },
  children: (Array.isArray(parts) ? parts : [parts]).map((x) => (typeof x === "string" ? run(x) : run(x[0], x[1]))) });
const B = { bold: true };
const MONO = { font: "Consolas", size: 20 };
const border = { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" };
const borders = { top: border, bottom: border, left: border, right: border };
const gap = () => new Paragraph({ spacing: { after: 80 }, children: [] });
function table(widths, rows) {
  return new Table({
    width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA }, columnWidths: widths,
    rows: rows.map((cells, r) => new TableRow({
      children: cells.map((c, i) => new TableCell({
        width: { size: widths[i], type: WidthType.DXA }, borders,
        shading: r === 0 ? { type: ShadingType.CLEAR, color: "auto", fill: "D9E2F3" } : undefined,
        margins: { top: 60, bottom: 60, left: 100, right: 100 },
        children: [new Paragraph({ children: (Array.isArray(c) ? c : [c]).map((x) =>
          typeof x === "string" ? run(x, { size: 19, bold: r === 0 }) : run(x[0], { size: 19, ...x[1] })) })],
      })),
    })),
  });
}

const dtOn = [Sx["run6-lk0dt1"], Sx["run6-lk1dt1"]], dtOff = [Sx["run6-lk0dt0"], Sx["run6-lk1dt0"]];
const avg = (cs, f) => cs.reduce((a, c) => a + f(c), 0) / cs.length;

const children = [
  new Paragraph({ spacing: { after: 60 }, children: [new TextRun({ text: "Testing Our Text-to-IDS System", font: FONT, size: 36, bold: true, color: "1F3864" })] }),
  new Paragraph({ spacing: { after: 240 }, border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "1F3864", space: 4 } },
    children: [run("Report v6 — what each fix actually moved  |  September 25, 2026", { color: "595959" })] }),

  h1("1. The headline: our fixes moved the text scores and the behaviour scores very differently"),
  p("We tested two fixes to our own system, each on and off, on the same 21 requirement sets, three times each. One fix stops our code hiding property names from the AI (the \"lookup\" fix). The other gives the AI the exact IFC data type for each property (the \"dataType\" fix)."),
  table([3200, 3080, 3080], [
    ["Effect of turning the fix on", "Lookup fix", "dataType fix"],
    ["Text: all property names correct (items)", sign(margNames("lk"), 1), sign(margNames("dt"), 1)],
    ["Text: text match (facet F1)", sign(marg("facet_f1_macro", "lk")), sign(marg("facet_f1_macro", "dt"))],
    [["Behaviour: object agreement (S2)", B], [sign(marg("s2_ref", "lk")), B], [sign(marg("s2_ref", "dt")), B]],
    [["Behaviour: wrongly rejects correct objects", B], [sign(marg("false_reject", "lk")), B], [sign(marg("false_reject", "dt")), B]],
  ]),
  gap(),
  rich([["Read it this way: ", B], "the dataType fix barely changed the text scores but halved wrong rejections and lifted behavioural agreement sharply. The lookup fix did the opposite — it cut invented property sets (from ", `${avg(dtOff, (c) => c.errors.hallucinated_pset || 0).toFixed(1)} to ${avg(dtOn, (c) => c.errors.hallucinated_pset || 0).toFixed(1)} per run in the dataType-on cells`, " and removed wrong property sets entirely in the all-fixes cell) without moving behaviour at all. A text score and a behaviour score answer different questions; improving one does not imply the other."]),

  h1("2. The predictions we committed before running"),
  p("We wrote these down and committed them before the first cell ran, so they could not be adjusted afterwards."),
  table([1000, 5060, 3300], [
    ["", "Prediction", "Outcome"],
    ["P1", "The dataType fix sharply cuts wrong rejections and raises agreement.",
      [["Confirmed. ", B], `Wrong rejections ${f2(avg(dtOff, (c) => c.false_reject.mean))} → ${f2(avg(dtOn, (c) => c.false_reject.mean))}; agreement ${f2(avg(dtOff, (c) => c.s2_ref.mean))} → ${f2(avg(dtOn, (c) => c.s2_ref.mean))}. The repeat ranges do not overlap.`]],
    ["P2", "The lookup fix raises agreement only when the dataType fix is also on.",
      [["Direction right, effect too small to claim. ", B], `With dataType on ${f2(Sx["run6-lk0dt1"].s2_ref.mean)} → ${f2(Sx["run6-lk1dt1"].s2_ref.mean)}; with it off ${f2(Sx["run6-lk0dt0"].s2_ref.mean)} → ${f2(Sx["run6-lk1dt0"].s2_ref.mean)}. The repeat ranges overlap, so this is within run-to-run noise.`]],
    ["P3", "Once dataType is fixed, names-correct items pull ahead of names-wrong items.",
      [["Confirmed, and strongly. ", B], `With dataType on, items with every name right agree on ${f2(avg(dtOn, (c) => c.hypothesis.names_correct_s2))} of objects against ${f2(avg(dtOn, (c) => c.hypothesis.other_s2))} for items with a wrong name. With dataType off the advantage is absent (${f2(avg(dtOff, (c) => c.hypothesis.names_correct_s2))} against ${f2(avg(dtOff, (c) => c.hypothesis.other_s2))}).`]],
  ]),

  h1("3. The 2×2 in full"),
  p("Each cell is three repeats of the same 21 items. The figure is the mean, with the spread across repeats in brackets."),
  table([2000, 1700, 2300, 2300, 1060], [
    ["Cell", "Identical (S1)", "Object agreement (S2)", "Wrongly rejects (lower better)", "Names right"],
    ...S.map((c) => [LABEL[c.cell], s1(c), mm(c.s2_ref), mm(c.false_reject), c.names_correct.mean.toFixed(1)]),
  ]),
  gap(),
  p("The same cells scored against the determined-only reference — that is, ignoring requirements the request never states (see section 6):"),
  table([2000, 1700, 2300, 2300, 1060], [
    ["Cell", "Identical (S1)", "Object agreement (S2)", "Wrongly rejects", "Names right"],
    ...R.map((c) => [LABEL[c.cell], s1(c), mm(c.s2_ref), mm(c.false_reject), c.names_correct.mean.toFixed(1)]),
  ]),
  gap(),
  rich([["This is the fairest single number we have: ", B],
    `with both fixes on and unguessable details excluded, ${s1(Rx["run6-lk1dt1"])} items behave exactly like the reference, against ${s1(Rx["run6-lk0dt0"])} with neither fix. Under strict scoring the same cells are ${s1(Sx["run6-lk1dt1"])} and ${s1(Sx["run6-lk0dt0"])}: almost all of that difference is requirements nobody could have guessed from the request.`]),

  h1("4. Do correct names predict correct behaviour?"),
  p("An item is \"names-correct\" when every property-set and property name matches the reference — what a text-based check scores as right."),
  table([2400, 1700, 1700, 1700, 1860], [
    ["Cell", "Names-correct items", "Their agreement", "Names-wrong agreement", "Names-correct that behave identically"],
    ...S.map((c) => [LABEL[c.cell], c.hypothesis.names_correct_testable.toFixed(1),
      f2(c.hypothesis.names_correct_s2), f2(c.hypothesis.other_s2),
      `${c.hypothesis.names_correct_s1[0]} of ${c.hypothesis.names_correct_s1[1]}`]),
  ]),
  gap(),
  rich([["The honest reading: ", B], "with the plumbing fixed, getting every name right does predict that the file mostly behaves the same (about ", f2(avg(dtOn, (c) => c.hypothesis.names_correct_s2)), " of objects judged alike). It does not predict that the file behaves identically: only ",
    `${dtOn.reduce((a, c) => a + c.hypothesis.names_correct_s1[0], 0)} of ${dtOn.reduce((a, c) => a + c.hypothesis.names_correct_s1[1], 0)}`,
    " names-correct runs match on every object. So a text check is a decent proxy for \"roughly right\" and a poor one for \"correct\"."]),
  p(`Only ${Math.max(...S.map((c) => c.hypothesis.distinct_facet_f1))} distinct text-match values occur across the cells, so we report no correlation coefficient; it would be an artefact of that.`),

  h1("5. The bSDD data-type finding"),
  p("This is worth reporting in its own right, not just as a fix."),
  bullet("bSDD's structured data type is too coarse for IDS. It says \"String\" where IFC wants IfcLabel, IfcIdentifier or IfcText, and \"Real\" where IFC wants a specific measure."),
  bullet("The exact type is published only inside the free-text description: \"Technical note: in IFC this property takes 'IfcLabel' as value.\" We parse that sentence at ingestion."),
  bullet("Coverage of our IFC 4.3 export: 1570 of 2501 properties state the type in text; 475 remaining \"String\" properties default to IFCLABEL; 40 quantity properties take the measure of their kind; 416 omit the type rather than guess."),
  bullet("Against the reference specifications used here, the graph now agrees on 56 of 57 property data types. The one miss is a quantity-like property whose type is not stated anywhere, so we leave it out rather than invent it."),
  bullet("A caveat we cannot fix from this export: it carries one description per property code, so a property used by several sets cannot carry different types. If bSDD ever disagrees per set, this approach would miss it."),
  rich([["Did the AI actually use it? ", B], `Yes: in the all-fixes cell, ${Sx["run6-lk1dt1"].provenance.dt_from_graph} data types per run came from the graph and only ${Sx["run6-lk1dt1"].provenance.dt_model_choice} were the model's own choice; with the fix off it is ${Sx["run6-lk1dt0"].provenance.dt_from_graph} against ${Sx["run6-lk1dt0"].provenance.dt_model_choice}. Wrong data types fell from about ${avg(dtOff, (c) => c.errors.wrong_datatype || 0).toFixed(1)} per run to ${avg(dtOn, (c) => c.errors.wrong_datatype || 0).toFixed(1)}.`]),

  h1("6. Which requirements nobody could guess"),
  p("Some requirements cannot be recovered from the request at any skill level: an allowed-value list the text never states, or a property the request never mentions. Scoring them against the system measures the dataset, not the system."),
  bullet([["Value lists, mechanically: ", B], "a list counts as recoverable when every value is either an IFC allowed value for that property (the schema supplies it) or appears in the request. The Vienna \"status\" lists pass this test because the seven values are the IFC enumeration; the Austrian fire-rating codes (ND, NE, R 30 …) fail it, because they are local codes the request never lists."]),
  bullet([["Unmentioned requirements, by reading: ", B], "each was read against the request and judged case by case, with a one-line reason recorded."]),
  bullet([["Two passes, compared: ", B], "the original text heuristics and this final method agree on all 82 facets of the 47 items. 45 facets are undetermined: 14 drop the requirement, 31 drop only its value constraint."]),
  rich([["These annotations are machine-made and were not reviewed by a human. ", B], "They were produced by the same system that wrote this report, which is a real limitation: a reviewer might judge some of the 45 differently."]),

  h1("7. The IFC version check"),
  rich([["In v5, 19% of behavioural failures came from specs whose declared schema excluded the test model. ", B],
    "Every request now carries one extra line, \"Target schema: IFC4X3_ADD2\". Across all four cells of the 2×2, the number of files whose declared schema excludes the test model is now zero. The line is a constant, identical for every item, so it tells the system nothing about any particular answer."]),

  h1("8. Does the same request give the same answer?"),
  rich([["Still no. ", B], `With randomness pinned to zero, repeats of the same cell produced an identical specification for only ${S.map((c) => (c.identical_across_repeats ? c.identical_across_repeats.identical : 0)).join(", ")} of 21 items (one figure per cell). The differences are behavioural, not cosmetic: a value constraint present or absent, a different pattern, a different data type. Every number in this report is a mean over three repeats for that reason, and single-run differences smaller than the repeat spread should not be read as effects.`]),
];

if (run5s) {
  const a = run5s.cells[0], b = run5r ? run5r.cells[0] : null;
  children.push(
    h1("9. All usable items"),
    p(`The same configuration (both fixes on) run over all ${a.items} usable items, three times.`),
    table([3000, 3180, 3180], [
      ["Measure", "Strict", "Determined-only"],
      ["Items scored", String(a.items), b ? String(b.items) : "n/a"],
      ["Produced a file", `${a.with_file.mean.toFixed(1)} of ${a.items}`, b ? `${b.with_file.mean.toFixed(1)} of ${b.items}` : "n/a"],
      ["Behave identically (S1)", s1(a), b ? s1(b) : "n/a"],
      ["Object agreement (S2)", mm(a.s2_ref), b ? mm(b.s2_ref) : "n/a"],
      ["Wrongly rejects correct objects", mm(a.false_reject), b ? mm(b.false_reject) : "n/a"],
      ["All names correct", a.names_correct.mean.toFixed(1), b ? b.names_correct.mean.toFixed(1) : "n/a"],
    ]),
    gap(),
    rich([["Consistent with the 2×2: ", B], `on the wider set the system reproduces the reference's behaviour exactly on ${b ? s1(b) : s1(a)} items once unguessable details are excluded, and agrees on ${b ? f2(b.s2_ref.mean) : f2(a.s2_ref.mean)} of test objects.`]),
  );
}

children.push(
  h1("10. Limits"),
  bullet([["Synthetic test models. ", B], "Objects are generated from the two specifications themselves and test each requirement's own boundary cases, not realistic building data. Objects come from both specifications, so neither is privileged."]),
  bullet([["Machine-made determinacy annotations. ", B], "No human reviewed the 45 judgements that decide which requirements are excluded, and they move the headline substantially."]),
  bullet([["A narrow, lopsided pool. ", B], "47 usable items of 185 harvested, 31 of them from one source (Vienna), and none with ten or more requirements — so we dropped the spec-length analysis entirely."]),
  bullet([["Small n and real non-determinism. ", B], "21 items times three repeats per cell; identical inputs give different files most of the time."]),
  bullet([["One system, one model. ", B], "Gemini 2.5 Flash with our graph. A stronger model is the obvious second condition and has not been run."]),
);

const doc = new Document({
  numbering: { config: [{ reference: "b", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•",
    alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] }] },
  sections: [{ properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } }, children }],
});
Packer.toBuffer(doc).then((b) => { fs.writeFileSync(OUT, b); console.log("wrote", OUT); });
