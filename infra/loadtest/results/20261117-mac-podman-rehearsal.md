# Mac Podman performance rehearsal — 2026-11-17

## Environment and method

- Source HEAD: 779388f, with uncommitted load-test runner and documentation changes.
- Host: Apple Silicon MacBook Air, arm64, 16 GiB RAM.
- Podman 6.0.2; VM allocation: 4 CPUs, 8 GiB RAM.
- Docker Compose provider connected to the existing Podman VM.
- LLM: local stub, configured mean latency 1.5 s and p95 4 s.
- Retrieval: hashing embeddings, FAISS and BM25.
- Cache enabled; five concurrent users.
- Each measurement followed a 30-second warmup and ran for five minutes,
  with up to 200 seconds allowed for in-flight runs to finish.
- These results measure the pipeline with simulated LLM responses,
  not real-model reasoning quality.

## CSV summary results

| Workers | Users | Runs | Runs/s | Full-run p50 | Full-run p95 | Failures | Submit p95 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 5 | 66 | 0.20 | 24 s | 37 s | 0% | 0.014 s |
| 3 | 5 | 207 | 0.67 | 7.2 s | 12 s | 0% | 0.010 s |

Both configurations met the tested threshold: full-run p95 <= 60 seconds
and failures <= 1% at five concurrent users.
Three workers delivered approximately 3.3 times the observed throughput.

## Evidence and limitations

- One-worker files: 20261117T161302Z-mac-podman-cache-on/
- Three-worker files: 20261117T162403Z-mac-podman-w3-cache-on/
- Final console counts were 67 and 208; CSV summary counts were 66 and 207.
  Original files are retained; the counts have not been reconciled.
- Only five-user concurrency was measured in this Mac rehearsal.
  The summarizer's 'first fails at >5 users' line does not establish
  a failure point.
- Machine configuration is documented here because these manual runs
  did not generate meta.json.
- The real-model section 4.1 rehearsal and Vihaan's RDA decision remain
  pending. Stub responses do not establish the protein-claim outcome.
