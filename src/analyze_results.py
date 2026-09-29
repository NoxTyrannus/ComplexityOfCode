"""Statistical analysis of the complexity-conservation experiment."""
import json
import os
import math
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'out')


def load(name):
    return json.load(open(os.path.join(OUT, name)))


# ------------------------------------------------------------- stats
def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return float('nan')
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    return num / (dx * dy) if dx and dy else float('nan')


def rank(vals):
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    r = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def spearman(xs, ys):
    return pearson(rank(xs), rank(ys))


def wilcoxon(diffs):
    """Two-sided signed-rank test, normal approximation with tie correction."""
    d = [x for x in diffs if x != 0]
    n = len(d)
    if n < 6:
        return float('nan'), float('nan')
    r = rank([abs(x) for x in d])
    wplus = sum(x for x, ri in zip(d, r) if x > 0)
    npos = sum(1 for x in d if x > 0)
    mu = n * (n + 1) / 4.0
    tiegroups = defaultdict(int)
    for a in [abs(x) for x in d]:
        tiegroups[a] += 1
    tiesum = sum(t ** 3 - t for t in tiegroups.values() if t > 1)
    sigma = math.sqrt(n * (n + 1) * (2 * n + 1) / 24.0 - tiesum / 48.0)
    if sigma == 0:
        return wplus, float('nan')
    z = (wplus - mu) / sigma
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return z, p


def mean(xs):
    return sum(xs) / len(xs) if xs else float('nan')


def sd(xs):
    if len(xs) < 2:
        return float('nan')
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


# ------------------------------------------------------------- 1. natural variation
def natural():
    base = load('baseline.json')
    rows = []
    for k, v in base.items():
        rows.append({
            'repo': k, 'sloc': v['sloc'], 'funcs': v['S2_funcs'],
            'S1': v['S_gcc'] / max(1, v['files']),
            'S2': v['S2_gcc'] / max(1, v['S2_funcs']),
            'C': v['C_cross_ratio'],
            'Cexp': v['C_exposure'],
            'Lcc': v['L_mean_cc'],
            'Len': v['L_max_enest'],
            'Lbd': v['L_bool_density'],
            'nest': v['L_nesting'],
        })
    pairs = [('S1', 'Lcc'), ('S1', 'Len'), ('S2', 'Lcc'), ('S2', 'Len'),
             ('S1', 'Cexp'), ('C', 'Lcc'), ('S1', 'Lbd'), ('S2', 'Lbd')]
    out = []
    for a, b in pairs:
        xs = [r[a] for r in rows]
        ys = [r[b] for r in rows]
        out.append((a, b, len(rows), pearson(xs, ys), spearman(xs, ys)))
    return rows, out


# ------------------------------------------------------------- 2. perturbations
def perturb():
    raw = load('raw.json')
    by_op = defaultdict(list)
    for cell in raw:
        by_op[cell['op']].append(cell)
    table = []
    for op, cells in sorted(by_op.items()):
        d1 = [c['deltas']['S_edges'] for c in cells]
        d2 = [c['deltas']['S2_edges'] for c in cells]
        dc = [c['deltas']['C_cross_ratio'] for c in cells]
        dl = [c['deltas']['L_mean_cc'] for c in cells]
        de = [c['deltas']['L_max_enest'] for c in cells]
        cons = sum(sum(c['cons'].values()) for c in cells) / (5 * len(cells))
        table.append({
            'op': op, 'n': len(cells),
            'dS1': mean(d1), 'dS1_sd': sd(d1),
            'dS2': mean(d2), 'dS2_sd': sd(d2),
            'dC': mean(dc), 'dC_sd': sd(dc),
            'dL': mean(dl), 'dL_sd': sd(dl),
            'dEn': mean(de),
            'cons': cons,
        })
    return raw, by_op, table


