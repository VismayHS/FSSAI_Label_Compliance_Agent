"""Pluggable input detectors (L4). Each one looks at every free-text field and returns flags.

Enable with GUARDRAIL_DETECTORS (comma list, default "control,length,injection,toxicity"):
    control     control and invisible characters
    length      fields longer than GUARDRAIL_MAX_FIELD_CHARS
    injection   pattern heuristics, multilingual, plus base64 payloads decoded and rescanned
    toxicity    GUARDRAIL_TOXICITY_MODEL (a transformers text-classifier) if set, else a small lexicon
    judge       an LLM asks which fields try to instruct the system (opt-in: costs one LLM step per run)
    pkg.mod:Class   any class with scan(fields, ctx) -> list[Flag]

Heuristics are a first layer and are honest about it: they catch known phrasings, not every paraphrase.
decision 101 explains why this is the default and how the judge adds a second layer.
"""
from __future__ import annotations

import base64
import binascii
import importlib
import json
import os
import re
from dataclasses import dataclass
from typing import Protocol

from fssai_contracts.context import BudgetExceeded, RunContext
from fssai_contracts.interfaces import ProviderUnavailable

from .text import fold


@dataclass(frozen=True)
class Flag:
    field: str
    kind: str      # prompt_injection | toxicity | too_long | control_characters
    rule: str      # which rule fired; never the attacker's text

    @property
    def label(self) -> str:
        return f"{self.kind}:{self.field}"


class Detector(Protocol):
    name: str

    def scan(self, fields: dict[str, str], ctx: RunContext) -> list[Flag]: ...


# ---------------------------------------------------------------- control characters and length

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u200b-\u200f\u2028\u2029\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]")


class ControlCharDetector:
    name = "control"

    def scan(self, fields, ctx):
        return [Flag(f, "control_characters", "control_or_invisible") for f, t in fields.items() if _CONTROL.search(t)]


class LengthDetector:
    name = "length"

    def __init__(self, limit: int | None = None) -> None:
        self.limit = limit if limit is not None else int(os.environ.get("GUARDRAIL_MAX_FIELD_CHARS", "4000") or 4000)

    def scan(self, fields, ctx):
        return [Flag(f, "too_long", f"over_{self.limit}_chars") for f, t in fields.items() if len(t) > self.limit]


# ---------------------------------------------------------------- injection heuristics

def _rx(p: str) -> re.Pattern:
    return re.compile(p, re.IGNORECASE)


