# Mobile architecture

Follow the root AGENTS.md and the [Bulletproof React project structure guide](https://github.com/alan2207/bulletproof-react/blob/master/docs/project-structure.md), adapted for Expo / React Native.

- Compose features in src/app; keep feature-specific components in src/features/<feature>.
- Keep shared components, hooks, libraries, and configuration independent of features and the app layer.
- Avoid cross-feature imports; import modules directly instead of broad barrel files.
- Add directories only when needed. Keep styling and feature state close to their components.
- Use SDK-matched Expo modules and check versioned documentation before changing native configuration.
- Keep brand geometry and theme tokens in src/config/branding.ts; regenerate exported assets when changing them.
- Verify behavior with TDD, run tests, typecheck, lint, and platform exports before submitting mobile changes.
- Never embed backend secrets in the client. Public mobile configuration is visible to users.
