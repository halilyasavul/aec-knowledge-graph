"""Regression tests for the v9 request-fidelity checks.

Each case is a defect observed in the v8 evaluation (eval/reports/v9/README.md): a property
name with a space, a Boolean pinned where the request asks for the property to be recorded,
a truncated IFC enumeration, invented values and bounds, and a reply that claims a file
that was never produced.
"""
import pytest

import aec_kg.ids.request_checks as rc
import aec_kg.main_orchestrator as mo
from aec_kg.ids.pipeline import generate_ids_from_json
from aec_kg.ids.request_checks import RequestContext, reconcile_attachment_claim

STATUS = ["NEW", "EXISTING", "DEMOLISH", "TEMPORARY", "OTHER", "NOTKNOWN", "UNSET"]

RAMP_RESULT = {
    "class_code": "IfcRamp",
    "property_sets": {
        "Pset_RampCommon": {"properties": [
            {"code": "FireExit", "ifc_type": "IFCBOOLEAN", "allowed_values": []},
            {"code": "FireRating", "ifc_type": "IFCLABEL", "allowed_values": []},
            {"code": "RequiredSlope", "ifc_type": "IFCPLANEANGLEMEASURE", "allowed_values": []},
            {"code": "Status", "ifc_type": "IFCLABEL", "allowed_values": [{"Code": v} for v in STATUS]},
        ]}}}

VIENNA_81 = ("Angabe, ob das Element Teil des Notausgangs/Fluchtwegs ist. Im Fall der Verwendung bei "
             "Türen/Fenstern/Fenstertüren: nur das letztendliche Element (Ausgang ins Freie) ist TRUE/WAHR.")
OMA_10 = "Indication whether this object is designed to serve as an exit in the case of fire"
VIENNA_STATUS = ('Status bzw. Phase des Bauteils. Neben den Standard-Werten des IFC-Schemas können auch '
                 'weiterhin die Werte aus der PDF-Datei verwendet werden: "Neu" (new), "Bestand" (existing), '
                 '"Abbruch" (demolish), "Temporär" (temporary).')
FIRE = "Feuerwiderstandsklasse gemäß der nationalen oder regionalen Brandschutzverordnung."


def ctx(request, learn=True):
    c = RequestContext(request_text=request)
    if learn:
        c.learn(RAMP_RESULT)
    return c


def doc(prop):
    return {"info": {"title": "t"},
            "specifications": [{"name": "s", "ifcVersion": "IFC4X3_ADD2",
                                "applicability": {"entity": {"name": {"simpleValue": "IFCRAMP"}}},
                                "requirements": {"properties": [prop]}}]}


def prop(name, value=None, pset="Pset_RampCommon", dtype=None):
    p = {"propertySet": {"simpleValue": pset}, "baseName": {"simpleValue": name}}
    if value is not None:
        p["value"] = value
    if dtype:
        p["dataType"] = dtype
    return p


def errors(d, c):
    out = generate_ids_from_json(d, c)
    return out.get("request_errors", []) if "error" in out else []


@pytest.fixture(autouse=True)
def _enabled():
    rc.set_request_checks(True)
    rc.GUARDS.clear()
    yield


# ---------------------------------------------------------------- names
def test_property_name_with_whitespace_is_rejected_even_offline():
    errs = errors(doc(prop("Fire Rating", dtype="IFCLABEL")), ctx(FIRE, learn=False))
    assert len(errs) == 1 and "whitespace" in errs[0]
    assert rc.GUARDS["property_name_whitespace"] == 1


def test_property_unknown_to_the_graph_is_rejected_with_a_suggestion():
    errs = errors(doc(prop("FireResistance", dtype="IFCLABEL")), ctx(FIRE))
    assert len(errs) == 1 and "no property 'FireResistance'" in errs[0] and "FireRating" in errs[0]


