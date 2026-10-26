"""Judges: the LLM judge parses and caches; the TruLens judge calls the feedback functions (fake provider here)."""
import json

from fssai_contracts.schemas import LLMResponse
from fssai_eval.judges import Cache, LLMJudge, TruLensJudge, load_prompt, parse_json


class ScriptedLLM:
    def __init__(self, reply):
        self.reply, self.calls = reply, 0

    def complete(self, messages, ctx, *, agent, step, prompt=None, json_mode=False):
        self.calls += 1
        assert messages[0].content.startswith(f"[prompt:{prompt.name}@{prompt.version}]")
        return LLMResponse(text=self.reply, model_alias="scripted")


def test_prompts_are_tagged():
    for name in ("judge_support", "judge_relevance", "judge_status"):
        t = load_prompt(name)
        assert t.system.startswith(f"[prompt:{name}@{t.version}]")


def test_parse_json_tolerates_fences_and_prose():
    assert parse_json('```json\n{"score": 3}\n```') == {"score": 3}
    assert parse_json('Sure! {"score": 2, "reason": "x"} hope that helps') == {"score": 2, "reason": "x"}
    assert parse_json("no json") is None


def test_llm_judge_scores_and_caches(tmp_path):
    llm = ScriptedLLM(json.dumps({"score": 2, "reason": "mostly"}))
    judge = LLMJudge(llm=llm, cache=Cache(str(tmp_path)))
    assert judge.support("statement", "source") == 2 / 3
    assert judge.support("statement", "source") == 2 / 3 and llm.calls == 1, "second call served from the cache"
    again = LLMJudge(llm=llm, cache=Cache(str(tmp_path)))
    assert again.support("statement", "source") == 2 / 3 and llm.calls == 1, "cache survives a new process"


def test_llm_judge_unparseable_is_none():
    judge = LLMJudge(llm=ScriptedLLM("I cannot answer"), cache=Cache(None))
    assert judge.support("s", "src") is None and judge.status_follows({}, "r", "met", "e", "p") is None


def test_llm_judge_status():
    judge = LLMJudge(llm=ScriptedLLM('{"verdict": "does_not_follow", "reason": "x"}'), cache=Cache(None))
    assert judge.status_follows({"a": 1}, "req", "met", "expl", "passages") is False


def test_trulens_judge_uses_the_feedback_functions(tmp_path):
    class Provider:
        def __init__(self):
            self.calls = []

        def groundedness_measure_with_cot_reasons(self, source, statement):
            self.calls.append(("g", source, statement))
            return 0.75, {"reasons": "..."}

        def context_relevance_with_cot_reasons(self, question, context):
            self.calls.append(("r", question, context))
            return 1.0, {}

    p = Provider()
    judge = TruLensJudge(provider=p, llm=ScriptedLLM("{}"), cache=Cache(str(tmp_path)))
    assert judge.support("st", "src") == 0.75 and judge.relevance("q", "ctx", gold=None) == 1.0
    assert judge.support("st", "src") == 0.75 and len(p.calls) == 2, "cached"


def test_trulens_judge_failure_leaves_the_item_unscored():
    class Broken:
        def groundedness_measure_with_cot_reasons(self, **_):
            raise TimeoutError("provider down")
    judge = TruLensJudge(provider=Broken(), llm=ScriptedLLM("{}"), cache=Cache(None))
    assert judge.support("st", "src") is None
