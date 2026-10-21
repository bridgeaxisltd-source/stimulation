# MagicPath — 15s motion showreel

`magicpath_showreel.mp4` — 1920×1080, 60 fps, H.264 + AAC. Unofficial concept film / portfolio piece.

| Time | Section | What happens |
|---|---|---|
| 0–2s | Path | A neon path writes itself across the frame and lands as the dot of the "i" |
| 2–4s | Identity | Shockwave, masked wordmark reveal, then a zoom *through* the i-dot |
| 4–6.5s | Prompt | A brief gets typed, enter is hit, the prompt bar morphs into a design frame |
| 6.5–10s | Generate | Elements generate from skeletons, the camera pulls back to 3 variations, a cursor selects a card |
| 10–12.5s | Code | The card is wired line by line to its React code, then shipped |
| 12.5–15s | Signature | Everything implodes, the path draws an ∞ and becomes the logo lockup |

## How it's built
- `reel.js`: a Canvas 2D engine where every frame is a pure function of time. It renders 4 sub-frames per frame, blended into real motion blur.
- `render.mjs`: drives headless Chromium (Playwright) frame by frame and pipes the frames into ffmpeg.
- `audio.py`: a 120 BPM soundtrack synthesized from scratch with numpy, with each hit synced to a visual cue.

```bash
python3 audio.py                     # out/reel_audio.wav
node render.mjs                      # out/reel_silent.mp4  (~3 min)
ffmpeg -i out/reel_silent.mp4 -i out/reel_audio.wav -c:v copy -c:a aac -b:a 256k -shortest magicpath_showreel.mp4
node render.mjs --stills 2.6,9.3     # inspect single frames
```
Open `index.html` for a live preview (space = pause, ←/→ = scrub).
