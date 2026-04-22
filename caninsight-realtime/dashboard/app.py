from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH_DEFAULT = PROJECT_ROOT / "logs" / "stream_events.jsonl"


def _parse_jsonl_events(path: Path, max_events: int) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as fp:
        lines = fp.readlines()

    for raw in lines[-max_events:]:
        text = raw.strip()
        if not text:
            continue
        try:
            item = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


@st.cache_data(ttl=1)
def load_events(path: Path, max_events: int = 3000) -> list[dict]:
    if not path.exists():
        return []

    # Backward compatibility with old JSON array logs.
    first_char = path.read_text(encoding="utf-8")[:1]
    if first_char == "[":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return payload[-max_events:]
        return []

    return _parse_jsonl_events(path, max_events=max_events)


def parse_log_path(user_input: str) -> Path:
    candidate = Path(user_input)
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate


def available_log_paths() -> list[str]:
    return [
        str(LOG_PATH_DEFAULT),
        str(PROJECT_ROOT / "logs" / "stream_events.json"),
    ]


def _normalize_events(events: list[dict]) -> list[dict]:
    return [item for item in events if isinstance(item, dict) and "signals" in item]


def _risk_rank(level: str) -> int:
    ranks = {"low": 0, "medium": 1, "high": 2}
    return ranks.get(level, 0)


def compute_summary(events: list[dict]) -> dict:
    if not events:
        return {"total": 0, "alerts": 0, "high_risk": 0}

    total_alerts = sum(len(item.get("alerts", [])) for item in events)
    high_risk_events = sum(1 for item in events if _risk_rank(str(item.get("risk_level", "low"))) >= 2)
    return {
        "total": len(events),
        "alerts": total_alerts,
        "high_risk": high_risk_events,
    }


def safe_metric(df: pd.DataFrame, col: str, default: float = 0.0) -> float:
    if col not in df.columns or df[col].empty:
        return default
    return float(df[col].max())


def validate_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    expected_cols = ["speed_kph", "rpm", "engine_temp_c"]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = 0.0
    return df


def chart_width() -> str:
    return "stretch"


def table_width() -> str:
    return "stretch"


def render_summary(events: list[dict]) -> None:
    summary = compute_summary(events)
    s1, s2, s3 = st.columns(3)
    s1.metric("Events", summary["total"])
    s2.metric("Alerts", summary["alerts"])
    s3.metric("High Risk Events", summary["high_risk"])


def handle_no_events() -> None:
    st.warning("No stream events found. Run: python -m streaming.consumer --reset-log")
    st.stop()


def parse_mode(mode_input: str) -> str:
    return "Batch Snapshot" if mode_input == "Batch Snapshot" else "Live"


def resolve_batch_limit(events: list[dict]) -> int:
    return min(200, len(events))


def apply_batch_window(events: list[dict], mode_value: str) -> list[dict]:
    if mode_value != "Batch Snapshot":
        return events

    max_rows = max(100, len(events))
    default_rows = resolve_batch_limit(events)
    limit = st.slider("Rows", min_value=50, max_value=max_rows, value=default_rows)
    return events[-limit:]


def line_chart_safe(chart_df: pd.DataFrame, columns: list[str]) -> None:
    present_cols = [col for col in columns if col in chart_df.columns]
    if not present_cols:
        return
    st.line_chart(chart_df[present_cols], width=chart_width())


def parse_sidebar_log_path(default_path: Path) -> Path:
    selected = st.selectbox("Log Source", options=available_log_paths(), index=0)
    typed = st.text_input("Stream event log path", selected)
    return parse_log_path(typed) if typed else default_path


def normalize_mode_input() -> str:
    selected_mode = st.selectbox("Mode", ["Live", "Batch Snapshot"], index=0)
    return parse_mode(selected_mode)


def maybe_autorefresh(mode_value: str) -> None:
    if mode_value == "Live":
        st_autorefresh(interval=2000, key="live-refresh")


def build_dataframe(events: list[dict]) -> pd.DataFrame:
    rows = []
    for item in events:
        signals = item.get("signals", {})
        row = {
            "timestamp": item.get("timestamp"),
            "risk_level": item.get("risk_level", "low"),
            "alert_count": len(item.get("alerts", [])),
        }
        row.update(signals)
        rows.append(row)

    df = pd.DataFrame(rows)
    if not df.empty and "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.sort_values("timestamp")
    return df


def extract_alerts(events: list[dict]) -> pd.DataFrame:
    rows = []
    for item in events:
        for alert in item.get("alerts", []):
            rows.append(
                {
                    "timestamp": alert.get("timestamp"),
                    "severity": alert.get("severity"),
                    "category": alert.get("category"),
                    "source": alert.get("source"),
                    "message": alert.get("message"),
                }
            )

    df = pd.DataFrame(rows)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.sort_values("timestamp", ascending=False)
    return df


def _risk_color(risk: str) -> str:
    mapping = {
        "low": "#2e7d32",
        "medium": "#ed6c02",
        "high": "#d32f2f",
    }
    return mapping.get(risk, "#455a64")


def render_kpis(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No events processed yet. Start the consumer stream first.")
        return

    latest = df.iloc[-1]
    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Max Speed (kph)", f"{safe_metric(df, 'speed_kph'):.1f}")
    col2.metric("Max RPM", f"{safe_metric(df, 'rpm'):.0f}")
    col3.metric("Max Temp (C)", f"{safe_metric(df, 'engine_temp_c'):.1f}")
    col4.markdown(
        f"<div style='padding:0.5rem;border-radius:0.5rem;background:{_risk_color(str(latest['risk_level']))};color:white;text-align:center;font-weight:600;'>"
        f"Current Risk: {str(latest['risk_level']).upper()}"
        "</div>",
        unsafe_allow_html=True,
    )


def render_charts(df: pd.DataFrame) -> None:
    st.subheader("Realtime Telemetry")
    chart_df = df.set_index("timestamp")

    line_chart_safe(chart_df, ["speed_kph"])
    line_chart_safe(chart_df, ["rpm"])
    line_chart_safe(chart_df, ["engine_temp_c"])


def render_alerts(events: list[dict]) -> None:
    alerts_df = extract_alerts(events)
    st.subheader("Alerts")
    if alerts_df.empty:
        st.success("No alerts detected in current window.")
        return

    st.dataframe(alerts_df.head(50), width=table_width())


def build_and_validate(events: list[dict]) -> pd.DataFrame:
    return validate_dataframe(build_dataframe(events))


def main() -> None:
    st.set_page_config(page_title="CANInsight Realtime", layout="wide")
    st.title("CANInsight Realtime: Vehicle Telemetry Streaming & Intelligence")

    with st.sidebar:
        mode = normalize_mode_input()
        log_path = parse_sidebar_log_path(LOG_PATH_DEFAULT)
        maybe_autorefresh(mode)

    events = _normalize_events(load_events(log_path))
    if not events:
        handle_no_events()

    events = apply_batch_window(events, mode)

    render_summary(events)
    df_events = build_and_validate(events)
    render_kpis(df_events)
    if not df_events.empty:
        render_charts(df_events)
    render_alerts(events)

    if not df_events.empty:
        st.subheader("Recent Samples")
        st.dataframe(df_events.tail(30), width=table_width())


if __name__ == "__main__":
    main()
