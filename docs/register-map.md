# SunSpec register map — APsystems ECU-C

Firmware `ECU-C-Z_C1.2.26`, ECU-ID 2150000xxxxx, read over Modbus TCP on port 502,
unit 1 (QT2-3, serial 9015000xxxxx). Captured after sunset, so AC and DC measurement
fields read near zero — fields marked **no** are unimplemented by sentinel value
(0xFFFF, 0x8000 or NaN) and will not change in daylight.

## Chain layout

| Address | Contents |
|---|---|
| 40000 | identifier `SunS` |
| 40002 | model 1, length 66, data 40004–40069 |
| 40070 | model 103, length 50, data 40072–40121 |
| 40122 | model 113, length 60, data 40124–40183 |
| 40184 | model 123, length 24, data 40186–40209 |
| 40210 | end-of-chain marker |
| 40212 | **model 114, length 48, data 40214–40261 — after the end marker** |
| 40262–40300 | readable, all zero |
| 40301 and above | no response at all |

## Address space and Modbus units

The full 16-bit address space was probed on unit 1 (655 points, step 100) and only
one region answers: 40000 onwards. The upper bound is exactly **40300** — register
40300 reads 0, register 40301 and everything above it produce no response. The
firmware exposes a fixed 301-register window, of which the SunSpec chain plus the
out-of-chain model 114 occupy 262.

Unit ids 0 to 247 were scanned. Exactly nine answer — units 1 to 9, one per QT2,
each reporting its own serial number. Unit 0 does not respond. There is no address
folding: no high unit id mirrors a low one. **The ECU does not expose itself as a
Modbus device**, so its own CT clamps are not reachable over Modbus by any route —
not as a SunSpec meter model, not as a separate unit, not as an out-of-chain block.
They remain accessible only via port 8899 and the ECU local page.

Note on error handling: an out-of-range address produces silence, not a Modbus
exception. The gateway does not signal invalid requests.

## Model 1 — Common, data 40004–40069

| Register | Field | Type | Value | Implemented |
|---|---|---|---|---|
| 40004–40019 | Mn | str16 | 'APsystems' | yes |
| 40020–40035 | Md | str16 | 'QT2-3' | yes |
| 40036–40043 | Opt | str8 | 'unimplemented' | yes |
| 40044–40051 | Vr | str8 | 'V1169' | yes |
| 40052–40067 | SN | str16 | '9015000xxxxx' | yes |
| 40068 | DA | u16 | 1 | yes |
| 40069 | Pad | u16 | 0 | yes |

## Model 103 — Inverter, three phase (int+SF), data 40072–40121

| Register | Field | Type | Value | Implemented |
|---|---|---|---|---|
| 40072 | A | u16 | 0 | yes |
| 40073 | AphA | u16 | 0 | yes |
| 40074 | AphB | u16 | 0 | yes |
| 40075 | AphC | u16 | 0 | yes |
| 40076 | A_SF | sf | -2 | yes |
| 40077 | PPVphAB | u16 | 4190 | yes |
| 40078 | PPVphBC | u16 | 4180 | yes |
| 40079 | PPVphCA | u16 | 4200 | yes |
| 40080 | PhVphA | u16 | 0 | yes |
| 40081 | PhVphB | u16 | 0 | yes |
| 40082 | PhVphC | u16 | 0 | yes |
| 40083 | V_SF | sf | -1 | yes |
| 40084 | W | s16 | 9 | yes |
| 40085 | W_SF | sf | -1 | yes |
| 40086 | Hz | u16 | 4999 | yes |
| 40087 | Hz_SF | sf | -2 | yes |
| 40088 | VA | s16 | 9 | yes |
| 40089 | VA_SF | sf | -1 | yes |
| 40090 | VAr | s16 | 0 | yes |
| 40091 | VAr_SF | sf | -1 | yes |
| 40092 | PF | s16 | 1000 | yes |
| 40093 | PF_SF | sf | -3 | yes |
| 40094–40095 | WH | acc32 | 2114 | yes |
| 40096 | WH_SF | sf | 0 | yes |
| 40097 | DCA | u16 | 65535 | no |
| 40098 | DCA_SF | sf | -32768 | no |
| 40099 | DCV | u16 | 65535 | no |
| 40100 | DCV_SF | sf | -32768 | no |
| 40101 | DCW | s16 | -32768 | no |
| 40102 | DCW_SF | sf | -32768 | no |
| 40103 | TmpCab | s16 | 240 | yes |
| 40104 | TmpSnk | s16 | -32768 | no |
| 40105 | TmpTrns | s16 | -32768 | no |
| 40106 | TmpOt | s16 | -32768 | no |
| 40107 | Tmp_SF | sf | -1 | yes |
| 40108 | St | enum | 4 | yes |
| 40109 | StVnd | enum | 65535 | no |
| 40110–40111 | Evt1 | bf32 | 0x00000000 | yes |
| 40112–40113 | Evt2 | bf32 | 0xFFFFFFFF | no |
| 40114–40115 | EvtVnd1 | bf32 | 0xFFFFFFFF | no |
| 40116–40117 | EvtVnd2 | bf32 | 0xFFFFFFFF | no |
| 40118–40119 | EvtVnd3 | bf32 | 0xFFFFFFFF | no |
| 40120–40121 | EvtVnd4 | bf32 | 0xFFFFFFFF | no |

