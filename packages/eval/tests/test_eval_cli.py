"""The CLI keeps the options teammates call it with."""
from fssai_eval.__main__ import parser


def test_run_options():
    args = parser().parse_args(["run", "--scenarios", "packages/eval/scenarios.jsonl", "--tag", "baseline"])
    assert (args.command, args.scenarios, args.tag) == ("run", "packages/eval/scenarios.jsonl", "baseline")
