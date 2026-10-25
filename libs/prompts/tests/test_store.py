import pytest

from fssai_prompts.store import FilePromptStore, PromptError


def write(root, name, version, system=None, user="hello {x}"):
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    system = f"[prompt:{name}@{version}] sys" if system is None else system
    (folder / f"{version}.yaml").write_text(
        f"name: {name}\nversion: \"{version}\"\nsystem: |\n  {system}\nuser_template: |\n  {user}\n", encoding="utf-8")


@pytest.fixture
def store(tmp_path):
    for v in ("1.0.0", "1.2.0", "1.10.0", "2.0.0"):
        write(tmp_path, "researcher.act", v)
    write(tmp_path, "researcher.draft", "1.0.0")
    write(tmp_path, "researcher.draft", "2.0.0")
    return FilePromptStore(tmp_path)


def test_latest_is_numeric_not_alphabetical(tmp_path):
    for v in ("1.2.0", "1.10.0", "1.9.0"):
        write(tmp_path, "p", v)
    assert FilePromptStore(tmp_path).get("p").version == "1.10.0"


def test_explicit_version_pins(store):
    assert store.get("researcher.act", "1.2.0").version == "1.2.0"


def test_env_pins_exact_name(store, monkeypatch):
    monkeypatch.setenv("PROMPT_RESEARCHER_ACT_VERSION", "1.0.0")
    assert store.get("researcher.act").version == "1.0.0"
    assert store.get("researcher.draft").version == "2.0.0"  # only act is pinned


def test_family_env_pins_every_member(store, monkeypatch):
    monkeypatch.setenv("PROMPT_RESEARCHER_VERSION", "1.0.0")
    assert store.get("researcher.act").version == "1.0.0"
    assert store.get("researcher.draft").version == "1.0.0"


def test_exact_pin_beats_family_pin(store, monkeypatch):
    monkeypatch.setenv("PROMPT_RESEARCHER_VERSION", "1.0.0")
    monkeypatch.setenv("PROMPT_RESEARCHER_DRAFT_VERSION", "2.0.0")
    assert store.get("researcher.draft").version == "2.0.0"
    assert store.get("researcher.act").version == "1.0.0"


def test_env_comment_is_ignored(store, monkeypatch):
    monkeypatch.setenv("PROMPT_RESEARCHER_ACT_VERSION", "1.0.0  # baseline")
    assert store.get("researcher.act").version == "1.0.0"


def test_pin_to_missing_version_fails_loudly(store, monkeypatch):
    monkeypatch.setenv("PROMPT_RESEARCHER_ACT_VERSION", "9.9.9")
    with pytest.raises(PromptError, match="9.9.9"):
        store.get("researcher.act")


def test_unknown_prompt_and_version(store):
    with pytest.raises(PromptError, match="unknown prompt"):
        store.get("nope")
    with pytest.raises(PromptError, match="no version"):
        store.get("researcher.act", "0.0.1")


def test_tag_must_match_file(tmp_path):
    write(tmp_path, "p", "1.0.0", system="[prompt:p@9.9.9] wrong version")
    with pytest.raises(PromptError, match="must start with"):
        FilePromptStore(tmp_path).get("p")


def test_missing_tag_fails(tmp_path):
    write(tmp_path, "p", "1.0.0", system="no tag here")
    with pytest.raises(PromptError):
        FilePromptStore(tmp_path).get("p")


def test_name_in_file_must_match_folder(tmp_path):
    write(tmp_path, "p", "1.0.0")
    (tmp_path / "p" / "1.0.0.yaml").write_text(
        'name: other\nversion: "1.0.0"\nsystem: "[prompt:other@1.0.0] s"\nuser_template: u\n')
    with pytest.raises(PromptError, match="location says"):
        FilePromptStore(tmp_path).get("p")


def test_render_fills_placeholders(store):
    messages = store.get("researcher.act", "1.0.0").render(x="world")
    assert messages[0].role == "system" and messages[0].content.startswith("[prompt:researcher.act@1.0.0]")
    assert "hello world" in messages[1].content


def test_validate_all_reports_problems(tmp_path):
    write(tmp_path, "good", "1.0.0")
    write(tmp_path, "bad", "1.0.0", system="no tag")
    problems = FilePromptStore(tmp_path).validate_all()
    assert len(problems) == 1 and "bad" in problems[0]


def test_shipped_prompts_are_all_valid():
    assert FilePromptStore().validate_all() == []


def test_shipped_user_templates_only_use_known_placeholders():
    import string
    store = FilePromptStore()
    for info in store.describe():
        for v in info.versions:
            t = store.get(info.name, v)
            fields = {f for _, f, _, _ in string.Formatter().parse(t.user_template) if f}
            assert fields, f"{info.name}@{v} has no placeholders"
