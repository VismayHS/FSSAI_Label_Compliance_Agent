"""The D4 audit catches each kind of leak and honours the allow marker."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audit_secrets  # noqa: E402

FAKE = "x" * 32  # never a real secret: the patterns only need the shape


@pytest.mark.parametrize("line, what", [
    (f"LLM_API_KEY=sk-{FAKE}", "API key"),
    (f'key = "gsk_{FAKE}"', "Groq"),
    ("-----BEGIN RSA PRIVATE KEY-----", "private key"),  # audit: allow (test data)
    ("LLM_BASE_URL=https://api.groq.com/openai/v1", "endpoint"),  # audit: allow (test data)
    ("LLM_MODEL=llama-3.1-8b-instant", "model id"),  # audit: allow (test data)
    ("EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2", "embedding model id"),  # audit: allow (test data)
    ("LLM_FALLBACK_API_KEY=abc123", "env template"),
    ("the primary was gpt-oss-120b", "model id"),  # audit: allow (test data)
    ("LLM_FALLBACK_MODEL=openai/gpt-oss-20b", "model id"),  # audit: allow (test data)
    ("we tried moonshotai/kimi-k2-instruct", "model id"),  # audit: allow (test data)
    ("LLM_MODEL=qwen/qwen3.8-27b", "model id"),  # audit: allow (test data)
])
def test_flags_each_kind_of_leak(tmp_path, monkeypatch, line, what):
    (tmp_path / "leak.txt").write_text(f"ok line\n{line}\n", encoding="utf-8")
    monkeypatch.setattr(audit_secrets, "ROOT", tmp_path)
    hits = audit_secrets.scan("leak.txt")
    assert [(n, w) for n, w, _ in hits if what.lower() in w.lower()], hits
    assert all(n == 2 for n, _, _ in hits)


def test_clean_lines_and_allowed_mentions_pass(tmp_path, monkeypatch):
    (tmp_path / "ok.md").write_text("LLM_API_KEY=\nLLM_MODEL=            # from your provider\n"
                                    "We compared gpt-4o here.  <!-- audit: allow -->\n", encoding="utf-8")
    monkeypatch.setattr(audit_secrets, "ROOT", tmp_path)
    assert audit_secrets.scan("ok.md") == []


def test_a_provider_path_segment_is_not_mistaken_for_a_model_id(tmp_path, monkeypatch):
    (tmp_path / "ok.md").write_text("The gateway calls <base>/chat/completions; an openai/v1-style path is fine.\n",
                                    encoding="utf-8")
    monkeypatch.setattr(audit_secrets, "ROOT", tmp_path)
    assert audit_secrets.scan("ok.md") == []


def test_vendored_guidance_and_binaries_are_skipped():
    assert audit_secrets.scan("skills/vendor/x/SKILL.md") == []
    assert audit_secrets.scan("corpus/raw/FSS-AC-2018.pdf") == []
