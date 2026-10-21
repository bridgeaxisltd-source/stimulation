# video-kit

The shared engine behind `launch-video/` and `parentconnect-promo/`. A project is a folder with:

- `timeline.json`: bpm, beats, fps, duration, optional width/height, the beat lists
  (`clicks`, `ticks`, `impacts`, `whooshes`) and a `music` block (chords, bass, cutoffs,
  build, drop, end, breaks, fills, rolls, risers, stab, tail).
- `video.html`: a page exposing a deterministic `window.render(t)` and a `window.ready` promise.
  `__TIMELINE__` (and optionally `__RECTS__` from `assets/ui/rects.json`) get injected.
- `assets/`

Tools:

- `node render.js <project> stills 1.2 3.4` writes preview frames to `<project>/stills/`.
- `node render.js <project> video out.mp4` renders every frame through Playwright into H.264.
- `python3 synth.py <project>` synthesises `<project>/music.wav` (numpy only), with the UI clicks on the beat grid.
- `python3 sheet.py out.png frames...` makes a contact sheet for reviewing stills.

Since visuals and audio both read the same beat lists, cuts and clicks stay in sync.
