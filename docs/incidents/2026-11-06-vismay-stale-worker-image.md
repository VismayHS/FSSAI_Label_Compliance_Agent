# 2026-11-06: the grounding fix was merged but the running worker still had the old code

- **Author:** Vismay · **Severity:** a fix looked as if it had failed on the real LLM; a demo could have shown the
  bug it was meant to remove
- **Component:** Compose images (`fssai-worker:local`, `fssai-api:local`)

## What happened

After the grounding fix (incident `2026-11-06-vismay-grounding-dropped-real-quotes`, commit `2eb5101`), the first
real-Groq smoke run still routed with three `LBL-…: no verbatim citation survived grounding` reasons. That is
exactly the symptom the fix removes.

## How it was noticed

The routing reason in the smoke output. The worker image's creation time (5 Nov, 19:18 UTC) was earlier than the fix
commit (6 Nov, 01:36 IST). `inspect.getsource` of `fssai_agents.grounding` inside the container showed the old
whitespace-collapsing version.

## Cause

`docker compose up -d --force-recreate api worker` recreates containers **from the existing images**; it does not
rebuild them. The images are built from the source tree (`pip install` into the image), not bind-mounted, so code
changes reach a running stack only through `docker compose build` (or `up --build`).

## Fix

`docker compose build worker api`, then recreate. The next smoke run dropped one citation instead of three, and demo
#2 passed with 10 of 10 citations resolving.

## Lesson

After any code change, start the stack with `docker compose up -d --build`, as `docs/demo-script.md` already says
for the review. `--force-recreate` alone only re-reads `.env`. When a fix seems not to work on the stack, check the
image's creation time against the commit first.
