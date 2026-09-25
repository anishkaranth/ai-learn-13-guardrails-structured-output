"""Parse -> validate -> repair -> (retry with feedback) loop."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from schema import validate


def strict_parse(text: str) -> Tuple[Optional[Any], Optional[str]]:
    try:
        return json.loads(text), None
    except json.JSONDecodeError as e:
        return None, f"json: {e.msg}"


def lenient_parse(text: str) -> Tuple[Optional[Any], List[str]]:
    """Deterministic syntax repairs, applied in order; returns (obj, list_of_fixes)."""
    fixes = []
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t, _ = m.group(1).strip(), fixes.append("strip_fence")
    if not t.startswith("{") and "{" in t:
        t, _ = t[t.index("{"):], fixes.append("strip_prose")
    if "'" in t and '"' not in t:
        t, _ = t.replace("'", '"'), fixes.append("quotes")
    t2 = re.sub(r",\s*([}\]])", r"\1", t)
    if t2 != t:
        t, _ = t2, fixes.append("trailing_comma")
    obj, err = strict_parse(t)
    if obj is None:  # try closing a truncated object: drop the dangling partial token, then close brackets
        cut = max(t.rfind(","), t.rfind("["))
        for cand in (t, t[:cut] if cut > 0 else t):
            c = cand.rstrip().rstrip(",")
            if c.count('"') % 2:
                c += '"'
            c += "]" * max(0, c.count("[") - c.count("]")) + "}" * max(0, c.count("{") - c.count("}"))
            obj, err = strict_parse(c)
            if obj is not None:
                fixes.append("close_truncated")
                break
    return obj, fixes


def coerce(obj: Any, schema: Dict[str, Any]) -> Tuple[Any, List[str]]:
    """Schema-guided value repairs: numeric strings, enum case, drop unknown keys, normalise tags."""
    fixes = []
    if not isinstance(obj, dict):
        return obj, fixes
    props = schema.get("properties", {})
    out = {}
    for k, v in obj.items():
        if k not in props and schema.get("additionalProperties", True) is False:
            fixes.append(f"drop:{k}")
            continue
        ps = props.get(k, {})
        if ps.get("type") == "number" and isinstance(v, str):
            try:
                v = float(v)
                fixes.append(f"to_number:{k}")
            except ValueError:
                pass
        if ps.get("type") == "string" and "enum" in ps and isinstance(v, str) and v not in ps["enum"] and v.lower() in ps["enum"]:
            v = v.lower()
            fixes.append(f"enum_case:{k}")
        if ps.get("type") == "array" and isinstance(v, list) and ps.get("items", {}).get("pattern") == "[a-z_]+":
            nv = [re.sub(r"[^a-z_]", "_", str(x).lower()) for x in v]
            if nv != v:
                v = nv
                fixes.append(f"normalise:{k}")
        out[k] = v
    return out, fixes


def run_pipeline(llm, request: Dict, schema: Dict, *, repair: bool, max_retries: int) -> Dict:
    """Returns a trace with final validity, attempts and fixes. Repairs never invent missing values."""
    feedback = None
    trace = {"attempts": 0, "faults": [], "fixes": [], "valid": False, "errors": []}
    for attempt in range(max_retries + 1):
        raw, fault = llm.generate(request, feedback)
        trace["attempts"] += 1
        trace["faults"].append(fault)
        obj, perr = strict_parse(raw)
        if obj is None and repair:
            obj, fx = lenient_parse(raw)
            trace["fixes"] += fx
        if obj is None:
            errs = [perr or "json: unparseable"]
        else:
            if repair:
                obj, fx = coerce(obj, schema)
                trace["fixes"] += fx
            errs = validate(obj, schema)
        if not errs:
            trace.update(valid=True, output=obj, errors=[])
            return trace
        trace["errors"] = errs
        feedback = errs
    return trace
