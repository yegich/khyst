# Detection tables

How to identify what a project actually uses. **Detect from repo signals — never assume a default because a language usually uses one.** A Python repo with `alembic/` uses Alembic; a Python repo with `migrations/0001_initial.py` uses Django. Both are common. Guessing wrong poisons every downstream claim.

**These tables are a fast path, not an authority. A non-match is never evidence of absence.** Every row is a heuristic keyed on the conventional filename, and projects routinely deviate — a schema file with a non-standard name, a tool invoked only from a script, a wrapper that hides the real command. If nothing here matches but the project clearly *has* the thing, the answer is in the project's own docs and CI config. Go read them, and report what you found rather than reporting `UNKNOWN`.

When two signals conflict, the one referenced by CI is authoritative — CI is the closest thing to a statement of what the project really runs.

---

## Migration tools (lane B2)

**First decide declarative vs versioned, because several tools do both and the commands are unrelated.** A versioned setup has an ordered log of migration files and applies the ones not yet run. A declarative setup has one file describing the *desired* schema, and the tool diffs the live database against it. Look for a migration-log directory: if there isn't one but a schema file exists, the project is declarative.

Getting this backwards is not a small error — a session that assumes versioned mode will go looking for a `migrations/` directory that does not exist and propose adding a numbered migration to a repo that has no such concept.

| Signal | Tool | Mode | How schema changes are applied |
|---|---|---|---|
| `atlas.hcl` or `migrations/atlas.sum` **with** a migration dir | Atlas | versioned | `atlas migrate diff <name>`, then `atlas migrate apply --env <env>` |
| A `*.hcl` file containing `schema`/`table` blocks (commonly `db/schema.hcl`) and **no** migration dir — `atlas.hcl` may be absent entirely | Atlas | declarative | `atlas schema apply --url <db> --to file://<schema.hcl> --dev-url <throwaway db>`; preview with `atlas schema diff` |
| `db/changelog*.xml\|yaml\|json`, `liquibase.properties` | Liquibase | versioned | `liquibase update` |
| `db/migration/V*__*.sql`, `flyway.conf` | Flyway | versioned | `flyway migrate` |
| `alembic.ini`, `alembic/versions/` | Alembic | versioned | `alembic upgrade head` |
| `<app>/migrations/0001_*.py`, `manage.py` | Django | versioned | `./manage.py migrate`; inspect with `showmigrations` |
| `db/migrate/*.rb`, `db/schema.rb` \| `structure.sql` | Rails / ActiveRecord | versioned | `bin/rails db:migrate` |
| `prisma/schema.prisma` **with** `prisma/migrations/` | Prisma | versioned | `prisma migrate deploy` |
| `prisma/schema.prisma`, no `migrations/` | Prisma | declarative | `prisma db push` |
| `drizzle.config.*` **with** `drizzle/` | Drizzle | versioned | `drizzle-kit migrate` |
| `drizzle.config.*`, no migration dir | Drizzle | declarative | `drizzle-kit push` |
| `*.up.sql` + `*.down.sql` pairs, no other config | golang-migrate | `migrate -path ... up` |
| `db/migrations/*.sql` with `-- +goose Up` | goose | `goose up` |
| `ent/schema/`, `ent/migrate/` | Ent | generated; check `ent/generate.go` |
| `src/main/resources/db/migration/` in a Spring project | Flyway (Spring auto-run) | applied at boot — note this, it changes the workflow |
| `knexfile.*`, `migrations/*.js` | Knex | `knex migrate:latest` |
| `supabase/migrations/` | Supabase CLI | `supabase db push` |
| `*.sql` in a `sql/` dir with no ordering scheme | hand-applied | flag as `UNKNOWN` — ask the user |

**Also record for B2:** where the canonical schema lives (a checked-in `schema.sql`/`schema.rb`/`schema.hcl` beats reconstructing it from migration history), whether the schema is generated or hand-written, and whether migrations run automatically on deploy or as a separate step. That last one determines whether a schema change is safe to ship in the same PR as the code that uses it.

**Then ask what the tool does not know.** Projects grow conventions around their migration tool that no signal table can detect, and these are exactly what a session gets wrong:

