---
name: industrytech-iot
description: >
  Analyzes IoT and industrial automation systems including MQTT/OPC-UA protocols,
  sensor pipelines, predictive maintenance, digital twins, and IEC 62443 safety.
requires_bins: []
os: any
user_invocable: true
---

# IndustryTech / IoT Analysis

## When to Apply
- Industrial IoT sensor networks and data pipelines
- MQTT / OPC-UA / Modbus protocol implementations
- Predictive maintenance model integration
- Digital twin architectures
- Edge-to-cloud data flow design
- Industrial safety and security (IEC 62443)

## Checklist

### Protocol Design
- [ ] MQTT QoS levels appropriate per data criticality (0/1/2)
- [ ] OPC-UA security mode: Sign & Encrypt for production
- [ ] Retained messages and Last Will and Testament configured
- [ ] Topic hierarchy follows ISA-95 / Sparkplug B naming
- [ ] Protocol gateway between OT and IT networks

### Sensor Data Pipeline
- [ ] Edge preprocessing: filtering, aggregation, anomaly detection
- [ ] Time-series database (InfluxDB, TimescaleDB, QuestDB)
- [ ] Data schema versioning and backward compatibility
- [ ] Backpressure handling for burst sensor data
- [ ] Data compression for bandwidth-constrained links

### Edge Computing
- [ ] Latency-critical processing runs on edge (< 100ms requirement)
- [ ] Edge-to-cloud sync with store-and-forward on connectivity loss
- [ ] OTA firmware update mechanism with rollback
- [ ] Resource constraints documented (CPU, RAM, storage)
- [ ] Containerization (Docker/Podman) on edge where supported

### Predictive Maintenance
- [ ] Feature engineering from sensor time-series
- [ ] Model explainability (SHAP, LIME) for maintenance decisions
- [ ] Remaining Useful Life (RUL) estimation accuracy tracked
- [ ] Alert thresholds calibrated to avoid alarm fatigue
- [ ] Feedback loop: prediction → maintenance action → outcome

### Digital Twin
- [ ] Twin model reflects physical asset state in real-time
- [ ] Simulation capability for what-if scenarios
- [ ] State synchronization protocol defined (event-driven vs polling)
- [ ] Version control for twin model definitions
- [ ] Integration with asset management / CMMS systems

### Safety & Security (IEC 62443)
- [ ] Security zones and conduits defined (network segmentation)
- [ ] Security Level (SL) targets assigned per zone
- [ ] Authentication and authorization for all OT endpoints
- [ ] Patch management process for embedded systems
- [ ] Incident response plan for OT security events
- [ ] Functional safety assessment (SIL classification)
- [ ] Safety-critical loops have independent safety controllers

## Output Format
```
## System Architecture
Sensor network, edge, cloud topology diagram.

## Findings
| # | Severity | Category | Finding | Recommendation |
|---|---|---|---|---|

## Safety Assessment
IEC 62443 / SIL compliance status.

## Data Pipeline
Edge-to-cloud flow with latency and reliability analysis.
```
