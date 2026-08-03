---
name: prime-knowledge
description: Load task-anchored knowledge about a codebase into a fresh session before doing any work — Martin Fowler's Knowledge Priming applied to a specific ticket or subsystem. Takes a GitHub/Jira/Linear ticket URL, an issue number, or a plain-English question ("how does audio dialog correction work") and researches the slice of the codebase that task touches — data model and migrations, ORM-to-domain mapping, cross-cutting rules, I/O contracts (HTTP/gRPC/Kafka/SQS/SQL), the actual flow as a sequence diagram, the tests that guard it, and the exact files a change would touch. Caches to .hst/kb/ so later sessions are cheap. Use when starting work on an unfamiliar ticket, when a session keeps making shallow or generic decisions about the codebase, when the user says "prime knowledge", "prime this ticket", "get up to speed on X", "research before we implement", or pastes a ticket URL and asks to work on it. Do not use to run tests, review a diff, write code, or set up a branch or worktree for an issue — this skill only builds understanding and stops before implementation.
argument-hint: <ticket-url | issue-number | question> [--deep] [--refresh-base]
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, WebFetch, Task, Agent
---

Prime a fresh session with **task-anchored** knowledge about this codebase, then stop.

The technique is Martin Fowler's [Knowledge Priming](https://martinfowler.com/articles/reduce-friction-ai/knowledge-priming.html): an agent without project-specific context falls back on generic patterns from its training data, and produces code that is plausible, idiomatic for the internet, and wrong for this repo. Priming fills the context with the specific facts that override those defaults.

Two things make this skill different from a generic "read the repo" pass:

- **The task is the scope.** A whole-repo survey is unbounded and mostly irrelevant. The ticket or question decides which slice gets studied, and the slice gets studied *systematically* — which is the comprehension strategy that correlates with correct solutions, and which is only affordable because the slice is small.
- **Claims carry evidence.** Every fact written down is anchored to `file:line` or a reproducible command, and tagged with a confidence level. A confidently wrong knowledge base is worse than no knowledge base — it is the "false confidence" failure mode Fowler names, and it is the one that actually bites.

## Input

`$ARGUMENTS` is a scope argument, optionally followed by `--deep` and/or `--refresh-base`.

| Argument form | Example | Handling |
|---|---|---|
| GitHub issue/PR URL | `https://github.com/org/repo/issues/482` | `gh` fetch (step 1a) |
| Issue number | `482` | `gh` fetch against the current repo |
| Other ticket URL | `https://acme.atlassian.net/browse/PROJ-1841` | `WebFetch`; on auth failure, ask the user to paste the ticket body |
| Ticket key | `PROJ-1841` | no URL to fetch — treat as a search key (step 1b) and ask the user for the description |
| Plain English | `how audio dialog correction logic works` | semantic locate (step 1c) |
| Empty | | Ask what to prime. Do not survey the whole repo. |

`--deep` raises the depth tier (see **Depth**). It is also the refine path: if a slice already exists, `--deep` re-researches and upgrades it rather than reusing it. `--refresh-base` forces every base artifact to be rebuilt regardless of the staleness check.

## The cache

Artifacts live in `.hst/kb/` under the repo root (`git rev-parse --show-toplevel`). They are **workspace-local and gitignored** — scratch knowledge for this checkout, not a documentation deliverable.

```
.hst/kb/
  base/                  ← slice-independent; researched once, refreshed when stale
    brief.md               what this project is · stack · glossary · top gotchas
    structure.md           folder map, tooling, build/test/run commands
    data.md                ERD, migration tool + how to run it, invariants
    domain.md              ORM ↔ table mapping, where business logic lives
    crosscutting.md        auth, transactions, tenancy, retries, errors, config
    history.md             hotspots, change coupling, ADRs, deprecated zones
  slices/
    issue-482.md           per-task briefs; accumulate over time
    audio-dialog-correction.md
  .lanes/                ← raw lane reports, written as they arrive (see step 3)
  MANIFEST.json          ← per-artifact source SHA, files read, depth, skips
```

