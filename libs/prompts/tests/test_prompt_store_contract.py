"""FilePromptStore keeps the prompt store contract (fssai_contracts.conformance.check_prompt_store)."""
from fssai_contracts.conformance import check_prompt_store
from fssai_prompts.store import FilePromptStore

NAMES = ("classifier", "classifier_repair", "researcher.act", "researcher.draft")


def test_conforms():
    check_prompt_store(FilePromptStore(), names=NAMES)