def test_property_in_an_unlooked_up_or_custom_pset_is_not_judged():
    assert errors(doc(prop("Flaechenart", pset="Pset_ONORM_B1800")), ctx(FIRE)) == []
    assert errors(doc(prop("Whatever", pset="Pset_WallCommon")), ctx(FIRE)) == []


# ---------------------------------------------------------------- record vs. require
@pytest.mark.parametrize("request_text", [VIENNA_81, OMA_10])
def test_boolean_pinned_where_the_request_asks_to_record_it(request_text):
    errs = errors(doc(prop("FireExit", {"simpleValue": "TRUE"}, dtype="IFCBOOLEAN")), ctx(request_text))
    assert len(errs) == 1 and "pinned to 'TRUE'" in errs[0]
    assert errors(doc(prop("FireExit", dtype="IFCBOOLEAN")), ctx(request_text)) == []


def test_boolean_pinned_where_the_request_says_so_is_fine():
    for text in ("Every ramp must be a fire exit: FireExit must be TRUE.",
                 "FireExit muss WAHR sein.", "FireExit = TRUE"):
        assert errors(doc(prop("FireExit", {"simpleValue": "TRUE"}, dtype="IFCBOOLEAN")), ctx(text)) == []


def test_boolean_type_comes_from_the_graph_when_the_model_omits_it():
    errs = errors(doc(prop("FireExit", {"simpleValue": "TRUE"})), ctx(OMA_10))
    assert len(errs) == 1 and "pinned" in errs[0]


# ---------------------------------------------------------------- enumerations
def test_truncated_ifc_enumeration_is_rejected_when_the_request_names_no_subset():
    errs = errors(doc(prop("Status", {"restriction": {"enumerations": STATUS[:4]}})),
                  ctx("Status bzw. Phase des Bauteils gemäss den Standard-Werten des IFC-Schemas."))
    assert len(errs) == 1 and "4 of the property's 7" in errs[0] and "NOTKNOWN" in errs[0]


def test_complete_enumeration_plus_values_the_request_names_is_fine():
    full = STATUS + ["Neu", "Bestand", "Abbruch", "Temporär"]
    assert errors(doc(prop("Status", {"restriction": {"enumerations": full}})), ctx(VIENNA_STATUS)) == []


def test_subset_the_request_names_is_fine():
    assert errors(doc(prop("Status", {"restriction": {"enumerations": ["NEW", "EXISTING"]}})),
                  ctx("Status must be NEW or EXISTING.")) == []


def test_enumeration_member_from_nowhere_is_rejected():
    errs = errors(doc(prop("FireRating", {"restriction": {"enumerations": ["ND", "REI 30", "REI 60"]}})), ctx(FIRE))
    assert len(errs) == 1 and "REI 30" in errs[0]


# ---------------------------------------------------------------- exact values and bounds
def test_exact_value_not_in_the_request_is_rejected():
    errs = errors(doc(prop("FireRating", {"simpleValue": "REI 90"})), ctx(FIRE))
    assert len(errs) == 1 and "'REI 90'" in errs[0]


def test_exact_value_in_the_request_is_fine_across_number_formats():
    text = "Die maximale Polygonanzahl ist beschränkt auf 10.000."
    c = ctx(text)
    assert errors(doc(prop("MaxPolygonCount", {"simpleValue": "10000"}, pset="Pset_Custom")), c) == []
    assert errors(doc(prop("MaxPolygonCount", {"restriction": {"maxInclusive": "10000"}}, pset="Pset_Custom")), c) == []


def test_bound_not_in_the_request_is_rejected():
    errs = errors(doc(prop("RequiredSlope", {"restriction": {"maxInclusive": "0.06"}})),
                  ctx("Erforderliche Neigung des Objekts relativ zur Horizontalen."))
    assert len(errs) == 1 and "maxInclusive='0.06'" in errs[0]
    assert errors(doc(prop("RequiredSlope", {"restriction": {"maxInclusive": "0.06"}})),
                  ctx("Neigung höchstens 0,06.")) == []