Create `base/`, `slices/` and `.lanes/` before writing anything into them.

On first run, ensure `.hst/kb/` is ignored: if the repo's `.gitignore` has no line matching it, append `.hst/kb/`. Ignore **only** `.hst/kb/` — `.hst/checks.yaml` from `/hst:check` is meant to be committed, so never add a blanket `.hst/`.

See `references/artifacts.md` for the required shape of every file above.

## Path selection

Run the bundled helper — it reads the manifest, diffs each artifact's recorded SHA against HEAD, and returns the path plus the stale list:

```
python3 <skill-dir>/scripts/kb.py status --slug <slug> --root <repo-root>
```

`--root` is accepted on either side of the subcommand; expand `<skill-dir>` to an absolute path.

| Path | Condition | Work |
|---|---|---|
| **Hot** | base fresh **and** the slice exists with none of its recorded files changed | load `base/brief.md` + the slice; skip to step 5 |
| **Warm** | base fresh; slice is new or stale | slice lanes only (S1–S4) |
| **Cold** | no manifest, any base artifact is stale, or `--refresh-base` | stale base lanes + slice lanes |

Staleness is **per artifact, not global** — the helper intersects each artifact's recorded `files` list with `git diff --name-only <sha>..HEAD`, so a new migration invalidates `data.md` and leaves `crosscutting.md` untouched. Refresh only what it reports stale; reuse the rest verbatim.

Use the helper rather than reconstructing the diff by hand. The logic is identical on every run and the failure mode is silent — a mis-scoped intersection reports stale knowledge as fresh, which is the one outcome worse than no knowledge at all.

`--deep` forces the slice to be re-derived regardless of path. **It overwrites the slice file rather than merging** — a merged slice mixes claims verified at different SHAs under one header, and there's no way to tell afterwards which is which. Carry forward only the user-answered items from *Open questions*, marking them as answered.

Announce the chosen path in one line before starting, e.g.
`[prime] warm — base fresh (5 artifacts), researching slice "issue-482"`.

## Steps

### 1. Resolve the scope

Produce a **scope object**: `{slug, title, intent, acceptance_criteria[], seed_terms[], seed_files[]}`. The slug is kebab-case, 2–4 tokens (same rules as `/hst:worktree`), and names the slice file.

#### 1a. Ticket URL or issue number

```
gh issue view <n> --json number,title,body,url,labels,comments
gh pr view <n>    --json number,title,body,url,files,commits    # if the URL is a PR
```

Extract the intent and the acceptance criteria verbatim — these anchor every later step. Do not paraphrase away a constraint.

Then mine history for prior art, which is the highest-signal step on this path and exists only here:

```
git log --oneline --all --grep='<ticket-id>' -i
git log --oneline --all --grep='<ticket-prefix>' -i    # sibling tickets in the same area
```

Any commit that matches gives you files that were touched for closely related work. `git show --stat` those commits; their file lists seed `seed_files[]`. Linked PRs in the ticket body are worth the same treatment — a prior PR's diff is a free map of the change surface.

#### 1b. Ticket key with no fetchable URL

Run the `git log --grep` mining above on the key, and ask the user to paste the ticket description. Proceed with whatever they give; if they decline, fall back to 1c using the key's words as seed terms.

#### 1c. Plain-English question

Derive `seed_terms[]` from the question — domain nouns and verbs, plus plausible synonyms and naming variants (`audio dialog correction` → `dialog`, `dialogue`, `correction`, `correct`, `fixup`, `audio`). Then locate:

```
git ls-files | grep -iE '<terms>'
```

plus `Grep` over source for the terms in identifiers, and `git log --oneline --all --grep=<term> -i` for commits that named the concept. Rank hits by how central they look (a file named for the concept beats a passing mention) and take the top handful as `seed_files[]`.

