When analyzing industrial IoT and manufacturing systems, apply these domain reasoning patterns:

**Safety Integrity Level Reasoning**
Industrial systems have real-world safety implications. For every control loop and safety function, determine the required Safety Integrity Level (SIL 1-4) per IEC 61508/62443. Higher SIL levels require: lower probability of dangerous failure per hour, more rigorous development processes, and more independent verification. Ask: What is the worst-case consequence if this function fails? Could it cause physical injury, environmental damage, or equipment destruction? Safety-critical functions must be independent of non-safety functions — shared resources (CPU, memory, network) between safety and non-safety code violate independence requirements.

**Edge-Cloud Tradeoff Analysis**
For every data processing decision, evaluate the edge-cloud tradeoff along five dimensions:
- **Latency**: Control loops requiring <100ms response must process at the edge. Cloud round-trips add 50-200ms minimum.
- **Bandwidth**: Sensors generating high-frequency data (vibration at 10kHz+) cannot stream raw data to the cloud economically. Edge aggregation is required.
- **Reliability**: Edge processing continues during network outages. What happens to the system when cloud connectivity is lost?
- **Security**: Data processed at the edge never leaves the facility perimeter, reducing exposure. But edge devices may be physically accessible to attackers.
- **Compute**: Complex ML inference may exceed edge device capabilities. Consider model quantization, pruning, or split inference.
The right answer is usually a hybrid — determine what MUST be at the edge (safety, latency) and what CAN be in the cloud (analytics, training, dashboards).

**Protocol & Interoperability Assessment**
Industrial systems use diverse protocols. For each integration point, verify: Is the protocol appropriate for the use case (MQTT for telemetry, OPC-UA for device management, Modbus for legacy PLCs)? Are message formats well-defined with schema validation? Is there protocol translation at boundaries, and does it preserve data fidelity? For OPC-UA: Are security policies configured (at minimum Sign & Encrypt)? Are certificates managed? For MQTT: Is TLS enabled? Are topic ACLs configured to prevent unauthorized publish/subscribe?

**Predictive Maintenance Model Evaluation**
For predictive maintenance systems, assess: What failure modes is the model trained to detect? What is the false positive rate, and what is the cost of a false positive (unnecessary maintenance) vs. false negative (unexpected failure)? Is the model explainable — can a maintenance engineer understand why the model predicts a failure? Are model inputs validated — what happens if a sensor fails and sends garbage data? Is there a graceful degradation path when the model is unavailable?

**Time-Series Data Pipeline Integrity**
Industrial data is inherently time-series. Verify: Are timestamps synchronized across devices (NTP/PTP)? What is the clock drift tolerance? Is data stored in a time-series-optimized database? Are retention policies defined and enforced? Is late-arriving data handled correctly (out-of-order events)? For downsampling: Is the aggregation method appropriate (average, max, min) for the metric type? Downsampling vibration data by averaging destroys the high-frequency components that indicate bearing failure.