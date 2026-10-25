"""fssai_stub_llm: an OpenAI-compatible stand-in for the LLM provider (Nishkal, D6).

Load tests point LLM_BASE_URL at it so they measure our system, not a free tier's rate limits; the
circuit-breaker demo (A5, demo #8) switches it down at runtime.
"""
