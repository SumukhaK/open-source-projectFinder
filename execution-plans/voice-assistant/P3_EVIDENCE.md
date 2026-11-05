# P3 Home/Profile navigation

Base: `dc4ea0a7de50bb9762cf0ac35160c08677374419`. T25 merge `2bfab62` is an ancestor of the base; UX1 is approved.

The existing discovery screen retains its state and handlers. Home/Profile tabs move navigation below the scroll area, with 48-point targets and selected accessibility states. Profile contains the GitHub avatar, favourites, reused appearance controls, privacy text and sign-out. Tab changes dismiss inline details and invalidate outstanding detail responses. No navigation dependency or voice feature was added.

Verification on Windows, 2026-11-05:

- RED: new Home/Profile test failed on the missing Home tab before implementation.
- GREEN: 53 discovery-screen tests passed, including rollback, details, cache restoration and late-response cleanup.
- Full mobile coverage suite: 112 passed, one opt-in test skipped; existing coverage thresholds retained.
- Typecheck and lint passed.
- `npx expo export --platform all` passed for web, iOS and Android.
- Coverage: 95.48% statements, 87.42% branches, 95.08% functions, 99.58% lines.

No authenticated mobile development build was available in this session, so mobile-sized light/dark visual inspection and native screen-reader focus verification remain unverified. Existing appearance persistence is reused without a new storage key. Rollback is a code revert; no stored data migration is introduced.