If nothing matches, say so plainly and ask the user to name a file or symbol. Do not guess a subsystem.

#### 1d. Check the scope's name for collisions — always

Whatever path got you here, if the scope is named by a domain word, **search for other uses of that word before dispatching anything**:

```
git ls-files | grep -iE '<term>'
git grep -il '<term>' -- '*.md'
```

A domain term almost always means more than one thing in a mature repo — a different subsystem, a retired mechanism, a vendor's word for something unrelated. Every grep-driven lane downstream will silently mix the senses, and the mixing is invisible in the output because each individual citation is correct.

Record the collisions in the scope object and repeat them in the lane prompt as *"X means A here; it also appears as B, which is out of scope."* If two senses are both plausibly what the user meant, that is the one case worth asking about before spending anything — see **Depth**.

### 2. Orient — read what already claims to explain the project

Read the documents that assert things, **within a budget**. Doc trees routinely run to thousands of lines, and reading them all in this session would saturate exactly the context this skill exists to keep lean.

| Read in full | Sample | Dispatch |
|---|---|---|
| `README.md`, the root agent-rules file (`CLAUDE.md` / `AGENTS.md`), and any ADR directory (`docs/adr/`, `docs/decisions/`, `adr/`) | In `docs/`: files the seed terms hit, plus any file whose title claims to describe the architecture. Grep the rest. | If the doc set exceeds ~2000 lines, send it to lane **D0** instead of reading it here |

Count first (`wc -l` over the candidate set) so the choice is made on the actual size, not a guess.

**Treat these as claims, not facts.** Spot-check each load-bearing claim against the code. Every disagreement is a finding — record it in the slice's *Contradictions* section. A stale `CLAUDE.md` is not neutral; it actively steers every future session wrong, and surfacing that is often the single most valuable thing this skill produces.

**No ADR directory does not mean no decisions.** Most repos record them in ordinary docs — a roadmap, a design note, a long schema comment. Look for any document that states decisions with a status, and treat it as the decision log. Report whether it is current *for this slice specifically*: a decision log that stopped before the code you are about to change is worse than none, because it reads as complete.

ADRs get a second read for a different purpose: they explain why a strange choice is deliberate, which is what stops a later session "fixing" it.

### 3. Fan out the recon lanes

Dispatch lanes as **parallel read-only subagents** using the `Explore` agent type. Not `general-purpose` — it has write access, which contradicts the read-only constraint. Their file dumps must not land in this session; each returns only a compact report. Send all lanes for a stage in a single message so they run concurrently.

**Each lane writes its own report to disk and returns only a receipt.** This is the single most important mechanic in the fan-out, and it is what keeps the pass affordable.

A subagent's return value lands in this session's context in full. Lane reports run 1,000–6,500 words each, so nine lanes returning their prose directly costs ~30k tokens of context before synthesis even starts — recreating the saturation this skill exists to prevent. Having each lane write `.hst/kb/.lanes/<lane-id>.md` and return a short receipt cuts that to roughly a tenth, and the orchestrator reads the files back one at a time in step 6, holding only the one it is currently folding in.

It also makes the run resumable: reports on disk survive a compaction or an interruption, and one dead lane no longer forces re-running the ones that succeeded. Delete `.lanes/` on successful completion; keep it under `--deep`.

Use this prompt shape for every lane, so the reports come back comparable. Expand every `<…>` before sending — subagents cannot resolve paths relative to the plugin directory, so the reference paths must be absolute:

