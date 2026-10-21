# ParentConnect — 15s vertical promo

`parentconnect-promo.mp4`: 15.0s, 1080×1920 (9:16), 60fps, H.264 + AAC, −14 LUFS.
Made for Instagram Reels, TikTok, YouTube Shorts, Facebook Reels and WhatsApp Status.
Key content stays inside y ≈ 220–1550, clear of the platforms' caption and button overlays.

All product UI is cut from the real ParentConnect images in `bridgeaxis-website/public`
(roster + submitted phones, dashboard stat cards, trend chart, notification feed); copy
comes from the live site and the ParentConnect mockups. The track uses the same synth as the launch
video in a brighter key (F–C–G–Am, resolving to C), with taps on the beat.

## Storyboard (128 BPM, 32 beats)

| Beats | Time | Scene |
|---|---|---|
| 0–4 | 0.0–1.9s | Hook on navy: clock ticks, **"8:15 AM."** slams in, *Is every child accounted for?* |
| 4–8 | 1.9–3.8s | **Search. → Confirm.**: roster phone, zoom on search, taps *Mark Present* ×2, taps *Submit* |
| 8–14 | 3.8–6.6s | **Drop, Notify.**: phone flips to *Attendance Submitted*, the *Parent Notification Sent* card pops off the screen, parents' alert feed fills row by row |
| 14–20 | 6.6–9.4s | **Attendance visibility.**: four stat cards on half-beats, trend chart draws on, punch into 94.2% |
| 20–24 | 9.4–11.3s | Four features from the site, one per beat |
| 24–32 | 11.3–15.0s | ParentConnect logo + headline, tap *Explore ParentConnect*, demo contact, "Built by BridgeAxis" |

## Rebuild

```bash
python3 prep.py .                                   # crops + logo keying (inputs in assets/)
python3 ../video-kit/synth.py .                     # -> music.wav
node ../video-kit/render.js . stills 2.81 4.22      # optional preview frames
node ../video-kit/render.js . video silent.mp4
ffmpeg -i silent.mp4 -i music.wav -map 0:v -map 1:a -c:v copy \
  -af "loudnorm=I=-14:TP=-1:LRA=7" -ar 48000 -c:a aac -b:a 256k \
  -shortest -movflags +faststart parentconnect-promo.mp4
```

See `POSTING.md` for captions.
