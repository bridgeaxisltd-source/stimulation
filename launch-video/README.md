# BridgeAxis — 15s launch video

`bridgeaxis-launch.mp4`: 15.0s, 1920×1080 (16:9), 60fps, H.264 + AAC, loudness normalised to −14 LUFS.

Everything on screen comes from the real site (`bridgeaxisltd-source/bridgeaxis-website`):
the logo PNG, the brand tokens from `globals.css` (navy `#04234f`, deep navy `#031b3d`,
teal `#08a7a4` / `#058c8a`), its two typefaces (Bricolage Grotesque + Manrope), and
screenshots of the production build. Button and service-row hover states are real
captures of the site's `:hover` styles, not redraws. The music is synthesised from
scratch in numpy, and the UI clicks are placed on the same beat grid as the cursor presses.

## Storyboard (128 BPM, 1 beat = 0.469s, 32 beats)

| Beats | Time | Scene |
|---|---|---|
| 0–4 | 0.0–1.9s | Teal axis line draws, logo mark lands (impact), wordmark slides out (click), zoom through the teal leg |
| 4–8 | 1.9–3.8s | Hero headline "Technology / Built Around / How You Work." one line per beat; navy hero-plane sweeps in |
| 8–14 | 3.8–6.6s | **Drop.** Live site in a browser; cursor clicks *Explore Our Solutions* → scrolls to Services → hovers each row on 8th notes |
| 14–20 | 6.6–9.4s | ParentConnect: logo, headline, three product shots land on beats, click *Explore ParentConnect*, punch into the dashboard stats |
| 20–24 | 9.4–11.3s | Selected work: ParentConnect, Business Operations, Inventory & Logistics, CRM & Client Portal, one cut per beat with a click |
| 24–28 | 11.3–13.1s | "A clear path from idea to impact.": the real process timeline reveals node by node on 8ths |
| 28–32 | 13.1–15.0s | "Ready to build what's next?": click *Book a Consultation*, white end card grows out of the button: logo + bridgeaxisltd.com |

## Rebuild

Requires Node + Playwright (Chromium), Python 3 with numpy + Pillow, and ffmpeg.
`timeline.json` is the single source of truth for BPM, scene ranges and click/impact beats,
and both `video.html` and `synth.py` read it.

```bash
# 1. Serve the website build (from the bridgeaxis-website repo)
pnpm install && pnpm build && pnpm start -p 3123

# 2. Re-capture screenshots + hover states (only needed if the site changes)
node capture.js shots                     # then copy shots/*.png into assets/
node capture2.js assets/ui                # hover crops + element rects
python3 prep.py .                         # logo keying, button/strip crops

# 3. Render
python3 synth.py .                        # -> music.wav
node render.js stills 4.69 8.2            # optional preview frames -> stills/
node render.js video silent.mp4           # 900 frames -> H.264
ffmpeg -i silent.mp4 -i music.wav -map 0:v -map 1:a -c:v copy \
  -af "loudnorm=I=-14:TP=-1:LRA=7" -ar 48000 -c:a aac -b:a 256k \
  -shortest -movflags +faststart bridgeaxis-launch.mp4
```

(`prep.py` also expects the site's `public/` images copied into `assets/`; the committed
`assets/` folder already holds everything `video.html` uses.)
