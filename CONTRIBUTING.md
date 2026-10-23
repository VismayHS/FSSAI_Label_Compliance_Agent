# Contributing: branches, commits and PRs

Four people share this repo, and each one keeps **their own branch and their own commit history**.
Nobody works on `main` and nobody pushes to a shared branch. This file is the full workflow;
`AGENTS.md` and `contexts/LLM_Context.md` §8 summarise it for AI assistants.

## 1. The branch model

| Branch | Who pushes to it | What it is |
|---|---|---|
| `nishkal` | Nishkal only | Nishkal's complete working history |
| `namith` | Namith only | Namith's complete working history |
| `vihaan` | Vihaan only | Vihaan's complete working history |
| `vismay` | Vismay only | Vismay's complete working history |
| `main` | **nobody**: it changes only when a PR is merged | The integrated system. Always boots; it is what we demo and submit. |

- Your branch is **long-lived**. You use the same branch from day 1 to submission, and it is never deleted.
- Your commits stay yours. PRs are merged with a **merge commit** (never squash or rebase), so
  every commit on `main` keeps its original author, and `git log --author=<you>` shows exactly
  what you built.
- You never push to `main`, never push to a teammate's branch, and never force-push.
- Want to experiment? Make a *local* branch, then merge it into your own branch when it works. Only
  your own branch is ever pushed.

## 2. One-time setup (each person, on each laptop)

Prerequisites: Git, Python 3.11+, Docker Desktop (Compose v2.20+). See LLM_Context §8.8 for
Windows/macOS notes.

```bash
# 1. Make your commits show up under your GitHub account (use the email on your GitHub profile,
#    or your <id>+<user>@users.noreply.github.com address if you keep your email private)
git config --global user.name  "Your Name"
git config --global user.email "you@example.com"

# 2. Clone and run the setup script with your own name
git clone https://github.com/VismayHS/FSSAI_Label_Compliance_Agent.git
cd FSSAI_Label_Compliance_Agent
python scripts/setup_dev.py <your-name>      # nishkal | namith | vihaan | vismay
#   (Windows: `py -3.11 scripts/setup_dev.py <your-name>` if `python` isn't 3.11+)
```

The script:
1. switches you to your own branch (`<your-name>`) and sets it to track `origin/<your-name>`,
2. turns on the repo's git hooks (`.githooks/`, see §6) and records your branch name for them,
3. creates `.venv`, installs `contracts[test]` and runs the contract tests,
4. creates `.env` from `.env.example` if you don't have one.

It is safe to run again at any time.

## 3. Every working session

```bash
git switch <your-name>
git pull                       # picks up anything you pushed from another machine
git fetch origin
git merge origin/main          # brings in teammates' merged work. Merge; never rebase.

# ... work, test, commit as often as you like ...
git add <files> && git commit -m "retrieval: add clause lookup by id"

git push                       # always goes to origin/<your-name>, nowhere else
```

Commit messages: `<area>: <what changed>`, for example `gateway: add circuit breaker`,
`contracts: add Passage.page`, `docs: incident for redis timeout`. One logical change per commit.

## 4. Getting your work into `main`

1. Bring your branch up to date: `git fetch origin && git merge origin/main`.
2. Run the checks:
   ```bash
   <venv-python> -m pytest contracts -q
   <venv-python> -m pytest <your-package> -q
   # once Compose exists: docker compose up -d && make smoke   (or the plain command in the README)
   ```
3. Push, then open a PR on GitHub: **base `main` ← compare `<your-name>`**. Fill in the template.
4. Merge it with **"Create a merge commit"**. Squash and rebase merging are turned off.
   - If the PR only touches your own paths and the checks pass, you can merge it yourself.
   - PRs touching `contracts/`, `docker-compose.yml`, `.env.example` structure or `.github/` need
     one approval from an affected owner.
5. Keep working on the same branch. **Don't delete it** when GitHub offers to.

Merge into `main` **at most once per day per person**: batch the day's work into one PR. Commit and
push to your own branch as often as you like, because that affects nobody.

## 5. Working alongside each other

- **You need a teammate's code that isn't on `main` yet.** Keep using the fake from `contracts/`.
  Don't merge their branch into yours: their commits would then show up inside your PR. To *read*
  what they're doing:
  ```bash
  git fetch origin
  git log  origin/namith --oneline
  git diff main...origin/namith
  ```
- **A merge from `main` conflicts.** Owned paths don't overlap, so a conflict almost always means a
  file you don't own was changed on your branch. Keep `main`'s version of it:
  ```bash
  git checkout --theirs -- <file> && git add <file> && git commit
  ```
  If the conflict is in a file you do own, resolve it normally.
- **You committed something wrong.** If it isn't pushed yet, `git commit --amend` or
  `git reset --soft HEAD~1` is fine. If it is pushed, fix it with a new commit (or `git revert`).
  Never rewrite pushed history.
- **`main` is broken.** Tell the group chat straight away. Whoever's PR broke it fixes it with a
  follow-up PR from their own branch.

## 6. Git hooks (`.githooks/`)

GitHub can't limit who pushes to which branch in a personal repo, so the hooks enforce it on your
machine. `scripts/setup_dev.py` turns them on; by hand that's
`git config core.hooksPath .githooks && git config fssai.branch <your-name>`.

| Hook | What it does |
|---|---|
| `commit-msg` | Removes AI attribution lines (`Co-Authored-By: <AI tool>`, "Generated with ...") from every commit message. |
| `pre-push` | Refuses to push to `main` or to anyone else's branch, refuses force-pushes and branch deletions, and refuses commits that still carry AI attribution. |

Don't bypass them with `--no-verify`.

## 7. AI assistants

Use them freely, but **commits are written as yours alone**:
- No `Co-Authored-By:` trailers for AI tools, and no "Generated with ..." lines in commits or PRs.
  The `commit-msg` hook strips them anyway.
- Claude Code reads `.claude/settings.json`, which turns its attribution off for this repo. Other
  tools (Copilot, Cursor, Codex, ...) have a similar setting; switch it off.
- The assistant follows `AGENTS.md`: it edits only your paths, works only on your branch, and
  commits or pushes only when you ask.

## 8. Settings the repo owner applies on GitHub

(Vismay, once; listed so everyone knows what to expect.)
- **Settings → General → Pull Requests:** allow merge commits only (untick squash and rebase
  merging), and untick "Automatically delete head branches".
- **Settings → Rules → Rulesets → New branch ruleset** for `main`: require a pull request before
  merging, block force pushes, restrict deletions.
- A second ruleset for `nishkal`, `namith`, `vihaan`, `vismay`: block force pushes, restrict deletions.
