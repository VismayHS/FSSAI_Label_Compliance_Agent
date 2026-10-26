"""Pluggable text detectors for the guardrails (L4). Each takes text and returns the names of what it found.

Injection: heuristics over normalised text (case, width, zero-width characters and look-alike letters folded), in
several languages, covering instruction override, role-play, prompt exfiltration, delimiter escape, tool abuse and
attempts to dictate the verdict. Heuristics are a first layer, not a proof: the agents also keep label text inside
data delimiters, validate every tool argument against an allowlist and verify every citation (docs/decisions/101).

Toxicity: a small lexicon by default (no download, no network). Set GUARDRAIL_TOXICITY_MODEL to a local
text-classification model name to add a model on top; if it cannot be loaded the lexicon keeps working and the
fallback is logged.
"""
from __future__ import annotations

import logging
import os
import re
import unicodedata
from typing import Protocol

log = logging.getLogger("fssai.guardrails")

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)
_HOMOGLYPHS = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i",
                             "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x",
                             "і": "i", "ѕ": "s"})


def normalise(text: str, fold_digits: bool = False) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH).lower()
    if fold_digits:
        text = text.translate(_HOMOGLYPHS)
    return " ".join(re.sub(r"[_*`~|\\]+", " ", text).split())


class Detector(Protocol):
    name: str

    def scan(self, text: str) -> list[str]: ...


