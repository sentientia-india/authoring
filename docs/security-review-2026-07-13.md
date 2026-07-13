# Internal security review, 2026-07-13

Scope covered the MCP/API and authoring attack surface, Git history secret
patterns, Python supply chain, GitHub Actions, Docker isolation, inbound
webhooks, outbound providers, LLM boundaries, OWASP Top 10, STRIDE, and data
classification.

The review found no committed live-key pattern. Dependency resolution now uses
tracked hash-pinned production/development locks, and the locked production
graph passes `pip-audit` with no known vulnerabilities. GitHub Actions are
commit-pinned, security-sensitive files have CODEOWNERS rules, and default
gitleaks detection is enabled.

Two verified billing authorization issues were remediated:

1. Checkout previously accepted a caller-selected price and tier. The service
   now requires `STRIPE_PRICE_CATALOG` to bind every allowed price to its mode
   and entitlement tier on the server, rejecting mismatches.
2. The customer portal previously accepted a caller-provided Stripe customer
   ID. It now resolves the customer only from the authenticated tenant's latest
   persisted Stripe subscription.

Regression tests cover tier escalation, missing customer ownership, workflow
pinning/ownership, and PostgreSQL customer lookup. Stripe credentials are
mounted as Docker secrets rather than placed in repository configuration.

This AI-assisted internal review is not a substitute for an independent
professional penetration test. A qualified external tester must still assess
the deployed public endpoint, authenticated tenant boundaries, hosted learner
paths, custom domains, payment flows, and operational configuration before GA.