- **Escape-hatch scripts** for changes the tool cannot express — a directory of hand-written SQL (`db/pre-apply/`, `db/manual/`, `migrations/data/`) that must run *before* or *after* the tool. Declarative setups nearly always have one, because a schema diff cannot express a backfill, a type cast needing `USING`, or dropping an enum value.
- **The populated-table hazard.** Adding a `NOT NULL` column succeeds on an empty database and fails on a live one. If the project's test harness builds a fresh database, that failure reaches production. Find out whether a migration harness exists that seeds rows first, and whether it runs in CI or only locally.
- **Ordering rules** between schema apply and code deploy, and whether either is automatic.

None of this lives in tool config. It lives in `docs/`, a runbook, the CI workflow, or a long comment at the top of the escape-hatch directory. Read them.

Do not run any migration command. Read the files.

---

## ORM / data-access layer (lane B3)

| Signal | Layer | Where the mapping is declared |
|---|---|---|
| `gorm.io/gorm` | GORM | struct tags `gorm:"..."` |
| `entgo.io/ent` | Ent | `ent/schema/*.go` |
| `sqlc.yaml` | sqlc | `query.sql` → generated structs; SQL is the source of truth |
| `jmoiron/sqlx`, `database/sql` only | hand-rolled | scan targets in the repository layer |
| `sqlalchemy` | SQLAlchemy | declarative models or `Table()` definitions |
| `django.db.models` | Django ORM | `models.py` per app |
| `@Entity` + `javax/jakarta.persistence` | JPA / Hibernate | annotations, or `*.hbm.xml` |
| `@Table` + Spring Data | Spring Data JDBC/R2DBC | repository interfaces |
| `ActiveRecord::Base` | ActiveRecord | convention-based; the schema file *is* the mapping |
| `prisma` client | Prisma | `schema.prisma` |
| `typeorm` | TypeORM | `@Entity` decorators |
| `drizzle-orm` | Drizzle | `schema.ts` |
| `sequelize` | Sequelize | `models/` |
| `diesel` | Diesel | `schema.rs` (generated) + `#[derive(Queryable)]` |
| `sqlx` (Rust) | sqlx | compile-time-checked queries; no ORM mapping |

**What B3 must actually answer**, beyond naming the library:

- Is there a domain model *distinct* from the persistence model, or are ORM entities passed straight into business logic? This single fact changes where a change belongs.
- Where does business logic live in practice — service layer, fat models, handlers, or scattered? Report where it *is*, not where the framework says it should be.
- What are the aggregate boundaries — which objects are loaded and saved together, and what's the transaction unit.
- Which relations are lazy-loaded, and where that produces N+1s on a hot path.

---

## Contract types (lane S2)

Identify what actually crosses the boundary. A slice may have several.

### HTTP

| Signal | Framework | Where routes are declared |
|---|---|---|
| `chi`, `gorilla/mux`, `gin`, `echo`, `fiber` | Go routers | router setup in `main.go` / `router.go` |
| `@RestController`, `@RequestMapping` | Spring MVC | annotations |
| `FastAPI()`, `APIRouter` | FastAPI | decorators; OpenAPI is generated |
| `flask`, `blueprint` | Flask | `@app.route` |
| `urls.py`, `DefaultRouter` | Django / DRF | URLconf + serializers |
| `express`, `fastify`, `hono`, `nest` | Node | route registration or `@Controller` |
| `config/routes.rb` | Rails | `bin/rails routes` is authoritative |
| `app/api/**/route.ts` | Next.js | file-system routing |

Prefer a checked-in `openapi.yaml` / `swagger.json` when present, but **verify it matches the handlers** — generated specs go stale when generation isn't wired into CI. Record request shape, response shape, status codes, and error envelope.

### gRPC / protobuf

`*.proto`, `buf.yaml`, `buf.gen.yaml`, `protoc` invocations in a Makefile. Record: service and method, request/response messages with their field types, streaming mode (unary/server/client/bidi), and where the generated code lands. Note whether generated stubs are committed or built — it changes what a contract change requires.

### Async messaging

