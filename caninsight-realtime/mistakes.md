# Mistakes and Difficulties

## Step 1 Retrospective

During Step 1 implementation, I reviewed the running system and documented the main flaws that had to be fixed to make Phase 2 production-ready:

1. Log write scalability flaw
- Processed events were written as a full JSON array rewrite per message.
- This caused O(n) disk work for each event and created long-run performance risk.

2. Startup/runtime path fragility
- Consumer and dashboard behavior depended on where commands were launched from.
- Relative paths created runtime failures (missing config/log paths) when started outside project root.

3. Dashboard API deprecation debt
- Streamlit was emitting repeated deprecation warnings for use_container_width.
- This risked breakage and noisy logs during demos/ops.

4. Weak test coverage baseline
- Core decode/process behavior had no automated tests.
- Regression risk was high for future refactors.

These became the Phase 2 hardening targets.

## Runtime log tracking

- Mistake: Runtime stream logs (`stream_events.json`, `stream_events.jsonl`) were tracked in Git during active testing.
- Difficulty caused: repository growth, noisy commits, and avoidable deployment friction.
- Resolution: moved default runtime log path to `.runtime/stream_events.jsonl`, added ignore rules for generated logs, and stopped tracking historical runtime log files.
- Lesson: keep only code, config, and documentation under version control; keep runtime artifacts untracked.

## Architecture sprawl

- Mistake: I introduced a standalone dashboard spinoff that only read log files.
- Difficulty caused: it added a second deploy surface without fixing the real-time path, and the UI could become stagnant if the consumer was not running.
- Resolution: collapsed back to the integrated Phase 2 repo and removed the spinoff.
- Lesson: prefer one reliable end-to-end path before splitting deployment surfaces.