_W = r"[\w'’]+"
_INJECTION: dict[str, list[str]] = {
    "instruction_override": [
        r"\b(?:ignore|disregard|forget|override|bypass|skip)\b[^.\n]{0,40}\b(?:previous|prior|above|earlier|all|any|your|the|these|those)\b[^.\n]{0,30}\b(?:instructions?|prompts?|rules?|guidelines?|directions?|polic(?:y|ies)|constraints?)\b",
        r"\b(?:ignore|disregard)\s+(?:everything|all)\b(?:\s+(?:above|before|else))?",
        r"\bdo not follow\b[^.\n]{0,30}\b(?:instructions?|rules?|guidelines?)\b",
        r"\bnew instructions?\s*:", r"\binstead,? (?:you (?:must|should|will)|do|output|respond|say|return)\b",
        r"\bfrom now on\b[^.\n]{0,40}\b(?:you|always|only)\b",
    ],
    "role_play": [
        r"\byou are (?:now|no longer)\b", r"\bact as (?:a|an|the|if)\b", r"\bpretend (?:to be|you are|that you)\b",
        r"\broleplay\b|\brole-play\b", r"\bdeveloper mode\b|\bdan mode\b|\bjailbreak(?:ed)?\b",
        r"\bimagine you (?:are|were|have no)\b", r"\bunrestricted (?:ai|assistant|mode)\b",
    ],
    "prompt_exfiltration": [
        r"\b(?:reveal|show|print|repeat|output|leak|display|tell me)\b[^.\n]{0,30}\b(?:system prompt|your prompt|your instructions|hidden (?:prompt|instructions)|initial prompt)\b",
        r"\bsystem prompt\b", r"\bsystem message\b", r"\bwhat (?:are|were) your (?:instructions|rules)\b",
    ],
    "delimiter_escape": [
        r"</?\s*label_data\s*>", r"<\|(?:im_start|im_end|system|user|assistant|endoftext)\|>", r"\[/?inst\]", r"<</?sys>>",
        r"^\s*(?:#{2,}\s*)?(?:system|assistant|developer)\s*:", r"\n\s*(?:system|assistant)\s*:", r"```\s*(?:system|json)\b[^`]{0,40}(?:ignore|approve)",
        r"</?(?:system|instructions?|prompt)>", r"\bend of (?:label|data|input)\b[^.\n]{0,20}\bnew (?:task|instructions?)\b",
    ],
    "verdict_dictation": [
        r"\b(?:approve|approved|approving|pass|passes|certify|certified|clear|cleared)\b[^.\n]{0,25}\b(?:this|the|my|our)\b[^.\n]{0,15}\b(?:label|pack|packaging|product|claim)\b",
        r"\b(?:mark|set|route|rate|classify|label)\b[^.\n]{0,25}\b(?:as|to)\b[^.\n]{0,15}\b(?:clear[- ]?for[- ]?print|compliant|approved|passed|met)\b",
        r"\b(?:route|routing|verdict|result|status)\s*(?:is|=|:|should be|must be)\s*[\"']?(?:clear[- ]?for[- ]?print|approved|compliant|accept)\b",
        r"\balways (?:say|answer|respond|output|return|report)\b[^.\n]{0,30}\b(?:compliant|approved|met|clear|pass)\b",
        r"\bno (?:further )?(?:review|check(?:s|ing)?) (?:is |are )?(?:needed|required|necessary)\b",
        r"\b(?:all|every) requirements? (?:are |is )?(?:met|satisfied|fulfilled)\b[^.\n]{0,20}\b(?:regardless|anyway)\b",
    ],
    "tool_abuse": [
        r"\b(?:call|use|invoke|run|execute|trigger)\b[^.\n]{0,20}\b(?:corpus_search|clause_lookup|request_field_lookup|the (?:search )?tool)\b",
        r"\b(?:corpus_search|clause_lookup|request_field_lookup)\s*[({]", r"\"tool\"\s*:", r"\bfunction_call\b|\btool_calls?\b",
        r"\b(?:fetch|visit|open|curl|wget|browse)\b[^.\n]{0,15}https?://", r"\bsend\b[^.\n]{0,30}\b(?:to|at)\b[^.\n]{0,30}(?:https?://|@\w+\.\w+)",
    ],
    "other_language": [
        r"ignor[ae][^.\n]{0,25}(?:instrucciones|indicaciones|reglas)\s+(?:anteriores|previas)",  # es
        r"ignor(?:ez|e)[^.\n]{0,25}(?:instructions|consignes|r[eè]gles)\s+(?:pr[eé]c[eé]dentes|ci-dessus|ant[eé]rieures)",  # fr
        r"ignorier(?:e|en)?[^.\n]{0,25}(?:vorherigen|obigen|bisherigen)\s+(?:anweisungen|instruktionen|regeln)",  # de
        r"ignora[^.\n]{0,25}(?:istruzioni|regole)\s+(?:precedenti|sopra)",  # it
        r"ignore[^.\n]{0,25}(?:instru[cç][oõ]es|regras)\s+(?:anteriores|acima)",  # pt
        r"(?:पिछले|ऊपर के|पहले के)\s*(?:सभी\s*)?(?:निर्देश|आदेश|नियम)[^.\n]{0,20}(?:अनदेखा|नज़रअंदाज़|नजरअंदाज|भूल)",  # hi
        r"(?:निर्देशों|आदेशों|नियमों)\s*(?:को)?\s*(?:अनदेखा|नज़रअंदाज़|नजरअंदाज|भूल)",  # hi
        r"(?:忽略|无视|忘记)[^.\n]{0,10}(?:之前|以上|先前|所有)[^.\n]{0,10}(?:指示|指令|规则|说明)",  # zh
        r"(?:以前|前|上記)の(?:指示|命令|ルール)を(?:無視|忘れ)",  # ja
        r"(?:игнорируй|игнорируйте|забудь)[^.\n]{0,30}(?:предыдущие|прежние|все)\s+(?:инструкции|указания|правила)",  # ru
        r"تجاهل[^.\n]{0,20}(?:التعليمات|الأوامر)\s+(?:السابقة|أعلاه)",  # ar
    ],
}
_INJECTION_RE = {cat: [re.compile(p, re.I | re.M) for p in pats] for cat, pats in _INJECTION.items()}
_ENCODED = re.compile(r"(?:[A-Za-z0-9+/]{60,}={0,2})")
_NEGATION = re.compile(r"\b(?:not|never|no|cannot|can't|without|isn't|aren't|does not|do not)\s+(?:\w+\s+){0,2}$")


class InjectionHeuristics:
    name = "injection"

    def scan(self, text: str) -> list[str]:
        found: list[str] = []
        for variant in dict.fromkeys((normalise(text), normalise(text, fold_digits=True))):
            for category, patterns in _INJECTION_RE.items():
                if category in found:
                    continue
                for pattern in patterns:
                    m = pattern.search(variant)
                    if m is None:
                        continue
                    if category == "verdict_dictation" and _NEGATION.search(variant[:m.start()]):
                        continue
                    found.append(category)
                    break
        if _ENCODED.search(text) and "encoded_payload" not in found:
            found.append("encoded_payload")
        return found


