# stimulation ⚽ 11 Messis vs 11 Ronaldos

A Monte Carlo football simulator. Every position on one team, keeper included,
is **Messi**, and every position on the other is **Ronaldo**. The ratings come
from their **all-time career stats** on
[messivsronaldo.app](https://www.messivsronaldo.app/detailed-stats/). The engine
is calibrated against real football numbers, and it reports who wins and why.

Pure Python 3.10+, no dependencies.

```bash
python -m stimulation                        # 2,000 matches, league rules (draws allowed)
python -m stimulation -n 10000 --knockout    # extra time + penalties, always a winner
python -m stimulation --single --seed 7      # one match with the goal log
python -m stimulation --show-ratings         # every rating + whether it came from data or an estimate
python -m stimulation --calibrate            # check the engine against real-world benchmarks
python -m stimulation --neutral-personality  # every trait set to 50: ability only, no ego
python -m stimulation --estimates-only       # ignore the real stats, use hand estimates
python -m stimulation --away messi           # mirror match (sanity check: should be ~even)
python -m unittest discover -s tests
```

## Current result (v0.2, 10,000 matches, seed 42)

| | Team Messi | Team Ronaldo |
|---|---|---|
| **Win rate** | **52.7%** | 31.6% (draw 15.8%) |
| Knockout win rate | **60.3%** | 39.7% |
| Goals / xG | 4.15 / 3.64 | 3.50 / 2.66 |
| Possession | **63%** | 37% |
| Pass accuracy | **89%** | 81% |
| Penalties won | **0.75** | 0.27 |
| Aerial duels won | 12.1 | **23.5** |
| Goals from headers | 4% | **35%** |

**What the model says:** the Messis win, but not by a landslide. They keep the
ball, win more fouls and penalties, and turn more of their chances into high-quality
shots. The Ronaldos still have a real threat: about a third of their goals are
headers. Even so, crosses complete less than 40% of the time against anyone, so
that route can't make up for having the ball only 37% of the time.

**The data decided it, not me.** The same engine with my old hand-estimated
ratings (`--estimates-only`) gives Ronaldo 50%, Messi 34%. Switching to the
messivsronaldo.app numbers flipped it. Messi's real edges are 4.43 vs 2.00
successful dribbles per 90, 0.82 vs 0.15 through balls, 0.80 vs 0.36 big chances
created, and +33 goals above xG vs +4.6. They outweigh Ronaldo's edges of 1.38 vs
0.20 aerials and 83.6% vs 76.5% penalties.

Ego barely matters: with every personality trait set to neutral it's 51% vs 35%.

## Where the numbers come from

### 1. Real stats → ratings (`stimulation/derive.py`)
`data/stats/messivsronaldo_detailed.json` holds the site's career numbers (site
updated 28 Sep 2026). Each data-backed rating comes from one stat through a
piecewise-linear scale, and `--show-ratings` prints the trail:

| Rating | Stat | Messi → rating | Ronaldo → rating |
|---|---|---|---|
| dribbling | successful dribbles /90 | 4.43 → 99 | 2.00 → 85 |
| vision | accurate through balls /90 | 0.82 → 98 | 0.15 → 73 |
| short passing | key passes /90 | 2.49 → 95 | 1.66 → 84 |
| finishing | goals per shot | 0.183 → 92 | 0.156 → 86 |
| composure | goals above xG | +15% → 97 | +2% → 87 |
| long shots | open-play outside-box goals / game | 0.093 → 94 | 0.054 → 83 |
| free kicks | FK goals / game | 0.065 → 92 | 0.049 → 84 |
| penalties | conversion | 76.5% → 80 | 83.6% → 90 |
| heading | aerial duels won /90 | 0.20 → 49 | 1.38 → 84 |
| selfishness | shots ÷ (shots + key passes) | 67% → 64 | 80% → 89 |
| teamplay | big chances created /90 | 0.80 → 95 | 0.36 → 74 |
| clutch | G+A /90 in finals & UCL KOs | 0.91 → 89 | 0.82 → 83 |

**12 of the 29 ratings per player come from data.** The other 17 have no stat
on the site behind them and are still my estimates: pace, strength, jumping,
tackling, ego, patience, work rate and so on. Height is real.

### 2. Calibration (`stimulation/calibrate.py`, `data/benchmarks.json`)
Every duel is measured **relative to an average top-flight starter**. Run
`--calibrate` and the engine has to pass all of these:

