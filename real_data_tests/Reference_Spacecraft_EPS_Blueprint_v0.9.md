# Reference Spacecraft Electrical Power System (EPS)
**Temporary Blueprint – Version 0.9 (Backup Only)**

> **UNVERIFIED, AI-GENERATED TEMPLATE — NOT REAL ADAPT DOCUMENTATION.**
> This document is temporary scaffolding for developing multi-agent
> rulebooks, nothing more. It is deliberately ADAPT-INSPIRED but
> GENERIC — it was not derived from ADAPT's actual files or diagrams
> (those remain unreachable; see `real_data_tests/adapt/PROFILE.md`).
> No number, relationship, sensor name or topology detail in this
> file may be used or cited as real, and it must never be presented
> as ADAPT's own documentation. Map real sensor names and parameters
> onto this structure only once the final craft definition or ADAPT's
> actual files become available.

---

## 1. High-Level Topology

```
Solar Array A ──► Charge Controller A ──┐
                                        ├──► Battery Bus (24 V nominal)
Solar Array B ──► Charge Controller B ──┘         │
                                                  ├──► Main Bus Relay Bank
Battery Pack 1 (2×12 V lead-acid series) ────────┤
Battery Pack 2 (2×12 V lead-acid series) ────────┤
Battery Pack 3 (2×12 V lead-acid series) ────────┘
                                                  │
                                    ┌─────────────┴─────────────┐
                                    ▼                           ▼
                              Load Bank 1                   Load Bank 2
                         (AC via Inverter 1)           (AC via Inverter 2)
                         + 2 DC loads                  + 2 DC loads
```

---

## 2. Core Components

| ID              | Component                  | Notes                                      |
|-----------------|----------------------------|--------------------------------------------|
| SA_A / SA_B     | Solar Arrays               | Independent strings                        |
| CC_A / CC_B     | Charge Controllers         | Can be cross-strapped                      |
| BAT1 / BAT2 / BAT3 | Battery Packs           | 24 V nominal, different capacities possible |
| INV1 / INV2     | Inverters                  | 24 V DC → 120 V AC                         |
| EY###           | Relays                     | Controllable switches                      |
| CB###           | Circuit Breakers           | Protective, can trip                       |
| LB1 / LB2       | Load Banks                 | Mix of AC and DC loads                     |

---

## 3. Sensor Categories & Naming Convention

Use a consistent naming pattern so agents can reason generically:

| Sensor Type          | Example Names                     | Units     | Typical Nominal Range          |
|----------------------|-----------------------------------|-----------|--------------------------------|
| Voltage              | V_BAT1, V_MBUS, V_INV1_OUT       | V         | 22.0 – 28.5 V (DC)             |
| Current              | I_BAT1, I_SA_A, I_LOAD_LB1       | A         | 0 – 40 A (context dependent)   |
| Temperature          | T_BAT1, T_INV1, T_CC_A           | °C        | 5 – 45 °C                      |
| Switch / Relay State | EY101_POS, CB201_POS             | Open/Closed | Discrete                     |
| State of Charge      | SOC_BAT1, SOC_BAT2, SOC_BAT3     | %         | 20 – 100 %                     |
| Frequency (AC)       | F_INV1, F_INV2                   | Hz        | 59.5 – 60.5 Hz                 |
| Power                | P_SA_A, P_LOAD_TOTAL             | W         | Derived                        |

---

## 4. Suggested Nominal Operating Windows (for rulebooks)

- **Battery voltage**: 22.0 – 28.5 V  
- **Battery SOC**: 30 – 95 % (soft limits), 20 – 100 % (hard limits)  
- **Bus voltage**: 23.5 – 27.5 V  
- **Inverter output**: 115 – 125 V AC, 59.5 – 60.5 Hz  
- **Component temperatures**: 5 – 45 °C (warning), 0 – 55 °C (critical)  
- **Solar array current**: depends on illumination (0 when dark)

---

## 5. Common Fault Classes (for agent rulebooks)

- Battery undervoltage / overvoltage  
- Battery imbalance between packs  
- Stuck-open or stuck-closed relay  
- Circuit breaker trip  
- Inverter failure (no AC output or frequency drift)  
- Sensor stuck / biased / noisy  
- Charge controller failure  
- Load fault (short or open)

---

## 6. Suggested Minimal Sensor List (Starter Set)

### Battery Pack Sensors
- V_BAT1, V_BAT2, V_BAT3
- I_BAT1, I_BAT2, I_BAT3
- T_BAT1, T_BAT2, T_BAT3
- SOC_BAT1, SOC_BAT2, SOC_BAT3

### Bus & Distribution
- V_MBUS
- I_MBUS
- EY101_POS, EY102_POS, EY103_POS (example main bus relays)
- CB201_POS, CB202_POS (example circuit breakers)

### Power Generation
- V_SA_A, V_SA_B
- I_SA_A, I_SA_B
- T_CC_A, T_CC_B

### Inverters & Loads
- V_INV1_OUT, V_INV2_OUT
- F_INV1, F_INV2
- I_LOAD_LB1, I_LOAD_LB2
- T_INV1, T_INV2

---

## 7. Notes for Use

- Treat all IDs, ranges, and fault classes above as **scaffolding only**.
- Write agent rulebooks against these names for now.
- When real ADAPT data or your final craft definition arrives, create a simple mapping table (e.g. `V_BAT1` → actual sensor name).
- This structure is intentionally close to the real ADAPT topology so the later mapping should be straightforward.

---

**Document Status**: Temporary backup reference  
**Version**: 0.9  
**Created**: 2026-10-28  
**Purpose**: Support multi-agent rulebook development for LEON while awaiting final system definition.