## Model 113 — Inverter, three phase (float), data 40124–40183

| Register | Field | Type | Value | Implemented |
|---|---|---|---|---|
| 40124–40125 | A | f32 | 0.004 | yes |
| 40126–40127 | AphA | f32 | 0.001 | yes |
| 40128–40129 | AphB | f32 | 0.001 | yes |
| 40130–40131 | AphC | f32 | 0.001 | yes |
| 40132–40133 | PPVphAB | f32 | 419.0 | yes |
| 40134–40135 | PPVphBC | f32 | 418.0 | yes |
| 40136–40137 | PPVphCA | f32 | 420.0 | yes |
| 40138–40139 | PhVphA | f32 | 0.0 | yes |
| 40140–40141 | PhVphB | f32 | 0.0 | yes |
| 40142–40143 | PhVphC | f32 | 0.0 | yes |
| 40144–40145 | W | f32 | 0.95 | yes |
| 40146–40147 | Hz | f32 | 49.99 | yes |
| 40148–40149 | VA | f32 | 0.95 | yes |
| 40150–40151 | VAr | f32 | 0.0 | yes |
| 40152–40153 | PF | f32 | 1.0 | yes |
| 40154–40155 | WH | f32 | 2114.685 | yes |
| 40156–40157 | DCA | f32 | NaN | no |
| 40158–40159 | DCV | f32 | NaN | no |
| 40160–40161 | DCW | f32 | NaN | no |
| 40162–40163 | TmpCab | f32 | 24.0 | yes |
| 40164–40165 | TmpSnk | f32 | NaN | no |
| 40166–40167 | TmpTrns | f32 | NaN | no |
| 40168–40169 | TmpOt | f32 | NaN | no |
| 40170 | St | enum | 65535 | no |
| 40171 | StVnd | enum | 65535 | no |
| 40172–40173 | Evt1 | bf32 | 0xFFFFFFFF | no |
| 40174–40175 | Evt2 | bf32 | 0xFFFFFFFF | no |
| 40176–40177 | EvtVnd1 | bf32 | 0xFFFFFFFF | no |
| 40178–40179 | EvtVnd2 | bf32 | 0xFFFFFFFF | no |
| 40180–40181 | EvtVnd3 | bf32 | 0xFFFFFFFF | no |
| 40182–40183 | EvtVnd4 | bf32 | 0xFFFFFFFF | no |

**Note:** `St` and `Evt1` are readable in model 103 but unimplemented in model 113.
A client that picks the float model for precision loses operating state and events.

## Model 123 — Immediate controls, data 40186–40209