| Check | Engine | Real-world target | Source |
|---|---|---|---|
| Avg vs avg: goals per team | 1.44 | 1.2–1.6 | top-5 leagues 2025/26 |
| Avg vs avg: crosses per team | 11.4 | 8–15 | PL: 22.4 per match |
| Avg vs avg: cross completion | 21.6% | 17–27% | PL: 21.7% |
| Avg vs avg: headed goal share | 22.5% | 12–24% | PL: 16.3–21.3% |
| Avg vs avg: shots per goal | 9.6 | 7.5–11.5 | league norms |
| 11 Messis: dribble success | 63% | 55–68% | Opta: 57.2% / 66.0% |
| 11 Messis: shots per goal | 4.7 | 4.6–6.6 | site: 5.45 |
| 11 Ronaldos: shots per goal | 6.9 | 5.4–7.6 | site: 6.43 |
| 11 Messis: pass accuracy | 86% | 84–94% | Pep's Barça 89.6% |
| 11 Messis: possession vs avg | 58% | 55–80% | Pep's Barça 66–73% |

Two checks matter most. The **average vs average** checks make a normal match look
normal. The **per-player** checks fix how much an elite rating is worth. Without
the second set, an early version gave Messi 94% dribble success and 11 goals a
game. That broke against Messi's real numbers: even the best dribbler ever beats
his man only about 6 times in 10.

**Judgement call, out in the open:** the possession floor started at 62% ("11
Messis should match Pep's Barça"). After pass accuracy was anchored to real
rates, the engine gave 58%. I lowered the floor to 55% instead of forcing the
number up, because Pep's Barça also had Xavi, Iniesta and Busquets, who were
better pure passers and defenders than Messi.

## How the engine works (`stimulation/engine.py`)
- **5 zones** (own box → opponent box), always seen from the team on the ball.
  When the ball is lost, the zone is mirrored.
- **Choosing an action:** the player on the ball picks a pass, through ball,
  dribble, long ball, cross or shot. Base weights per zone are bent by stats and
  personality: patience means more recycling, selfishness means more shots, and
  ego means more long shots (up to ×1.5).
- **Resolving it:** `P(win) = sigmoid(base + (attack − defence) / 50)`, using
  ratings relative to an average starter. `base` is the average-vs-average rate,
  and the slope (50) is anchored to the real Messi/Ronaldo per-action rates.
- **What decides possession** is technique, not muscle:
  - **press resistance** (control, agility, balance, composure)
  - **counter-pressing** (work rate: winning the ball back right after losing it)
  - **patience** (recycle the ball rather than force it forward)
- **Physical stuff matters where it should:** aerial duels (heading, jumping,
  strength, height), keeper reach, and pace on counter-attacks.
- **Set pieces:** fouls drawn by dribblers, penalties, short corners for teams
  that are weak in the air, and outfield players in goal (×1.3 penalty, height
  helps against high balls).

## Honest limitations
- **Career stats, not prime seasons.** Both players' numbers include
  post-peak years (Ronaldo at Juventus, Man Utd and Al Nassr; Messi at PSG and
  Inter Miami). Prime-season figures from search snippets show the same picture:
  Messi 2011-12 had 222 successful dribbles and 125 key passes, while Ronaldo
  2013-14 had 92 dribbles and 70 key passes. They aren't used until the scraper
  can verify them.
- 17 of 29 ratings per player are still estimates. Ronaldo's `work_rate` (40)
  and Messi's (60) matter for possession and aren't backed by data yet.
- **Transcribed by hand.** The stats were copied from screenshots. The
  scraper (below) should replace that.

## Roadmap
1. **Scraper:** use Playwright to read messivsronaldo.app (season pages + detailed stats) into
   `data/stats/`. This needs the site allowed in the environment's network policy.
2. **Prime mode:** `--era prime` would use 2011-12 Messi and 2013-14 Ronaldo season stats
   instead of career stats.
3. **More data-backed ratings:** tackles and interceptions per 90 for work rate,
   and sprint data for pace.
4. **Back-testing:** model real teams (e.g. Barcelona vs Newcastle 2026, 8-3 on aggregate)
   and check the engine predicts sensible results.
5. **Sensitivity analysis:** vary each rating by ±5 and see which ones decide the result.