_W = r"[^.\n]"
INJECTION_RULES: list[tuple[str, re.Pattern]] = [
    # override the instructions
    ("instruction_override", _rx(rf"\b(ignore|disregard|forget|override|bypass|neglect|discard|skip)\b{_W}{{0,40}}\b(previous|prior|above|earlier|preceding|all|any|your|these|those|system)\b{_W}{{0,30}}\b(instructions?|prompts?|rules?|directions?|guidelines?|constraints?|commands?|programming)\b")),
    ("instruction_override", _rx(r"\b(do not|don'?t|never)\s+follow\s+(the|your|any)\s+(\w+\s+)?(instructions?|rules?)\b")),
    ("new_instructions", _rx(r"\b(new|updated|real|actual|secret|hidden)\s+(instructions?|task|system prompt|rules)\s*(is|are|:|follow)")),
    # role-play and mode switches
    ("role_play", _rx(r"\byou\s+are\s+now\s+(a|an|the|my|in|free|unrestricted|dan|going\s+to|to\s+act)\b|\byou\s+are\s+no\s+longer\b")),
    ("role_play", _rx(r"\b(act|behave|respond|function|operate)\s+as\s+(if\s+you\s+(are|were)\s+)?(an?\s+|the\s+)?(unrestricted|jailbroken|different|new|evil|dan|developer|admin|administrator|system|root|compliance officer|regulator|auditor|assistant|ai|chatbot)\b")),
    ("role_play", _rx(r"\bpretend\s+(to be|you\s+are|that\s+you)\b")),
    ("role_play", _rx(r"\b(developer|debug|god|dan|jailbreak|sudo|admin|maintenance)\s+mode\b")),
    ("role_play", _rx(rf"\bfrom\s+now\s+on\b{_W}{{0,20}}\byou\s+(will|must|should|shall|are|only|always|never|have\s+to|need\s+to)\b")),
    # fake system / chat-template markers
    ("system_impersonation", _rx(r"(?:^|\n|[.!?;]\s)\s*(system|assistant|developer|admin)\s*:")),
    ("system_impersonation", _rx(r"<\|im_(start|end)\|>|<\|system\|>|\[/?inst\]|<<\s*sys\s*>>|###\s*(system|instruction)s?\b|\[\s*system\s*\]|<\s*system\s*>")),
    # break out of the data block
    ("delimiter_escape", _rx(r"</?\s*label_data\b")),
    ("delimiter_escape", _rx(r"</?\s*(system|assistant|instructions?|prompt|tool|tool_call|function_call)\b[^>]*>")),
    ("delimiter_escape", re.compile(r"```")),
    # try to set the outcome
    ("approval_coercion", _rx(r"\bapprove\s+(this|the|my|our)\s+(label|pack|packaging|product|artwork|submission)\b")),
    ("approval_coercion", _rx(rf"\b(mark|set|rate|declare|certify|output|return|report|say|state)\b{_W}{{0,30}}\b(compliant|approved|clear[- ]for[- ]print|passes|passed)\b")),
    ("route_override", _rx(rf"\b(set|force|change|route|send|override)\b{_W}{{0,30}}\b(clear[- ]for[- ]print|regulatory[- ]review|revise[- ]and[- ]recheck)\b")),
    # leak or abuse
    ("exfiltration", _rx(rf"\b(reveal|show|print|repeat|output|display|leak|disclose|tell me)\b{_W}{{0,40}}\b(system prompt|your (instructions|prompt|rules)|hidden (instructions|prompt)|api[- ]?key|secrets?|credentials?|passwords?|tokens?)\b")),
    ("tool_abuse", _rx(r"\b(execute|run)\s+(the\s+following\s+)?(command|code|script|shell|sql)\b")),
    ("tool_abuse", _rx(r"\b(clause_lookup|corpus_search|request_field_lookup)\s*\(|\btool_call\b|\bfunction_call\b")),
    # other languages (the same ideas; coverage is partial by nature)
    ("instruction_override_es", _rx(r"\b(ignora|olvida|omite|descarta)\b[^.\n]{0,30}\b(instrucciones|indicaciones|reglas)\b")),
    ("approval_coercion_es", _rx(r"\b(aprueba|aprobar|apruebe)\s+(esta|la)\s+etiqueta\b")),
    ("instruction_override_fr", _rx(r"\b(ignorez|ignorer|ignore\s+(les|toutes|vos|mes)|oubliez|oublier|oublie\s+(les|toutes|vos)|négligez|négliger)\b[^.\n]{0,30}\b(instructions?|consignes?|règles)\b")),
    ("approval_coercion_fr", _rx(r"\b(approuve[zr]?|valide[zr]?)\s+(cette|l')\s*étiquette\b")),
    ("instruction_override_de", _rx(r"\b(ignoriere|vergiss|missachte)\b[^.\n]{0,30}\b(anweisungen|instruktionen|regeln)\b")),
    ("approval_coercion_de", _rx(r"\b(genehmige|bestätige)\s+(dieses|das)\s+etikett\b")),
    ("instruction_override_hi", re.compile(r"(पिछले|पिछली|ऊपर\s*के|पहले\s*के)\s*(सभी\s*)?(निर्देश|निर्देशों|आदेश|आदेशों|नियमों)\s*(को\s*)?(अनदेखा|नज़रअंदाज़|नजरअंदाज|भूल)")),
    ("approval_coercion_hi", re.compile(r"(इस|इस\s*पैक\s*के)\s*लेबल\s*को\s*(मंज़ूर|मंजूर|स्वीकृत|अनुमोदित|पास)")),
    ("instruction_override_hi_latin", _rx(r"\b(pichhle|pichle|purane|upar\s+ke)\b[^.\n]{0,25}\b(nirdesh|instructions?|aadesh|niyam)\b[^.\n]{0,25}\b(ignore|bhool|andekha|nazarandaz)\b")),
    ("approval_coercion_hi_latin", _rx(r"\bis\s+label\s+ko\s+(approve|pass|manzoor|sahi)\b")),
    ("instruction_override_ta", re.compile(r"முந்தைய\s*(அனைத்து\s*)?(அறிவுறுத்தல்களை|கட்டளைகளை|வழிமுறைகளை|விதிகளை)\s*(புறக்கணி|மறந்து|கண்டுகொள்ள)")),
    ("approval_coercion_ta", re.compile(r"இந்த\s*லேபிளை\s*(அங்கீகரி|ஏற்று|அனுமதி)")),
    ("instruction_override_zh", re.compile(r"忽略(之前|以上|先前|所有|上面)[^。\n]{0,10}(指令|指示|规则|说明)")),
]

