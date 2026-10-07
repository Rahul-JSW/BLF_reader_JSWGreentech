# Vehicle CAN Data Analyzer

A Streamlit-based web application for decoding vehicle CAN data from:

- DBC files
- BLF files

The application uses:

- Streamlit for the web UI
- python-can for BLF reading
- cantools for DBC parsing and CAN signal decoding
- pandas/numpy for data handling
- Streamlit charts for signal visualization

## 1. Architecture

```text
                    ┌─────────────────────┐
                    │     Streamlit UI    │
                    └──────────┬──────────┘
                               │
                  ┌────────────┴────────────┐
                  │                         │
             Upload DBC                 Upload BLF
                  │                         │
                  ▼                         ▼
          ┌───────────────┐        ┌────────────────┐
          │   cantools    │        │   python-can   │
          │ DBC parser    │        │   BLFReader    │
          └───────┬───────┘        └────────┬───────┘
                  │                         │
                  │ CAN message definitions│ Raw CAN frames
                  └────────────┬────────────┘
                               ▼
                    ┌────────────────────┐
                    │   DBC Decoder      │
                    │                    │
                    │ CAN ID → Message   │
                    │ Message → Signals  │
                    │ Raw → Engineering  │
                    │ Value              │
                    └─────────┬──────────┘
                              ▼
                    ┌────────────────────┐
                    │ Decoded DataFrame  │
                    │                    │
                    │ Time               │
                    │ CAN ID             │
                    │ Message            │
                    │ Signal             │
                    │ Value              │
                    └─────────┬──────────┘
                              ▼
                 ┌──────────────────────────┐
                 │       Analysis UI        │
                 ├──────────────────────────┤
                 │ Signal browser           │
                 │ Signal search            │
                 │ Signal plot              │
                 │ CAN message browser      │
                 │ Raw decoded data         │
                 │ CSV export               │
                 └──────────────────────────┘
```

## 2. Installation

Create a Python virtual environment.

### Windows

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Start the application

```bash
streamlit run app.py
```

The browser will open the Streamlit application.

## 4. Input

Upload:

```text
vehicle.dbc
vehicle.blf
```

The DBC defines how the raw CAN bytes should be interpreted.

The BLF contains the recorded CAN frames.

## 5. Example decoding flow

Suppose the DBC contains:

```text
CAN ID:       0x100
Message:      BMS_Status
Signal:       SOC
Start Bit:    0
Length:       8
Factor:       0.4
Offset:       0
Unit:         %
```

and the BLF contains:

```text
CAN ID: 0x100
Data:   AD 1E 02 19 4B FB 25 03
```

The decoder extracts the SOC raw value from the defined bits and applies:

```text
Physical value = Raw value × Factor + Offset
```

The result is then available as:

```text
Timestamp | CAN ID | Message    | Signal | Value
-------------------------------------------------
12.345    | 0x100  | BMS_Status | SOC    | ...
```

## 6. Current MVP functionality

- DBC upload
- BLF upload
- DBC parsing
- BLF reading
- CAN ID to DBC message matching
- Signal decoding
- Engineering-unit conversion
- Signal list
- Signal search
- Signal statistics
- Individual signal plotting
- CAN message browsing
- Raw decoded data table
- CSV export
- Time-window filtering

## 7. Recommended next development phases

### Phase 2 — Engineering analysis

Add:

- Multiple signal selection
- Multiple signals on one plot
- Left/right Y axes
- Zoom and pan
- Signal statistics
- RMS
- Standard deviation
- Min/max
- Rate of change
- Derivative
- Integration
- Moving average
- Signal correlation
- Histogram
- FFT
- Cycle detection
- Event detection

### Phase 3 — BMS-specific analysis

Add predefined BMS signal groups:

```text
Pack
 ├── Pack Voltage
 ├── Pack Current
 ├── SOC
 ├── SOH
 ├── SOP
 └── Power

Cells
 ├── Cell Voltage 01...N
 ├── Cell Temperature 01...N
 ├── Min Cell Voltage
 ├── Max Cell Voltage
 └── Cell Voltage Delta

Thermal
 ├── Inlet Temperature
 ├── Outlet Temperature
 ├── Coolant Temperature
 └── Temperature Delta

Faults
 ├── DTC
 ├── Over Voltage
 ├── Under Voltage
 ├── Over Temperature
 └── Isolation Fault
```

### Phase 4 — Automated vehicle-data reports

Generate:

- PDF reports
- Excel reports
- Signal summary
- Fault summary
- SOC analysis
- Cell imbalance analysis
- Thermal analysis
- CAN communication health
- Missing message analysis
- Message cycle-time analysis

### Phase 5 — Team deployment

For an engineering team, consider:

```text
                  ┌───────────────────┐
                  │   Web Browser     │
                  └─────────┬─────────┘
                            │
                            ▼
                  ┌───────────────────┐
                  │ Streamlit Server  │
                  └─────────┬─────────┘
                            │
                 ┌──────────┴──────────┐
                 │                     │
                 ▼                     ▼
           Analysis Engine       File Storage
                 │                     │
                 ▼                     ▼
          Python/C++ modules     BLF/DBC archive
```

For large BLF files, the decoder should eventually be changed from loading the entire file into memory to chunked/streaming processing.