def test_checks_can_be_switched_off_for_ablation():
    rc.set_request_checks(False)
    assert errors(doc(prop("Fire Rating")), ctx(FIRE)) == []


def test_without_request_text_only_offline_checks_run():
    c = RequestContext()
    assert errors(doc(prop("FireRating", {"simpleValue": "REI 90"})), c) == []
    assert errors(doc(prop("Fire Rating")), c) != []


# ---------------------------------------------------------------- no file
def test_reply_claiming_a_file_that_was_never_made_is_corrected():
    text = "The IDS specification has been generated successfully and is attached."
    fixed = reconcile_attachment_claim(text, had_success=False)
    assert fixed.startswith(text) and "No IDS file was produced" in fixed
    assert reconcile_attachment_claim(text, had_success=True) == text
    assert reconcile_attachment_claim("I could not map that property.", had_success=False) == \
        "I could not map that property."


def test_generate_ids_stops_after_the_retry_cap():
    mo.TURN.reset("FireRating required.")
    bad = '{"info": {"title": "t"}, "specifications": []}'           # fails Pydantic (min_length)
    results = [mo.dispatch_tool("generate_ids", {"ids_json_string": bad}) for _ in range(rc.MAX_GENERATE_FAILURES + 1)]
    assert all("error" in r for r in results)
    assert "final_attempt" in results[rc.MAX_GENERATE_FAILURES - 1]
    assert results[-1].get("stop") is True and "will not be retried" in results[-1]["error"]
    assert mo.TURN.generate_failures == rc.MAX_GENERATE_FAILURES


def test_query_class_results_feed_the_checks_through_the_turn():
    mo.TURN.reset(FIRE)
    mo.TURN.ctx.learn(RAMP_RESULT)                                   # what dispatch_tool does on query_class
    out = mo.dispatch_tool("generate_ids", {"ids_json_string": __import__("json").dumps(
        doc(prop("FireResistance")))})
    assert "request_errors" in out and "FireRating" in out["request_errors"][0]
    assert mo.TURN.generate_success is False and mo.TURN.generate_failures == 1


def test_old_prompt_is_reproducible_for_resuming_earlier_runs():
    v9 = mo.SYSTEM_PROMPT
    mo.set_request_rules(False)
    try:
        assert "Record vs. require" not in mo.SYSTEM_PROMPT and "ifc_type" in mo.SYSTEM_PROMPT
    finally:
        mo.set_request_rules(True)
    assert mo.SYSTEM_PROMPT == v9 and "Record vs. require" in v9


# ---------------------------------------------------------------- the agent loop, offline
class _FakeResponse:
    def __init__(self, content):
        self.candidates = [type("C", (), {"content": content, "finish_reason": "STOP"})()]
        self.text = "".join(p.text or "" for p in content.parts if getattr(p, "text", None))


class _FakeClient:
    """Scripted Gemini: a generate_ids call with an empty document, then a reply claiming a file."""

    def __init__(self):
        from google.genai import types
        self.types = types
        self.calls = 0
        self.models = self

    def generate_content(self, model, contents, config):
        t = self.types
        self.calls += 1
        if self.calls == 1:
            part = t.Part.from_function_call(name="generate_ids", args={"ids_json_string":
                                             '{"info": {"title": "t"}, "specifications": []}'})
            return _FakeResponse(t.Content(role="model", parts=[part]))
        return _FakeResponse(t.Content(role="model", parts=[
            t.Part(text="The IDS specification has been generated successfully and is attached.")]))


def test_run_agent_marks_a_turn_that_produced_no_file(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(mo.genai, "Client", lambda api_key=None: fake)
    answer, contents, tool_log = mo.run_agent("Walls need a fire rating.")
    assert fake.calls == 2
    assert tool_log[0]["tool"] == "generate_ids" and "ids_error" in tool_log[0]
    assert "No IDS file was produced" in answer
    assert mo.TURN.ctx.request_text == "Walls need a fire rating."
