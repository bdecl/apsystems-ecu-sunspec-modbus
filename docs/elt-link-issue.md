# Silent curtailment failure when the ECU is linked to an ELT storage system

## Symptom

Power limiting over SunSpec Modbus stops working, with no error anywhere.

- Writes to `WMaxLimPct` (40189) succeed. No Modbus exception is returned.
- The register reads back the written value correctly, within a few seconds.
- `WMaxLim_Ena` (40193) reads 1.
- `Conn` (40188) reads 1, and writing 0 to it still stops the inverters normally.
- AC output does not change. At all. Indefinitely.

The combination is what makes this hard to diagnose. Because `Conn` still works,
the radio path from ECU to inverters is demonstrably healthy, which rules out the
first thing anyone would suspect. Because the register echoes back correctly, the
Modbus transport is demonstrably healthy too. Every layer reports success.

## Evidence

Curtailment ramped from 100 % to 1 % over eleven minutes and then held. Measured
export to the grid over the same period:

| Time | Limit | Grid power |
|---|---|---|
| 14:30 | 100 % | +59 W |
| 14:35 | ramping | -1818 W |
| 14:40 | ramping | -3247 W |
| 14:45 | 1 % | -5320 W |
| 14:55 | 1 % | -6383 W |
| 15:10 | 1 % | -7414 W |
| 15:15 | 1 %, `Conn` = 0 | +574 W |

Export rises throughout the descent. The installation exported 7.4 kW while
holding a 1 % limit the ECU had confirmed. Only writing `Conn = 0` stopped it.

Per-inverter channel power for the unit that was addressed, read over the ECU's
separate port 8899 protocol, confirms the same thing from the other side: 209 W,
then 257 W, then 245 W, across the whole ramp. Unchanged.

## Cause

The ECU was linked to an APsystems ELT storage system in the owner's EMA account.
The link was not visible anywhere in the interface and had not been created
knowingly. While it exists, the ECU stores power-limit commands in its register
bank but never dispatches them to the inverters.

The plausible reading is that the storage system's energy manager is treated as
the authority for curtailment, and the Modbus path is suppressed to avoid two
controllers fighting. That is defensible behaviour. Doing it silently, while
continuing to acknowledge and echo the commands, is not.

## Fix

Re-apply the site configuration with a current version of the EMA app so that the
ECU is no longer linked to the ELT system.

## Verification after the fix

Same installation, writing 1 % to 40189:

| Elapsed | Array output |
|---|---|
| 0 s | 8530 W |
| 5 s | 6144 W |
| 10 s | 3834 W |
| 16 s | 1482 W |
| 21 s | 320 W |

Then a stable plateau between 313 W and 323 W for four minutes, and a return to
7.3 kW on release. That is what a working dispatch looks like: a 21-second descent
and a flat plateau, not a slow drift.

## If you are testing this yourself

Pick a setpoint that is genuinely below your current production. A limit above
what the array is producing is not binding and proves nothing — an earlier test at
20 % appeared to fail for exactly this reason, when in fact the limit had simply
never been reached.

Measure with a sensor that updates in seconds. The ECU's own port 8899 data and
slow Modbus polls refresh every five minutes, which is far too coarse to see a
21-second transition, and short tests against them produce meaningless results.

Watch measured power, never the readback. The readback is the one signal that
looks correct in both the working and the broken case.
