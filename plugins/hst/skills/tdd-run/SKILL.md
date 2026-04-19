---
name: tdd-run
description: Use this skill for test-driven development — implementing a feature, class, function, or module by writing a failing test first, then minimal code to pass, then refactoring. Applies whenever the user's intent is to grow production code incrementally through tests rather than run existing ones. Signals include wanting to "see red" or watch a test fail before writing code, working through a scenario or test list one item at a time, Kent Beck style, strict red-green-refactor, or "TDD this" on a named target file/class. Also applies when the user has a scenario list (inline, in a markdown file, or from the tdd-scenario-planner agent) and wants to start implementing it. The presence of a build command (gradle, pytest, go test, jest, cargo, etc.) alongside test-first framing still indicates TDD, not suite execution. Do not use for running or debugging an existing test suite, reviewing PRs, editing CI, fixing flaky tests, or generating coverage.
argument-hint: [scenario-list-path]
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

Walk a scenario list through a **strict Red → Green → Refactor cycle**, one scenario at a time. This skill is language-agnostic but *project-specific*: it discovers the project's own build and test workflow — its package manager, its build tool, its test framework, its CI entry point — and uses those rather than generic defaults.

### Why this skill is strict

The power of Red-Green-Refactor comes from three specific signals, and each step exists to produce exactly one of them:

- **Red** — watching the test fail proves the test can actually catch a regression. A test written after the code passes trivially; it proves nothing.
- **Green** — the minimum code change that flips Red to Green tells you that change was sufficient and no more. Anything bigger mixes behaviors.
- **Refactor** — because behavior is pinned by green tests, design changes become free of risk. This is where the compounding value of TDD actually shows up.

Every rule in this skill exists because skipping it erases one of those signals. Batching scenarios hides which code change made which test pass. Writing production code before the failing test hides whether the test can fail at all. Loosening a regressing pre-existing test hides a real defect under a green bar. Running tests via a generic command when the project has its own wrapper hides CI-relevant setup. The rationale for each rule is spelled out at the step where it applies — follow them because the cycle stops working when you don't.

## Input

`$ARGUMENTS` is one of:

- **Empty** → use the most recent scenario list present in the current conversation (typically just produced by the `tdd-scenario-planner` agent). If none is present, tell the user to generate one first with that agent and stop.
- **A file path** (ends in `.md`, or is readable) → `Read` the file and parse the scenario list from it.
- **A feature description** (free-form text) → do not guess scenarios. Tell the user: *"Generate a scenario list first with the tdd-scenario-planner agent, then re-invoke /tdd-run."* and stop.

The list must follow the format produced by `tdd-scenario-planner`: numbered items, each with a "When … then …" sentence and `Drives` / `Strategy` / optional `Refactor after` fields.

## Steps

### 1. Acquire and parse the scenario list

Locate the list per the Input rules above. Parse each entry into:

- `n` — sequence number
- `name` — short scenario name
- `sentence` — the "When … then …" behavior
- `drives` — what production code this forces
- `strategy` — `Fake It` | `Triangulate` | `Obvious Implementation`
- `refactor_after` — optional refactor note

If parsing fails for any entry, show the offending item and ask the user to fix the list or clarify.

### 2. Discover the project's build and test workflow

**Treat the project's own declared workflow as authoritative.** Do not jump to language defaults (`pytest`, `go test ./...`, `cargo test`, etc.) without first checking these sources, in order:

1. **Project docs** — read, if they exist:
   - `CLAUDE.md` (root and nested) — often documents the exact test/build commands this project uses.
   - `README.md` — look for "Testing", "Development", "Contributing" sections.
   - `CONTRIBUTING.md`, `DEVELOPMENT.md`, `docs/development*`.
   - `AGENTS.md`, `.cursorrules`, or similar AI-assistant guidance files.