_TOXIC_WORDS = (
    "idiot", "idiots", "stupid", "moron", "morons", "imbecile", "dumbass", "scum", "trash people", "bastard", "bastards",
    "asshole", "assholes", "bitch", "bitches", "bullshit", "shithead", "dickhead", "fuck", "fucking", "fucker", "motherfucker",
    "crap", "damn you", "piece of shit", "shut up", "retard", "retarded", "slut", "whore", "cunt", "nigger", "faggot",
    "chutiya", "madarchod", "bhenchod", "behenchod", "gandu", "harami", "saala", "kutta",
)
_TOXIC_RE = [re.compile(rf"(?<![a-z]){re.escape(w)}(?![a-z])") for w in _TOXIC_WORDS]
_THREAT_RE = [re.compile(p) for p in (
    r"\bi (?:will|am going to|'ll) (?:kill|hurt|destroy|find|hunt|burn|attack)\b", r"\b(?:kill|hurt|murder) (?:you|him|her|them|yourself)\b",
    r"\byou (?:should|deserve to) die\b", r"\bkys\b", r"\bblow (?:it|this|them|the \w+) up\b", r"\bbomb (?:the|this|their)\b")]


class ToxicityLexicon:
    name = "toxicity"

    def scan(self, text: str) -> list[str]:
        for variant in dict.fromkeys((normalise(text), normalise(text, fold_digits=True))):
            if any(r.search(variant) for r in _TOXIC_RE):
                return ["abusive_language"]
            if any(r.search(variant) for r in _THREAT_RE):
                return ["threat"]
        return []


class ToxicityModel:
    """Optional local classifier (GUARDRAIL_TOXICITY_MODEL), loaded once, lazily. Never makes a network call at scan time."""

    name = "toxicity_model"

    def __init__(self, model: str, threshold: float = 0.8) -> None:
        self.model, self.threshold, self._pipe, self._failed = model, threshold, None, False

    def _load(self):
        if self._pipe is None and not self._failed:
            try:
                from transformers import pipeline  # type: ignore
                self._pipe = pipeline("text-classification", model=self.model, top_k=None, truncation=True)
            except Exception as exc:  # noqa: BLE001
                self._failed = True
                log.warning("toxicity model %s unavailable, lexicon only: %s", self.model, exc)
        return self._pipe

    def scan(self, text: str) -> list[str]:
        pipe = self._load()
        if pipe is None or not text.strip():
            return []
        try:
            scores = pipe(text[:1000])
            scores = scores[0] if scores and isinstance(scores[0], list) else scores
            hit = [s for s in scores if str(s["label"]).lower() not in ("non-toxic", "neutral", "not_toxic", "label_0")
                   and float(s["score"]) >= self.threshold]
            return ["toxic_model"] if hit else []
        except Exception as exc:  # noqa: BLE001
            self._failed = True
            log.warning("toxicity model failed, lexicon only: %s", exc)
            return []


def build_detectors() -> dict[str, list[Detector]]:
    """{'injection': [...], 'toxicity': [...]} from GUARDRAIL_DETECTORS (default both) and GUARDRAIL_TOXICITY_MODEL."""
    enabled = {x.strip() for x in (os.environ.get("GUARDRAIL_DETECTORS", "injection,toxicity").split("#", 1)[0]).split(",") if x.strip()}
    out: dict[str, list[Detector]] = {"injection": [], "toxicity": []}
    if "injection" in enabled:
        out["injection"].append(InjectionHeuristics())
    if "toxicity" in enabled:
        out["toxicity"].append(ToxicityLexicon())
        model = os.environ.get("GUARDRAIL_TOXICITY_MODEL", "").split("#", 1)[0].strip()
        if model:
            out["toxicity"].append(ToxicityModel(model, float(os.environ.get("GUARDRAIL_TOXICITY_THRESHOLD", "0.8") or 0.8)))
    return out
