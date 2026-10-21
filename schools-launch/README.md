# BridgeAxis OS — 15s launch video (schools.bridgeaxisltd.com)

`bridgeaxis-os-launch.mp4`: 15.0s, 1920×1080 (16:9), 60fps, H.264 + AAC, −14 LUFS.

Built from the real product in `bridgeaxisltd-source/parentconnect` (BridgeAxis OS):

- **Landing:** the `/schools` page from a normal production build of `apps/web` (the same page
  `schools.bridgeaxisltd.com` serves): hero, package cards, rollout steps and the conversation section.
- **App:** a real click-through of the browser-only demo build (`VITE_STATIC_DEMO=true`, the same
  sample-data workspace as `demo.bridgeaxisltd.com`): Home → Admissions → Attendance → Analytics → SMS wallet,
  driven through the sidebar like a user. The hover states and click positions are captured, not drawn.
  The demo-only notice bar is hidden and the first-visit guided tour is marked as seen.
- **Brand:** the vector mark from `apps/web/public/platform/brand-symbol.svg`, the serif
  "BridgeAxis OS" wordmark, navy `#12365d`, teal `#009fa3`, paper `#edf8fb`.
- **Type:** the site specifies Georgia (headings) and Inter (body) but loads no webfonts, so each
  visitor sees whatever their device has. The video uses Inter and **Gelasio**, an open-source,
  metric-compatible stand-in for Georgia, so it looks like the intended design.

## Storyboard (128 BPM, 32 beats; B minor → D, "calmer" progression)

| Beats | Time | Scene |
|---|---|---|
| 0–4 | 0.0–1.9s | The mark assembles from its four real pieces (ticks), wordmark reveals, "A calmer way / to run your / school." then **match-cuts** into the real hero H1 |
| 4–8 | 1.9–3.8s | The landing page in a browser; the cursor clicks **Explore the demo**, the URL turns to demo.bridgeaxisltd.com |
| 8–20 | 3.8–9.4s | **Drop.** Inside the app: group + link clicks on the beat: Admissions, Attendance, Analytics, SMS wallet, with a caption card; punch into the ₦15,320 SMS balance |
| 20–24 | 9.4–11.3s | "Start with what your school needs now.": the four real package cards land on 8ths, Academic Suite lifts |
| 24–28 | 11.3–13.1s | "Move at a pace your team can manage.": rollout steps reveal one per 8th |
| 28–32 | 13.1–15.0s | "Let's talk about your school.", click **Book a conversation**, end card with the mark, the tagline, schools.bridgeaxisltd.com and hello@bridgeaxisltd.com |

## Rebuild

```bash
# In bridgeaxis-os (parentconnect repo), apps/web:
bun install
bunx vite build --outDir /tmp/site && bunx vite preview --outDir /tmp/site --port 4174   # landing
VITE_STATIC_DEMO=true bunx vite build && bunx vite preview --port 4173                    # demo app

# Here:
node capture.js /tmp/cap      # then: hovers -> assets/ui/, other PNGs -> assets/, rects.json -> assets/ui/
python3 ../video-kit/synth.py .
node ../video-kit/render.js . video silent.mp4
ffmpeg -i silent.mp4 -i music.wav -map 0:v -map 1:a -c:v copy \
  -af "loudnorm=I=-14:TP=-1:LRA=7" -ar 48000 -c:a aac -b:a 256k \
  -shortest -movflags +faststart bridgeaxis-os-launch.mp4
```

`measure.js` prints the hero H1 geometry used for the intro match cut.
