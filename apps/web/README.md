# FSSAI Label Check (web client)

The analyst's workspace (A8): submit a label, follow the run, read the route, the findings with their
clauses and quotes, and the full trace. Owner: Vismay. Product truth in [PRODUCT.md](PRODUCT.md),
visual rules in [DESIGN.md](DESIGN.md), stack in decision 303.

```bash
npm ci                 # Node 22+
npm run dev            # http://localhost:5173; /v1 is proxied to FSSAI_API_URL (default http://localhost:8000)
npm run check          # types + lint + tests + production build (the definition of done)
npm run add:react-bits -- <Name>   # pinned React Bits component, see tools/skills/project/react-bits
```

Start the API first (from the repo root):
`.venv/Scripts/python -m uvicorn app.main:create_app --factory --env-file .env --port 8000`
(`.venv/bin/python` on macOS).

| Path | What |
|---|---|
| `src/api/` | `types.ts` mirrors `packages/contracts/fssai_contracts/schemas.py`; `client.ts` is the HTTP contract as typed outcomes |
| `src/components/` | Header, RequestPanel (form / JSON), RunPanel (declaration block, stage board, findings, trace), RecentRuns |
| `src/components/reactbits/` | Vendored React Bits components (licence header in each file); don't edit beyond token mapping |
| `src/styles/` | `tokens.css` (the only place colours, type, space and motion are defined), `base.css`, `app.css` |
| `public/config.js` | Runtime settings (API base URL), generated from env in Compose |
| `.impeccable/` | impeccable's design records: the surface brief (direction contract) and the decision sketches |

Design work follows `tools/skills/project/fssai-frontend`; its gate includes
`node tools/skills/vendor/taste-skill/skills/taste-skill/scripts/inspect.mjs http://localhost:5173 --allow mono,few-pictures`.
