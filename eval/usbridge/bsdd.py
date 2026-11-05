"""bSDD usTransportation/usBridge — fetch once, cache every response under eval/usbridge/bsdd/.

    python -X utf8 -m eval.usbridge.bsdd            # fetch what is not cached yet
    python -X utf8 -m eval.usbridge.bsdd --offline  # cache only; fail on a miss

Every GET is stored as bsdd/<endpoint>/<sha1 of the full URL>.json with the URL in the file,
so a later run reproduces the same data without the network. `load()` returns the dictionary as
{"dictionary": ..., "classes": {uri: class detail}, "properties": {uri: property detail}}.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "bsdd"
API = "https://api.bsdd.buildingsmart.org"
DICT_URI = "https://identifier.buildingsmart.org/uri/usTransportation/usBridge/1"
IFC_URI = "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3"
OFFLINE = False
_session = requests.Session()
_session.headers["User-Agent"] = "aec-knowledge-graph-eval/1.0"


def get(path: str, **params) -> dict:
    url = f"{API}{path}?{urlencode(params)}"
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    f = CACHE / path.strip("/").replace("/", "_") / f"{key}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))["response"]
    if OFFLINE:
        raise FileNotFoundError(f"not cached: {url}")
    for attempt in range(8):
        r = _session.get(url, timeout=90)
        if r.status_code in (429, 500, 502, 503, 504):
            wait = r.headers.get("Retry-After")
            time.sleep(float(wait) if wait and wait.replace(".", "").isdigit() else min(60, 3 * 2 ** attempt))
            continue
        break
    r.raise_for_status()
    data = r.json()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"url": url, "fetched": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                             "response": data}, ensure_ascii=False, indent=1), encoding="utf-8")
    time.sleep(0.15)
    return data


def paged(path: str, key: str, **params) -> list:
    out, offset = [], 0
    while True:
        d = get(path, Offset=offset, Limit=1000, **params)
        page = d.get(key) or []
        out += page
        total = d.get("totalCount") or d.get(f"{key}TotalCount")
        offset += len(page)
        if not page or (total is not None and offset >= total):
            return out


def load() -> dict:
    head = get("/api/Dictionary/v1", Uri=DICT_URI, IncludeTestDictionaries="true")
    classes = paged("/api/Dictionary/v1/Classes", "classes", Uri=DICT_URI, UseNestedClasses="false")
    props = paged("/api/Dictionary/v1/Properties", "properties", Uri=DICT_URI)
    # Class/v1 with IncludeClassProperties is deprecated and rate-limited hard (429 after two
    # calls); the class head and Class/Properties/v1 are not.
    def class_detail(u: str) -> dict:
        head = get("/api/Class/v1", Uri=u, IncludeClassRelations="true", IncludeChildClassReferences="true")
        cps, offset = [], 0
        while True:
            page = get("/api/Class/Properties/v1", ClassUri=u, Offset=offset, Limit=1000)
            cps += page.get("classProperties") or []
            offset += len(page.get("classProperties") or [])
            if not page.get("classProperties") or offset >= (page.get("totalCount") or 0):
                break
        return {**head, "classProperties": cps}

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=1 if OFFLINE else 2) as pool:
        cls_detail = dict(zip([c["uri"] for c in classes], pool.map(class_detail, [c["uri"] for c in classes])))
        prop_detail = dict(zip([p["uri"] for p in props], pool.map(
            lambda u: get("/api/Property/v4", uri=u, IncludeClasses="false"), [p["uri"] for p in props])))
    return {"dictionary": head, "class_list": classes, "property_list": props,
            "classes": cls_detail, "properties": prop_detail}


def main(argv=None):
    global OFFLINE
    argv = sys.argv[1:] if argv is None else argv
    OFFLINE = "--offline" in argv
    d = load()
    files = sum(1 for _ in CACHE.rglob("*.json"))
    print(json.dumps({"dictionary": DICT_URI, "classes": len(d["classes"]), "properties": len(d["properties"]),
                      "cached_responses": files}, indent=1))


if __name__ == "__main__":
    main()
