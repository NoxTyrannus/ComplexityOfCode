# Complexity Is Conserved, Not Removed

## Structural and node-level complexity trade off in real codebases — and why scalar complexity metrics reward the trade

### Abstract

Execution-based coding-agent benchmarks return a single bit per task: the tests pass or they do not. Three years of leaderboard progress on SWE-bench and its successors tell us that agents increasingly produce passing patches. They say nothing about what those patches do to the *structure* of the code they land in. Meanwhile, five decades of software-metrics research attempted to compress code quality into a single number, and largely failed. We identify why: structural complexity and node-level complexity are not independent, and they are not positively correlated. Measuring 14 mature Python projects, call-graph cyclomatic complexity per symbol and mean intra-procedural McCabe complexity correlate at **r = -0.88** (Spearman -0.75; -0.63 under leave-one-out). Complex call structure buys simple functions. We show the same trade-off under controlled perturbation: inlining private helpers removes a mean of 5.4% of call-graph edges while raising mean function complexity in 10 of 11 affected projects, and the two deltas correlate at **r = -0.74**. We then show that "structural complexity" operationalised as a dependency-edge count is maximally fooled by the one change in our study that unambiguously degrades structure: routing all intra-package imports through a single gateway cuts edges by 52.7% on average while raising cross-package coupling by 17.1 points and hub in-degree by 81%. A five-constraint feasibility filter rejects that change in 13 of 14 projects and rejects a second, which silently drops 101 public symbols. We release a static, execution-free, three-axis instrument. We argue that the absence of any such measurement is why structural quality is currently both unmeasured and unmeasured-and-rewardable in agent evaluation.

---

### 1. Introduction

Failure analyses of SWE-bench attribute roughly 35% of agent failures to *localization* — the agent cannot identify which files and functions need to change — against roughly 20% attributed to pure implementation error. The bottleneck for repository-level agents is navigation, not writing. Yet the field's instrument for progress is a pass/fail test run: a container, a `pytest` invocation, one bit. That instrument is deliberately execution-based and therefore deliberately blind to a whole class of properties of the resulting code, including how its dependency structure changed.

The obvious repair is a complexity metric: score an agent by how much structural complexity it removes. This is what software engineering has proposed before, repeatedly, for fifty years. Halstead metrics, McCabe cyclomatic complexity, the Maintainability Index, Martin's coupling and cohesion measures — each was introduced as a scalar summary of code quality, and each has been substantially abandoned, usually for the same reason: the scalar does not predict anything reliably, and it can be improved without improving the code.

We think this history has been misread. The problem is not that scalar complexity metrics are poorly *calibrated*. The problem is that they collapse a space in which the coordinates are **negatively** correlated, and therefore a scalar objective does not measure the thing it claims to measure.

This paper makes that claim precise and testable. We ask three questions. **(1)** Do structural complexity and node-level complexity trade off in real, mature codebases, or are they independent? **(2)** If they trade off, does a controlled structural reduction *move* complexity to the other axis, or delete it? **(3)** If it moves it, what does a scalar complexity score do to an optimizing agent, and can a constraint set close the resulting degenerate optimum? We answer all three with static analysis over 14 projects and 98 controlled transformations, and we release the instrument.

Our central finding is a negative correlation that is strong enough to be a design constraint: **at symbol granularity, r = -0.88.** Code with a dense call graph has simple functions. The complexity is in the wiring. We further show that the *granularity of measurement determines whether the trade-off is visible at all*: at module granularity the same correlation collapses to r = -0.18. An evaluator measuring "architectural complexity" at the module level would conclude the axes are independent and would be wrong.

### 2. Related work

**Execution-based agent evaluation.** SWE-bench established the repository-repair paradigm; SWE-bench Verified curated 500 instances after human review found roughly a quarter of the original set had defective tests or statements; Multi-SWE-bench and SWE-bench Pro extended coverage to more languages and harder, multi-file changes; SWE-bench Live rotates task sets to counter contamination. FeatureBench extends evaluation to feature development spanning multiple commits, reporting that a model resolving 74% of SWE-bench Verified tasks resolved 11% of FeatureBench tasks. All are execution-based. None observes the structural consequences of a patch.

