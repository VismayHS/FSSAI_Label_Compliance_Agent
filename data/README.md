# data: source material

| Path | What | Owner |
|---|---|---|
| [`corpus/`](corpus/) | The two FSSAI regulations (PDFs) with their provenance (`sources.yaml`, `manifest.json`), the claim-trigger map and the retrieval test queries. The index is built from here. | Nishkal |

Built artefacts never live here in git: the indexer writes the search index into the `index-data` volume, and a
local build's `data/index/` and model cache `data/hf-cache/` are git-ignored.
