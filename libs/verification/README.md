# fssai_verification (`libs/verification`)

The verifier agent (A3: every answer checked against retrieved text; A2: the second agent) and the router (F6, F7).
Design: decisions [202](../../docs/decisions/202-vihaan-verifier-design.md) (verifier) and
[201](../../docs/decisions/201-vihaan-routing-rules.md) (routing rules).

**Owner:** Vihaan · tasks V2.1, V2.2 in [`contexts/Vihaan.md`](../../contexts/Vihaan.md).

| File | What |
|---|---|
| `fssai_verification/verifier.py` | `AgentVerifier`, the `Verifier` seam: citations resolve → numbers re-derived → LLM support check → accept / retry with hint / escalate |
| `fssai_verification/checks.py` | The deterministic checks: `resolve_citation`, reading a claim's condition from passage text, `numeric_check` |
| `fssai_verification/router.py` | `RuleRouter`, the `Router` seam: rules R1–R9, first match wins, the rule id starts every reason |
| `fssai_verification/prompts/verifier_support/` | The verifier's own versioned prompt (`[prompt:verifier_support@1.0.0]`) |
| `tests/` | conformance, checks on the real Schedule I rows, verifier on hand-built dossiers, one test per routing rule |

```bash
<venv-python> -m pip install -e "libs/verification[test]"
<venv-python> -m pytest libs/verification -q
<venv-python> eval/tools/demo_trust.py --in-process      # demo #6: a bad citation retried with a hint, then verified
```

**Switched on with** `IMPL_VERIFIER=fssai_verification.verifier:AgentVerifier` and
`IMPL_ROUTER=fssai_verification.router:RuleRouter`. Env: `VERIFIER_SUPPORT_CHECK` (llm/off),
`VERIFIER_TOLERANCE_PCT` (20, FSS-LD-2020 5(3)(d)), `VERIFIER_MAX_LOOKUPS`, `PROMPT_VERIFIER_SUPPORT_VERSION`.

Trace (D5): one `verification` step per attempt with per-finding results (citations, numeric comparison, support
label, retry/escalate reasons) and the `resolve_citation` calls; a `tool` step with the full passage for each
`clause_lookup`; the LLM client's own `llm` step; one `routing` step with the rule id.
