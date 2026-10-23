<!-- Base: main  ←  Compare: your own branch (nishkal | namith | vihaan | vismay). See CONTRIBUTING.md §4. -->

## What this merges
<!-- 1–3 lines: what works now that didn't before. Link the checklist items from contexts/<Name>.md. -->

## Checks
- [ ] My branch is up to date: `git fetch origin && git merge origin/main`
- [ ] `pytest contracts -q` passes
- [ ] My package's tests pass: `pytest <package> -q`
- [ ] Once Compose exists: `docker compose up` + smoke test pass
- [ ] Only my own paths are changed (LLM_Context §5), or the approval below is requested
- [ ] New config is env-only and documented in my section of `.env.example`; no secrets, endpoints or model ids
- [ ] No AI attribution lines in commits or in this description
- [ ] Ticked the done items in my `contexts/<Name>.md`

## Needs approval?
<!-- Only if this touches contracts/, docker-compose.yml, .env.example structure or .github/. Name the owner asked. -->

<!-- Merge with "Create a merge commit". Don't delete your branch afterwards. -->
