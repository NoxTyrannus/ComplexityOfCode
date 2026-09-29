Execution-based coding-agent benchmarks return one bit per task — the tests pass, or they do not. Three years of leaderboard progress tell us agents increasingly produce passing patches. They say nothing about what those patches do to the *structure* of the code they land in.

I built a static, execution-free instrument that measures what those benchmarks cannot, and then used it to show that the most natural way to score "structural complexity" is maximally fooled by the one change that most degrades structure.

## Three axes, deliberately not collapsed

- **S — structure**, at two granularities: the module import graph (**S1**) and the symbol-level call graph (**S2**).
- **C — coupling**: public interface exposure, cross-package import fraction, external-dependency load.
- **L — node logic**: McCabe cyclomatic complexity *and* expression-nesting depth / boolean density, because McCabe is blind to a single 40-token chained expression that contains no branch at all.

The axes are not collinear (r = +0.09, +0.11, −0.18), which is what makes the trade-off observable at all.

## What I found

**1. Structural and node-level complexity are negatively correlated, and the granularity decides whether you see it.** Across 14 mature Python projects, call-graph cyclomatic complexity per symbol and mean McCabe complexity correlate at **r = −0.880** (Spearman −0.754). At module granularity the same pairing gives **r = −0.175**. Dense call structure buys simple functions — the complexity is in the wiring. An evaluator measuring "architectural complexity" at the module level would conclude the axes are independent, and would be wrong.

**2. The relationship is not one project's artifact.** *black* has high leverage on a 14-point correlation, so I report the full leave-one-out range: **r stays between −0.63 and −0.92 under removal of any single project**, and remains −0.63 with *black* removed.

**3. Under controlled perturbation, complexity moves rather than disappears.** Inlining private helpers removes a mean of **5.41% of call-graph edges** while raising mean function complexity in **10 of 11** affected projects; the two deltas correlate at **r = −0.741**. Conservation holds at 100% for expression-level inlining and module merging, and 90.9% for statement-level inlining. Dead-code removal, the one genuinely destructive operator, sits lowest — consistent with it being the one case where complexity is actually eliminated.

**4. An edge-count complexity metric is maximally fooled by the hub trap.** Routing every intra-package import through a single re-export gateway cuts dependency edges by **−52.7% on average** (−81.7% on *tox*, −69.8% on *sphinx*) — roughly ten times the movement of any other change. It is a hub: mean maximum in-degree rises from **23.1 to 41.9** (sphinx: 91 → 171). A five-constraint feasibility filter rejects it in **13 of 14** projects, and separately rejects a module-merging refactor that silently drops **101 public symbols**. Under the filter, the surviving ranking begins with the change that actually reduces structure while preserving behaviour.

## What I release

A three-axis static analyzer, seven semantics-preserving transformations, a five-constraint feasibility checker, and the full 98-cell result set. No GPU, no network, no LLM calls: three commands reproduce every number reported. Two methodological details are load-bearing and documented: a `noop` control (reformatting alone moves a line-based SLOC by >20%, swamping most real effects) and a formatting-invariant statement count.

## Limitations I want stated plainly

The perturbation experiments use synthetic operators, not agents — this instrument *predicts* agent behaviour, it does not *demonstrate* it, and the unmodified-code analysis is the load-bearing result. Behavioural equivalence is construction-provable for expression-level inlining, `compile()`-gated for all operators, and **full-test-suite-verified for none**. All 14 projects are single-language Python; I have no evidence about codebases with heavy dynamic dispatch, where my call-graph resolution is already lossy.