```
Repo root: <root>.  You are recon lane <ID> for a codebase priming pass.

Task being primed: <title>
Intent: <intent>
Acceptance criteria: <criteria>
Seed files: <seed_files>
Seed terms: <seed_terms>
Term collisions: <from step 1d — "X means A here; it also appears as B, out of scope">
Depth: <standard | deep>

Your lane answers exactly this: <the lane's question from the table below>

Shape your report like the "<target artifact>" section of
<skill-dir>/references/artifacts.md — read that file first.
For identifying tools, formats and frameworks, consult
<skill-dir>/references/detection.md. Its tables are a fast path, not an
authority: if nothing in a table matches but the project clearly has the
thing, the answer is in the project's own docs. Go read them. A non-match
is never evidence of absence.

WRITE your full report to exactly one file: <root>/.hst/kb/.lanes/<ID>.md
That file is the deliverable. Do not paste it back.

Then RETURN ONLY this receipt, under 120 words — nothing else:
  - the path you wrote
  - 3-6 bullets of headline findings (the things that would change a decision)
  - the count of ASSUMPTION and UNKNOWN tags you left
  - a `files:` list of every path you actually depended on

Your prose is expensive in the caller's context and cheap on disk, which is why
the split exists. Do not summarise the report *instead* of writing it, and do
not message other agents.

Omit any `sha:` from the report header; the orchestrator stamps one SHA
across all artifacts. The `files:` list is yours to report — you are the only
one who knows what you read, and that list is what staleness checks run against.

Every claim carries `path:line` or the command that produced it. Tag claims
VERIFIED / INFERRED / ASSUMPTION / UNKNOWN. `UNKNOWN` is a useful answer — say
it rather than guessing. End with a `## Skipped` list of anything you bounded
or sampled. Do not report on questions outside your lane.