**Structural and retrieval-oriented evaluation.** RepoBench and CrossCodeEval measure repository-level and cross-file completion. RepoReason introduces white-box abductive assertion verification with program-slicing metrics. RepoReasoner evaluates call-chain prediction and output prediction. Agent Retrieval Bench measures file-level retrieval for coding agents and is notable for including natural no-gold and counterfactual controls. These are the closest neighbours to our work: they establish that code-graph structure is worth measuring separately. They do not measure *whether a change moved complexity between structural and procedural levels*.

**Software complexity metrics.** Halstead (1967) proposed operator-operand volume; McCabe (1976) proposed cyclomatic complexity; Martin's object-oriented metrics separate coupling from cohesion; the Maintainability Index combines volume, cyclomatic complexity and SLOC into a single score. Each is a scalar, and the literature's standard criticism is instability and poor empirical validity. We do not argue that these measures are badly chosen. We argue the scalar *form* is the defect, and we quantify why.

### 3. Method

#### 3.1 Three axes, deliberately not collapsed

We measure three orthogonal syntactic levels, chosen so that no axis is a linear function of another.

**Axis S — structure.** Computed at two granularities. *S1* is the module import graph: nodes are modules, edges are intra-package imports. We report edge count, mean fan-in/fan-out, longest path, and graph cyclomatic complexity *E − V + 2P*. *S2* is the symbol-level call graph: every function and method is a node, and a call edge is added when a call site resolves to a module-level definition or an intra-package imported symbol. S2 exists because a module graph cannot see inlining: inlining a helper removes a call edge and no module edge at all.

**Axis C — coupling.** Public interface exposure (fraction of module-level definitions that are not underscore-private), the fraction of import edges crossing a package boundary, and mean external-dependency count per module.

**Axis L — node logic.** Two sub-measures, because McCabe alone is incomplete. *L1* is cyclomatic complexity per procedure, plus maximum block nesting. *L2* is **expression nesting depth** and boolean-operator density, which measure the cost of a single long chained expression containing no branch at all. L2 exists because a project can have an average McCabe complexity of 3 and still contain a 26-deep expression tree.

Across our 14 projects the three axes are not collinear: r(S1, C) = +0.09, r(C, L1) = +0.11, r(S1, L1) = -0.18. Cross-axis collinearity would have made the trade-off unobservable by construction.

#### 3.2 A control operator, and a formatting-invariant size measure

All measurements are taken on `ast.unparse` output rather than source text. This is not cosmetic. Reformatting alone reflows multi-line expressions onto single lines and moves a line-based SLOC by more than 20% — larger than most effects we are trying to measure. We therefore (i) define a **`noop` control** that parses and re-emits every file, apply every operator *on top of* the noop output, and compare every operator against the noop output rather than against pristine source; and (ii) size packages by **AST statement count**, which is invariant under reformatting. Without the noop control our deltas are dominated by codegen artifacts.

#### 3.3 The operator suite

We apply seven semantics-preserving-to-first-order transformations, each modelling a pattern a coding agent actually produces or a degenerate pattern a metric rewards: `inline` (expression-level inlining of private single-expression helpers, admitted only when the body reads nothing but its parameters, builtins, and module-level bindings resolvable identically at the call site — a provable no-op), `unfold` (statement-level inlining of helpers used at most twice, splicing the body into the call site with fresh temporaries), `merge` (consolidation of same-prefix sibling modules), `guard` (wrapping every public function body in `try/except Exception: raise`, semantically inert but adding one decision point and one nesting level per function), `dedup` (deletion of unreferenced private functions), `facade` (routing intra-package symbol imports through a single re-export gateway), and `hardcode` (replacing constant-returning helpers with their constant). Every operator's output is gated on a full `compile()` pass.

`unfold` is the instrument that isolates the trade-off, because it is the one operator that provably reduces structure without removing behaviour.

#### 3.4 The constraint set

