# Nutrition Engine V2 Shadow Runtime

## Ownership and Lifecycle

`nutrition_engine.shadow_hook` owns one lazy `ThreadPoolExecutor` in each
application worker process. It creates the executor only after validating its
fixed one-worker configuration, admission capacity, timeout configuration, and
telemetry state. The executor is process-local; request handlers never own or
retain it.

`shutdown_runtime()` closes admission, cancels queued work, releases every
cancelled task permit, and joins the running worker. It is registered with
`atexit` and is idempotent. A closed runtime cannot create another executor in
the same process. A fresh process owns a fresh runtime after a reload.

## Queue and Timeout Policy

At most two tasks are admitted: one executing and one queued. Admission uses a
non-blocking semaphore. A third task is dropped immediately and never runs in
the request thread.

Each admitted task receives a 750 ms monotonic deadline. The isolated service
and optimizer cooperatively check that deadline throughout catalog resolution,
candidate construction, optimization, quality, assembly, and projection. A
deadline expiry returns the typed `timeout` outcome, never a partial plan. The
task's `finally` block always updates telemetry and releases its permit.

The runtime records a stall when a completed task reaches 500 ms. A stalled
task remains isolated from delivery; it is only an in-memory operational signal.

## Telemetry and Logging

Telemetry is process-local, bounded, and contains no identity, profile,
conversation, food name, source identifier, or model content. It tracks:

- eligibility, skips, dispatches, drops, completions, timeouts, exceptions;
- internal fail-closed, optimizer, catalog, and quality failures;
- current and maximum inflight work and queue depth;
- longest duration, stalls, initialization failures, and shutdown cancellations.

Successful execution is silent. Unexpected hook, dispatch, or worker failures
emit a compact structured warning with the `nutrition-v2-shadow` prefix, event,
reason, exception type, and process worker identifier. Shadow telemetry is not
persisted and has no user-facing endpoint.

## Failure Model

The hook receives only an immutable typed target projection. It has no Flask,
database, LLM, HTTP, SSE, quota, voice, persistence, or user-interface access.
All shadow output is discarded in production. A failure in initialization,
dispatch, service execution, timeout handling, or projection cannot change the
canonical `/chat` response.