_B64 = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{40,}={0,2}(?![A-Za-z0-9+/])")


def injection_rules_hit(text: str) -> list[str]:
    """Names of the rules that match this text (plain, folded, and digit-folded variants)."""
    hits: list[str] = []
    for variant in (text, fold(text), fold(text, leet=True)):
        for name, rx in INJECTION_RULES:
            if name not in hits and rx.search(variant):
                hits.append(name)
    return hits


def _decoded_payloads(text: str) -> list[str]:
    out = []
    for m in _B64.finditer(text):
        try:
            raw = base64.b64decode(m.group(0) + "=" * (-len(m.group(0)) % 4), validate=True)
            decoded = raw.decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
        if decoded.isprintable() or "\n" in decoded:
            out.append(decoded)
    return out


class InjectionHeuristics:
    name = "injection"

    def scan(self, fields, ctx):
        flags = []
        for field, text in fields.items():
            hits = injection_rules_hit(text)
            for payload in _decoded_payloads(text):
                if injection_rules_hit(payload):
                    hits.append("encoded_payload")
                    break
            flags += [Flag(field, "prompt_injection", rule) for rule in hits]
        return flags


# ---------------------------------------------------------------- toxicity

_PROFANITY = ("fuck", "fucking", "fucker", "shit", "shitty", "bitch", "bastard", "asshole", "dickhead", "cunt",
              "motherfucker", "bullshit", "piss off", "screw you")
_THREATS = (r"\bi\s*(will|'ll|am going to|'m going to)\s+(kill|hurt|destroy|burn|shoot|stab|murder)\b",
            r"\b(kill|hurt|murder)\s+(yourself|you|them|him|her|everyone)\b",
            r"\byou\s+(deserve|should)\s+to\s+(die|suffer)\b", r"\b(go|just)\s+die\b")
_TOX_RX = [re.compile(rf"\b{re.escape(w)}\b", re.IGNORECASE) for w in _PROFANITY] + [_rx(t) for t in _THREATS]


class LexiconToxicity:
    """Small word-boundary lexicon. Cheap and offline; set GUARDRAIL_TOXICITY_MODEL for a real model."""
    name = "toxicity"

    def scan(self, fields, ctx):
        flags = []
        for field, text in fields.items():
            if any(rx.search(v) for v in (text, fold(text, leet=True)) for rx in _TOX_RX):
                flags.append(Flag(field, "toxicity", "lexicon"))
        return flags


