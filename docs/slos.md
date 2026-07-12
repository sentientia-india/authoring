# Production SLOs and alert policy

| Indicator | Objective | Measurement |
|---|---:|---|
| MCP and authoring API availability | 99.9% monthly | successful synthetic requests / scheduled requests |
| Hosted learner availability | 99.95% monthly | successful hosted launch and event synthetic checks |
| API read latency | p95 below 400 ms; p99 below 1 s | server request histogram |
| Authoring save latency | p95 below 750 ms | save endpoint histogram |
| Hosted event acceptance | p95 below 300 ms | event endpoint histogram |
| Standard course generation | p95 below 5 minutes | job duration |
| Standard SCORM export | p95 below 60 seconds | export job duration |
| Recovery point | 15 minutes or less | last successful protected backup |
| Recovery time | 60 minutes or less | quarterly clean restore drill |

Critical alerts page the operator for total unavailability, dependency failure, suspected tenant isolation failure, billing reconciliation differences, backup staleness, or failed deployment health checks. Warning alerts cover sustained error rate, queue delay, latency, capacity, email failure, and webhook retries.

SLO compliance is not claimed until synthetic checks and retained metrics provide the required 14-day beta or 30-day GA measurement window.