2. **Task runners and wrappers** — prefer these over raw tool invocations when present:
   - `Makefile` targets (`test`, `check`, `ci`, `verify`).
   - `justfile` / `Justfile` recipes.
   - `Taskfile.yml` / `Taskfile.yaml` tasks.
   - `./gradlew` / `gradlew.bat` → use instead of a system-wide `gradle`.
   - `./mvnw` / `mvnw.cmd` → use instead of a system-wide `mvn`.
   - `bin/test`, `script/test`, `scripts/test*`, or similar repo-local scripts.
   - Workspace scripts: `package.json` → `scripts.test` (and related `test:*`, `lint`, `typecheck` used in CI).

3. **Package-manager-specific invocation** — respect the declared manager:
   - Node: `package.json` + lockfile tells you the manager.
     - `package-lock.json` → `npm test` / `npm run <script>`
     - `yarn.lock` → `yarn test` / `yarn <script>`
     - `pnpm-lock.yaml` → `pnpm test` / `pnpm <script>`
     - `bun.lockb` → `bun test` or `bun run <script>`
   - Python: if `poetry.lock` → `poetry run pytest`; if `pdm.lock` → `pdm run pytest`; if `uv.lock` → `uv run pytest`; if `tox.ini` / `noxfile.py` present and used by CI → `tox` / `nox`; if `pipenv` → `pipenv run pytest`; if none → `pytest` directly (or `python -m pytest` in a venv).
   - Ruby: `Gemfile` present → `bundle exec rspec` / `bundle exec rake test`.
   - Rust: `cargo test`; respect `Cargo.toml` workspace structure.
   - .NET: `dotnet test` (scope to a test project if the solution has many).
   - Elixir: `mix test`.
   - Swift: `swift test` for SwiftPM; `xcodebuild test ...` only if the project is Xcode-only.
   - Dart/Flutter: `flutter test` if `pubspec.yaml` has Flutter deps, else `dart test`.
   - Go: `go test ./...` — but if the repo uses `gotestsum`, `mage`, or a Makefile wrapper, use that.

4. **CI configuration** — this is the closest thing to an authoritative answer about what "green" means:
   - `.github/workflows/*.yml` — find the job that runs tests; its steps reveal the real command, including any prerequisite steps (install, codegen, migrations).
   - `.circleci/config.yml`, `.gitlab-ci.yml`, `azure-pipelines.yml`, `Jenkinsfile`, `buildkite.yml`.
   - If CI runs multiple quality gates (tests + lint + typecheck + format check), note them — they matter in step 5d.

5. **Pre-commit and pre-push hooks** — check `.pre-commit-config.yaml`, `.husky/`, `lefthook.yml`, `.git/hooks/`, `package.json` → `husky`/`lint-staged`. Whatever the project gates on locally must stay green too.

6. **Framework signals within source code** — confirm the test framework by reading an existing test file (see step 3 below), not just by manifest dependencies. A project may have `jest` in `devDependencies` but actually run `vitest` now.

If multiple plausible workflows exist, or the project has no declared workflow and no existing tests, **ask the user** — do not guess.

### 3. Study how this project writes tests

Glob for existing test files in the style the project actually uses. Read one or two near the code you will modify, and extract:

- **Location and naming** — e.g. Go `*_test.go` next to source, Python `tests/` top-level vs `test_*.py` alongside, Node `__tests__/` vs `*.test.ts` colocated, Java `src/test/java/...`, Rust inline `#[cfg(test)] mod tests` vs `tests/`.
- **Imports / preamble** — what the project pulls in for each test (framework, helpers, test doubles).
- **Assertion idioms** — the project's own style: `assertThat(...).isEqualTo(...)` (AssertJ), `expect(x).toBe(y)` (jest/vitest), `assert x == y` (pytest), table-driven `for _, tt := range tests` in Go, `describe/it` vs `test()`, `@Test` with JUnit 5 vs 4.
- **Test double / mocking library** — Mockito, Jest mocks, `unittest.mock`, `testify/mock`, RSpec doubles, Sinon, etc. Use whatever is already in the project.
- **Fixtures / setup / teardown** — pytest fixtures, `beforeEach`, `@BeforeEach`, `before(:each)`, Go `t.Cleanup`, etc.
- **Custom helpers** — project-specific factories, builders, matchers, test utilities. Prefer them to inventing new ones.
- **Parametrization style** — pytest `@pytest.mark.parametrize`, Jest `test.each`, Go table tests, JUnit `@ParameterizedTest`.

