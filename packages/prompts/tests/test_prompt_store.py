"""Behaviour tests for FilePromptStore (M1.1): pinning, latest, tag validation, render."""
import textwrap

import pytest

from fssai_prompts.store import FilePromptStore, PromptError


def write(root, name, version, *, tag=None, file_name=None, file_version=None):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    tag = tag or f"[prompt:{name}@{version}]"
    (d / f"{version}.yaml").write_text(textwrap.dedent(f"""\
        name: {file_name or name}
        version: {file_version or version}
        system: "{tag} be helpful"
        user_template: "hello {{who}}"
    """))


def test_latest_is_highest_numeric_version(tmp_path):
    for v in ("1.2.0", "1.10.0", "1.9.0"):
        write(tmp_path, "demo", v)
    assert FilePromptStore(tmp_path).get("demo").version == "1.10.0"


def test_explicit_version_wins_over_env_and_latest(tmp_path, monkeypatch):
    write(tmp_path, "demo", "1.0.0")
    write(tmp_path, "demo", "2.0.0")
    monkeypatch.setenv("PROMPT_DEMO_VERSION", "2.0.0")
    assert FilePromptStore(tmp_path).get("demo", "1.0.0").version == "1.0.0"


def test_env_pin_overrides_latest(tmp_path, monkeypatch):
    write(tmp_path, "demo", "1.0.0")
    write(tmp_path, "demo", "2.0.0")
    monkeypatch.setenv("PROMPT_DEMO_VERSION", "1.0.0")
    assert FilePromptStore(tmp_path).get("demo").version == "1.0.0"


def test_env_pin_with_inline_comment_and_blank(tmp_path, monkeypatch):
    write(tmp_path, "demo", "1.0.0")
    write(tmp_path, "demo", "2.0.0")
    monkeypatch.setenv("PROMPT_DEMO_VERSION", "1.0.0  # pinned for eval")
    assert FilePromptStore(tmp_path).get("demo").version == "1.0.0"
    monkeypatch.setenv("PROMPT_DEMO_VERSION", "")
    assert FilePromptStore(tmp_path).get("demo").version == "2.0.0"


def test_unknown_name_or_version_fails_loudly(tmp_path):
    write(tmp_path, "demo", "1.0.0")
    store = FilePromptStore(tmp_path)
    with pytest.raises(PromptError):
        store.get("missing")
    with pytest.raises(PromptError, match="no version"):
        store.get("demo", "9.9.9")


def test_tag_must_match_file(tmp_path):
    write(tmp_path, "demo", "1.0.0", tag="[prompt:demo@0.0.1]")
    with pytest.raises(PromptError, match="must start with"):
        FilePromptStore(tmp_path).get("demo")


def test_name_and_version_inside_file_must_match_path(tmp_path):
    write(tmp_path, "demo", "1.0.0", file_version="1.0.1")
    with pytest.raises(PromptError, match="path says"):
        FilePromptStore(tmp_path).get("demo")


def test_render_fills_user_template(tmp_path):
    write(tmp_path, "demo", "1.0.0")
    msgs = FilePromptStore(tmp_path).get("demo").render(who="Namith")
    assert [m.role for m in msgs] == ["system", "user"]
    assert msgs[0].content.startswith("[prompt:demo@1.0.0]")
    assert msgs[1].content == "hello Namith"


def test_shipped_prompts_all_load_and_render_literal_braces():
    store = FilePromptStore()
    for name in store.names():
        assert store.get(name).system.startswith(f"[prompt:{name}@")
    # system prompts are not str.format()ed, so the JSON example must use single braces
    assert '{"category"' in store.get("classifier").system and "{{" not in store.get("classifier").system
