from __future__ import annotations

import json
from typing import Any

from app.rca.rca_models import RCAResult


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _string_list(items: Any, *keys: str) -> list[str]:
    if not isinstance(items, list):
        return []
    result: list[str] = []
    for item in items:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = ""
            for key in keys:
                if item.get(key) is not None:
                    text = _as_text(item.get(key))
                    if text:
                        break
        else:
            text = _as_text(item)
        if text:
            result.append(text)
    return result


def _evidence_refs(items: Any) -> list[dict]:
    if not isinstance(items, list):
        return []
    refs = []
    for item in items:
        if not isinstance(item, dict):
            continue
        service = _as_text(item.get("service_name") or item.get("service") or item.get("resource") or "unknown")
        evidence_type = _as_text(item.get("evidence_type") or item.get("type") or "observation")
        observation = _as_text(item.get("observation") or item.get("detail") or item.get("message"))
        if observation:
            refs.append({
                "service_name": service,
                "evidence_type": evidence_type,
                "observation": observation,
            })
    return refs


def normalize_rca_payload(payload: dict) -> dict:
    """Normalize common structured-output drift without inventing evidence."""
    if "rca" in payload and isinstance(payload["rca"], dict):
        payload = dict(payload["rca"])
    elif "result" in payload and isinstance(payload["result"], dict):
        payload = dict(payload["result"])
    else:
        payload = dict(payload)

    limitations = _string_list(payload.get("limitations"), "limitation", "text", "message")

    causes = []
    raw_causes = payload.get("probable_causes")
    if isinstance(raw_causes, list):
        for item in raw_causes:
            if isinstance(item, str):
                cause_text = item.strip()
                confidence = 0.5
                evidence = []
            elif isinstance(item, dict):
                cause_text = _as_text(item.get("cause") or item.get("name") or item.get("title") or item.get("reason"))
                try:
                    confidence = float(item.get("confidence", 0.5))
                except (TypeError, ValueError):
                    confidence = 0.5
                evidence = _evidence_refs(item.get("evidence"))
            else:
                continue
            if cause_text:
                causes.append({
                    "cause": cause_text,
                    "confidence": max(0.0, min(1.0, confidence)),
                    "evidence": evidence,
                })

    five_whys = []
    raw_whys = payload.get("five_whys")
    if isinstance(raw_whys, list):
        for index, item in enumerate(raw_whys[:5], start=1):
            if isinstance(item, str):
                five_whys.append({
                    "level": index,
                    "why": item.strip(),
                    "answer": "The model did not provide an evidence-backed answer for this Why step.",
                    "evidence_supported": False,
                    "evidence": [],
                })
            elif isinstance(item, dict):
                why = _as_text(item.get("why") or item.get("question") or item.get("prompt"))
                answer = _as_text(item.get("answer") or item.get("because") or item.get("explanation"))
                if why or answer:
                    raw_level = item.get("level") or index
                    try:
                        level = int(raw_level)
                    except (TypeError, ValueError):
                        level = index
                    level = min(max(level, 1), 5)
                    raw_supported = item.get("evidence_supported")
                    if isinstance(raw_supported, bool):
                        evidence_supported = raw_supported
                    elif isinstance(raw_supported, str):
                        evidence_supported = raw_supported.strip().lower() in {"true", "1", "yes"}
                    else:
                        evidence_supported = bool(item.get("evidence")) and bool(answer)
                    five_whys.append({
                        "level": level,
                        "why": why or f"Why #{index}",
                        "answer": answer or "The model did not provide an evidence-backed answer for this Why step.",
                        "evidence_supported": evidence_supported,
                        "evidence": _evidence_refs(item.get("evidence")),
                    })

    if any(not item["evidence_supported"] for item in five_whys):
        note = "One or more 5 Why steps were returned without an evidence-backed answer."
        if note not in limitations:
            limitations.append(note)

    root_cause = payload.get("root_cause")
    if isinstance(root_cause, dict):
        root_cause = root_cause.get("cause") or root_cause.get("name") or root_cause.get("summary")
    root_cause = _as_text(root_cause) or None

    summary = _as_text(payload.get("summary"))
    if not summary:
        if root_cause:
            summary = root_cause
        elif causes:
            summary = f"Probable cause identified: {causes[0]['cause']}."
        elif payload.get("is_problem_found") is False:
            summary = "No problem was found in the collected evidence."
        elif payload.get("is_problem_found") is True:
            summary = "A problem was found in the collected evidence, but the model did not return a complete RCA summary."
        else:
            summary = "The model returned an incomplete RCA response."

    raw_insufficient = payload.get("insufficient_evidence")
    if isinstance(raw_insufficient, bool):
        insufficient_evidence = raw_insufficient
    elif isinstance(raw_insufficient, str):
        insufficient_evidence = raw_insufficient.strip().lower() in {"true", "1", "yes"}
    else:
        insufficient_evidence = root_cause is None

    normalized = {
        "summary": summary,
        "impact": _as_text(payload.get("impact")) or None,
        "five_whys": five_whys,
        "root_cause": root_cause,
        "probable_causes": causes,
        "contributing_factors": _string_list(payload.get("contributing_factors"), "factor", "name", "text"),
        "recommended_checks": _string_list(payload.get("recommended_checks"), "check", "action", "recommendation", "text"),
        "recommended_actions": _string_list(payload.get("recommended_actions"), "action", "recommendation", "text"),
        "insufficient_evidence": insufficient_evidence,
        "limitations": limitations,
    }
    return normalized


def parse_rca_json(text: str) -> RCAResult:
    cleaned = (text or "").strip()
    fence = chr(96) * 3
    if cleaned.startswith(fence + "json"):
        cleaned = cleaned.removeprefix(fence + "json").removesuffix(fence).strip()
    elif cleaned.startswith(fence):
        cleaned = cleaned.removeprefix(fence).removesuffix(fence).strip()
    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise ValueError("RCA response must be a JSON object")
    return RCAResult.model_validate(normalize_rca_payload(payload))
