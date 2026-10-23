"""Shared contracts for the FSSAI label compliance service.

schemas     data shapes passed between modules and over HTTP
context     RunContext: loop bounds, step trace, structured events
interfaces  the seam between each owner's module
fakes       a working fake for every seam
pipeline    the reference hand-off order (replaced by the LangGraph pipeline)
registry    picks fake or real implementations from IMPL_* env vars
dev_llm     bare OpenAI-compatible client for development
"""