A complexity metric is only useful with a feasibility filter, or an optimizing agent will find the degenerate corner. We define five constraints: **K1** every file compiles; **K2** AST statement count stays within 10% of baseline; **K3** every baseline public symbol is still defined; **K4** no new external dependency appears; **K5** maximum in-degree on the *module* import graph grows by no more than 15%. K5 encodes the hub anti-pattern and is deliberately placed on the module graph, where hub concentration actually occurs, rather than on the call graph, where our gateway operator turns out to be invisible.

### 4. Results

#### 4.1 Structure and node complexity are anti-correlated in real code

Across the 14 projects, call-graph cyclomatic complexity per symbol (S2) and mean McCabe complexity (L1) correlate at **r = -0.880** (Spearman -0.754). S2 and boolean density correlate at -0.830. At module granularity the same pairing gives **r = -0.175** (Spearman -0.240), and module coupling is essentially independent of both (+0.09 and +0.11).

Because one project — *black*, a code formatter with unusually deep expression trees and an unusually sparse call graph — has high leverage on a 14-point correlation, we report the full leave-one-out range: **r lies between -0.63 and -0.92 under removal of any single project**, and remains -0.63 with *black* removed. The relationship is not an artefact of one project. The monotone rank correlation (-0.754) is the more conservative summary.

The granularity result is the sharper claim. Dense call structure and simple procedures are two faces of the same design: a codebase that routes work through many small functions looks tortuous in the call graph and trivially simple in each node. A metric computed at module granularity cannot see this, because the trade is conducted *between* modules, not within them. This is, as far as we are aware, the first reported evidence that the structural/procedural trade-off in real code is a granularity artefact as much as a design property.

#### 4.2 Controlled structural reduction moves complexity rather than deleting it

Applying `unfold` across 14 projects, the call graph loses a mean of **5.41% of its edges (SD 4.90)** while mean function complexity rises by **+0.48 McCabe points (SD 0.39)**. Restricted to the 11 projects where the operator fired, structural edges fell in **11 of 11** cases (Wilcoxon z = -2.93) and node complexity rose in **10 of 11** (median +0.38). The two deltas correlate at **r = -0.741** (Spearman -0.764): the more structure an inlining removes, the more node complexity it creates.

Pooling operators, the conservation rate — the fraction of structural reductions paid for on at least one other axis — is **100% for `inline` (6/6)**, **100% for `merge` (4/4)**, **90.9% for `unfold` (10/11)** and **57.1% for `facade` (8/14)**. `dedup`, the only genuinely destructive operator, sits at 4/6, consistent with dead-code removal being the one case where complexity is actually eliminated. The `guard` operator moves no structure at all and inflates mean McCabe complexity by **+22.6% (SD 5.7)** with no offsetting reduction anywhere — defence-in-depth scaffolding, which coding agents add constantly, is pure cost on this measure.

#### 4.3 An edge-count metric is maximally fooled by the hub

We score each operator with two scalars. The first is **edge-only**: because "structural complexity" is very often operationalised as a count of dependency edges, this is the scalar most likely to be deployed. The second is **equal-weight** over all four normalised axes.

The two disagree completely, and the disagreement is the whole result:

| operator | edge-only rank | score | equal-weight rank | max fan-in | public symbols lost | feasible rank |
|---|---|---|---|---|---|---|
| **facade** | **1** | **+0.527** | 7 | 23.1 → **41.9** | 0 | **REJECT** |
| unfold | 2 | +0.054 | 1 | 23.1 → 23.1 | 0 | 1 |
| inline | 3 | +0.016 | 3 | 23.1 → 23.1 | 0 | 3 |
| merge | 4 | +0.015 | 5 | 23.1 → 22.8 | **101** | **REJECT** |
| dedup | 5 | +0.006 | 4 | 23.1 → 23.1 | 0 | 4 |
| hardcode | 6 | −0.000 | 2 | 23.1 → 23.1 | 0 | 2 |
| guard | 7 | −0.000 | 6 | 23.1 → 23.1 | 0 | 5 |

