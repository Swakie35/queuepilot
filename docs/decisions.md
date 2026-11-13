# Design notes — queuepilot

**Why this exists.** A SQLite-backed job queue with leases, idempotency, retries and dead-letter handling.

The default implementation is intentionally self-contained so reviewers can run it without private services, paid accounts or unpublished data. The README names its limitations; this project is an engineering reference, not a claim about production deployment.