class ModelToxicity:
    """A transformers text-classification model (for example unitary/toxic-bert), loaded on first use.
    If it cannot load, the lexicon takes over and the run records a degraded event."""
    name = "toxicity"

    def __init__(self, model: str, threshold: float = 0.8, classifier=None) -> None:
        self.model, self.threshold, self._clf = model, threshold, classifier
        self._fallback = LexiconToxicity()
        self._failed = False

    def _load(self):
        if self._clf is None and not self._failed:
            try:
                from transformers import pipeline  # optional dependency
                self._clf = pipeline("text-classification", model=self.model, top_k=None, truncation=True)
            except Exception:
                self._failed = True
        return self._clf

    def scan(self, fields, ctx):
        clf = self._load()
        if clf is None:
            ctx.event("guardrail_degraded", detector="toxicity", reason="model_unavailable")
            return self._fallback.scan(fields, ctx)
        flags = []
        for field, text in fields.items():
            scores = clf(text[:2000])
            rows = scores[0] if scores and isinstance(scores[0], list) else scores
            worst = max((r["score"] for r in rows if str(r["label"]).lower() not in ("non-toxic", "neutral", "label_0", "not_toxic")),
                        default=0.0)
            if worst >= self.threshold:
                flags.append(Flag(field, "toxicity", f"model>={self.threshold}"))
        return flags


# ---------------------------------------------------------------- LLM judge (opt-in second layer)

class LLMJudgeInjection:
    """One LLM call per run: which fields try to instruct the system? Wrapped as data; output validated.
    Needs an LLM step, so it is off by default. If the provider is down the heuristics still apply."""
    name = "judge"

    def __init__(self, llm, prompts) -> None:
        self.llm, self.prompts = llm, prompts

    def scan(self, fields, ctx):
        names = list(fields)
        if not names:
            return []
        blocks = "\n".join(f'<label_data field="{n}">\n{re.sub(r"</?\s*label_data[^>]*>", "[removed tag]", t)[:1500]}\n</label_data>'
                           for n, t in fields.items())
        prompt = self.prompts.get("guardrail_judge")
        messages = prompt.render(fields=blocks, input=blocks)
        ctx.check_budget()
        try:
            resp = self.llm.complete(messages, ctx, agent="guardrails", step="judge", prompt=prompt, json_mode=True)
        except BudgetExceeded:
            raise
        except ProviderUnavailable:
            ctx.event("guardrail_degraded", detector="judge", reason="provider_unavailable")
            return []
        try:
            data = json.loads(resp.text)
            flagged = data.get("flagged_fields", []) if isinstance(data, dict) else []
        except ValueError:
            return []
        return [Flag(f, "prompt_injection", "llm_judge") for f in flagged if f in fields]


# ---------------------------------------------------------------- assembling the set

DEFAULT_DETECTORS = "control,length,injection,toxicity,"


def build_detectors(spec: str | None = None, *, llm=None, prompts=None) -> list[Detector]:
    spec = (spec if spec is not None else os.environ.get("GUARDRAIL_DETECTORS", "")).split("#", 1)[0]
    names = [n.strip() for n in (spec or DEFAULT_DETECTORS).split(",") if n.strip()]
    out: list[Detector] = []
    for name in names:
        if name == "control":
            out.append(ControlCharDetector())
        elif name == "length":
            out.append(LengthDetector())
        elif name == "injection":
            out.append(InjectionHeuristics())
        elif name == "toxicity":
            model = os.environ.get("GUARDRAIL_TOXICITY_MODEL", "").split("#", 1)[0].strip()
            out.append(ModelToxicity(model, float(os.environ.get("GUARDRAIL_TOXICITY_THRESHOLD", "0.8") or 0.8)) if model
                       else LexiconToxicity())
        elif name == "judge":
            if llm is None or prompts is None:
                from fssai_contracts.registry import build
                llm, prompts = llm or build("llm"), prompts or build("prompts")
            out.append(LLMJudgeInjection(llm, prompts))
        elif ":" in name:
            module, _, attr = name.partition(":")
            cls = getattr(importlib.import_module(module), attr)
            out.append(cls())
        else:
            raise ValueError(f"unknown guardrail detector '{name}'")
    return out
