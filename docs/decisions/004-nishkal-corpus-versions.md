# 004: Corpus: FSSAI's consolidated compendia, amended text in force

- **Owner:** Nishkal · **Status:** Accepted
- **Requirements:** spec §3 (corpus), D2 (freshness: which versions are indexed)

## Context

FSSAI publishes each regulation as a principal Gazette notification plus separate amendment
notifications and Directions. It also publishes a consolidated **compendium** per regulation that
prints the principal text with each amendment after the provision it replaces. Spec §3 asks for the two
regulations "including the latest consolidated or amended versions if published", with a text layer
preferred.

## Options

1. Principal Gazette notifications, plus each amendment as its own document.
2. The compendia.
3. Mixed: compendium plus newer amendments not yet consolidated.

## Decision

Option 2, the compendia as published by FSSAI:

| Code | Compendium | Pages | Text layer |
|---|---|---:|---|
| FSS-AC-2018 | Advertising and Claims, Version-II (16.11.2021) | 23 | yes, all pages |
| FSS-LD-2020 | Labelling and Display, Version-VI (22.02.2023) | 42 | yes, all pages |

Why:

- One document per regulation, with the amended text placed next to the text it amends. The chunker can
  mark what is superseded (decision 002) instead of reconciling separate notifications.
- Both have a full text layer, so no OCR is needed and the quotes are exact.
- They are the versions an FSSAI analyst reads.

Provenance is in `data/corpus/sources.yaml` and is computed into `data/corpus/manifest.json`: source URL, the URL the
bytes actually came from, version, sha256, pages, text layer. `fssai_ingest manifest` regenerates the
manifest, and a test fails if the committed manifest no longer matches the PDFs.

## Consequences and caveats

- **A compendium is not the legal text.** FSSAI states that where it differs from the Gazette
  notifications, the notifications prevail. The system's output is a compliance *finding* for a
  professional (never an approval), which this caveat supports. It belongs in the report's scope section.
- **Newer amendments may exist.** FSSAI's amendments page lists Labelling amendments after Version-VI
  (e.g. 2025). They are not in the corpus. A label affected by them is outside what the system knows.
  `IndexStale` alerts after 30 days to prompt a check, and the freshness metrics show which versions
  are loaded.
- **Where the bytes came from.** On 2026-10-25 every connection to fssai.gov.in was reset from our
  network (incident `docs/incidents/2026-10-25-nishkal-fssai-site-unreachable.md`). The files were
  fetched from the Internet Archive's captures of the official URLs (`retrieved_via` in
  `data/corpus/sources.yaml`). When fssai.gov.in is reachable, download from `source_url` and compare the
  sha256 in the manifest. A mismatch means a newer upload: re-run the manifest, rebuild the index
  (`--reembed changed`) and recheck the §4.1 passages.
