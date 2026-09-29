"""Figures for the paper."""
import json
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'out')
plt.rcParams.update({'font.size': 9, 'axes.spines.top': False,
                     'axes.spines.right': False, 'figure.dpi': 160})


def fig_scatter(rows, path):
    """Structure vs node complexity across real projects."""
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.9))
    for ax, (xk, yk, xl, yl) in zip(axes, [
            ('S2', 'Lcc', 'call-graph cyclomatic\ncomplexity (per symbol)',
             'mean McCabe\ncomplexity'),
            ('S1', 'Len', 'module-graph cyclomatic\ncomplexity (per module)',
             'max expression\nnesting depth')]):
        x = [r[xk] for r in rows]
        y = [r[yk] for r in rows]
        ax.scatter(x, y, s=34, c='#4C72B0', edgecolor='white', linewidth=0.8,
                   zorder=3)
        for r in rows:
            ax.annotate(r['repo'], (r[xk], r[yk]), fontsize=6.5,
                        xytext=(3, 3), textcoords='offset points', color='#555')
        b, a = _linreg(x, y)
        xs = sorted(x)
        ax.plot(xs, [a + b * v for v in xs], color='#C44E52', lw=1.2, ls='--',
                zorder=2)
        r = _pearson(x, y)
        ax.set_xlabel(xl); ax.set_ylabel(yl)
        ax.set_title(f'r = {r:+.2f}', fontsize=9, pad=4)
    fig.tight_layout()
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)


def fig_tradeoff(raw, path):
    """Per-project structural reduction vs complexity paid elsewhere."""
    cells = [c for c in raw if c['op'] == 'unfold' and
             c['deltas']['S2_edges'] < -0.05]
    x = [c['deltas']['S2_edges'] for c in cells]
    y = [c['deltas']['L_mean_cc'] for c in cells]
    fig, ax = plt.subplots(figsize=(3.5, 2.9))
    ax.axhline(0, color='#999', lw=0.8, zorder=1)
    ax.axvline(0, color='#999', lw=0.8, zorder=1)
    ax.scatter(x, y, s=40, c='#55A868', edgecolor='white', linewidth=0.8,
               zorder=3)
    b, a = _linreg(x, y)
    xs = sorted(x)
    ax.plot(xs, [a + b * v for v in xs], color='#C44E52', lw=1.4, ls='--',
            zorder=2)
    ax.set_xlabel('$\\Delta$ call-graph edges (%)')
    ax.set_ylabel('$\\Delta$ mean McCabe complexity')
    ax.set_title(f'unfold: n={len(cells)}', fontsize=9, pad=4)
    fig.tight_layout()
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)


def fig_operators(tab, path):
    """Directional summary per operator."""
    ops = [t for t in tab if t['op'] != 'noop']
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.7))
    xs = range(len(ops))
    for ax, keys, title in [
            (axes[0], ['dS1', 'dS2', 'dC'], 'structure + coupling'),
            (axes[1], ['dL'], 'node logic')]:
        w = 0.8 / len(keys)
        for i, k in enumerate(keys):
            vals = [t[k] for t in ops]
            sd = [t.get(k + '_sd', 0) or 0 for t in ops]
            ax.bar([x + i * w for x in xs], vals, width=w, label=k,
                   yerr=sd, capsize=2, error_kw=dict(lw=0.7))
        ax.axhline(0, color='#333', lw=0.8)
        ax.set_xticks([x + 0.4 for x in xs])
        ax.set_xticklabels([t['op'] for t in ops], rotation=45, ha='right',
                           fontsize=7)
        ax.set_ylabel('mean $\\Delta$ vs control')
        ax.set_title(title, fontsize=9)
        ax.legend(fontsize=7, frameon=False)
    fig.tight_layout()
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)


def _pearson(xs, ys):
    n = len(xs); mx = sum(xs) / n; my = sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = (sum((a - mx) ** 2 for a in xs)) ** .5
    dy = (sum((b - my) ** 2 for b in ys)) ** .5
    return num / (dx * dy) if dx and dy else 0.0


def _linreg(xs, ys):
    n = len(xs); mx = sum(xs) / n; my = sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    den = sum((a - mx) ** 2 for a in xs)
    b = num / den if den else 0.0
    return b, my - b * mx


if __name__ == '__main__':
    an = json.load(open(os.path.join(OUT, 'analysis.json')))
    raw = json.load(open(os.path.join(OUT, 'raw.json')))
    fig_scatter(an['natural'], os.path.join(OUT, 'fig1_axes.png'))
    fig_tradeoff(raw, os.path.join(OUT, 'fig2_tradeoff.png'))
    fig_operators(an['perturb'], os.path.join(OUT, 'fig3_operators.png'))
    print('wrote 3 figures')
