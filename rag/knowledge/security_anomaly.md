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

Model test results:

- Accuracy: 98.31%
- Anomaly precision: 82.26%
- Anomaly recall: 84.40%
- Anomaly F1-score: 83.32%
- False alarms: 91
- Missed anomalies: 78

The model was evaluated on synthetic RescueCloud activity logs, so results may be higher than performance on real hospital logs.

The prediction endpoint is:

POST /anomaly/predict
