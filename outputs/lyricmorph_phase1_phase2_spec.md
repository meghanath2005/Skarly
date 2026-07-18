# Skarly Phase 1 + Phase 2 Implementation Spec

## Summary
This package locks the MVP and defines the frontend design direction for the first Skarly prototype. The product should feel like a clean native app: practical, creative, waveform-led, and polished without looking like a paid subscription product.

Primary deliverable:
- Visual design board: `lyricmorph_phase1_phase2_design.html`
- Build spec: this document

## Phase 1: Locked MVP
Core flow:
1. User opens app.
2. User enters as Guest Creator, saves a Creator Workspace, or resumes an existing workspace.
3. User records up to 30 seconds of singing or uploads a short vocal file.
4. User selects one genre.
5. App shows dummy processing states.
6. App shows a result player with sample/generated MP3 behavior.
7. User can download, share, save to workspace, or find the track in private history.

MVP limits:
- Max recording length: 30 seconds.
- Output format: MP3.
- One generation at a time.
- Frontend can use dummy processing and sample audio first.
- No existing-song remixing.
- No AI singer voice cloning.
- No full 3-minute song generation.
- No payments.
- No social feed.

Locked MVP genres:
- Lo-fi
- Piano
- Pop
- Rock
- Indian classical
- EDM
- Acoustic
- Cinematic

## Phase 2: UI/UX Direction
Theme:
- Clean free music tool.
- Apple Health-inspired dark mobile foundation with premium visual depth.
- Large SF-style headings, rounded metric cards, rich but restrained chart surfaces, and visible data hierarchy.
- Logo design is intentionally deferred; keep the product mark text-only for now.
- Clear audio creation workflow.
- Waveform visuals as the main identity.
- Friendly enough for casual singers, structured enough to feel like a real tool.

Palette:
- App Black: `#050506`
- Card Charcoal: `#1C1C1E`
- Elevated Gray: `#2C2C2E`
- Primary Text: `#F5F5F7`
- Secondary Text: `#8E8E93`
- Health Blue: `#0A84FF`
- Audio Purple: `#6F5CFF`
- Record Pink: `#FF6B8A`

Design rules:
- Use waveform previews on recording, processing, and result screens.
- Waveforms must be genre-aware: keep the base pink/purple Skarly aura, then add an intertwined genre-colored line for the selected style.
- Use a polished clean progress-ring record control, paired with a vocal length bar for the 30-second limit.
- Use genre tiles with clear selected states.
- Use compact native-app cards instead of marketing-style cards.
- Make every screen's primary action obvious.
- Keep the prototype free-tool feeling; do not add pricing, premium labels, or subscription messaging.
- Avoid overdecorated prototype cues: no neon glow, no blurred color blobs, no overused bright gradients, and no excessive glassmorphism.
- Use Apple-style system typography only through `-apple-system` / SF Pro defaults. Do not introduce other font families.
- Avoid bland flat black: use layered charcoal surfaces, subtle inner highlights, stacked Health-style charts, and selective blue/purple/pink accents.
- Use clear icons for play, download, share, regenerate, settings, generate, retry, error, and success states.
- Processing success uses an animated blue check/tick pop; active generation uses a generate symbol; retry/error states use distinct retry/error symbols.
- Use specific action icons: `Enter` for Continue as Guest Creator and Enter Studio, `Mic` for Start Creating, and `Process` for processing/generating job states.
- Guest Creator and Saved Creator cards use a dedicated aligned creator-label layout with icon badge, title, subtitle, and state chip.

Creator Workspace model:
- Do not frame the user model as only guest versus signed-in. Use creative storage language instead.
- Login must be choice-first: user taps `Guest Creator` or `Saved Creator` before details are shown. Saved Creator details appear only after that path is selected.
- `Guest Creator`: can record, generate, download, and keep temporary drafts during the current session.
- `Saved Creator`: can keep history, rename tracks, save defaults, and sync later when Firebase is connected.
- Track ownership states: `Temporary`, `Saved`, `Downloaded`, `Processing`, `Failed`, and `Retry`.
- Voice privacy controls: private by default, delete raw recording, keep final mix only, export data later, delete account later.
- First-run prompt asks what the user is making: demo song, hook idea, vocal practice, or fun experiment.

## Figma Handoff
Create named Figma styles before drawing final screens:
- Color styles: `Background/App Black`, `Surface/Card Charcoal`, `Surface/Elevated Gray`, `Text/Primary`, `Text/Secondary`, `Accent/Health Blue`, `Accent/Audio Purple`, `Accent/Record Pink`.
- Text styles: `Large Title 34/41 Bold`, `Title 24/30 Semibold`, `Headline 17/22 Semibold`, `Body 15/21 Regular`, `Caption 12/16 Medium`.
- Layout tokens: mobile frame `390 x 844`, screen padding `20`, component gap `12`, section gap `24`, card radius `24-28`, bottom navigation height `64`.
- Effect style: dark-mode depth only, up to `0 26 70 rgba(0,0,0,.42)`, plus subtle inner card highlights. Do not use neon outer glows.
- Components to create first: AppShell, BottomNav, CreatorWorkspaceCard, CreatorSetup, AudioRecorder, AuraWaveform, GenreTile, ProcessingSteps, MusicPlayer, TrackListItem, UploadPicker.

