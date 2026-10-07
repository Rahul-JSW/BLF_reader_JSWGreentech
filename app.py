import streamlit as st
import pandas as pd
import numpy as np
import cantools
import can
import tempfile
from pathlib import Path
import os
import plotly.graph_objects as go

st.set_page_config(
    page_title="Vehicle CAN Data Analyzer",
    page_icon="🔋",
    layout="wide",
)

st.title("🚗 Vehicle CAN Data Analyzer")
st.caption("DBC + BLF based signal extraction and visualization")

# -----------------------------
# Helper functions
# -----------------------------
@st.cache_resource(show_spinner=False)
def load_dbc(dbc_bytes: bytes, dbc_name: str):
    """Load a DBC database from uploaded bytes."""
    suffix = Path(dbc_name).suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix or ".dbc") as f:
        f.write(dbc_bytes)
        dbc_path = f.name

    try:
        return cantools.database.load_file(dbc_path)
    finally:
        try:
            os.remove(dbc_path)
        except OSError:
            pass


def decode_blf(blf_bytes: bytes, db):
    """
    Decode BLF CAN messages using the supplied DBC.

    Returns:
        decoded_df: one row per decoded signal sample
        message_df: raw CAN message summary
        stats: decoding statistics
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=".blf") as f:
        f.write(blf_bytes)
        blf_path = f.name

    decoded_rows = []
    message_rows = []

    total_messages = 0
    decoded_messages = 0
    undecoded_messages = 0
    non_can_messages = 0

    try:
        reader = can.BLFReader(blf_path)

        for msg in reader:
            if not isinstance(msg, can.Message):
                continue

            non_can_messages += 1

            if msg.is_error_frame:
                continue

            total_messages += 1

            arbitration_id = int(msg.arbitration_id)
            timestamp = float(msg.timestamp)

            try:
                message = db.get_message_by_frame_id(arbitration_id)
            except KeyError:
                message = None

            message_rows.append(
                {
                    "Timestamp [s]": timestamp,
                    "CAN ID": f"0x{arbitration_id:X}",
                    "CAN ID Decimal": arbitration_id,
                    "DLC": msg.dlc,
                    "Message": message.name if message else "Unknown",
                    "Data": " ".join(f"{b:02X}" for b in msg.data),
                }
            )

            if message is None:
                undecoded_messages += 1
                continue

            try:
                decoded = message.decode(
                    bytes(msg.data),
                    decode_choices=False,
                    scaling=True,
                )
            except Exception:
                undecoded_messages += 1
                continue

            decoded_messages += 1

            for signal_name, value in decoded.items():
                if isinstance(value, (list, tuple, np.ndarray)):
                    # Multiplexed/array signals are stored as text for MVP.
                    value = str(value)

                decoded_rows.append(
                    {
                        "Timestamp [s]": timestamp,
                        "CAN ID": f"0x{arbitration_id:X}",
                        "Message": message.name,
                        "Signal": signal_name,
                        "Value": value,
                    }
                )

    finally:
        try:
            os.remove(blf_path)
        except OSError:
            pass

    decoded_df = pd.DataFrame(decoded_rows)
    message_df = pd.DataFrame(message_rows)

    if not decoded_df.empty:
        decoded_df = decoded_df.sort_values(
            ["Signal", "Timestamp [s]"]
        ).reset_index(drop=True)

    if not message_df.empty:
        message_df = message_df.sort_values(
            "Timestamp [s]"
        ).reset_index(drop=True)

    stats = {
        "total_messages": total_messages,
        "decoded_messages": decoded_messages,
        "undecoded_messages": undecoded_messages,
        "non_can_messages": non_can_messages,
        "decoded_signal_samples": len(decoded_df),
    }

    return decoded_df, message_df, stats


def make_signal_summary(decoded_df: pd.DataFrame):
    if decoded_df.empty:
        return pd.DataFrame()

    rows = []
    for signal, group in decoded_df.groupby("Signal", sort=True):
        values = pd.to_numeric(group["Value"], errors="coerce").dropna()

        rows.append(
            {
                "Signal": signal,
                "Message": group["Message"].iloc[0],
                "CAN ID": group["CAN ID"].iloc[0],
                "Samples": len(group),
                "Start Time [s]": group["Timestamp [s]"].min(),
                "End Time [s]": group["Timestamp [s]"].max(),
                "Min": values.min() if not values.empty else np.nan,
                "Max": values.max() if not values.empty else np.nan,
                "Mean": values.mean() if not values.empty else np.nan,
            }
        )

    return pd.DataFrame(rows)


# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    st.header("Input Files")

    dbc_file = st.file_uploader(
        "Upload DBC file",
        type=["dbc"],
        help="CAN database containing message and signal definitions.",
    )

    blf_file = st.file_uploader(
        "Upload BLF file",
        type=["blf"],
        help="Vector Binary Logging Format containing recorded CAN traffic.",
    )

    st.divider()

    st.header("Analysis Options")
    start_time = st.number_input(
        "Start time [s]",
        min_value=0.0,
        value=0.0,
        step=0.1,
    )

    end_time = st.number_input(
        "End time [s]",
        min_value=0.0,
        value=0.0,
        step=0.1,
        help="Set to 0 to use the complete BLF duration.",
    )

    st.divider()
    st.caption("MVP: DBC decoding + signal browsing + plotting")


# -----------------------------
# Main workflow
# -----------------------------
if dbc_file is None or blf_file is None:
    st.info(
        "Upload both a **.dbc** file and a **.blf** file from the sidebar to begin."
    )

    st.markdown(
        """
