"""Input and output guardrails: regex/keyword detectors, no ML, fully inspectable."""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

INJECTION_PATTERNS = [
    r"\bignore\b.{0,30}\b(previous|prior|above|all|earlier)\b.{0,20}\b(instructions?|rules?|prompts?)",
    r"\bdisregard\b.{0,40}\b(instructions?|rules?|guidelines?|system)",
    r"\b(reveal|print|show|repeat|leak)\b.{0,30}\b(system|hidden|secret)\b.{0,15}\b(prompt|instructions?|message)",
    r"\byou are now\b|\bpretend (you are|to be)\b|\bact as (an? )?(unfiltered|unrestricted|jailbroken)",
    r"\b(developer|dan|god) mode\b|\bjailbreak\b",
    r"\bno (longer )?(bound|restricted) by\b|\bwithout (any )?(restrictions|filters|rules)\b",
    r"</?(system|assistant)>|\[\s*system\s*\]",
]
_INJ = [re.compile(p, re.I) for p in INJECTION_PATTERNS]

PII_PATTERNS = {
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    "phone": r"(?<!\d)(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}|\d{5}[\s-]?\d{5})(?!\d)",
    "credit_card": r"(?<!\d)\d(?:[ -]?\d){12,15}(?!\d)",
    "ssn": r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)",
    "ip_address": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
}
_PII = {k: re.compile(v) for k, v in PII_PATTERNS.items()}
BANNED_OUTPUT_TERMS = ["idiot", "stupid", "hate you", "kill yourself"]
SYSTEM_CANARY = "CANARY-7f3a"  # a secret token planted in the system prompt; must never appear in output


def _luhn(digits: str) -> bool:
    d = [int(c) for c in digits][::-1]
    s = sum(d[0::2]) + sum(sum(divmod(2 * x, 10)) for x in d[1::2])
    return s % 10 == 0


def find_pii(text: str) -> List[Tuple[str, str]]:
    hits = []
    for kind, rx in _PII.items():
        for m in rx.finditer(text):
            s = m.group(0)
            if kind == "credit_card":
                digits = re.sub(r"\D", "", s)
                if not (13 <= len(digits) <= 16 and _luhn(digits)):
                    continue
            if kind == "ip_address" and not all(0 <= int(x) <= 255 for x in s.split(".")):
                continue
            hits.append((kind, s))
    # a credit-card number can also look like a phone number; keep the more specific label
    cc = {s for k, s in hits if k == "credit_card"}
    return [(k, s) for k, s in hits if not (k == "phone" and any(s in c for c in cc))]


def redact(text: str) -> str:
    for kind, s in sorted(find_pii(text), key=lambda x: -len(x[1])):
        text = text.replace(s, f"[{kind.upper()}]")
    return text


def detect_injection(text: str) -> List[str]:
    return [p.pattern[:40] for p in _INJ if p.search(text)]


def input_guard(text: str) -> Dict:
    """Block prompt-injection attempts; redact (not block) PII so the request can still be served."""
    inj = detect_injection(text)
    pii = find_pii(text)
    return {"action": "block" if inj else ("redact" if pii else "allow"), "injection_hits": inj,
            "pii": [k for k, _ in pii], "sanitized": redact(text) if not inj else None}


def output_guard(text: str) -> Dict:
    """Block system-prompt leaks and abusive text; redact PII the model may have echoed."""
    reasons = []
    if SYSTEM_CANARY in text or re.search(r"\bmy (system )?instructions (are|say)\b", text, re.I):
        reasons.append("system_prompt_leak")
    if any(t in text.lower() for t in BANNED_OUTPUT_TERMS):
        reasons.append("toxicity")
    pii = find_pii(text)
    action = "block" if reasons else ("redact" if pii else "allow")
    return {"action": action, "reasons": reasons, "pii": [k for k, _ in pii], "text": redact(text) if action == "redact" else text}