## Screen Blueprint
Splash:
- Purpose: brand signal and short loading moment.
- Primary UI: Skarly title, waveform mark, tagline.
- Empty/error state: route fallback to login/home if startup check fails.

Login/Signup:
- Purpose: choose storage level without blocking creation.
- Primary UI: tappable Guest Creator and Saved Creator cards first; Saved Creator detail fields appear only after selecting that card; continue as Guest Creator remains available without details.
- Future integration: Firebase Auth.
- Error states: invalid email, failed login, offline.

Creator Setup:
- Purpose: personalize the first session without adding social features.
- Primary UI: intent choices for demo song, hook idea, vocal practice, and fun experiment; default vibe selector; enter studio action.
- States: no intent selected, intent selected, default vibe selected.

Home:
- Purpose: start creation quickly.
- Primary UI: Start creating, Upload vocal, Today's Studio card, draft counts, recent tracks with ownership chips.
- Empty state: no tracks or drafts in this workspace yet.

Record Voice:
- Purpose: capture the vocal take.
- Primary UI: clean progress-ring record control, vocal length bar, aura waveform, max 30-second cue, retry/use-take actions.
- States: idle, recording, paused/stopped, max duration reached, permission denied.

Upload Audio:
- Purpose: choose a vocal file instead of recording.
- Primary UI: file picker area, supported format note, selected-file preview.
- States: empty, selected, unsupported format, too long, too large.

Choose Genre:
- Purpose: select one style for generation.
- Primary UI: 8 genre tiles, selected state, Generate preview action.
- Each genre tile should include a tiny intertwined waveform preview using that genre's color identity.
- States: no selection, selected, disabled while processing.

Processing:
- Purpose: show progress while dummy or real backend job runs.
- Primary UI: animated/static waveform, stage list.
- Stages: uploading, analyzing, generating, mixing, ready.
- Failure state: failed with retry and back-to-genre actions.

Result Player:
- Purpose: play final MP3 and expose next actions.
- Primary UI: title, genre, waveform/player, play/pause, download, share.
- Future state: regenerate disabled or marked as later.

Download/Share:
- Purpose: save or share final MP3.
- Primary UI: download confirmation, share action, save-to-workspace state.
- Error states: download failed, share unavailable.

History:
- Purpose: list private workspace tracks.
- Primary UI: track rows with title, genre, ownership/status chip, date, play/retry action.
- States: empty, temporary, saved, downloaded, processing, failed, retry.

Profile/Settings:
- Purpose: creator identity, defaults, and voice privacy surface.
- Primary UI: Guest/Saved Creator identity, privacy actions, default vibe, export/delete placeholders.
- Future integration: delete account, export data, Firebase user profile.

## Phase 3 Frontend Component Map
Recommended React Native/Expo components:
- `AppShell`: safe area, page background, bottom tabs, screen padding.
- `CreatorWorkspaceCard`: shows Guest/Saved Creator state, temporary draft count, and saved/history affordance.
- `CreatorSetup`: first-run intent selector and default-vibe selector.
- `AudioRecorder`: clean progress ring, recording state, vocal length bar, permission handling.
- `AuraWaveform`: animated flowing SVG ribbon for recording, processing, and result playback states; accepts a genre variant for the intertwined color layer.
- `GenreWavePreview`: tiny two-line waveform inside each genre tile using the same genre color token as the full AuraWaveform.
- `UploadPicker`: file selection, validation display, selected file preview.
- `GenreTile`: genre title, accent color, selected state.
- `ProcessingSteps`: current backend/dummy job stage and failure retry.
- `MusicPlayer`: playback controls, waveform, metadata, download/share.
- `TrackListItem`: history row with status and quick action.
- `OwnershipChip`: temporary, saved, downloaded, processing, failed, retry, and private chips.
- `IconButton/IconSymbol`: reusable symbols for play, download, share, regenerate, settings, generate, retry, error, and animated success tick.

Dummy data to use first:
- Sample track title: `Midnight Morph`
- Sample genre: `Lo-fi`
- Sample duration: `00:30`
- Sample status sequence: `uploading -> analyzing -> generating -> mixing -> ready`
- Sample workspace state: `Guest Creator` with `2` temporary drafts and `0` saved tracks.

## Acceptance Criteria
- A frontend developer can start Phase 3 without deciding MVP scope again.
- The app flow is clear from home to result download/share.
- All screens have purpose, primary action, and states, including Creator Setup.
- The visual style is polished and tool-like, not a streaming clone.
- The design supports dummy frontend behavior before backend integration.
- The MVP excludes remixing existing songs, AI voice cloning, payments, and social feed.
- The 8 roadmap genres are locked and represented in the UI.
- Creator Workspace states are visible without requiring backend auth.

## Reference Direction
- Apple Health-style app structure: dark canvas, rounded metric cards, large default-looking headings, and calm progress/status views.
- Apple typography and hierarchy: Apple Human Interface Guidelines, especially system text styles and readable hierarchy.
- Waveform and recording UI inspiration: SoundLab, WaveEditor, audio editor apps.
- Player polish inspiration: Cloud Player UI, Mume Music Player UI Kit, Music Mobile App UI Kit.
- Product distinction: Skarly should look like a creation tool, not a Spotify-style listening app.
