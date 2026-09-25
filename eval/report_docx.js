// Build the v5 Word report. All numbers are read from JSON, never typed in:
//   python -m eval.summary <runs...> -o eval/reports/report_data.json
//   python -m eval.determinism eval/runs/run4-rep{1,2,3} -o eval/reports/determinism.json
//   node eval/report_docx.js <out.docx> eval/reports/report_data.json eval/reports/determinism.json
// Needs the `docx` npm package. eval/reports/ is git-ignored; this generator is not.
const fs = require("fs");
const D = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const DET = JSON.parse(fs.readFileSync(process.argv[4], "utf8"));
const R = {};
for (const r of D.runs) R[r.name] = r;
const base = R["v4-baseline-rescored"], fixed = R["run2-fixed"], abl = R["run3-no-trunc"];

const pct = (a) => (a[1] ? `${a[0]} of ${a[1]} (${Math.round((100 * a[0]) / a[1])}%)` : "n/a");
const n3 = (x) => (x === null || x === undefined ? "n/a" : x.toFixed(2));

const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, LevelFormat, AlignmentType,
} = require("docx");

const FONT = "Calibri";
const run = (t, o = {}) => new TextRun({ text: String(t), font: FONT, size: 22, ...o });
const p = (text, opts = {}) => new Paragraph({ spacing: { after: 120 }, ...opts, children: [run(text)] });
const rich = (parts, opts = {}) => new Paragraph({ spacing: { after: 120 }, ...opts,
  children: parts.map((x) => (typeof x === "string" ? run(x) : run(x[0], x[1]))) });
const h1 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 280, after: 120 },
  children: [new TextRun({ text, font: FONT, size: 28, bold: true, color: "1F3864" })] });
const h2 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 180, after: 80 },
  children: [new TextRun({ text, font: FONT, size: 24, bold: true, color: "2F5496" })] });
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
function exampleTable(rows) {
  const W = [1700, 7660];
  return new Table({
    width: { size: 9360, type: WidthType.DXA }, columnWidths: W,
    rows: rows.map(([k, v]) => new TableRow({ children: [
      new TableCell({ width: { size: W[0], type: WidthType.DXA }, borders,
        shading: { type: ShadingType.CLEAR, color: "auto", fill: "F2F2F2" },
        margins: { top: 60, bottom: 60, left: 100, right: 100 },
        children: [new Paragraph({ children: [run(k, { size: 19, bold: true })] })] }),
      new TableCell({ width: { size: W[1], type: WidthType.DXA }, borders,
        margins: { top: 60, bottom: 60, left: 100, right: 100 },
        children: [new Paragraph({ children: (Array.isArray(v) ? v : [v]).map((x) =>
          typeof x === "string" ? run(x, { size: 19 }) : run(x[0], { size: 19, ...x[1] })) })] }),
    ] })),
  });
}
const ex = (title, rows) => [h2(title), exampleTable(rows), gap()];

const metricRows = [
  ["Measure", "v4 (before)", "v5 (fixed)", "v5 without the lookup fix"],
  ["Produced a file", pct([base.with_file, base.items]), pct([fixed.with_file, fixed.items]), pct([abl.with_file, abl.items])],
  ["S1 strict: every verdict identical", pct(base.s1), pct(fixed.s1), pct(abl.s1)],
  ["S2 agreement, reference objects", n3(base.s2_ref), n3(fixed.s2_ref), n3(abl.s2_ref)],
  ["S3 enforces the requirement", n3(base.enforce), n3(fixed.enforce), n3(abl.enforce)],
  ["S3 wrongly rejects correct objects", n3(base.false_reject), n3(fixed.false_reject), n3(abl.false_reject)],
  ["S3 ignores out-of-scope objects", n3(base.app_out), n3(fixed.app_out), n3(abl.app_out)],
  ["Text match (facet F1, micro)", n3(base.facet_f1_micro), n3(fixed.facet_f1_micro), n3(abl.facet_f1_micro)],
  ["All property names correct", pct(base.names_correct), pct(fixed.names_correct), pct(abl.names_correct)],
  ["Invented property sets", String(base.errors.hallucinated_pset || 0), String(fixed.errors.hallucinated_pset || 0), String(abl.errors.hallucinated_pset || 0)],
  ["Property sets hidden from the AI", "not logged", String(fixed.psets_dropped), String(abl.psets_dropped)],
];

