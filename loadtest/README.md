# loadtest

Load testing against the declared SLO (D6, A7, D7). Owner: Nishkal.

| File | What |
|---|---|
| [`SLO.md`](SLO.md) | The target, declared before measuring: full-run p95 ≤ 60 s at 5 concurrent runs and ≤ 1 % failed, with the stub LLM |
| `locustfile.py` | Each simulated analyst submits a check and polls it to the end; the whole run is one `full_run` sample |
| `run_matrix.py` | The 1/2/5/10/20-user matrix at each worker scale, saved under `results/` with machine and index metadata |
| `summarize.py` | Turns a results folder into the table D6 asks for: RPS, p50 and p95 against the SLO |
| `payloads/` | The request bodies the load test sends |
| [`results/`](results/) | Measured results. Every reported number comes from a folder here |

```bash
python loadtest/run_matrix.py --host http://localhost:8000 --compose --scales 1 3
```
