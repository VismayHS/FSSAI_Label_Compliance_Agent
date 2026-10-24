"""The CLI keeps the options the indexer container calls it with."""
from fssai_ingest.__main__ import parser


def test_build_options():
    args = parser().parse_args(["build", "--corpus", "corpus/raw", "--out", "idx", "--reembed", "changed"])
    assert (args.command, args.corpus, args.out, args.reembed) == ("build", "corpus/raw", "idx", "changed")
