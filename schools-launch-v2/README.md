# BridgeAxis OS — 15s launch reel (v2), schools.bridgeaxisltd.com

`bridgeaxis-os-reel.mp4`: 15.0s, 1920×1080, 60fps with 5-sample motion blur (180° shutter),
H.264 + AAC, −14 LUFS. v1 (flat screenshots in a browser frame) is in git history at `7a819c8`.

## What changed from v1

- **The UI is animated, not panned.** `capture.js` isolates every real component of the running app
  (sidebars, top bars, stat cards, table rows, class cards, balance cards, the landing preview,
  package cards, rollout steps, the conversation card) on transparency at 3× density, and records
  each component's rect. The reel assembles them in 3D exactly where they live in the product.
- **Live numbers.** Numbers are blanked in the captures, and their text, position and computed font
  are stored in `assets/meta.json`. The reel counts them up in the same type: 642 / 28 / 12 / 93%,
  class averages to 87.0 / 47.7 / 78.2 / 79.8%, ₦15,320 / 1,532 / ₦10.
- **Every click causes something.** *Refresh attendance* brings in the live check-ins (each "SMS queued");
  clicking the *Primary 5 Gold* card shows its real hover state; *Refresh balance* counts the SMS wallet up.
- **Concept:** the site's own line, "Everything your school needs, in one place". The hook's four module
  components converge and become the four pieces of the mark.
- **Motion blur** (`video-kit/render.js`, opt-in via `motionBlur` in the timeline).
- **New track** (`music.py`, built on `video-kit/synthlib.py`): D–A–Bm–G, chord stabs on every hook word,
  a lead hook, offbeat house stabs and bass, a reverse cymbal into the drop, a one-beat break, a half-time
  rollout section, and UI clicks on the beat.
- **Verified sync:** `video-kit/sync_check.py` decodes the audio from the final MP4 and measures every
  click, hook stab and impact against the timeline.

## Storyboard (128 BPM, 32 beats)

| Beats | Time | Scene |
|---|---|---|
| 0–2 | 0.0–0.9s | Navy hook: "Admissions. / Attendance. / Analytics. / Parents." on 8ths, each over its real component flying in from depth |
| 2–4 | 0.9–1.9s | White wipe: "Everything your school needs, in one place."; the components converge into the mark |
| 4–8 | 1.9–3.8s | Wordmark, "A calmer way to run your school." match-cuts into the real hero; preview lifts off and counts up; click *Explore the demo* |
| 8–20 | 3.8–9.4s | **Drop.** The app builds itself; 4 modules × 3 beats: Admissions, Attendance (refresh → rows), Analytics (count → open class), SMS wallet (refresh → balance, punch-in) |
| 20–24 | 9.4–11.3s | Package cards: deck → fan → row; Academic Suite lifts; click *Discuss this package* |
| 24–28 | 11.3–13.1s | Rollout steps flip in on 8ths along a drawn path |
| 28–32 | 13.1–15.0s | "Let's talk about your school."; click *Book a conversation*; the mark re-assembles on the end card |

## Rebuild

```bash
# BridgeAxis OS (parentconnect repo), apps/web: landing on :4174, demo on :4173
bunx vite build --outDir /tmp/site && bunx vite preview --outDir /tmp/site --port 4174
VITE_STATIC_DEMO=true bunx vite build && bunx vite preview --port 4173

node capture.js assets                         # component layers + assets/meta.json
python3 music.py .                             # -> music.wav
node ../video-kit/render.js . stills 4.3 8.5   # preview frames
node ../video-kit/render.js . video silent.mp4 # ~13 min with motion blur
ffmpeg -i silent.mp4 -i music.wav -map 0:v -map 1:a -c:v copy \
  -af "loudnorm=I=-14:TP=-1:LRA=7" -ar 48000 -c:a aac -b:a 256k \
  -shortest -movflags +faststart bridgeaxis-os-reel.mp4
python3 ../video-kit/sync_check.py bridgeaxis-os-reel.mp4 timeline.json
```

Capture notes: brand fonts are applied (Gelasio stands in for Georgia; the app's `system-ui` renders as
Inter here), the demo-only notice bar is hidden, and the first-visit guided tour is marked as seen.
All data shown is the demo workspace's sample data (Greenfield Academy).
