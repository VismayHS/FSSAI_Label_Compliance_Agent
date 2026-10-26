"""The agents keep their seams' contracts (fssai_contracts.conformance), built on the fakes for everything else.

Day-0 baseline: each skeleton raises NotImplementedError, so these are expected failures until the task is
built. strict=True turns the first pass into a failure that reminds you to delete that marker. Your own
behaviour tests go in other files next to this one.
"""
import pytest

from fssai_agents.classifier import LLMClassifier
from fssai_agents.graph import LangGraphPipeline
from fssai_agents.researcher import LangGraphResearcher
from fssai_contracts.conformance import check_classifier, check_pipeline, check_researcher


def test_classifier_conforms():
    check_classifier(LLMClassifier.from_registry())


def test_researcher_conforms():
    check_researcher(LangGraphResearcher.from_registry())


def test_pipeline_conforms():
    check_pipeline(LangGraphPipeline.from_registry())