If no test files exist, confirm with the user: framework choice, directory layout, and whether the detected test command will actually work. Do not invent a layout silently.

### 4. Confirm the plan with the user

Before running any scenario, print a compact preamble:

```
TDD run
  Scenarios:    12
  Stack:        Node / TypeScript
  Manager:      pnpm (pnpm-lock.yaml)
  Build tool:   vite
  Test runner:  vitest
  Test cmd:     pnpm test           (from package.json scripts.test)
  Also gated:   pnpm typecheck, pnpm lint   (from CI)
  Mirrors:      src/auth/login.test.ts
  Commit:       per scenario? (y/N)
```

Ask in a single message:

1. "Is the detected workflow correct? (y/n — if no, tell me what's off)"
2. "Commit after each green-then-refactor cycle? (y/N)" — default no.

Wait for the user's answer. If they correct any field, re-show the preamble and re-confirm before proceeding.

### 5. Execute the Red → Green → Refactor loop

For each scenario in order, walk every sub-step (5a → 5f) in sequence. The sub-steps are what produce the Red/Green/Refactor signals explained in the intro — fusing two scenarios into one cycle, or skipping a sub-step, collapses those signals and makes later diagnosis guesswork. Small cycles are the point: they keep the blast radius of any failure to the last few lines you touched.

#### 5a. Announce

```
── Scenario N/TOTAL: <name> ──
When … then …   (strategy: <Fake It | Triangulate | Obvious Implementation>)
```

#### 5b. Red — write exactly one failing test

1. Write **one** test case using the project's conventions (location, naming, imports, assertion idiom, helpers, mocking library) — mirrored from the neighbor test file identified in step 3. Encode the scenario's literal example values.
2. Sanity-check before running:
   - It asserts exactly the observable outcome in the scenario — nothing more.
   - It depends on no state from prior scenarios.
   - It would fail against an empty/no-op implementation.
3. Run the test, scoped narrowly when the runner supports it — **using the project's wrapper**, not a generic command:
   - `pnpm vitest run path -t "name"` / `npm test -- -t "name"` / `yarn jest path -t "name"`
   - `poetry run pytest path::test_name` / `pytest path::test_name` / `tox -e py -- path::test_name`
   - `go test -run TestName ./pkg`
   - `cargo test test_name`
   - `./gradlew test --tests "ClassName.testName"` / `./mvnw test -Dtest=ClassName#testName`
   - `bundle exec rspec path -e "name"`
   - `dotnet test --filter FullyQualifiedName~TestName`
4. **Verify it fails** — and for the expected reason:
   - Missing symbol/function → OK, proceed to Green.
   - Assertion mismatch → OK, proceed to Green.
   - Compile/type error when the symbol was supposed to already exist → fix the test, do not proceed.
   - **Test passes unexpectedly** → stop. Either the scenario is not falsifiable, existing code already satisfies it, or the harness is broken. Report and ask the user.

#### 5c. Green — write the minimum production code

1. Apply the scenario's `strategy`:
   - **Fake It** → return a hard-coded constant matching the expected outcome. Valid only because the next scenario is a Triangulate that breaks the fake.
   - **Triangulate** → generalize the previous fake just enough that both scenarios pass. Do not over-generalize.
   - **Obvious Implementation** → write the straightforward real implementation, kept small.
2. Run the **project's full test command** (step 2's authoritative command, not just the scoped test). If the project gates additional checks in CI (typecheck, lint, format), run those too when they're cheap and the project treats them as part of "green".
3. **Verify**: the new test passes **and** every pre-existing test still passes. If a pre-existing test regresses, treat that as real information — either the scenario's change broke existing behavior, or the scenario genuinely requires updating the old test. Stop and let the user decide which. Loosening or deleting the test to reach green would hide a real defect under a green bar, which is the exact failure mode TDD is meant to prevent.

