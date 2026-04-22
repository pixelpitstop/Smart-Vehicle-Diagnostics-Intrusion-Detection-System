# CANInsight Realtime

CANInsight Realtime is a streaming-first Phase 2 system for vehicle telemetry intelligence.

It extends the Phase 1 architecture into a production-style realtime pipeline:

RAW CAN FRAME -> CONFIG-DRIVEN DECODE -> STATE UPDATE -> HYBRID DETECTION -> INSIGHT EVENT -> LIVE DASHBOARD

## Step 1 Retrospective (What I identified as flaws)

During Step 1 implementation, I reviewed the running system and documented the key flaws that must be fixed to make Phase 2 production-ready:

1. Log write scalability flaw
- Processed events were written as a full JSON array rewrite per message.
- This caused O(n) disk work for each event and created long-run performance risk.

2. Startup/runtime path fragility
- Consumer and dashboard behavior depended on where commands were launched from.
- Relative paths created runtime failures (missing config/log paths) when started outside project root.

3. Dashboard API deprecation debt
- Streamlit was emitting repeated deprecation warnings for use_container_width.
- This risks breakage and noisy logs during demos/ops.

4. Weak test coverage baseline
- Core decode/process behavior had no automated tests.
- Regression risk was high for future refactors.

These are now treated as the official Step-1 findings and Phase-2 hardening targets.

## Phase 2 Hardening Plan (Implemented)

### 1) Scalable stream log format
- Migrated event logging from JSON array rewrite to append-only JSONL.
- Each processed event is now written as one line, reducing write complexity to O(1) per event.

Implemented in:
- core/processor.py
- streaming/consumer.py

### 2) Deterministic startup and pathing
- Consumer defaults now resolve from project-root absolute paths.
- Dashboard default log path is project-root based.
- Added a one-command dual-service launcher for industry-style operation.

Implemented in:
- streaming/consumer.py
- dashboard/app.py
- run_phase2.py

### 3) Dashboard resilience and performance
- Added JSONL tail-loading with backward compatibility for legacy JSON-array logs.
- Added event normalization and safer dataframe handling.
- Added summary metrics section for quick situational awareness.

Implemented in:
- dashboard/app.py

### 4) Streamlit deprecation cleanup
- Replaced use_container_width with width="stretch" where applicable.
- Removed warning spam and aligned with future Streamlit behavior.

Implemented in:
- dashboard/app.py

### 5) Baseline automated tests
- Added tests for decoder output shape and value extraction.
- Added processor JSONL write-path test to validate event emission.

Implemented in:
- tests/test_decoder.py
- tests/test_processor_jsonl.py
- requirements-dev.txt

## Project Layout

```text
caninsight-realtime/
├── streaming/
│   ├── producer.py
│   └── consumer.py
├── core/
│   ├── decoder.py
│   ├── processor.py
│   └── state.py
├── detection/
│   ├── rules.py
│   ├── statistical.py
│   └── ml_model.py
├── config/
│   └── signals.json
├── dashboard/
│   └── app.py
├── logs/
│   ├── stream_events.jsonl
│   └── stream_events.json
├── tests/
│   ├── test_decoder.py
│   └── test_processor_jsonl.py
├── run_phase2.py
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

## Runtime Features

- Real-time message production and consumption
- Config-driven signal decoding via JSON mapping
- Stateful rolling-window processing
- Hybrid anomaly detection:
  - rules (overheating, RPM spikes, harsh braking, aggressive acceleration)
  - statistical z-score anomalies
  - optional IsolationForest detector
- Unified alert schema and risk scoring
- Live Streamlit dashboard with auto-refresh
- Append-only JSONL stream event logging

## Quick Start

### 1) Install runtime dependencies

```bash
pip install -r requirements.txt
```

### 2) Run both stream + dashboard together (recommended)

```bash
python run_phase2.py --reset-log --hz 8 --port 8501
```

Dashboard URL:
- http://localhost:8501

### 3) Run services separately (optional)

Consumer:

```bash
python -m streaming.consumer --reset-log --hz 8
```

Dashboard:

```bash
streamlit run dashboard/app.py
```

## Tests

### Install dev dependencies

```bash
pip install -r requirements-dev.txt
```

### Run tests

```bash
pytest -q
```

## Config-Driven Decoding

The decoder uses config/signals.json, so adding a new signal only requires config updates.

Example:

```json
{
  "rpm": {"bytes": [0, 1], "scale": 0.25},
  "speed_kph": {"bytes": [3]},
  "engine_temp_c": {"bytes": [4], "offset": -40}
}
```

## Stream Event Output (JSONL)

Each processed line in logs/stream_events.jsonl is a complete event object:

```json
{"timestamp":"2026-04-22T10:41:22.091Z","can_id":"0x100","payload":"0E FE 18 00 76 00 00 00","signals":{"rpm":1325.0,"speed_kph":42.0,"engine_temp_c":92.0},"alerts":[],"risk_level":"low"}
```

## Notes

- This implementation is streaming-first by design.
- Batch-style analysis can still be supported by replaying historical messages through core/processor.py.
- Kafka integration can be added by replacing in-memory queue transport in streaming/producer.py and streaming/consumer.py while retaining the same processor contract.
