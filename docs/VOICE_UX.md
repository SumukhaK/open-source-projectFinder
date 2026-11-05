# Voice settings and onboarding UX

Decided 2026-11-05 (the owner delegated the UI/UX calls). Companion to [voice assistant architecture](VOICE_ASSISTANT_ARCHITECTURE.md); tasks in [execution-plans/voice-assistant](../execution-plans/voice-assistant/TRACKER.md).

## Starting point

Signed out, the app has one screen with "Continue with GitHub" and the only appearance picker (System, Dark, Light). Signed in, it has one screen with no navigation bar: a header (logo, "Discover projects", @username, Sign out), Discover/Favourites segmented tabs, the idea box, "Search projects" and the results. There is no settings place, no microphone affordance, and the original Home/Profile design (bottom bar, Profile page with avatar and favourites, tap-to-type / long-press-to-speak button) was never built.

## Decisions

| ID | Decision |
| --- | --- |
| UX1 | Build the original **Home / Profile bottom bar** first (task P3). Profile is the settings home: avatar and @username, Favourites, Settings (Appearance, Voice, About and privacy), and Sign out at the bottom. |
| UX2 | The spoken-summary control is **Profile › Voice › "Read summaries aloud"**, subtitle "After a voice search, hear a short summary. The list always shows." |
| UX3 (= VD4) | Default **On, for voice searches only**. Typed searches never speak on their own. Never auto-speak while VoiceOver/TalkBack is running; respect the phone's silent mode. |
| UX4 | A **visible mic button** at the right edge of the idea box replaces the hidden long-press floating button. |
| UX5 | Explain voice **at the moment of need**: a hint under the idea box until voice is used once, a one-time sheet on the first hold (before the system microphone prompt), and a "How voice works" page in Profile › Voice. No onboarding tour. |

## Screens

```text
Profile                          Profile › Voice
┌──────────────────────────┐     ┌──────────────────────────┐
│ (avatar) @username       │     │ Read summaries aloud [ON]│
│ Favourites          12 › │     │ After a voice search,    │
│ SETTINGS                 │     │ hear a short summary.    │
│ Appearance  Sys/Dark/Lt  │     │ The list always shows.   │
│ Voice                  › │     │ Microphone: Allowed      │
│ About and privacy      › │     │  (or Off – Open settings)│
│ Sign out                 │     │ How voice works        › │
└──────────────────────────┘     └──────────────────────────┘
```

## Voice journey

1. **Discover.** Mic button inside the idea box; muted hint "Hold the mic to say your idea." until first use.
2. **First hold.** Sheet "Search by voice": hold and describe, let go to search; you'll see what we heard and can edit it; audio is turned into text by Deepgram and nothing is saved; summaries are read aloud, change this in Profile › Voice. Buttons: Continue (opens the system microphone prompt) and Not now (keeps text search; the sheet shows again next time).
3. **Holding.** Haptic tap, pulsing ring reusing the Bracket Navigator motion, timer, "Let go to search · Slide away to cancel", 30-second limit with a countdown in the last 5 seconds.
4. **Release.** The words fill the idea box labelled "We heard" and the search starts; the user can edit and search again. Empty or failed: "We couldn't catch that. Try again or type your idea."
5. **Results.** The list shows first. A Summary card above it has an "AI" tag, "Based only on the results below", and a speaker button (Stop while playing) so any summary can be heard once regardless of the setting. The first spoken summary shows a one-time tip "Turn this off in Profile › Voice".
6. **Permission denied.** The mic stays visible; holding opens "Microphone is off for RepoRadar" with "Open phone settings". Text search is never blocked.
7. **How voice works.** Plain answers: what is sent where (audio to Deepgram, the result list to the summary model), what is never kept, that summaries describe only the listed projects and can be imperfect, and how to turn voice off.

## Build rules

- Settings live on the device per GitHub account, in the same account-scoped AsyncStorage pattern as the results cache, with defaults from central mobile config. Nothing is sent to the server. Sign-out clears the voice consent flag so the next account sees the sheet.
- 8-point grid, 20-point screen padding, 48-point touch targets, existing theme tokens; screen-reader labels and focus order on every new control.
- Plain copy; no "STT", "LLM" or provider jargon beyond the one Deepgram disclosure.
- Every new screen gets a real mobile-sized light/dark inspection on a development build, or the reason it could not run is recorded.
