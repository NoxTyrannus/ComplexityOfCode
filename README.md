# Complexity Is Conserved — reproduction package

Everything in the paper is reproducible from this directory with three commands.
No GPU, no network, no LLM calls. Total runtime ~25 minutes on one CPU core.

## Layout

```
src/analyze.py         three-axis static analyzer (S at two granularities, C, L)
src/transform.py       seven semantics-preserving code transformations
src/run.py             experiment driver: 14 projects x 7 operators x 5 constraints
src/analyze_results.py statistics: correlations, conservation, anti-gaming
src/figures.py         paper figures
src/assets.py          submission assets (card + media gallery), >=640x360
src/card.py            earlier card draft (superseded by assets.py)
src/repos.py           project -> package path / module name
out/paper.md           the submitted paper
out/analysis.txt       full statistics output
out/analysis.json      machine-readable results
out/raw.json           all 98 (project, operator) cells
out/baseline.json      the 14 unmodified projects
out/card_1280x720.png  card / thumbnail  (passes Kaggle's >=640x360 check)
out/card_1280x640.png  card, 2:1 variant
out/gallery_*.png      media gallery, 16:9
```

## Reproduce

```bash
# 1. fetch the 14 projects into ./data/ (default branch of each)
bash fetch_repos.sh

# 2. run the experiment  -> out/raw.json          (~12 min)
python3 src/run.py

# 3. statistics + figures -> out/analysis.*, *.png (~2 min)
python3 src/analyze_results.py
python3 src/figures.py
```

Requires Python 3.11+ and `matplotlib` (analysis itself needs only the stdlib).

## The 14 projects

all from PyPI-registered maintainers, default branch at time of collection:
`anyio`, `black`, `click`, `flask`, `itsdangerous`, `jinja`, `jsonschema`,
`pytest`, `requests`, `setuptools`, `sphinx`, `tox`, `urllib3`, `werkzeug`.
Chosen for architectural variety (web frameworks, CLI, test runner, doc tool,
async runtime, data validation, build tool, HTTP stack) rather than popularity.

## Three methodological points that materially affect the numbers

**1. The `noop` control is not optional.** Every measurement is taken on
`ast.unparse` output. Reformatting reflows multi-line expressions onto single
lines and moves a line-based SLOC by more than 20% — larger than most effects
we measure. Every operator is therefore applied *on top of* the noop output and
compared *against* the noop output. Package size is measured as **AST statement
count**, which is invariant under reformatting.

**2. Granularity is a variable, not a detail.** `S1` is the module import graph;
`S2` is the symbol-level call graph. The headline anti-correlation exists only at
S2 (r = -0.88) and is nearly absent at S1 (r = -0.18). Measuring at the wrong
granularity would have led us to conclude the axes are independent.

**3. K5 is on the module graph, deliberately.** We first tried to detect hub
concentration via maximum fan-in on the *call* graph; it never fired, because a
re-export gateway produces no resolvable call edges. The hub anti-pattern lives
on the import graph. K5 is placed there and rejects `facade` in 13 of 14
projects. This is reported in the paper as the constraint we had to add after
observing the failure, not as a constraint we anticipated.

## Known limitations of this package

- Behavioural equivalence of the operators is established by construction for
  `inline`, by a `compile()` gate for all operators, and by a full test-suite
  run for **none**. `guard` in particular is a no-op modulo exception-chaining
  context.
- The operators are synthetic. Experiments 1 (natural cross-project
  variation) is the load-bearing result; Experiments 2–4 establish mechanism.
- `S2` call resolution is lexical (module-level defs and imported symbols only)
  and does not model `getattr`, decorators that rebind, or dynamic dispatch.