# ------------------------------------------------------------- 3. conservation
def conservation(raw):
    """Fraction of structural reductions that are paid for on another axis."""
    out = {}
    for op in ('inline', 'unfold', 'dedup', 'merge', 'facade', 'guard', 'hardcode'):
        cells = [c for c in raw if c['op'] == op]
        fired = [c for c in cells if c['deltas']['S2_edges'] < -0.05 or
                 c['deltas']['S_edges'] < -0.05]
        if not fired:
            out[op] = {'n': len(cells), 'fired': 0}
            continue
        paid_l = sum(1 for c in fired if c['deltas']['L_mean_cc'] > 0.01)
        paid_c = sum(1 for c in fired if c['deltas']['C_cross_ratio'] > 0.001)
        paid_any = sum(1 for c in fired
                       if c['deltas']['L_mean_cc'] > 0.01 or
                       c['deltas']['C_cross_ratio'] > 0.001)
        out[op] = {'n': len(cells), 'fired': len(fired),
                   'paid_L': paid_l, 'paid_C': paid_c, 'paid_any': paid_any,
                   'rate': paid_any / len(fired),
                   'dS2': mean([c['deltas']['S2_edges'] for c in fired]),
                   'dL': mean([c['deltas']['L_mean_cc'] for c in fired])}
    return out


# ------------------------------------------------------------- 4. anti-gaming
def antigaming(raw, by_op):
    """Two scalars: an equal-weight one over all axes, and an EDGE-ONLY one.

    The edge-only scalar is the one that matters in practice: "structural
    complexity" is very often operationalised as a count of dependency edges,
    and that is precisely the quantity the hub operator attacks.
    """
    rows = []
    for op, cells in by_op.items():
        if op == 'noop':
            continue
        d1 = mean([c['deltas']['S_edges'] for c in cells])
        d2 = mean([c['deltas']['S2_edges'] for c in cells])
        dc = mean([c['deltas']['C_cross_ratio'] for c in cells])
        dl = mean([c['deltas']['L_mean_cc'] for c in cells])
        de = mean([c['deltas']['L_max_enest'] for c in cells])
        equal = -(d1 / 100.0 + d2 / 100.0 + dc * 1.0 + dl / 10.0 + de / 100.0)
        # edge-only: what a "dependency count" metric sees
        edge = -(d1 / 100.0 + d2 / 100.0)
        k5 = sum(1 for c in cells if not c['cons'].get('K5_no_new_hub', True))
        rows.append({'op': op, 'naive': equal, 'edge': edge,
                     'dS1': d1, 'dS2': d2, 'dC': dc, 'dL': dl, 'dEn': de,
                     'api_lost': sum(c['api_lost'] for c in cells),
                     'k5_fail': k5, 'n': len(cells),
                     'constraint_pass': sum(1 for c in cells for v in c['cons'].values() if v)
                     / (5 * len(cells)),
                     'hub_before': mean([c['ref'].get('S1_maxfanin', 0) for c in cells]),
                     'hub_after': mean([c['metrics'].get('S1_maxfanin', 0) for c in cells])})
    rows.sort(key=lambda r: -r['edge'])
    for i, r in enumerate(rows):
        r['edge_rank'] = i + 1
    rows.sort(key=lambda r: -r['naive'])
    for i, r in enumerate(rows):
        r['equal_rank'] = i + 1
    for r in rows:
        r['eligible'] = (r['k5_fail'] == 0 and r['api_lost'] == 0 and
                         r['constraint_pass'] == 1.0)
    elig = sorted([r for r in rows if r['eligible']], key=lambda r: -r['naive'])
    for i, r in enumerate(elig):
        r['feasible_rank'] = i + 1
    return rows


