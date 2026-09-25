"""A toy 'LLM' that emits ticket JSON but sometimes gets it wrong, the way real models do.

Faults are injected with a seeded RNG. On a retry the generator receives the validator's error
messages as feedback and the fault probability drops (it imitates a model that follows the error message
most of the time, but not always).
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional, Tuple

import numpy as np

SYNTAX_FAULTS = ["markdown_fence", "trailing_comma", "single_quotes", "truncated", "prose_prefix"]
SCHEMA_FAULTS = ["missing_field", "number_as_string", "enum_case", "extra_field", "bad_tag", "negative_amount"]
ALL_FAULTS = SYNTAX_FAULTS + SCHEMA_FAULTS

_NAMES = ["Asha Rao", "Ben Ortiz", "Chen Wei", "Dana Kim", "Eli Novak", "Farah Ali", "Gus Lund", "Hana Sato"]
_CATS = {"billing": ["refund", "double_charge", "invoice"], "shipping": ["late", "lost_parcel", "address"],
         "technical": ["crash", "login_bug", "slow"], "account": ["password", "delete_account", "email_change"]}


def make_requests(n: int, rng: np.random.Generator) -> List[Dict]:
    """Ground-truth ticket per request (what a perfect model would output)."""
    reqs = []
    for i in range(n):
        cat = list(_CATS)[rng.integers(4)]
        t = {"customer": _NAMES[rng.integers(len(_NAMES))], "category": cat,
             "priority": ["low", "medium", "high"][rng.integers(3)],
             "amount": float(round(rng.uniform(0, 500), 2)) if cat == "billing" else 0.0,
             "tags": list(rng.choice(_CATS[cat], size=int(rng.integers(1, 3)), replace=False))}
        if rng.random() < 0.5:
            t["order_id"] = f"ORD-{rng.integers(10000, 99999)}"
        reqs.append({"id": f"req{i:03d}", "truth": t})
    return reqs


def _apply(fault: str, obj: Dict) -> Tuple[Optional[Dict], Optional[str]]:
    """Return (object_to_serialise, raw_text_override)."""
    o = json.loads(json.dumps(obj))
    if fault == "missing_field":
        o.pop("priority")
    elif fault == "number_as_string":
        o["amount"] = f"{o['amount']}"
    elif fault == "enum_case":
        o["priority"] = o["priority"].upper()
    elif fault == "extra_field":
        o["confidence"] = 0.93
    elif fault == "bad_tag":
        o["tags"] = [t.replace("_", " ").title() for t in o["tags"]]
    elif fault == "negative_amount":
        o["amount"] = -abs(o["amount"]) - 1.0
    else:
        txt = json.dumps(o)
        if fault == "markdown_fence":
            return None, f"```json\n{txt}\n```"
        if fault == "trailing_comma":
            return None, txt[:-1] + ", }"
        if fault == "single_quotes":
            return None, txt.replace('"', "'")
        if fault == "truncated":
            return None, txt[: int(len(txt) * 0.85)]
        if fault == "prose_prefix":
            return None, "Sure! Here is the ticket you asked for:\n" + txt
    return o, None


class ToyLLM:
    def __init__(self, rng: np.random.Generator, p_fault: float = 0.45, p_fault_retry: float = 0.25):
        self.rng, self.p_fault, self.p_fault_retry = rng, p_fault, p_fault_retry

    def generate(self, request: Dict, feedback: Optional[List[str]] = None) -> Tuple[str, Optional[str]]:
        """Returns (raw_text, injected_fault_or_None)."""
        p = self.p_fault if feedback is None else self.p_fault_retry
        fault = None
        if self.rng.random() < p:
            fault = ALL_FAULTS[self.rng.integers(len(ALL_FAULTS))]
            obj, raw = _apply(fault, request["truth"])
            return (raw if raw is not None else json.dumps(obj)), fault
        return json.dumps(request["truth"]), None