#### 5d. Refactor — improve without changing behavior

1. Apply the scenario's `refactor_after` note if present.
2. Independently, look for:
   - Duplication introduced this cycle (Rule of Three: extract on the third instance, not the second).
   - Misleading or stale names.
   - Dead code or unused parameters.
   - Obvious simplifications.
3. Re-run the project's full test command. Must stay green. Re-run any other CI gates the project enforces locally (typecheck, lint) if they're cheap.
4. If nothing meaningful appeared this cycle, say "refactor: none needed" and move on. Inventing a refactor out of nothing introduces churn and can mask real design pressure the next scenario was supposed to surface — the Refactor step earns its place only when it removes something actually there (duplication, a misleading name, dead code).

#### 5e. Commit (only if the user said yes in step 4)

Create a commit. Follow the repo's existing commit-message style — inspect recent `git log` first. If the project uses Conventional Commits, use:

```
test(tdd): scenario N/TOTAL — <scenario name>
```

Otherwise use a plain subject that matches the repo's prevailing style. Include the scenario's "When … then …" sentence and the strategy in the body.

#### 5f. Report one line

```
✓ Scenario N — red OK, green OK, refactor: <one-line summary or "none needed">
```

Continue to scenario N+1.

### 6. Pause, resume, and stop conditions

- **Natural pause points:** after each scenario completes, before announcing the next. On interruption, resume from the next unfinished scenario.
- **Hard stops** (stop and ask the user; do not proceed on your own):
  - Red step: a test passes unexpectedly.
  - Green step: a pre-existing test regresses, or the minimum change would ripple far beyond this scenario's `drives`.
  - Refactor step: tests go red and the fix isn't a trivial mechanical correction of the refactor.
  - The scenario references a collaborator that doesn't yet exist — ask whether to introduce it with a test double, defer the scenario, or reshape the plan.
  - A scenario turns out to be a duplicate of one already passing — ask whether to drop it from the list.
  - The project's authoritative test command fails for infrastructure reasons (missing deps, failed codegen, missing env var) — stop and surface it; don't paper over it.

### 7. Final report

After the last scenario (or when the user stops the run):

```
TDD run complete
  Scenarios implemented: X/TOTAL
  Scenarios skipped:     Y  (reasons inline)
  Refactors applied:     Z
  Commits created:       C  (if per-scenario commits were enabled)
  Workflow used:         <the project's own test command>   →   all green
```

If any scenarios were deferred or skipped, list them with one-line reasons.

## Principles behind the rules

Every rule above exists because violating it breaks one of the TDD signals. Short form of the *why* for each:

- **Tests before production code.** A test written after the code passes trivially — it proves nothing about whether the code will catch a regression. Writing the failing test first and watching it fail is how you know the test has teeth.
- **One scenario per cycle.** Two scenarios in one cycle means the Green change covered two behaviors at once, and you can no longer attribute a later failure to a specific code path. Small cycles keep diagnosis cheap.
- **Pre-existing tests stay green.** A regressing pre-existing test is information — silencing it (by loosening or deleting) hides a real defect under a green bar, which is exactly what TDD is meant to prevent. Stop and surface it.
- **No speculative refactors.** The Refactor step capitalizes on pressure that appeared this cycle. Invented refactors add churn and can mask real pressure that the next scenario was supposed to surface. "None needed" is a valid outcome.
- **Project's own test command.** When a project declares its own runner (gradle wrapper, npm script, Makefile target, `mix test` over a bare `elixir`), it's usually because the generic invocation is wrong — missing env setup, codegen, or path config. A generic command can print green locally and still disagree with CI.
- **CI-declared gates count as "green".** If the project's CI treats typecheck/lint/format as blocking, then a cycle that passes tests but breaks the typechecker is not actually green — it would fail the first time the user pushes.
- **Mirror existing test style.** A new test that doesn't match the project's conventions (JUnit 4 vs 5, jest vs vitest, table-driven Go, RSpec describe/context) fragments the suite. Consistency is a maintenance cost that compounds.
