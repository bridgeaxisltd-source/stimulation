# stimulation ⚽ 11 prime Messis vs 11 prime Ronaldos

This is a Monte Carlo football simulator. Every outfield spot and the goalkeeper
spot on one team is **2011-12 Messi**, and every spot on the other is
**2013-14 Ronaldo**. The engine plays thousands of matches using each player's
ability *and* personality (ego, patience, selfishness, work rate, clutch), then
reports who comes out on top and why.

Pure Python 3.10+, no dependencies.

```bash
python -m stimulation                      # 2,000 matches, league rules (draws allowed)
python -m stimulation -n 10000             # more matches = tighter confidence interval
python -m stimulation --knockout           # extra time + penalty shootout, always a winner
python -m stimulation --single --seed 7    # one match with the goal log
python -m stimulation --neutral-personality   # every trait set to 50: ability only, no ego
python -m stimulation --home-formation 4-2-3-1 --away-formation 3-5-2
python -m stimulation --away messi         # mirror match (sanity check: should be ~even)
python -m stimulation --json > results.json
python -m unittest discover -s tests       # run the tests
```

## Current result (v0.1, 10,000 matches, seed 42)

| | Team Messi | Team Ronaldo |
|---|---|---|
| **Win rate** | 29.6% | **55.4%** (draw 15.0%) |
| Knockout win rate | 34.9% | **65.1%** |
| Goals / xG | 3.30 / 3.29 | 4.07 / 3.73 |
| Possession | **58%** | 42% |
| Pass accuracy | **78%** | 63% |
| Aerial duels won | 27.5 | **46.5** |
| Goals from headers | 1% | **30%** |

**What the model says:** the Messis control the ball, but the Ronaldos win the
match. With nobody on the pitch who can truly defend, possession matters less
than turning chances into goals, and the Ronaldos get a whole extra way to score
(crosses, corners and headers) that the Messis can neither use nor stop.
Setting every personality trait to neutral (`--neutral-personality`) narrows
it only slightly (34.5% vs 51.2%), so in this model the gap comes from
**physical ability, especially in the air**, not from ego.

> These ratings are hand-estimated, so treat the result as a hypothesis,
> not a verdict. Changing a few numbers in `data/players.json` can move it.
> Making those numbers data-driven is the next milestone (see Roadmap).

## How it works

```
data/players.json ──► data_loader.py ──► PlayerProfile (attributes + personality)
                                               │
                         models.py: Team = player × formation (4-3-3, 4-4-2, 3-5-2, 4-2-3-1)
                                               │
                     engine.py: MatchEngine.play()  ◄── one seeded random.Random per match
                                               │
                 monte_carlo.py: run N matches (parallel) ─► SimulationSummary
                                               │
                         report.py: terminal table / JSON
```

### 1. The pitch is 5 zones, not x/y coordinates
Zones are always seen from the team on the ball:
`0 own box → 1 own third → 2 midfield → 3 final third → 4 opponent's box`.
When the ball is lost the zone is mirrored (`4 - zone`), so if you lose it in
your final third (zone 3), the other team picks it up in their own third (zone 1).
A full 2D physics engine would look nicer but would be much slower. It would also
not be more *accurate* until we have positional data to calibrate it.

### 2. Each step: choose an action (`_choose_action`)
Each zone has base weights for `short_pass`, `through_ball`, `dribble`,
`long_ball`, `cross` and `shot`. Those weights are then bent by:
- **attributes**: good dribblers dribble more (`(dribbling/80)²`), and teams with
  aerial power cross more (`(aerial/70)²`)
- **personality**:
  - `patience` and `teamplay` add more short passes
  - `selfishness` adds more shots
  - `ego` is the **ego modifier** from the original plan: up to ×1.5 more
    long-range shots from the final third, whatever the passing lanes look like
  - `clutch` adds more shots after 75' when level or behind

### 3. Resolve it as a duel (`_contest`)
`P(success) = sigmoid(base + (attack_rating − defence_rating − 50) / 25)`.
Ratings are composites. For example, dribble is `0.45·dribbling + 0.2·agility +
0.2·balance + 0.15·acceleration`, and the defender's tackle rating mixes
tackling, strength, pace and marking. Several modifiers then shift the logit:
- **zone congestion**: the box is packed, so everything is harder there
- **defensive cover**: comes from the formation (more defenders → harder)
- **pressing**: the opponent's `work_rate`, which only applies when you build from the back
- **ego crowding**: high-ego teams fight over the same central spaces, so their
  passes near goal fail more often
- **fatigue**: from `stamina`, and it costs more for high `work_rate` teams

### 4. Set pieces and transitions
- Failed dribbles can **draw fouls**: free kicks, plus a penalty in the box.
  This favours the Messis, who won 13 fouls a game vs 9.
- **Corners** come from saves, blocks and cleared crosses. Low-aerial teams play
  them short, which is what the Messis do.
- **Counter-attacks** after a turnover depend on the winner's pace and
  directness (`1.5 − patience`) and on how lazy the losing team's `work_rate` is.
- **Goalkeeper**: an outfield player, rated at 60% of a mix of jumping, agility,
  composure and height. Height also helps against headers and long shots.

### 5. Monte Carlo (`monte_carlo.py`)
Match `i` uses `Random(seed * 1_000_003 + i)`, so results can be reproduced
exactly and parallel runs equal serial runs. Teams take turns kicking off.
The win rate is reported with a 95% confidence interval: if the intervals of
two teams overlap, you haven't simulated enough matches to call a winner.

## Honest limitations
- **The ratings are my estimates**, not scraped data. Only `reference` (season
  goals/apps) contains real numbers.
- Calibration aims for believable totals: about 22-33 shots and 3-4 goals per
  team. The total is high on purpose: there are 22 attackers, no real
  defenders and outfield players in goal.
- The model doesn't simulate individual positions *within* a zone, off-ball
  runs, offsides, cards or substitutions.

## Roadmap
1. **Data pipeline**: a Playwright scraper for messivsronaldo.app (the site is
   rendered client-side, so first check its XHR/JSON endpoints in DevTools →
   Network). Save the raw stats to `data/raw/`.
2. **Derive ratings**: map the stats to attributes, e.g. dribble success % →
   `dribbling`, aerial duels won → `heading`/`jumping`, key passes →
   `vision`, outside-box goals → `long_shots`. Keep the formulas in code so
   every rating can be traced back to a stat.
3. **Sensitivity analysis**: vary each attribute ±5 and record how much the win
   rate moves. This shows which attributes actually decide the result.
4. **Visual replay**: a web page (Next.js) that streams one match's events.
5. More players and eras: add any profile to `players.json` and pass `--home <id>`.