| Register | Field | Type | Value | Implemented |
|---|---|---|---|---|
| 40186 | Conn_WinTms | u16 | 65535 | no |
| 40187 | Conn_RvrtTms | u16 | 65535 | no |
| 40188 | Conn | enum | 1 | **yes** |
| 40189 | WMaxLimPct | u16 | 1000 | **yes** |
| 40190 | WMaxLimPct_WinTms | u16 | 65535 | no |
| 40191 | WMaxLimPct_RvrtTms | u16 | 65535 | no |
| 40192 | WMaxLimPct_RmpTms | u16 | 65535 | no |
| 40193 | WMaxLim_Ena | enum | 1 | **yes** |
| 40194 | OutPFSet | s16 | -32768 | no |
| 40195 | OutPFSet_WinTms | u16 | 65535 | no |
| 40196 | OutPFSet_RvrtTms | u16 | 65535 | no |
| 40197 | OutPFSet_RmpTms | u16 | 65535 | no |
| 40198 | OutPFSet_Ena | enum | 65535 | no |
| 40199 | VArWMaxPct | s16 | -32768 | no |
| 40200 | VArMaxPct | s16 | -32768 | no |
| 40201 | VArAvalPct | s16 | -32768 | no |
| 40202 | VArPct_WinTms | u16 | 65535 | no |
| 40203 | VArPct_RvrtTms | u16 | 65535 | no |
| 40204 | VArPct_RmpTms | u16 | 65535 | no |
| 40205 | VArPct_Mod | enum | 65535 | no |
| 40206 | VArPct_Ena | enum | 65535 | no |
| 40207 | WMaxLimPct_SF | sf | -1 | yes |
| 40208 | OutPFSet_SF | sf | -1 | yes |
| 40209 | VArPct_SF | sf | -1 | yes |

**Note:** three of twenty-four registers carry real commands. No power-factor
control, no VAr control, no timing registers. `WMaxLimPct_SF` = -1, so the
setpoint is written in tenths of a percent (1000 = 100.0 %).

**The controls are global, not per-inverter.** Although model 123 is read and
written through an individual inverter's unit id, the ECU applies the command to
the entire array. Two independent confirmations: writing `Conn` = 0 on unit 1
stopped every inverter, not just unit 1; and writing `WMaxLimPct` = 1 % on unit 1
brought total array output from 8530 W to 315 W in 21 seconds, which is 1 % of the
whole array's rated base, not 1 % of one QT2. All other models (1, 103, 113, 114)
are genuinely per-inverter and return that unit's own data.

Anyone writing a client should assume that any write into 40186–40209, on any unit
id, curtails or disconnects the complete installation. This has been confirmed on
several different unit ids: the scope is always the whole array. There is therefore
no reason to declare model 123 on more than one unit — the other units are still
needed for per-inverter measurement, but a single control endpoint is enough, and
declaring several invites the mistake of believing they act independently.

## Model 114 — proprietary DC block, data 40214–40261

Placed *after* the end-of-chain marker at 40210, so a conforming SunSpec client
that walks the chain will never see it. Reachable only by hard-coded address.
Twenty-four float32 values in three groups of eight, with four channels populated
and four at zero, matching a four-channel QT2 in an eight-channel layout.
Captured after sunset; interpretation provisional.

| Registers | Raw | As float32 | Group |
|---|---|---|---|
| 40214–40215 | [16919, 5767] | 37.772 | A, ch1 |
| 40216–40217 | [16919, 5767] | 37.772 | A, ch2 |
| 40218–40219 | [16919, 5767] | 37.772 | A, ch3 |
| 40220–40221 | [16919, 5767] | 37.772 | A, ch4 |
| 40222–40229 | [0, 0] ×4 | 0.0 | A, ch5–8 unused |
| 40230–40231 | [15551, 45403] | 0.023 | B, ch1 |
| 40232–40233 | [15423, 45403] | 0.012 | B, ch2 |
| 40234–40235 | [15551, 45403] | 0.023 | B, ch3 |
| 40236–40237 | [15631, 50437] | 0.035 | B, ch4 |
| 40238–40245 | [0, 0] ×4 | 0.0 | B, ch5–8 unused |
| 40246–40247 | [16226, 17654] | 0.884 | C, ch1 |
| 40248–40249 | [16098, 17654] | 0.442 | C, ch2 |
| 40250–40251 | [16226, 17654] | 0.884 | C, ch3 |
| 40252–40253 | [16297, 46009] | 1.326 | C, ch4 |
| 40254–40259 | [0, 0] ×3 | 0.0 | C, ch5–8 unused |

Group B looks like DC current (leakage at night), group C like DC voltage.
Group A is identical across all four channels and does not match V × I, so it is
not instantaneous power. To be resolved with a daylight capture.

## Open items

- Do the group A values track irradiance, and do they diverge between channels?
- Are `PhVphA/B/C` (40080–40082) permanently zero, or only at night? Line-to-line
  voltages read correctly at 419 V.
- Extend the probe to 40270 to find the real terminator of model 114.
