"""Print the red-team block rate at the end of every guardrails test run, so CI logs always show it."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def pytest_terminal_summary(terminalreporter, exitstatus, config):  # noqa: ARG001
    try:
        from redteam import score
        r = score()
    except Exception as exc:  # noqa: BLE001 - reporting must never fail a run
        terminalreporter.write_line(f"red-team report unavailable: {type(exc).__name__}: {exc}")
        return
    terminalreporter.write_sep("-", "red-team block rate (input guardrail, heuristics default set)")
    terminalreporter.write_line(
        f"blocked {r['blocked']}/{r['attacks']} attacks ({r['block_rate']:.0%}); "
        f"false positives {len(r['false_positives'])}/{r['clean']} clean label texts ({r['false_positive_rate']:.0%})")
    if r["missed"]:
        terminalreporter.write_line("missed: " + ", ".join(r["missed"]))