### Tool workflow

**1. Upload DBC**

Contains:
- CAN IDs
- Message names
- Signal names
- Start bit / length
- Byte order
- Signed/unsigned information
- Scaling factor
- Offset
- Units

**2. Upload BLF**

Contains the recorded CAN frames.

**3. Decode**

The application matches each BLF CAN ID against the DBC and converts raw bytes into engineering values.

**4. Analyze**

Select a signal and visualize:

`Time → Signal Value`

Example:

`VehicleSpeed → km/h`

`SOC → %`

`PackVoltage → V`

`PackCurrent → A`

`CellVoltage_01 → V`
        """
    )

    st.stop()


# Load DBC
try:
    with st.spinner("Loading DBC..."):
        db = load_dbc(dbc_file.getvalue(), dbc_file.name)
except Exception as e:
    st.error(f"Unable to load DBC: {e}")
    st.stop()


# DBC information
with st.expander("DBC Information", expanded=False):
    dbc_messages = list(db.messages)

    col1, col2, col3 = st.columns(3)
    col1.metric("Messages", len(dbc_messages))
    col2.metric(
        "Signals",
        sum(len(m.signals) for m in dbc_messages),
    )
    col3.metric(
        "Nodes",
        len(db.nodes),
    )

    dbc_rows = []
    for msg in dbc_messages:
        for sig in msg.signals:
            dbc_rows.append(
                {
                    "CAN ID": f"0x{msg.frame_id:X}",
                    "Message": msg.name,
                    "Signal": sig.name,
                    "Start Bit": sig.start,
                    "Length": sig.length,
                    "Byte Order": sig.byte_order,
                    "Signed": sig.is_signed,
                    "Factor": sig.scale,
                    "Offset": sig.offset,
                    "Unit": sig.unit or "",
                }
            )

    st.dataframe(
        pd.DataFrame(dbc_rows),
        use_container_width=True,
        hide_index=True,
    )


# Decode BLF
cache_key = f"{dbc_file.name}_{dbc_file.size}_{blf_file.name}_{blf_file.size}"

if (
    "decoded_cache_key" not in st.session_state
    or st.session_state.decoded_cache_key != cache_key
):
    with st.spinner("Reading and decoding BLF..."):
        try:
            decoded_df, message_df, stats = decode_blf(
                blf_file.getvalue(),
                db,
            )
        except Exception as e:
            st.error(f"Unable to decode BLF: {e}")
            st.stop()

    st.session_state.decoded_cache_key = cache_key
    st.session_state.decoded_df = decoded_df
    st.session_state.message_df = message_df
    st.session_state.stats = stats
else:
    decoded_df = st.session_state.decoded_df
    message_df = st.session_state.message_df
    stats = st.session_state.stats


# -----------------------------
# Statistics
# -----------------------------
st.header("BLF Analysis")

c1, c2, c3, c4 = st.columns(4)
c1.metric("CAN Messages", f"{stats['total_messages']:,}")
c2.metric("Decoded Messages", f"{stats['decoded_messages']:,}")
c3.metric("Unknown / Undecoded", f"{stats['undecoded_messages']:,}")
c4.metric("Signal Samples", f"{stats['decoded_signal_samples']:,}")


if decoded_df.empty:
    st.warning(
        "No signals were decoded. Check that the DBC matches the CAN IDs and "
        "message formats contained in the BLF."
    )
    st.stop()


# Apply time filter
filtered_df = decoded_df.copy()

if end_time > 0:
    filtered_df = filtered_df[
        (filtered_df["Timestamp [s]"] >= start_time)
        & (filtered_df["Timestamp [s]"] <= end_time)
    ]
else:
    filtered_df = filtered_df[
        filtered_df["Timestamp [s]"] >= start_time
    ]


# -----------------------------
# Signal browser
# -----------------------------
tab1, tab2, tab3, tab4 = st.tabs(
    [
        "📊 Signals",
        "📈 Plot",
        "🚌 CAN Messages",
        "📋 Raw Decoded Data",
    ]
)

with tab1:
    st.subheader("Available Signals")

    summary = make_signal_summary(filtered_df)

    search = st.text_input(
        "Search signal",
        placeholder="e.g. SOC, Voltage, Current, Temperature...",
    )

    if search:
        mask = (
            summary["Signal"].str.contains(search, case=False, na=False)
            | summary["Message"].str.contains(search, case=False, na=False)
            | summary["CAN ID"].str.contains(search, case=False, na=False)
        )
        display_summary = summary[mask]
    else:
        display_summary = summary

    st.write(f"Showing **{len(display_summary)}** signals")

    st.dataframe(
        display_summary,
        use_container_width=True,
        hide_index=True,
    )

with tab2:
    st.subheader("Signal Plot")

    # -----------------------------------------
    # Signal lists
    # -----------------------------------------
    all_signal_names = sorted(
        filtered_df["Signal"].dropna().unique().tolist()
    )

    if not all_signal_names:
        st.warning("No signals available for plotting.")
        st.stop()

    # -----------------------------------------
    # User controls
    # -----------------------------------------
    st.markdown("### Select signals")

    col_primary, col_secondary = st.columns(2)

    with col_primary:
        st.markdown("#### 🟦 Primary Y-axis")

        primary_signals = st.multiselect(
            "Signals on Primary Axis",
            options=all_signal_names,
            default=[],
            max_selections=12,
            key="primary_signals",
            help="Select up to 12 signals for the primary Y-axis.",
        )

    with col_secondary:
        st.markdown("#### 🟧 Secondary Y-axis")

        # Prevent signals already selected on primary axis
        secondary_options = [
            s for s in all_signal_names
            if s not in primary_signals
        ]

        secondary_signals = st.multiselect(
            "Signals on Secondary Axis",
            options=secondary_options,
            default=[],
            max_selections=12,
            key="secondary_signals",
            help="Select up to 12 signals for the secondary Y-axis.",
        )

    # -----------------------------------------
    # Selection summary
    # -----------------------------------------
    total_selected = (
        len(primary_signals) +
        len(secondary_signals)
    )

    st.caption(
        f"Selected: {total_selected}/24 signals "
        f"({len(primary_signals)} primary + "
        f"{len(secondary_signals)} secondary)"
    )

    if total_selected == 0:
        st.info(
            "Select one or more signals from the Primary or Secondary "
            "Y-axis lists to generate the plot."
        )
        st.stop()

    # -----------------------------------------
    # Plot data
    # -----------------------------------------
    primary_df = filtered_df[
        filtered_df["Signal"].isin(primary_signals)
    ].copy()

    secondary_df = filtered_df[
        filtered_df["Signal"].isin(secondary_signals)
    ].copy()

    # Convert values to numeric
    primary_df["Value Numeric"] = pd.to_numeric(
        primary_df["Value"],
        errors="coerce",
    )

    secondary_df["Value Numeric"] = pd.to_numeric(
        secondary_df["Value"],
        errors="coerce",
    )

    primary_df = primary_df.dropna(
        subset=["Value Numeric"]
    )

    secondary_df = secondary_df.dropna(
        subset=["Value Numeric"]
    )

    # -----------------------------------------
    # Create Plotly figure
    # -----------------------------------------
    
    fig = go.Figure()

    # -----------------------------------------
    # Primary Y-axis signals
    # -----------------------------------------
    for signal in primary_signals:

        signal_df = primary_df[
            primary_df["Signal"] == signal
        ].sort_values("Timestamp [s]")

        if signal_df.empty:
            continue

        fig.add_trace(
            go.Scatter(
                x=signal_df["Timestamp [s]"],
                y=signal_df["Value Numeric"],
                mode="lines",
                name=signal,
                yaxis="y",
                hovertemplate=(
                    "<b>%{fullData.name}</b><br>"
                    "Time: %{x:.3f} s<br>"
                    "Value: %{y}<extra></extra>"
                ),
            )
        )

    # -----------------------------------------
    # Secondary Y-axis signals
    # -----------------------------------------
    for signal in secondary_signals:

        signal_df = secondary_df[
            secondary_df["Signal"] == signal
        ].sort_values("Timestamp [s]")

        if signal_df.empty:
            continue

        fig.add_trace(
            go.Scatter(
                x=signal_df["Timestamp [s]"],
                y=signal_df["Value Numeric"],
                mode="lines",
                name=signal,
                yaxis="y2",
                hovertemplate=(
                    "<b>%{fullData.name}</b><br>"
                    "Time: %{x:.3f} s<br>"
                    "Value: %{y}<extra></extra>"
                ),
            )
        )

    # -----------------------------------------
    # Layout
    # -----------------------------------------
    fig.update_layout(
        height=650,

        xaxis=dict(
            title="Time [s]",
            showgrid=True,
            zeroline=False,
        ),

        yaxis=dict(
            title="Primary Y-axis",
            showgrid=True,
            zeroline=False,
            side="left",
        ),

        yaxis2=dict(
            title="Secondary Y-axis",
            overlaying="y",
            side="right",
            showgrid=False,
            zeroline=False,
        ),

        hovermode="x unified",

        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
        ),

        margin=dict(
            l=70,
            r=70,
            t=100,
            b=60,
        ),
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
    )

    # -----------------------------------------
    # Selected signal information
    # -----------------------------------------
    st.markdown("### Selected Signal Information")

    info_rows = []

    for signal in primary_signals:

        temp = filtered_df[
            filtered_df["Signal"] == signal
        ]

        info_rows.append(
            {
                "Axis": "Primary",
                "Signal": signal,
                "Message": (
                    temp["Message"].iloc[0]
                    if not temp.empty else ""
                ),
                "CAN ID": (
                    temp["CAN ID"].iloc[0]
                    if not temp.empty else ""
                ),
                "Samples": len(temp),
            }
        )

    for signal in secondary_signals:

        temp = filtered_df[
            filtered_df["Signal"] == signal
        ]

        info_rows.append(
            {
                "Axis": "Secondary",
                "Signal": signal,
                "Message": (
                    temp["Message"].iloc[0]
                    if not temp.empty else ""
                ),
                "CAN ID": (
                    temp["CAN ID"].iloc[0]
                    if not temp.empty else ""
                ),
                "Samples": len(temp),
            }
        )

    if info_rows:
        st.dataframe(
            pd.DataFrame(info_rows),
            use_container_width=True,
            hide_index=True,
        )

with tab3:
    st.subheader("Decoded CAN Messages")

    message_search = st.text_input(
        "Search CAN ID or message name",
        key="message_search",
    )

    message_display = message_df.copy()

    if message_search:
        mask = (
            message_display["CAN ID"].str.contains(
                message_search,
                case=False,
                na=False,
            )
            | message_display["Message"].str.contains(
                message_search,
                case=False,
                na=False,
            )
        )
        message_display = message_display[mask]

    st.dataframe(
        message_display,
        use_container_width=True,
        hide_index=True,
    )

with tab4:
    st.subheader("Raw Decoded Signal Samples")

    st.dataframe(
        filtered_df,
        use_container_width=True,
        hide_index=True,
    )

    csv = filtered_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "⬇️ Download Decoded Signals CSV",
        data=csv,
        file_name="decoded_signals.csv",
        mime="text/csv",
    )