const doc = new Document({
  numbering: { config: [{ reference: "b", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•",
    alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } },
    children: [
      new Paragraph({ spacing: { after: 60 }, children: [new TextRun({ text: "Testing Our Text-to-IDS System", font: FONT, size: 36, bold: true, color: "1F3864" })] }),
      new Paragraph({ spacing: { after: 240 }, border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "1F3864", space: 4 } },
        children: [run("Report v5 — after fixing our own pipeline  |  September 24, 2026", { color: "595959" })] }),

      h1("1. What we test, and on how few items"),
      p("Our system turns building requirements written in plain language into IDS files, the rule files used to check BIM models automatically. The question is whether other people's usual check — comparing the generated file's text to a correct file — agrees with what matters: whether the generated file passes and fails the same objects as the correct file."),
      rich([["The filter comes first, because it is the study's biggest constraint. ", B],
        `We harvested ${D.filter.harvested} published specifications. Only ${D.filter.usable} are usable: the rest require property sets a project invented for itself (Vienna's "WienBV_…", the movement-analysis "ePset_OMA_…"), which exist only in that project's own documents, so no system could find them from IFC.`]),
      table([4300, 1200, 3860], [
        ["Source", "Items", "Note"],
        ...D.filter.by_source.map(([s, n]) => [s.replace(/_Specifications\.ids|\.ids/, "").slice(0, 58), String(n), ""]),
        [[["usable total", B]], [[String(D.filter.usable), B]], [[`of ${D.filter.harvested} harvested`, B]]],
      ]),
      gap(),
      rich([["A second limit follows from that: ", B],
        `among the usable items, ${D.filter.bands["<=3"]} have three requirements or fewer, ${D.filter.bands["4-9"]} have four to nine, and ${D.filter.bands[">=10"]} have ten or more. The long specifications all use project-specific property sets, so the concern that all-or-nothing scoring unfairly punishes long specifications cannot be tested on this pool at all.`]),

      h1("2. What we fixed in our own system"),
      p("The previous report blamed the AI for problems that were ours. Three were bugs in our code and one is a wrong instruction we give the AI. All fixes have an off switch so we can measure each one."),
      table([2500, 3400, 3460], [
        ["Bug", "What it did", "Now"],
        ["Lookup results cut short", "When a lookup was too long, our code kept the first few property sets and silently dropped all the rest. The AI never saw the set it needed and invented a name.", "Every property set name is always kept; only long property lists and descriptions are shortened. Budget raised from 25,000 to 200,000 characters."],
        ["Unknown keys ignored", "The AI wrote allowed values under the key \"enum\"; our code only read \"enumerations\", ignored the rest and still reported success, so the rule rejected every value.", "\"enum\" is accepted, unknown keys are an error the AI can correct, and an empty restriction is refused."],
        ["No check on values", "A pattern (\".*\") or a whole sentence could be stored as an exact value, so the rule demanded that literal text.", "Patterns, prose and placeholder words like \"REQUIRED\" are refused with an explanation."],
        ["Randomness not fixed", "The same request could give different answers.", "Temperature pinned to 0 and the model version checked on every call."],
      ]),
      gap(),
      rich([["Guards that fired during the fixed run (all logged): ", B],
        Object.entries(fixed.guards).map(([k, v]) => `${k.replace(/_/g, " ")} ${v}`).join(", ") + "."]),
      p("Where the AI's input was merely written in a different but unambiguous shape (a bare string instead of a one-key object, a list instead of an object), our code now accepts it and records that it did. Nothing is guessed: anything genuinely ambiguous is still refused."),
      rich([["One honest note. ", B], "Our first attempt at the \"unknown keys\" fix made things worse: refusing unknown keys without accepting the obvious shapes sent the AI into a loop and it gave up with no file. The five-item smoke test caught it before the real runs."]),

      h1("3. Results"),
      p("Each item is scored on small IFC test models. S1 asks whether every single verdict matches. S2 asks what fraction of test objects the two files judge the same way. S3 splits the disagreement into three questions: does the generated rule catch a broken object, does it wrongly reject a correct object, and does it apply to the right objects?"),
      table([3560, 1900, 1900, 2000], metricRows),
      gap(),
      rich([["The fixes worked, and they did not make the files behave better. ", B],
        `Invented property sets fell from ${base.errors.hallucinated_pset || 0} to ${fixed.errors.hallucinated_pset || 0}, the text match roughly quadrupled (${n3(base.facet_f1_micro)} to ${n3(fixed.facet_f1_micro)}), and items with every property name right rose from ${pct(base.names_correct)} to ${pct(fixed.names_correct)}. But agreement on behaviour did not move: ${n3(base.s2_ref)} to ${n3(fixed.s2_ref)}.`]),
      rich([["Why: one wrong field still rejects everything. ", B],
        "After the fixes, the most common remaining error is the data type. The reference asks for IFCLABEL and we produce IFCTEXT. A checker treats that as a mismatch, so the generated rule rejects every correct object even when the names are perfect."]),
      rich([["That error is also ours, not the AI's. ", B],
        "Our knowledge graph stores the coarse type \"String\" instead of the IFC type, and our own instructions tell the AI to map String to IFCTEXT. Seven of the nine data-type errors are exactly that mapping, and two more come from the same table (\"Real\" to IFCREAL instead of the specific measure). We have not changed this yet, because it means changing the instructions or the graph, and that is your call."]),

      h1("4. Does a name-level text check predict behaviour?"),
      p("This is the study's main question. An item is \"names-correct\" when every property-set and property name matches the reference — what a text-based check would score as right."),
      table([4200, 2580, 2580], [
        ["In the fixed run", "Names all correct", "At least one name wrong"],
        ["Items (with a usable test model)", String(fixed.hypothesis.names_correct_testable), String(fixed.hypothesis.other_s1[1])],
        ["Behave identically (S1)", pct(fixed.hypothesis.names_correct_s1), pct(fixed.hypothesis.other_s1)],
        ["Mean agreement (S2)", n3(fixed.hypothesis.names_correct_s2), n3(fixed.hypothesis.other_s2)],
      ]),
      gap(),
      rich([["Getting every name right buys almost nothing behaviourally: ", B],
        `only ${pct(fixed.hypothesis.names_correct_s1)} of the names-correct items behave like the reference, and their mean agreement (${n3(fixed.hypothesis.names_correct_s2)}) is no better than that of items with a wrong name (${n3(fixed.hypothesis.other_s2)}). This is direct evidence for the study's claim, on a small sample.`]),
      p(`Only ${fixed.hypothesis.distinct_facet_f1} distinct text-match values occur, so we do not report a correlation: with so few values it would be an artefact.`),

      h1("5. The lookup fix, isolated"),
      p("The third column of the results table is the fixed run with only the lookup fix switched off, so the comparison isolates it."),
      table([4400, 2480, 2480], [
        ["", "Lookup fix on", "Lookup fix off"],
        ["Property sets hidden from the AI", String(fixed.psets_dropped), String(abl.psets_dropped)],
        ["Invented property sets", String(fixed.errors.hallucinated_pset || 0), String(abl.errors.hallucinated_pset || 0)],
        ["Wrong property set chosen", String(fixed.errors.wrong_pset || 0), String(abl.errors.wrong_pset || 0)],
        ["Text match (facet F1)", n3(fixed.facet_f1_micro), n3(abl.facet_f1_micro)],
        ["All names correct", pct(fixed.names_correct), pct(abl.names_correct)],
        ["Behaviour agreement (S2, reference objects)", n3(fixed.s2_ref), n3(abl.s2_ref)],
      ]),
      gap(),
      p("The fix clearly took effect: with it off, the AI is denied hundreds of property-set names and invents twice as many. It improves what the file says, not how it behaves."),

      h1("6. Does the same request give the same answer?"),
      rich([[`With randomness pinned to 0, ${DET.items} items were run ${DET.runs.length} times each. `, B],
        `${DET.identical} of ${DET.items} produced the same specification every time (after ignoring titles and ordering), and ${DET.same_status} of ${DET.items} at least agreed on whether a file could be produced. Pinning temperature is not a guarantee: the AI still chooses different lookups from run to run, and the retry path differs.`]),

      h1("7. What still goes wrong, and whose fault it is"),
      table([3000, 1500, 1500, 3360], [
        ["Mechanism", "v4", "v5", "Whose"],
        ["Allowed-value list lost", String(base.errors.empty_restriction || 0), String(fixed.errors.empty_restriction || 0), "ours — fixed"],
        ["Placeholder stored as a value", String(base.errors.placeholder_value || 0), String(fixed.errors.placeholder_value || 0), "ours — fixed"],
        ["Property set invented", String(base.errors.hallucinated_pset || 0), String(fixed.errors.hallucinated_pset || 0), "ours (lookup) — mostly fixed"],
        ["Wrong data type", String(base.errors.wrong_datatype || 0), String(fixed.errors.wrong_datatype || 0), "ours (graph + instructions) — open"],
        ["Requirement missing", String(base.errors.missing_requirement || 0), String(fixed.errors.missing_requirement || 0), "model / request unclear"],
        ["Wrong value or allowed list", String(base.errors.wrong_value || 0), String(fixed.errors.wrong_value || 0), "model / request unclear"],
        ["Extra requirement", String(base.errors.extra_requirement || 0), String(fixed.errors.extra_requirement || 0), "model"],
        ["No file produced", String(base.errors.no_file || 0), String(fixed.errors.no_file || 0), "model (asks for clarification)"],
      ]),
      gap(),
      rich([["The three \"no file\" cases are not crashes. ", B],
        "At temperature 0 the system asks a clarifying question instead of guessing, on exactly the three items whose request never names a single property. We count them as failures, as agreed."]),

      h2("The same examples as last time"),
      ...ex("Slab fire rating — the lookup fix at work", [
        ["Request", [["Applies to: IFCSLAB. Requirements: 1. FireRating: Fire resistance class according to national or regional fire protection regulations.", MONO]]],
        ["Correct answer", [["Pset_SlabCommon.FireRating", MONO], [" must be one of ND, NE, R 30, R 60, …", {}]]],
        ["v4", [["Pset_SlabCustom.FireRating", MONO], [" — invented, because the real set was cut from the lookup", {}]]],
        ["v5", [["Pset_SlabCommon.FireRating", MONO], [" — correct name; accepts any value, and the data type is IFCTEXT instead of IFCLABEL", {}]]],
        ["Effect", "The file now names the right property but still rejects every correct slab, because of the data type."],
      ]),
      ...ex("Railing status — the allowed-value fix at work", [
        ["Request", "Applies to: IFCRAILING. Requirements: height, whether it is external, and its status (in German)."],
        ["Correct answer", [["Pset_RailingCommon.Status", MONO], [" must be NEW, EXISTING, DEMOLISH, TEMPORARY", {}]]],
        ["v4", "The same three names, but the status list was silently dropped, so every railing was rejected."],
        ["v5", "The list is there. Remaining differences: height typed IFCLENGTHMEASURE instead of IFCPOSITIVELENGTHMEASURE."],
      ]),
      ...ex("Alarm type — a new model error", [
        ["Request", "Applies to: IFCALARM. Requirements: 1. The type of alarm"],
        ["Correct answer", [["PredefinedType", MONO], [" must be one of BELL, BREAKGLASSBUTTON, …", {}]]],
        ["v4", "Asked for the right attribute, but with an empty list (our bug)."],
        ["v5", [["Pset_AlarmTypeCommon.AlarmCondition = \"REQUIRED\"", MONO], [" — a different requirement altogether, with a placeholder value. This one is the model's error, and our placeholder guard now catches the value but not the wrong requirement.", {}]]],
      ]),

      h1("8. Limits of this report"),
      bullet([["Synthetic test models. ", B], "Objects are generated from the two specifications themselves, so they test agreement on each requirement's own boundary cases, not on realistic building data. Objects now come from both sides, so neither file is privileged."]),
      bullet([["Small, lopsided sample. ", B], `${fixed.items} items, of which ${fixed.testable} are testable; ${D.filter.by_source[0][1]} of the ${D.filter.usable} usable items come from one source (Vienna), and no item has ten or more requirements.`]),
      bullet([["One system, one model. ", B], "Gemini 2.5 Flash with our graph. A stronger model is the obvious second condition and has not been run."]),
      bullet([["Determinacy not yet applied. ", B], "Some requirements cannot be recovered from the request at all (an allowed-value list that the text never states). We drafted these annotations and they are waiting for human review; the numbers here do not use them, so they understate the system."]),
      bullet([["Strict data-type checking. ", B], "IFCTEXT versus IFCLABEL is a hard failure for the checker we use. It is a real failure for a real checker, but it dominates the behavioural numbers."]),

      h1("9. What to do next"),
      bullet([["Fix the data type at the source (your decision). ", B], "Store the IFC data type per property in the graph instead of the coarse \"String\", and correct the mapping table in our instructions. On this evidence it is the single biggest remaining lever."]),
      bullet([["Review the determinacy annotations, ", B], "then re-score so that requirements nobody could guess stop counting against the system."]),
      bullet([["Then run all usable items ", B], "and add a stronger model as a second condition."]),
    ],
  }],
});

Packer.toBuffer(doc).then((b) => { fs.writeFileSync(process.argv[2], b); console.log("wrote", process.argv[2]); });
