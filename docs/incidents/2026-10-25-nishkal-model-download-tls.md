# 2026-10-25: embedding model download failed TLS verification

- **Author:** Nishkal · **Severity:** first real-model index build failed; caught before anyone else depended on it
- **Component:** `fssai_ingest build` with `EMBEDDING_MODEL` set to the sentence-transformers model

## What happened

The first build with the real embedding model ran for two minutes and then failed:

```
OSError: We couldn't connect to 'https://huggingface.co' to load the files, and couldn't find them in the cached files.
```

A retry with `huggingface_hub.snapshot_download` showed the real error:

```
ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate
```

Yet `curl` and Python's `urllib` reached huggingface.co fine, with HTTP 200.

## Cause

The development laptop runs antivirus software that intercepts HTTPS and re-signs it with its own root
certificate. That root is in the Windows certificate store, which curl (Schannel) and `urllib` use. The
HuggingFace client uses `httpx`, which trusts only the `certifi` bundle, so it rejected the re-signed
certificate. The first error message ("couldn't connect") hid this.

## Fix

For the one-off download on this laptop: `pip install truststore`, then `truststore.inject_into_ssl()`
before `snapshot_download(...)`, so Python verifies against the OS store. The model now sits in
`data/hf-cache` (on D:, git-ignored), and builds run with `HF_HUB_OFFLINE=1`. No project code was changed
to weaken verification.

## Lesson

- When a client says "couldn't connect" but curl works, look for TLS interception before blaming the
  network. Compare clients that use the OS trust store with clients that use `certifi`.
- The indexer container downloads the model on first start into the `hf-cache` volume. On a machine
  that intercepts TLS, that download can fail the same way, and the worker would then wait for the
  indexer forever. The runbook entry for "index missing" should check the indexer's log for
  `CERTIFICATE_VERIFY_FAILED`. The workaround is to copy a pre-downloaded model into the volume, or to
  add the intercepting root CA to the image.
- Download once, run offline: workers set `HF_HUB_OFFLINE=1` and never touch the network for the model.
