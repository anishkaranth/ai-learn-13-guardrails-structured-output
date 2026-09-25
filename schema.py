"""A tiny JSON-Schema-like validator written from scratch.

Supported keywords: type, properties, required, additionalProperties (bool), enum, minimum, maximum,
minLength, maxLength, pattern, items, minItems, maxItems. Errors are returned as "path: message" strings.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def validate(value: Any, schema: Dict[str, Any], path: str = "$") -> List[str]:
    errs: List[str] = []
    t = schema.get("type")
    if t is not None and not _TYPES[t](value):
        return [f"{path}: expected {t}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: {value!r} not in enum {schema['enum']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errs.append(f"{path}: {value} < minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errs.append(f"{path}: {value} > maximum {schema['maximum']}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errs.append(f"{path}: shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errs.append(f"{path}: longer than maxLength {schema['maxLength']}")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            errs.append(f"{path}: does not match pattern {schema['pattern']}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errs.append(f"{path}: fewer than minItems {schema['minItems']}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errs.append(f"{path}: more than maxItems {schema['maxItems']}")
        if "items" in schema:
            for i, v in enumerate(value):
                errs += validate(v, schema["items"], f"{path}[{i}]")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in value:
                errs.append(f"{path}: missing required '{k}'")
        for k, v in value.items():
            if k in props:
                errs += validate(v, props[k], f"{path}.{k}")
            elif schema.get("additionalProperties", True) is False:
                errs.append(f"{path}: unexpected property '{k}'")
    return errs


# The schema our toy "LLM" must follow: extract a support ticket from a user message.
TICKET_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["customer", "category", "priority", "amount", "tags"],
    "additionalProperties": False,
    "properties": {
        "customer": {"type": "string", "minLength": 2, "maxLength": 40},
        "category": {"type": "string", "enum": ["billing", "shipping", "technical", "account"]},
        "priority": {"type": "string", "enum": ["low", "medium", "high"]},
        "amount": {"type": "number", "minimum": 0, "maximum": 10000},
        "tags": {"type": "array", "items": {"type": "string", "pattern": "[a-z_]+"}, "minItems": 1, "maxItems": 5},
        "order_id": {"type": "string", "pattern": "ORD-[0-9]{5}"},
    },
}
