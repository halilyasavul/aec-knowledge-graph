# Predictions for the 2x2 experiment

Committed before any cell was run (work order v6 §4). Factors: the lookup fix (tool results
never drop a property-set name) and the dataType fix (the graph serves the exact IFC type and
the prompt tells the model to copy it). All other v5 fixes on, temperature 0, model pinned,
21 items, 3 repeats per cell.

## P1 — the dataType fix sharply cuts false rejection and raises S2

In v5, 9 of 18 items had a wrong dataType and 7 of those were exactly IFCLABEL -> IFCTEXT,
produced by our own mapping table. A single wrong dataType makes the candidate reject every
conforming object, so false rejection sat at 0.81 with the names already correct.

Expect: false rejection well below 0.81 in both dataType-on cells, and S2 on reference-derived
objects above the 0.51 it has held at since v4.

## P2 — the lookup fix raises S2 only when the dataType fix is also on

The lookup fix improved names (facet F1 0.09 -> 0.19) without moving S2, because a wrong
dataType rejected conforming objects regardless of the name. Once the type is right, a correct
name should finally pay off behaviourally.

Expect: S2(lookup on, dataType on) > S2(lookup off, dataType on), while
S2(lookup on, dataType off) is about equal to S2(lookup off, dataType off).

## P3 — once dataType is fixed, the names-correct gap opens

In v5 the names-correct items had mean S2 0.48 against 0.51 for items with a wrong name: no
advantage at all, because the dataType error hit both groups.

Expect: in the dataType-on cells, names-correct items show a clearly higher mean S2 than
items with at least one wrong name. If the gap stays closed there too, then names really do
not predict behaviour even with the plumbing fixed — a stronger version of the study's claim.

## What would falsify the fix rather than the prediction

If false rejection stays near 0.81 in the dataType-on cells, check the dataType source log
(`dt_from_graph` vs `dt_model_choice`): the model may not be copying `ifc_type` at all, in
which case the fix did not take effect and the cell comparison says nothing.
