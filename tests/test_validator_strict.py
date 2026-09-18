"""Strict mode must turn an unloadable XSD into an error, never a pass."""
import pytest

import aec_kg.ids.validator as v


@pytest.fixture
def missing_xsd(monkeypatch, tmp_path):
    monkeypatch.setattr(v, "IDS_XSD_PATH", tmp_path / "nope.xsd")
    monkeypatch.setattr(v, "_schema", None)
    monkeypatch.setattr(v, "_schema_load_attempted", False)
    monkeypatch.setattr(v, "_schema_load_error", None)


def test_lenient_default_passes_when_xsd_missing(missing_xsd):
    assert v.validate_ids_xml("<x/>", strict=False) == (True, [])


def test_strict_raises_when_xsd_missing(missing_xsd):
    with pytest.raises(v.XsdUnavailableError):
        v.validate_ids_xml("<x/>", strict=True)


def test_module_flag_enables_strict(missing_xsd, monkeypatch):
    monkeypatch.setattr(v, "STRICT", True)
    with pytest.raises(v.XsdUnavailableError):
        v.validate_ids_xml("<x/>")
