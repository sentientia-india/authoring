# Adapt Authoring go/no-go decision

Decision: **no-go for embedded Adapt; continue the in-house SCORM editor.**

Adapt Authoring remains viable only as an arm's-length GPL-3.0 service. Its legacy MongoDB and Node compatibility requirements add a second persistence, upgrade and security surface, while mapping Samrat's slide blocks, branching schema, game options, media references, licensing stamps and dual-version SCORM runtime would still require a custom translation layer.

Estimated production mapping cost: 8–12 engineering days plus ongoing compatibility testing. The existing editor already round-trips `data/course.json` and preserves the exact exporter runtime, so extending it is lower risk and directly testable. Adapt can be reconsidered if customers require its collaborative authoring workflow strongly enough to justify running it as a separately deployed product.
