# 2026-10-25: fssai.gov.in unreachable while fetching the corpus

- **Author:** Nishkal · **Severity:** blocked a task (N0.2) for about 20 minutes; no system impact
- **Component:** corpus acquisition (`corpus/raw/`)

## What happened

Downloading the two regulation compendia from their official URLs failed on every attempt:

```
curl: (35) Recv failure: Connection was reset
```

The same happened over IPv4 only, HTTP/1.1, TLS 1.2 and TLS 1.3, over plain `http://`, from Python's
`urllib` (OpenSSL instead of Windows Schannel), and in the app's built-in browser. It also happened for
the `www.`, `mail.`, `stg-old.` and `foscos.` subdomains. `cdd.fssai.gov.in` timed out. Other HTTPS sites
worked from the same machine.

## How we noticed

The first `curl` of the Claims compendium returned HTTP 000 with zero bytes.

## Cause

Not confirmed. A reset at connect time on every protocol and from every client points at a network-level
block between our network and fssai.gov.in (a firewall or geo/bot filtering), not at our tooling. It was
not a TLS-interception problem: plain HTTP was reset too.

## Fix

Fetched the official files from the Internet Archive's captures of the exact official URLs, using the
`id_` form, which returns the original bytes rather than an archive page:

- `https://web.archive.org/web/20260605090411id_/https://fssai.gov.in/upload/uploadfiles/files/Compendium_Advertising_Claims_Regulations_16_11_2021.pdf`
- `https://web.archive.org/web/20260329130834id_/https://fssai.gov.in/upload/uploadfiles/files/Comp_Labelling.pdf`

Both are valid PDFs with a full text layer, and their version labels match FSSAI's (Version-II
16.11.2021, Version-VI 22.02.2023). `corpus/sources.yaml` records both the official `source_url` and
`retrieved_via`; `corpus/manifest.json` records the sha256.

## Lesson

- Record where the bytes actually came from, not only where they should have come from. Provenance is
  part of data freshness (D2).
- The archived copy is only as good as the date of the capture. When fssai.gov.in is reachable again,
  download from `source_url` and compare the sha256 (decision 004).
- The same block would hit any container that tried to download the corpus at start-up. The corpus is
  therefore committed to the repo, not fetched by the indexer.
