"""LLM gateway (owner: Vismay). Select it with IMPL_LLM=fssai_llm_gateway.client:GatewayLLMClient.

client   GatewayLLMClient: the LLMClient every agent calls (A5, L5)
breaker  CircuitBreaker with a shared (Redis) or per-process state store
metrics  Prometheus metrics for calls, retries, breaker state, tokens and cost
"""
