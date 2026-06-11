# Secure Secret Export Importer Design

## Purpose

Permit a one-time, in-memory conversion of the owner-only `secrets.txt` export
into ArthaBot's existing `SecretConfig` without creating `.env` files, modifying
process environment, logging values, or committing credentials.

## Format And Rules

The importer accepts only an owner-only regular file. It recognizes exact,
case-insensitive labels `API KEY`, `API secret`, `Access token`, and
`Newsapi.org API`. Values must occur after a single colon on the same line.
Unknown lines are ignored. Duplicate recognized labels, empty values, unsafe
permissions, missing Kite key/secret, or missing NewsAPI value fail with stable
redacted errors that never include input content.

The result is `SecretConfig`; its existing redacted repr remains the only
display form. A missing Kite access token is allowed for NewsAPI/read-only
workflows but `has_zerodha_credentials` remains false, so broker probes and
deployment preflight continue to block.

## Read-Only Validation

Add a NewsAPI smoke runner that uses the imported configuration in memory,
issues a minimal `/v2/everything` read request through `NewsHttpClient`, and
audits only success, article count, and provider name. It does not log request
headers, URLs containing keys, headlines, or response bodies.

## Testing

Tests cover valid imports, absent access token, unsafe permissions, duplicates,
empty/missing required values, redacted repr/errors, and a fully injected
NewsAPI smoke path. Real network use occurs only after tests pass.

