# GitHub authentication

## Implemented flow

1. The app creates a cryptographically random PKCE verifier and sends its SHA-256 challenge to FastAPI.
2. FastAPI creates expiring random OAuth state and a separate provider PKCE verifier. It stores the verifier encrypted and returns the GitHub authorization URL.
3. The system browser handles GitHub authorization. The backend callback atomically consumes state, exchanges the code once, and fetches `/user` to verify GitHub's stable numeric identity.
4. FastAPI creates/updates the account and encrypts GitHub credentials with Fernet. The native return URI receives only a short-lived handoff and state, never a GitHub token or app session.
5. The app verifies callback destination/state and redeems the handoff with its verifier. FastAPI atomically consumes it and returns a random RepoRadar session; only its SHA-256 hash is stored.
6. iOS/Android persist that app session in Expo SecureStore. Startup verifies it through `/auth/me`. Logout revokes it server-side before clearing local storage.

GitHub signup and returning login use the same action. No private-repository or email scope is requested. Account identity follows the GitHub numeric ID even if the username changes.

OAuth state expires in 10 minutes; handoffs in 60 seconds; app sessions in 8 hours or earlier than the reported GitHub access-token expiry. These durations are centralized configuration. Incorrect handoff proof consumes the handoff, forcing a fresh attempt. Denied authorization and provider failures return safe error codes to the allowlisted app destination. Saved sessions are cleared on 401; transient restore errors preserve stored credentials and offer a new login. Failed logout keeps the current account visible so revocation can be retried.

## Rate limits and provider retries

All auth routes share a persistent per-connection-IP quota. A 429 includes `Retry-After`. Client-supplied forwarding headers cannot select a new quota; the deployment must retain that property with explicit trusted-proxy configuration. Single-use storage operations and counters use SQLite write transactions. Oversized request bodies are rejected. An ingress request timeout/body limit and infrastructure abuse protection are still required for public deployment.

Safe GitHub identity GET requests use at most three attempts, 10-second timeouts and exponential delays (0.5, 1 second plus jitter). Transient network failures, 429 and selected 5xx responses can retry. GitHub rate-limit 403 responses retry only when identified by rate-limit headers. Retry-After (seconds/date) and reset timestamps are respected; delays above five seconds fail immediately rather than retrying before the provider permits it. Rate-limit responses without usable timing headers fail immediately rather than violating GitHub's minimum one-minute wait. Invalid credentials and other permanent errors are not retried.

Authorization-code POST exchanges are attempted once. A timeout may mean GitHub already consumed the code; restarting sign-in is safer than blindly replaying it. The app does not automatically retry authentication POST requests.

## Boundaries and remaining work

This phase implements authentication only. GitHub access/refresh tokens, when issued, are encrypted for later search integration. Automatic provider refresh and token-revocation handling during search belong to that feature; until then users reauthenticate when the short app session expires. Background repository ingestion will use separate service credentials and budgets.

Native login requires a development/release binary with the `reporadar` URL scheme. Expo Go cannot validate this custom-scheme flow. Web is a visual preview; browser login is deliberately not enabled in this mobile phase. No tokens go into web localStorage or AsyncStorage. Physical iOS/Android browser return, secure storage, accessibility and live GitHub authorization need validation with registered OAuth credentials and native builds.

The automated cross-layer test drives the real mobile authentication page/client through a real local FastAPI HTTP server and SQLite, replacing only GitHub and native browser/storage APIs. It covers signup, session restore, logout and returning login. It does not claim to test GitHub's live service or OS browser behavior.

## References

- [GitHub OAuth authorization](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps)
- [Expo system-browser authentication](https://docs.expo.dev/versions/latest/sdk/webbrowser/)
- [Expo SecureStore](https://docs.expo.dev/versions/latest/sdk/securestore/)

- [GitHub rate-limit retry guidance](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api)