def main():
    rows, nat = natural()
    raw, by_op, ptab = perturb()
    cons = conservation(raw)
    game = antigaming(raw, by_op)

    print('=' * 78)
    print('EXPERIMENT 1 — natural cross-repository variation (n=%d projects)' % len(rows))
    print('=' * 78)
    print(f"{'axis A':>6s} {'axis B':>6s} {'n':>3s} {'pearson':>8s} {'spearman':>9s}")
    for a, b, n, p, s in nat:
        print(f'{a:>6s} {b:>6s} {n:3d} {p:+8.3f} {s:+9.3f}')

    # leave-one-out robustness for the headline correlation
    x = [r['S2'] for r in rows]; y = [r['Lcc'] for r in rows]
    loo = [pearson(x[:i] + x[i+1:], y[:i] + y[i+1:]) for i in range(len(rows))]
    worst = loo.index(max(loo))
    print()
    print(f'  leave-one-out r(S2, Lcc): min {min(loo):+.3f}  max {max(loo):+.3f}  '
          f'(most influential: {rows[worst]["repo"]}, r={max(loo):+.3f} without it)')

    print()
    print('=' * 78)
    print('EXPERIMENT 2 — controlled structural perturbations')
    print('=' * 78)
    print(f"{'operator':>9s} {'n':>3s} | {'dS1%':>14s} {'dS2%':>15s} {'dC(pp)':>14s} {'dL(cc)':>15s} {'cons':>5s}")
    for t in ptab:
        print(f"{t['op']:>9s} {t['n']:3d} | "
              f"{t['dS1']:+6.2f}+-{t['dS1_sd']:<6.2f} "
              f"{t['dS2']:+6.2f}+-{t['dS2_sd']:<6.2f} "
              f"{t['dC']:+6.3f}+-{t['dC_sd']:<6.3f} "
              f"{t['dL']:+6.2f}+-{t['dL_sd']:<6.2f} "
              f"{t['cons']:5.2f}")

    print()
    print('=' * 78)
    print('EXPERIMENT 3 — conservation: when structure falls, where does it go?')
    print('=' * 78)
    print(f"{'operator':>9s} {'fired':>6s} {'paid on L':>10s} {'paid on C':>10s} "
          f"{'paid any':>9s} {'mean dS2%':>10s} {'mean dL':>8s}")
    for op, c in cons.items():
        if not c.get('fired'):
            continue
        print(f"{op:>9s} {c['fired']:6d} {c['paid_L']:10d} {c['paid_C']:10d} "
              f"{c['paid_any']:9d} {c['dS2']:+10.2f} {c['dL']:+8.2f}")

    print()
    print('  conservation rate (structural reduction paid somewhere else):')
    for op, c in cons.items():
        if c.get('fired'):
            print(f"    {op:>9s}  {c['rate']*100:5.1f}%  (n={c['fired']})")

    uf = [c for c in raw if c['op'] == 'unfold' and c['deltas']['S2_edges'] < -0.05]
    if uf:
        ds2 = [c['deltas']['S2_edges'] for c in uf]
        dL = [c['deltas']['L_mean_cc'] for c in uf]
        z2, p2 = wilcoxon(ds2)
        nneg, npos = sum(1 for x in ds2 if x < 0), sum(1 for x in ds2 if x > 0)
        print(f"\n  paired test on `unfold` (n={len(uf)} cells that fired):")
        print(f"    dS2  fell in {nneg}/{len(uf)} cells, rose in {npos}/{len(uf)}"
              f"   Wilcoxon z={z2:+.2f}")
        nposL = sum(1 for x in dL if x > 0)
        print(f"    dL   rose in {nposL}/{len(uf)} cells "
              f"(median {sorted(dL)[len(dL)//2]:+.2f})")
        print(f"    corr(dS2, dL) across cells = {pearson(ds2, dL):+.3f}  "
              f"(spearman {spearman(ds2, dL):+.3f})")

    print()
    print('=' * 78)
    print('EXPERIMENT 4 — anti-gaming: naive scalar ranking vs constrained')
    print('=' * 78)
    print(f"{'operator':>9s} {'edgeRank':>8s} {'edgeScore':>9s} {'equalRank':>9s} "
          f"{'maxFanIn':>16s} {'APIlost':>7s} {'feasible':>12s}")
    for r in sorted(game, key=lambda x: x['edge_rank']):
        fr = str(r.get('feasible_rank', 'REJECT'))
        print(f"{r['op']:>9s} {r['edge_rank']:8d} {r['edge']:+9.4f} "
              f"{r['equal_rank']:9d} "
              f"{r['hub_before']:7.1f}->{r['hub_after']:<7.1f} "
              f"{r['api_lost']:7d} {fr:>12s}")

    json.dump({'natural': rows, 'nat_corr': nat, 'loo': loo, 'perturb': ptab,
               'conservation': cons, 'antigaming': game},
              open(os.path.join(OUT, 'analysis.json'), 'w'), indent=1, default=str)
    print('\nwrote analysis.json')


if __name__ == '__main__':
    main()
