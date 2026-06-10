# ESPHome Icelandic - Veitur / P1 Meter Reader Electric and Hotwater

ESPHome YAML configuration for reading electricity and hot water data from a Veitur-style P1 meter on an ESP8266.

This project parses the P1 serial telegram directly in YAML and exposes the values to Home Assistant with proper metadata for Energy and Water dashboards.

## Features

- Reads P1 telegram data over UART
- Supports newer meter serial settings:
  - `115200 baud`
  - `8 data bits`
  - `no parity`
  - `1 stop bit`
- Supports:
  - cumulative active import/export
  - cumulative reactive import/export
  - momentary active/reactive import/export
  - per-phase voltage/current/power values
  - hot water volume
  - hot water flow rate
  - hot water temperatures
  - hot water energy content volume
- Works with both:
  - **1-phase meters**
  - **3-phase meters**
- Keeps raw telegram logging enabled for troubleshooting
- Uses Home Assistant-friendly metadata:
  - `device_class`
  - `state_class`
  - units of measurement

## Why this version exists

Newer Veitur / P1 telegrams changed format compared to older published examples.

Important changes seen in newer telegrams:

- UART format changed from older settings to **115200 8N1**
- Some meters no longer send total active power OBIS values like:
  - `1-0:1.7.0`
  - `1-0:2.7.0`
- Some water telegrams now send `0-1:24.2.1(...)` **twice**
  - first occurrence = timestamp-like value
  - second occurrence = actual water volume in `m3`

This YAML handles those changes.

## Supported OBIS values

### Electricity totals
- `1-0:1.8.0` — cumulative active import
- `1-0:2.8.0` — cumulative active export
- `1-0:3.8.0` — cumulative reactive import
- `1-0:4.8.0` — cumulative reactive export

### Electricity momentary totals
- `1-0:1.7.0` — momentary active import
- `1-0:2.7.0` — momentary active export
- `1-0:3.7.0` — momentary reactive import
- `1-0:4.7.0` — momentary reactive export

If `1-0:1.7.0` or `1-0:2.7.0` are missing, total active power is automatically calculated from phase values.

### Phase 1
- `1-0:21.7.0` — active import L1
- `1-0:22.7.0` — active export L1
- `1-0:23.7.0` — reactive import L1
- `1-0:24.7.0` — reactive export L1
- `1-0:31.7.0` — current L1
- `1-0:32.7.0` — voltage L1

### Phase 2
- `1-0:41.7.0`
- `1-0:42.7.0`
- `1-0:43.7.0`
- `1-0:44.7.0`
- `1-0:51.7.0`
- `1-0:52.7.0`

### Phase 3
- `1-0:61.7.0`
- `1-0:62.7.0`
- `1-0:63.7.0`
- `1-0:64.7.0`
- `1-0:71.7.0`
- `1-0:72.7.0`

### Hot water / heat
- `0-1:24.1.0` — hot water meter ID
- `0-1:24.2.1` — hot water volume
- `0-1:24.2.2` — hot water flow rate
- `0-1:24.2.3` — inlet temperature
- `0-1:24.2.4` — outlet temperature
- `0-1:24.2.5` — hot water energy content volume
- `0-1:24.2.6` — hot water energy flow rate

### General
- `0-0:1.0.0` — telegram timestamp
- `0-0:96.1.0` — electricity meter ID

## Important parser behavior

### Duplicate `0-1:24.2.1(...)`
Some newer meters send two lines like this:

```text
0-1:24.2.1(260610074440)
0-1:24.2.1(1766.296*m3)