| Signal | Transport | Contract lives in |
|---|---|---|
| `*.avsc`, Confluent Schema Registry config | Kafka + Avro | the `.avsc` schema; note the compatibility mode |
| `kafka`, `sarama`, `confluent-kafka`, `KafkaListener` | Kafka | topic name + payload struct |
| `sqs`, `@SqsListener`, `boto3.client('sqs')` | SQS | message body shape; check for a dead-letter queue |
| `sns`, `publish(TopicArn=...)` | SNS | message + attributes; note fan-out subscribers |
| `pika`, `amqp`, `@RabbitListener` | RabbitMQ | exchange, routing key, payload |
| `celery`, `sidekiq`, `bullmq`, `river` | job queue | task signature and its arguments |
| `*.proto` used as a message payload | any | the proto message |
| `cloudevents` | any | the CloudEvent envelope + `type` |

**Always record for async:** topic/queue name, payload schema, ordering guarantees, delivery semantics (at-least-once is the default and implies the consumer must be idempotent), retry policy, and the DLQ. Idempotency is the thing sessions most often get wrong here.

### ETL / data pipelines

Signals: `dbt_project.yml`, `dags/*.py` (Airflow), `dagster.yaml`, `models/**/*.sql`, Spark jobs, `*.hql`. Record: source tables, target tables, the transformation as SQL or code, the schedule, incremental vs. full-refresh strategy, and how late/duplicate data is handled.

---

## Cross-cutting concerns (lane B4)

For each, find the mechanism and cite it. `UNKNOWN` is a valid and useful answer — it tells the user the codebase has no consistent approach, which is itself important.

| Concern | What to look for |
|---|---|
| Authentication | middleware, filter chain, decorator; where the identity is put |
| Authorization | policy objects, casbin, Spring Security, per-handler checks, DB row-level security |
| Multi-tenancy | a `tenant_id`/`org_id` on tables, a scoped session, schema-per-tenant. **Find where scoping is enforced and whether it's possible to bypass** |
| Transactions | where `Begin`/`@Transactional`/`with transaction:` sits, nesting rules, whether handlers or services own the boundary |
| Idempotency | idempotency keys, dedup tables, upserts, consumer-side dedup |
| Retries | client config, backoff policy, what is and isn't safe to retry |
| Error handling | error types/wrapping, the HTTP/gRPC error envelope, what leaks to the caller |
| Observability | logger and its required fields, tracing propagation, metric naming |
| Configuration | env vars, config structs, `.env.example`, feature flags and who owns them |
| Caching | cache layer, key scheme, TTLs, invalidation |
| Validation | where input is validated, and whether the domain re-validates |
| Concurrency | locks, advisory locks, optimistic versioning, leader election |

---

## Test layers (lane S3)

Identify the layers and how to run each **in isolation** — a session that can only run the whole suite will avoid running tests at all.

| Signal | Framework | Run a single test |
|---|---|---|
| `*_test.go` | Go | `go test -run TestName ./pkg` |
| `test_*.py`, `conftest.py` | pytest | `pytest path::test_name` |
| `*.test.ts`, `*.spec.ts` | jest / vitest | `vitest run path -t "name"` |
| `src/test/java/**` | JUnit | `./gradlew test --tests "Class.method"` |
| `spec/**/*_spec.rb` | RSpec | `bundle exec rspec path -e "name"` |
| `#[test]`, `tests/` | Rust | `cargo test test_name` |
| `*_test.exs` | ExUnit | `mix test path:line` |

**Also record:**

- **Layers present** — unit, integration, contract (Pact), e2e, snapshot, property-based, load. Which ones actually run in CI vs. exist but are skipped.
- **Fixtures and factories** — factory-boy, FactoryBot, testcontainers, golden files, seeded DBs. A session must reuse these rather than invent new ones.
- **What's faked vs. real** — an integration test hitting a real Postgres via testcontainers means schema changes must land in the test path too.
- **Edge cases the tests encode.** This is the deliverable: the tests state the constraints nobody wrote in prose. Read them and extract the rules.
- **Conspicuous gaps** — an untested branch on the path being changed is a finding worth reporting.

---

## Deployment & runtime (feeds `base/structure.md`)

`Dockerfile`, `docker-compose*.yml`, `k8s/`, `helm/`, `*.tf`, `serverless.yml`, `fly.toml`, `Procfile`, `.github/workflows/*deploy*`.

Record: how it runs locally (the exact command), what external services it needs, required env vars, and where it runs in production. This is what stops a session inventing infrastructure that doesn't exist.
