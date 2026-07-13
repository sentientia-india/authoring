# Commerce operations

Commerce state is authoritative in PostgreSQL. Stripe is the payment provider;
entitlements are derived from persisted subscription snapshots, and product
licenses are stored only as SHA-256 hashes. Raw card data never enters this
service.

## Checkout modes

- `subscription` provisions or updates the tenant subscription, entitlement,
  and product license after a signed `checkout.session.completed` event.
- `payment` requires a hosted share token and purchaser email. It creates a
  purchase entitlement and queues an encrypted enrollment email. It does not
  create a SaaS product license.
- Return URLs must use HTTPS and match `PUBLIC_BASE_URL`.

## Replay and ordering guarantees

Stripe event IDs are unique and processed idempotently. Subscription writes
accept only snapshots at least as new as the stored provider timestamp. Older
events are recorded as stale but cannot regress access. Quota consumption locks
the tenant product-license row before reading and appending usage.

## Required production secrets

- `STRIPE_SECRET_KEY_FILE` and `STRIPE_WEBHOOK_SECRET_FILE` Docker secrets
- `STRIPE_PRICE_CATALOG`, a JSON object binding each allowed Stripe price to
  its server-authoritative `tier` and `mode`; clients cannot select entitlements
- `PUBLIC_BASE_URL`
- `PII_ENCRYPTION_KEY` shared by the API, analytics worker, and outbox worker
- email provider or SMTP credentials described in `docs/deployment.md`

Never put these values in the repository. Rotation must retain the previous PII
key until queued messages encrypted with it have been delivered or redriven.

## Daily operator checks

1. Run billing reconciliation and investigate every unexplained difference.
2. Check webhook retries, email suppressions, and outbox dead letters.
3. Confirm subscription status, entitlement state, and license tier agree for
   sampled active, past-due, canceled, refunded, and disputed customers.
4. Confirm the latest low-value test purchase produced exactly one entitlement
   and one enrollment delivery.
