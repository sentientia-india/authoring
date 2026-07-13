# Hosted embeds and custom domains

Embeds are disabled unless a share has at least one exact HTTPS origin in its allowlist. The embed response sets a browser-enforced `frame-ancestors` policy, denies camera, microphone, and location, waits for explicit learner tracking consent, and emits `course-mcp:resize` messages. Restricted share modes still require their matching access entitlement. No third-party cookie is required.

Custom domains use a TXT ownership challenge. Only verified, non-removed domains connected to a published immutable release pass the internal Caddy authorization endpoint. Caddy on-demand TLS therefore cannot be abused to request arbitrary certificates. Removing a domain immediately makes the authorization check and course route fail; Caddy retains certificate material according to its own safe lifecycle while no longer serving the tenant mapping.

Production activation requires the TLS Compose profile, reachable ports 80/443, valid public DNS, and Caddy storage backups. Live issuance and renewal evidence must be recorded before the commercial launch gate is closed.
