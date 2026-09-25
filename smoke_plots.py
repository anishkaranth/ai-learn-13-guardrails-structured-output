"""Matplotlib SVG plots + RESULTS.md writer for the guardrails smoke run."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from svg_utils import minify_svg  # noqa: E402

plt.rcParams.update({"svg.hashsalt": "ai-learn-13", "svg.fonttype": "none", "font.family": "sans-serif",
                     "font.sans-serif": ["DejaVu Sans"], "axes.unicode_minus": False})


def _save(fig, path: Path) -> str:
    fig.tight_layout()
    buf = io.StringIO()
    fig.savefig(buf, format="svg", metadata={"Date": None})
    plt.close(fig)
    path.write_text(minify_svg(buf.getvalue()), encoding="utf-8")
    return path.name


def make_plots(out: Path, m: Dict[str, Any]) -> List[str]:
    names = []
    s = m["structured_output"]
    conds = list(s)
    x = np.arange(len(conds))
    fig, ax = plt.subplots(figsize=(6, 3.6))
    ax.bar(x - 0.2, [s[c]["valid_rate"] for c in conds], 0.4, label="schema-valid", color="#126782")
    ax.bar(x + 0.2, [s[c]["faithful_rate"] for c in conds], 0.4, label="valid and equal to ground truth", color="#8ecae6")
    ax.set_xticks(x, [c.replace("_", " ") for c in conds])
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("rate")
    ax.set_title(f"Structured output: repair and retry (n={m['config']['n_requests']})")
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, frameon=False)
    names.append(_save(fig, out / "valid_rate_by_strategy.svg"))

    pf = {k: v for k, v in m["per_fault"].items() if v["n"]}
    ks = list(pf)
    y = np.arange(len(ks))
    fig, ax = plt.subplots(figsize=(6, 4.4))
    ax.barh(y + 0.2, [pf[k]["repair_only_valid"] for k in ks], 0.4, label="repair only", color="#e9c46a")
    ax.barh(y - 0.2, [pf[k]["repair_plus_retry_valid"] for k in ks], 0.4, label="repair + retry", color="#126782")
    ax.set_yticks(y, [f"{k} ({pf[k]['kind']}, n={pf[k]['n']})" for k in ks], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.05)
    ax.set_xlabel("final valid rate")
    ax.set_title("Recovery by injected fault type")
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2, frameon=False)
    names.append(_save(fig, out / "recovery_by_fault.svg"))

    g = m["guards"]
    dets = [("input: injection block", g["input_injection_block"]), ("input: PII detect", g["input_pii_detect"]),
            ("output: block", g["output_block"])]
    x = np.arange(len(dets))
    fig, ax = plt.subplots(figsize=(6, 3.6))
    ax.bar(x - 0.2, [d["precision"] for _, d in dets], 0.4, label="precision", color="#2a9d8f")
    ax.bar(x + 0.2, [d["recall"] for _, d in dets], 0.4, label="recall", color="#e76f51")
    ax.set_xticks(x, [n for n, _ in dets])
    ax.set_ylim(0, 1.05)
    ax.set_title("Guardrail detectors on labeled sets")
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2, frameon=False)
    names.append(_save(fig, out / "guard_precision_recall.svg"))
    return names


def _pct(x) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def write_results_md(path: Path, m: Dict[str, Any]) -> None:
    s, g, e = m["structured_output"], m["guards"], m["guard_errors"]
    c = m["config"]
    L = ["# Results: guardrails and structured output (smoke run)", "",
         f"Seed {m['seed']}. Runtime {m['runtime_sec']}s. {c['n_requests']} ticket-extraction requests. The toy LLM injects a fault "
         f"on the first attempt with p={c['p_fault']} and on retries with p={c['p_fault_retry']} (retries receive the validator's errors). "
         f"Max retries: {c['max_retries']}.", "",
         "## Valid-output rate before vs after repair", "",
         "| strategy | schema-valid | valid and equal to truth | mean LLM calls | total calls |", "|---|---|---|---|---|"]
    for k, v in s.items():
        L.append(f"| {k} | **{_pct(v['valid_rate'])}** | {_pct(v['faithful_rate'])} | {v['mean_attempts']} | {v['total_llm_calls']} |")
    L += ["", "Per injected fault (first attempt):", "", "| fault | kind | n | repair only | repair + retry |", "|---|---|---|---|---|"]
    for k, v in m["per_fault"].items():
        L.append(f"| {k} | {v['kind']} | {v['n']} | {_pct(v['repair_only_valid'])} | {_pct(v['repair_plus_retry_valid'])} |")
    L += ["", f"Repairs applied (repair + retry): {m['repair_fix_counts']}", "",
          "## Guardrail detectors (hand-labeled sets)", "",
          "| detector | n | precision | recall | F1 | TP/FP/FN |", "|---|---|---|---|---|---|"]
    for name, key in [("input injection block", "input_injection_block"), ("input PII detection", "input_pii_detect"),
                      ("output block", "output_block")]:
        d = g[key]
        L.append(f"| {name} | {d['n']} | **{_pct(d['precision'])}** | **{_pct(d['recall'])}** | {d['f1']} | {d['tp']}/{d['fp']}/{d['fn']} |")
    L += ["", "Errors (kept visible on purpose):", ""]
    for k, v in e.items():
        L.append(f"- **{k}** ({len(v)}): " + ("; ".join(f"`{t}`" for t in v) if v else "none"))
    L += ["", "## Takeaways", "",
          "- Deterministic syntax repair (fences, prose, quotes, trailing commas, truncation) fixes most malformed JSON without another LLM call.",
          "- Schema faults with no safe fix (missing field, negative amount) need a retry with the validator errors as feedback. Repair and retry together work best.",
          "- A valid output is not always a correct one: closing a truncated object can silently drop fields. Track faithfulness separately from validity.",
          "- Regex guards reach high precision, but paraphrased or obfuscated injections, spelled-out numbers and paraphrased leaks slip through. Recall is the weak side.", "",
          "Plots: " + ", ".join(f"`{p}`" for p in m["plots"]), ""]
    path.write_text("\n".join(L), encoding="utf-8")