`facade` produces by a margin of roughly ten-to-one the largest apparent reduction in dependency edges of any transformation we applied — **−52.7% on average, ranging from −18.8% to −81.7%** (tox) — and that reduction is entirely an artefact of routing every intra-package import through one re-export gateway. The same change raises mean maximum in-degree from 23.1 to 41.9 (sphinx: 91 → 171). Its effect on cross-package coupling is heavy-tailed and we report it as such: mean **+17.1pp** but median **+4.7pp**, unchanged in 6 of 14 projects, and driven by a few extremes (tox +88.7pp, setuptools +49.6pp). The robust signal is not the coupling shift but the fan-in concentration, which rises in every project where the operator fires. It is a hub, and it is the unambiguous regression in the study.

One caveat on this operator, stated as a limitation of the instrument rather than a property of the code: `facade`'s effect on the *call* graph is exactly zero in all 14 projects, because a re-export gateway produces no resolvable call edges. That is a resolution limit of S2, not a finding.

None of K1–K4 rejects it: it compiles, its statement count is unchanged, its public API is intact, and it adds no dependency. Only K5, which we added *after observing this failure*, rejects it, and it does so in 13 of 14 projects. K3 separately rejects `merge`, which silently drops **101 public symbols** across the 14 projects while scoring as a mild improvement on both scalars. Under the feasibility filter the surviving ranking begins `unfold`, `hardcode`, `inline` — the two degenerate optima are gone, and the change that actually reduces structure while preserving behaviour is first.

The finding is not that a well-chosen weighted scalar fails. It is that **the most natural operationalisation of "structural complexity" — a dependency-edge count — is maximally fooled by the change that most degrades structure**, and that an agent optimizing such a metric has an available strategy worth −52.7% edge reduction for a change that makes the codebase worse.

### 5. Discussion

**What this changes for agent evaluation.** A patch that improves structural metrics and a patch that degrades them produce *identical* test outcomes, because the two effects cancel on the axes the tests do not observe. Structural quality is therefore not merely unmeasured by current benchmarks — it is measurable, optimizable, and free to exploit. We regard the three-axis instrument as a diagnostic layer to be reported *alongside* execution results, not a replacement for them: a repaired bug that concentrates the module graph into a hub has not been made better by any definition we can defend.

**On ontology-derived complexity.** A natural alternative is to define a complexity ontology and derive a scalar from it. We think this reproduces the failure we document. Given the anti-correlation in §4.1, any monotone scalarization of the axes has a direction, and the direction determines what an optimizer does. The fix is not a better ontology but a change of the scored quantity: score *movement under constraint*, not *level*.

**For post-training.** Because the trade-off is measurable without execution, a structural-complexity signal can be computed on any corpus at negligible cost, and used as an auxiliary reward or a rejection-sampling filter — with K5 and K3 as the guard rails, since without them the signal is gameable exactly as §4.3 shows.

### 6. Limitations

Three, stated plainly. **First**, the perturbation experiment uses synthetic operators, not agents; §4.1 is measured on unmodified real code and is the load-bearing result, while §4.2–4.3 establish mechanism and should be read as a controlled demonstration of it rather than as measurements of agent behaviour. **Second**, behavioural equivalence of the operators is established by construction for `inline`, by a compile gate for all, and by a full test-suite run for none; `guard` in particular is a no-op modulo exception chaining context. **Third**, all 14 projects are mature, single-language Python, where the measured trade-off is strongest; we have no evidence about whether it holds for codebases with heavy dynamic dispatch, where S2 resolution is already lossy.

---

**Code and data.** The three-axis analyzer, the seven operators, the constraint checker, and the full 98-cell result set are released with this submission. Every number reported here is reproducible from the release with a single command.

**Reference** — Elan Markowitz, Bryan Perozzi, Benedek Rózemberczki, Glenn Cameron, Hadi Hemmati, Yuchen Li, Michael Galkin, Majid Farhadi, Ryan Holbrook, Ashley Oldacre. Google - The Gemma 4 Developer Agent Paper Track. https://www.kaggle.com/competitions/gemma-4-developer-agent-paper, 2026. Kaggle.
