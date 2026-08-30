# Security and Anomaly Detection

RescueCloud uses an Isolation Forest model to detect suspicious system activity.

The model is trained on 50,000 synthetic audit-log events:

- 47,500 normal events
- 2,500 suspicious events

Example activity features:

- failed login attempts
- requests per minute
- records accessed
- records modified
- records deleted
- export size
- session duration
- off-hours access
- new IP address
- privilege changes
- user role
- user action
- request status

Example normal event:

A doctor views four patient records during working hours from a known IP address.

Example suspicious event:

An administrator exports 2,500 records at night from a new IP address with many failed login attempts.

Model evaluation threshold sweep:

- **Default Production Baseline (Threshold = 0.00)**:
  - Anomaly Recall (Sensitivity): **79.0%**
  - Anomaly Precision (Purity): **84.8%**
  - F1-Score: **81.8%**

- **High-Security Defense Mode (Threshold = 0.05)**:
  - Anomaly Recall (Sensitivity): **95.0%**
  - Anomaly Precision (Purity): **58.9%**
  - F1-Score: **72.7%**

The model was evaluated on 50,000 synthetic RescueCloud audit-log events (5.0% true attack rate). Results on live hospital logs may vary depending on noise.


The prediction endpoint is:

POST /anomaly/predict
