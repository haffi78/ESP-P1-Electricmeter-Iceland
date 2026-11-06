# Energy graph investigation — November 2026

A reported Energy Dashboard interruption followed a Home Assistant update. The
reader uses its own YAML parser, independently of `gardart/veitur-meter-reader`.
The investigation found a reproducible cumulative-import lockout in this YAML,
but did not establish it as the cause of the reported dashboard interruption.

## Confirmed observations

- The inspected deployment runs Home Assistant Core 2026.11.0 and ESPHome
  2026.10.2. Its previous Core version was not confirmed.
- Both this YAML and the device startup log specify **115200 baud, 8N1**.
- Runtime logs show numeric cumulative import being parsed and published at
  approximately 30-second intervals. A later sample contains 21 monotonically
  increasing publications over ten minutes, with no warning/error entries or
  import-jump rejection messages.
- Direct inspection confirmed that the existing Home Assistant import entity
  was increasing and retained `device_class: energy`,
  `state_class: total_increasing`, and unit `kWh`.
- Statistics reported no issue for cumulative electricity import or water
  volume. Historical dashboard data was present across November 5 and into
  November 6. The persistent freeze was not reproduced during inspection.
- Available Core log issues contained no matches for Recorder, statistics, or
  this reader. This was not a complete historical log audit.

These observations distinguish receiving serial bytes from successfully parsing,
publishing, receiving in Home Assistant, and displaying recorded statistics.
They do not identify the original interruption's cause or recovery time.

## Reproduced firmware defect and fix

Previously, an import reading more than 0.20 kWh ahead of the last accepted
reading was always rejected. Since the meter keeps increasing, later readings
could never get back inside that limit until the in-memory baseline was cleared.

For example, with synthetic readings:

```text
Accepted total: 1000.000 kWh
After missed readings: 1000.500, 1000.510, 1000.520 kWh
Previous implementation: retains 1000.000 forever
Updated implementation: accepts 1000.520 after three confirmations
```

The fix confirms a larger forward jump using three consecutive import readings.
Each candidate must differ from the previous candidate by between -0.0005 and
+0.20 kWh. Isolated spikes and significant backward readings remain rejected.
Missing import rows interrupt confirmation; inconsistent candidates restart it.
Normal accepted readings clear pending confirmation.

If every candidate advances by more than 0.20 kWh, confirmation still restarts.
This change does not define a new maximum consumption rate or support meter
replacement/reset. All existing sensor names, IDs, units, and classes are retained.

The ignored `esp8266_store_log_strings_in_flash: false` option was also removed
following the ESPHome 2026.10.2 build warning. UART and request signaling are
unchanged.

Validation: 11 host regression tests execute the actual UART parser and import
sensor lambda extracted from the YAML. They cover normal readings, gaps,
isolated spikes, backward readings, interrupted confirmation, and fragmented
telegrams. The original implementation fails the recovery cases. This workspace
has no full ESPHome build environment. A subsequently supplied runtime log shows
new firmware running, but does not independently identify its exact source or
exercise the recovery branch.

## Comparison with the Veitur migration

[Veitur migration PR #4](https://github.com/gardart/veitur-meter-reader/pull/4)
changes another implementation. Its remaining differences should be assessed
against actual telegrams rather than copied as a presumed dashboard fix.

| PR change | This YAML | Assessment |
| --- | --- | --- |
| 115200 8N1 | Already configured and verified | No baud change needed for the inspected deployment. |
| Held-HIGH request | Still pulses for 50 ms every 30 s | A real difference; readable telegrams were observed with pulses. |
| Bounded line buffer | UART RX buffer plus an accumulating string without an explicit size limit | Buffer hardening remains useful future work. |
| Multi-field heat rows and timestamp filtering | First-field extraction; only water volume selects the last matching row | Additional parsing safeguards remain useful future work. |
| Avoid absent-value zeros | Numeric globals initialize to `NAN`; assignments require a matching row | No equivalent zero-initialization fix needed; older readings can remain stale. |
| Heat Wh-to-kWh conversion | Copies the number without unit conversion | Required if incoming heat rows use Wh; not an explanation for electricity import freezing. |

## Home Assistant changes examined

The source comparison used Core 2026.10.4 and 2026.11.0, not an independently
verified before/after installation pair.

- [Core PR #185600](https://github.com/home-assistant/core/pull/185600) clears
  an ESPHome unit/state class when firmware stops reporting it. Both fields were
  present on this reader and its inspected Home Assistant entity. An isolated
  probe of the old/new adapter methods retained the same valid numeric reading
  and metadata; deliberately omitted metadata reproduced the intended change.
- The ESPHome API dependency changed from `aioesphomeapi==46.6.0` to `46.25.0`.
  Live Home Assistant state delivery was working during inspection.
- [Core PR #186150](https://github.com/home-assistant/core/pull/186150) adds
  child devices; this YAML defines ordinary sensors on the main node.
- [Core PR #188492](https://github.com/home-assistant/core/pull/188492) changes
  statistics query streaming/reduction. Other Recorder changes include retries,
  calendar/DST handling, and history initialization. No matching failure was
  reproduced in the inspected charts.
- [Frontend PR #54560](https://github.com/home-assistant/frontend/pull/54560)
  changes energy/water card update dependencies, and
  [#54590](https://github.com/home-assistant/frontend/pull/54590) changes energy
  badges and statistics graph inputs.
- [Frontend PR #54741](https://github.com/home-assistant/frontend/pull/54741)
  changes Energy refresh/subscription handling to prevent obsolete date-range
  responses from replacing the selected period. These UI changes are relevant
  candidates if a display stays stale while stored statistics advance, but are
  not confirmed causes here.

The installed [Frontend 20261028.4 Energy source](https://github.com/home-assistant/frontend/blob/20261028.4/src/data/energy.ts#L977)
schedules the active collection's hourly refresh for **20 minutes past the
hour**. At 08:45 an hourly view ending around 08:00 can therefore be normal.
This is verified refresh behavior, not evidence that the schedule was introduced
in 2026.11. A 30-second sensor publication interval does not imply a 30-second
Energy Dashboard refresh interval.

Sources: [full 2026.11 changelog](https://www.home-assistant.io/changelogs/core-2026.11/),
[long-term statistics](https://www.home-assistant.io/docs/configuration/long-term-statistics/),
and [energy sensor requirements](https://www.home-assistant.io/docs/energy/faq/).

## If the interruption recurs

1. Compare the raw import row, parsed total, ESPHome sensor publication, and
   Home Assistant entity state over the same interval.
2. If ESPHome publishes new values but the Home Assistant entity is frozen,
   inspect the ESPHome integration connection and Core log errors.
3. If the Home Assistant entity increases but statistics stop, inspect Recorder
   exclusions/errors and Settings → Tools → Statistics for that same entity.
4. If statistics advance but the chart does not, inspect the dashboard's selected
   period/source and frontend refresh behavior.

Preserve the existing entity/statistic IDs and energy history. The evidence does
not justify deleting statistics, recreating the integration, or asserting that
the external migration fixes this symptom. An eventual cumulative increase can
recover aggregate consumption after a gap, but cannot reconstruct its actual
hour-by-hour distribution by itself.