Read-only shell: git, gh, file inspection, and `python3 <skill-dir>/scripts/kb.py`.
No builds, tests, migrations, or servers. The ONE file above is your only write.
```

The lane-scope constraint matters: lanes that wander produce overlapping, contradictory reports that cost more to reconcile than they added.

#### Base lanes — cold path only, or when the artifact is stale

| Lane | Question it answers | Writes |
|---|---|---|
| **D0 docs** *(only when step 2 exceeded its budget)* | What do the project's own docs claim, and which claims disagree with the code | feeds `base/brief.md` and the slice's *Contradictions* |
| **B1 structure & tooling** | What is this, what's the stack, how do I build/test/run it, what's the folder layout, what generates code | `base/structure.md`, feeds `base/brief.md` |
| **B2 data model** | What's the schema, which migration tool owns it, how is a migration written and applied, what are the invariants and indexes | `base/data.md` |
| **B3 domain model** | How do tables map to application objects, where does business logic actually live vs. leak, what are the aggregate boundaries | `base/domain.md` |
| **B4 cross-cutting** | Auth/authz, transaction boundaries, tenancy scoping, idempotency & retries, error taxonomy, logging/tracing, config & feature flags, caching | `base/crosscutting.md` |
| **B5 history** | Hotspots (churn × size), change coupling, ADRs, deprecated/frozen zones, who owns what | `base/history.md` |

B4 is the lane that most often prevents a shallow decision — a handler that forgets tenant scoping or opens a second transaction is exactly the kind of correct-looking, wrong code an unprimed session writes. Do not skip it to save time.

**B2 must ask one question the detection table cannot answer:** does this project have a migration convention the tool itself does not know about? Hand-written pre-apply scripts, a required backfill step, an ordering rule between schema and deploy — these live in the project's docs and runbooks, never in tool config, and no signal table will ever find them. A session that knows the tool but not the convention will write a migration that fails on a populated database.

B5 uses git as the instrument, via the bundled helper:

```
python3 <skill-dir>/scripts/kb.py hotspots --root <repo-root> [--path <subtree>] [--months 12]
```

It returns files ranked by `churn × current_line_count`, plus change-coupling pairs. Hotspots tell you which code to study first — a small fraction of a codebase absorbs most of the work, and that fraction is where a change is most likely to land. Coupling (files that keep changing together) reveals dependencies no static read finds: if a handler consistently changes alongside a migration, that relationship is real even though nothing imports anything.

Run it twice — once scoped to the slice's subtree, once repo-wide — and report the intersection plus anything in the slice's neighbourhood. The helper already excludes deleted files, ignores sweeping refactors that would couple everything to everything, and normalises coupling as a share of the file's own commits rather than a raw count, which would otherwise just re-rank by churn.

**Check creation dates before trusting a low churn score:**

```
git log --diff-filter=A --format='%ad %H' --date=short -- <path> | tail -1
```

Churn over twelve months is meaningless for code that is two weeks old, and the arithmetic inverts the signal exactly where it matters: brand-new code scores near zero and drops off the ranking, so the lane reports "not a hotspot" about the most actively-developed area in the repo. When the slice's files are recent, say so — *"new code, churn understates"* — and rank by recent commit density instead.

#### Slice lanes — every non-hot run

| Lane | Question it answers |
|---|---|
| **S1 flow** | Where does this start, what calls what, what's the end-to-end path — expressed as a mermaid `sequenceDiagram` |
| **S2 contracts** | What crosses the boundary in and out: HTTP request/response shapes, gRPC service+message, Kafka topic + schema, SQS/SNS payload, or source/target SQL for an ETL |
| **S3 tests as spec** | Which tests guard this path, what edge cases they already encode, what's conspicuously untested, how to run just those tests |
| **S4 change surface** | Given the acceptance criteria, exactly which files a change would touch, and the blast radius of touching them |

S3 earns its place because tests are the most reliable specification in most repos — they state the edge cases the prose docs forgot. S4 is what makes the output actionable rather than encyclopedic.

See `references/detection.md` for how to identify migration tools, ORMs, contract types, and test layers across ecosystems. Detect from repo signals; never assume a default because a language usually uses one.

### 4. Reporting contract — every lane, every claim

Each lane returns markdown with:

- **Evidence on every claim.** `path/to/file.go:142`, or the exact command whose output backs it. A claim with no anchor is deleted, not softened.
- **A confidence tag** where it isn't self-evident:
  - `VERIFIED` — read the code that does this
  - `INFERRED` — deduced from strong signals, not directly read
  - `ASSUMPTION` — plausible, unconfirmed, and load-bearing
  - `UNKNOWN` — tried to determine it and could not
- **Commands over prose** wherever a command exists. `atlas migrate apply --env local` beats "migrations are applied via Atlas." Commands stay correct when prose rots.
- **A skipped list.** Anything bounded (top-N, sampled, a directory excluded for size) is stated explicitly. Silent truncation reads as complete coverage when it isn't.

Read-only shell is limited to `git`, `gh`, file inspection, and `python3 <skill-dir>/scripts/kb.py`. Do not run builds, migrations, servers, or anything that mutates state or hits a network service other than the ticket host.

### 5. Verify

Sample the assembled claims and re-open the cited `file:line`. Any claim whose evidence does not actually support it gets downgraded or deleted. Prioritise claims in `crosscutting.md` and the slice's *Rules you must not break* — those are the ones that cause damage when wrong.

At standard depth, verify the load-bearing claims. At `--deep`, verify every claim, and dispatch adversarial verifiers whose instruction is to *refute* — a claim survives only if the refutation attempt fails.

### 6. Write artifacts, then update the manifest

The reports in `.hst/kb/.lanes/` are the record. Most of them are already the artifact:

| Lane | Becomes | How |
|---|---|---|
| B1 · B2 · B3 · B4 · B5 | `base/structure.md` · `data.md` · `domain.md` · `crosscutting.md` · `history.md` | **move the file**, then stamp the SHA header |
| S1 · S2 · S3 · S4 | one `slices/<slug>.md` | read all four, merge into the slice template |
| D0 + receipts + the base artifacts | `base/brief.md` | read and synthesize — this is the only place a cross-lane view is needed |

Move rather than read wherever a lane maps 1:1 to an artifact. That is why lanes are told to write in the target artifact's shape: it lets five of the nine reports reach `base/` without ever entering this session's context. Only the slice merge and the brief genuinely need to read, and the brief is 2 pages built mostly from receipts.

Write the base and slice files per `references/artifacts.md`, then update `MANIFEST.json` (JSON, not YAML — `scripts/kb.py` parses it with no third-party dependency):

```json
{
  "generated_at": "2026-08-03T10:22:11Z",
  "head_sha": "8ba8995",
  "base": {
    "structure.md": {"sha": "8ba8995", "depth": "standard", "files": ["go.mod", "Makefile", "cmd/"]},
    "data.md":      {"sha": "8ba8995", "depth": "standard", "files": ["migrations/", "atlas.hcl"]}
  },
  "slices": {
    "issue-482": {
      "sha": "8ba8995",
      "source": "https://github.com/org/repo/issues/482",
      "depth": "deep",
      "files": ["internal/audio/correct.go", "internal/audio/correct_test.go"]
    }
  },
  "skipped": ["vendor/ — 12k files, excluded from all lanes"]
}
```

Take one `git rev-parse HEAD` for the whole pass and stamp it on every artifact you wrote this run — lanes do not know it and must not invent it, and per-lane SHAs would disagree if the tree moved mid-run. Artifacts you reused untouched keep their old SHA; that is what makes per-file staleness work. `head_sha` at the top records the pass; `kb.py` reads only the per-artifact values.

`files` comes from each lane's own report — it is the one thing only the lane knows. Directories are fine for lanes that swept them. **That list is the staleness check.** A path omitted here is a claim that will go stale silently, and silently-stale knowledge is trusted exactly as much as fresh knowledge.

Delete `.hst/kb/.lanes/` once the artifacts are written, unless this was a `--deep` run.

### 7. Emit the working brief, and stop

Print into the session — not the whole knowledge base, which would defeat the purpose:

1. **What this project is** — 3–5 lines from `base/brief.md`
2. **The task** — intent and acceptance criteria as resolved in step 1
3. **The flow** — the mermaid sequence diagram from S1
4. **Change surface** — the files a change would touch, with blast radius
5. **Contracts in play** — what crosses the boundary, in and out
6. **Rules you must not break** — the cross-cutting constraints on *this* path, concretely (`every query filters on tenant_id — internal/db/scope.go:31`), not as a topic list
7. **Tests that guard it** — plus the command to run just them
8. **Open questions** — `ASSUMPTION` and `UNKNOWN` items, and any contradictions from step 2
9. **Deeper reading** — the `.hst/kb/` paths, so this session can pull detail just-in-time

Then close with:

```
[prime] ready. <n> open questions above. Re-run with --deep to refine, or tell me to start.
```

**Do not begin implementing.** Priming and executing are separate turns on purpose: the map is cheapest to correct before code is written on top of it, and a session that slides straight into edits gives the user no chance to catch a wrong assumption. If the user's message asked for both, prime first, present, and wait.

## Depth

**Standard (default, auto-adapting).** Scale the fan-out to what the scope turns out to be:

| Signal | Effect |
|---|---|
| Seeds land in ≤3 files with one clear entry point | Drop S4 into S1; read the files directly instead of dispatching |
| Ticket touches a migration, or seeds include schema files | B2 and B3 are mandatory even if the base looks fresh |
| Ticket crosses a service/protocol boundary | S2 gets two lanes — one per side |
| Prior-art commits found in step 1a | Feed their diffs to S4; it costs almost nothing and sharpens the blast radius |
| Slice is broad (many files, or a whole subsystem) | Narrow it, **say which narrowing you took**, proceed, and put the remainder in *Open questions* — do not stall |
| Step 1d found the scope name is a coin-flip between two unrelated subsystems | **Ask.** This is the one ambiguity worth blocking on |

**`--deep`.** Adds: refutation-style verification of every claim (step 5); change-coupling analysis extended repo-wide rather than slice-local; full read of the relevant test suite rather than a sample; `git log -p` on the hotspot files to recover intent behind the odd parts; and re-derivation of any slice that already exists rather than reuse.

Use `--deep` when the ticket touches money, auth, data migration, or a hotspot from B5 — or when a standard run came back with more `ASSUMPTION` tags than you're comfortable building on.

**`--refresh-base`.** Rebuilds every base artifact regardless of what the staleness check says.

Needed because the check can only be as good as each artifact's recorded `files` list — the silent failure this skill warns about elsewhere. When a lane's list was too narrow, the artifact is stale and the helper will keep reporting it fresh forever, with no way out. `base/history.md` is the standing case: it records `"files": []` because it derives from commit metadata rather than file contents, so it is never invalidated and would otherwise be written once on the cold path and never again.

## Principles behind the rules

- **The task chooses the scope.** Studying a whole repo systematically is unaffordable, and studying it as-needed produces the shallow decisions this skill exists to fix. Bounding to the slice makes the systematic strategy affordable, which is the combination that correlates with correct work.
- **Evidence or deletion.** Softening an unsupported claim to "probably" keeps it in the context, where it still gets acted on. The tags exist so `ASSUMPTION` reads as *a question to resolve*, not as a fact with a hedge attached.
- **The brief is short on purpose.** Dumping the full knowledge base into the session recreates the problem — a saturated context degrades exactly the reasoning it was meant to improve. Compact brief in context, detail on disk, pulled when needed.
- **Cache split by what varies.** The repo-wide layer is identical for every ticket and expensive to build; the slice layer is cheap and different every time. Splitting them is what makes the second ticket of the day nearly free.
- **Per-file staleness.** A global "regenerate everything" flag makes people skip regeneration, and stale context is worse than absent context because it is trusted. Per-file invalidation keeps refreshes small enough to actually happen.
- **Docs are claims.** Documentation drifts and nothing fails when it does. Reading docs without checking them against code imports the drift and hands it to the session as fact.
- **Cross-cutting concerns before contracts.** Endpoint shapes are easy to read off the code at any time. Tenancy scoping, transaction boundaries, and idempotency rules are invisible in the local file and catastrophic to get wrong — they need to be in context *before* anyone proposes a change.
- **Tests are the specification.** Prose docs describe the happy path; tests encode the edge cases someone actually hit in production. Reading them is the cheapest route to the constraints nobody wrote down.
- **Git is evidence, not history.** Hotspots say which code matters, coupling says what breaks together, and `git log -p` on a strange function usually explains that it's strange on purpose — which is what stops the next session from "fixing" it.
- **Lane reports go to disk, and only a receipt comes back.** A subagent's return value lands in the caller's context in full, so nine lanes returning their prose would spend ~30k tokens recreating the saturation this skill exists to prevent. Writing the report and returning a receipt costs a tenth of that, lets synthesis read one report at a time, and makes an interrupted run resumable instead of forcing a re-run.
- **A word means more than one thing.** In any mature repo a domain term has a second, unrelated sense somewhere, and every grep-driven lane will mix them without noticing — each citation is individually correct, so nothing looks wrong. Naming the collision once, up front, is far cheaper than untangling a report that quietly spans two subsystems.
- **Detection tables are heuristics.** They key on conventional filenames, and real projects deviate constantly. Treating a non-match as proof of absence produces a confident wrong answer; the project's own docs are the authority whenever a table comes up empty.
- **Narrow and say so, rather than stall.** A broad question usually has an obvious primary reading, and a run that halts to ask delivers nothing. Stating the narrowing lets the user correct it in one word. Reserve blocking for a genuine coin-flip between unrelated subsystems, where guessing wastes the whole pass.
- **Stop before implementing.** Every wrong assumption in the brief becomes a wrong assumption in the diff, and it is far cheaper to correct a bullet than a branch.
