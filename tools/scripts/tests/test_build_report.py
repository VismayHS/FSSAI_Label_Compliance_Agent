"""The report assembler: order, heading levels, code left alone, honest gaps, decision and incident indexes."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("build_report", Path(__file__).parent.parent / "build_report.py")
br = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(br)


def tree(tmp_path: Path) -> Path:
    report = tmp_path / "docs" / "report"
    (tmp_path / "docs" / "decisions").mkdir(parents=True)
    (tmp_path / "docs" / "incidents").mkdir(parents=True)
    report.mkdir(parents=True)
    (report / "platform-and-integration.md").write_text(
        "# Platform\n\nIntro.\n\n## Cost\n\n```bash\n# not a heading\n```\n", encoding="utf-8")
    (report / "agent-design.md").write_text("# Agents\n\n## Tools\n", encoding="utf-8")
    (tmp_path / "docs" / "decisions" / "302-vismay-queue-rq.md").write_text(
        "# 302 · Queue: RQ on Redis\n\n**Status:** accepted · **Owner:** Vismay\n", encoding="utf-8")
    (tmp_path / "docs" / "decisions" / "001-nishkal-product-category.md").write_text(
        "# 001: Product category: breakfast cereals\n\n- **Owner:** Nishkal · **Status:** Proposed. The team confirms.\n",
        encoding="utf-8")
    (tmp_path / "docs" / "incidents" / "2026-10-25-nishkal-chunker.md").write_text(
        "# 2026-10-25: chunker split rows\n\n- **Author:** Nishkal · **Severity:** high\n", encoding="utf-8")
    return report


def test_sections_in_order_with_headings_demoted_and_code_untouched(tmp_path):
    text, _ = br.build(tree(tmp_path))
    assert text.index("## 1. Problem, architecture and platform") < text.index("## 2. Agent design")
    assert "### Cost" in text and "# Platform" not in text      # own title replaced by the part heading
    assert "```bash\n# not a heading\n```" in text            # code is never rewritten


def test_a_missing_section_is_named_as_pending_never_filled_in(tmp_path):
    text, missing = br.build(tree(tmp_path))
    assert missing == ["retrieval-and-performance.md", "verification-and-evaluation.md"]
    assert "> **Pending:** Vihaan writes `docs/report/verification-and-evaluation.md`." in text


def test_decisions_and_incidents_are_indexed_with_status_and_owner(tmp_path):
    text, _ = br.build(tree(tmp_path))
    assert "| 001 | [Product category: breakfast cereals](../decisions/001-nishkal-product-category.md) | Proposed | Nishkal |" in text
    assert "| 302 | [Queue: RQ on Redis](../decisions/302-vismay-queue-rq.md) | Accepted | Vismay |" in text
    assert "| 2026-10-25 | [chunker split rows](../incidents/2026-10-25-nishkal-chunker.md) | Nishkal |" in text


def test_strict_mode_fails_while_sections_are_missing(tmp_path):
    report, out = tree(tmp_path), tmp_path / "REPORT.md"
    assert br.main(["--report-dir", str(report), "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("# FSSAI Label Compliance Agent: project report")
    assert br.main(["--strict", "--report-dir", str(report), "--out", str(out)]) == 1
    for name in ("retrieval-and-performance.md", "verification-and-evaluation.md"):
        (report / name).write_text("# Done\n", encoding="utf-8")
    assert br.main(["--strict", "--report-dir", str(report), "--out", str(out)]) == 0


def test_strict_mode_fails_on_numbers_still_to_fill_but_not_inside_code(tmp_path):
    report, out = tree(tmp_path), tmp_path / "REPORT.md"
    for name in ("retrieval-and-performance.md", "verification-and-evaluation.md"):
        (report / name).write_text("# Done\n", encoding="utf-8")
    (report / "agent-design.md").write_text(
        "# Agents\n\n| Route accuracy | TODO | TODO(LLM) |\n\n*Pending the load test.*\n\n```bash\n# TODO in code\n```\n",
        encoding="utf-8")
    assert br.placeholders(report) == ["agent-design.md:3", "agent-design.md:5"]
    assert br.main(["--report-dir", str(report), "--out", str(out)]) == 0      # a draft still builds
    assert br.main(["--strict", "--report-dir", str(report), "--out", str(out)]) == 1
    (report / "agent-design.md").write_text("# Agents\n\n| Route accuracy | 0.80 |\n", encoding="utf-8")
    assert br.main(["--strict", "--report-dir", str(report), "--out", str(out)]) == 0
