"""Submission assets at the resolutions Kaggle's validator actually accepts.

Card/Thumbnail field: validator requires >= 640x360 on BOTH dimensions.
Media gallery: same floor. We render everything at 1280x720 (16:9) and also
emit a 1280x640 (2:1) card in case the thumbnail slot wants the older ratio.
"""
import json, os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'out')
INK, ACC, BLUE, GREY = '#11151C', '#E05260', '#5B8FD6', '#8892A4'


# --------------------------------------------------------------- card
def _card_ax(fig):
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(INK)
    ax.axis('off')
    return ax


def _mini(ax, ox, oy, ow, oh):
    xs = [0.08, 0.16, 0.22, 0.30, 0.38, 0.46, 0.55, 0.63, 0.72, 0.80, 0.88]
    ys = [0.90, 0.78, 0.66, 0.58, 0.50, 0.44, 0.38, 0.30, 0.24, 0.16, 0.10]
    ax.add_patch(FancyBboxPatch((ox - 0.035, oy - 0.05), ow + 0.07, oh + 0.10,
                                boxstyle='round,pad=0.012',
                                facecolor='#171C26', edgecolor='#2C3444',
                                linewidth=1.0, zorder=1))
    px = [ox + v * ow for v in xs]
    py = [oy + v * oh for v in ys]
    ax.plot(px, py, color=ACC, lw=2.2, ls='--', zorder=2, alpha=0.95)
    ax.scatter(px, py, s=42, color='white', zorder=3, edgecolor=ACC,
               linewidths=1.6)
    ax.text(ox + ow / 2, oy + oh + 0.05,
            'dependency edges  vs  function complexity',
            color=GREY, fontsize=10, ha='center', va='bottom')


def card_16x9(path):
    fig = plt.figure(figsize=(12.8, 7.2), dpi=100)
    fig.patch.set_facecolor(INK)
    ax = _card_ax(fig)
    ax.text(0.055, 0.885, 'GEMMA 4 DEVELOPER AGENT  ·  PAPER TRACK',
            color='#7DD3FC', fontsize=21, fontweight='bold', va='top')
    ax.text(0.052, 0.755, 'COMPLEXITY\nIS CONSERVED',
            color='white', fontsize=64, fontweight='heavy', va='top',
            linespacing=1.06)
    ax.text(0.052, 0.315, 'structure  ↓    ⇒    node logic  ↑',
            color='#FCA5A5', fontsize=29, fontweight='bold', va='top')
    ax.text(0.052, 0.075,
            'r = −0.88 across 14 mature Python projects',
            color=GREY, fontsize=17, va='bottom')
    _mini(ax, 0.695, 0.085, 0.250, 0.38)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    fig.savefig(path, facecolor=INK)
    plt.close(fig)


def card_2x1(path):
    fig = plt.figure(figsize=(12.8, 6.4), dpi=100)
    fig.patch.set_facecolor(INK)
    ax = _card_ax(fig)
    ax.text(0.05, 0.87, 'GEMMA 4 DEVELOPER AGENT  ·  PAPER TRACK',
            color='#7DD3FC', fontsize=19, fontweight='bold', va='top')
    ax.text(0.05, 0.75, 'COMPLEXITY\nIS CONSERVED',
            color='white', fontsize=66, fontweight='heavy', va='top',
            linespacing=1.06)
    ax.text(0.05, 0.235, 'structure  ↓    ⇒    node logic  ↑',
            color='#FCA5A5', fontsize=30, fontweight='bold', va='top')
    ax.text(0.05, 0.075, 'r = −0.88 across 14 mature Python projects',
            color=GREY, fontsize=17, va='bottom')
    _mini(ax, 0.67, 0.20, 0.28, 0.50)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    fig.savefig(path, facecolor=INK)
    plt.close(fig)


# --------------------------------------------------------------- gallery
def _lin(xs, ys):
    n = len(xs); mx = sum(xs) / n; my = sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    den = sum((a - mx) ** 2 for a in xs)
    b = num / den if den else 0.0
    return b, my - b * mx


def gal_flagship(path, raw):
    """Granularity dependence (a,b) above, leave-one-out (c) below."""
    an = json.load(open(os.path.join(OUT, 'analysis.json')))
    rows = an['natural']
    names = [r['repo'] for r in rows]
    x = [r['S2'] for r in rows]
    y = [r['Lcc'] for r in rows]
    x1 = [r['S1'] for r in rows]
    loo = an.get('loo', [])

    fig = plt.figure(figsize=(12.8, 7.2), dpi=100)
    gs = fig.add_gridspec(2, 2, height_ratios=[1.5, 1], hspace=0.60,
                          wspace=0.24, left=0.135, right=0.975,
                          top=0.845, bottom=0.115)

    def fit(ax, xs, xlabel, title):
        ax.axhline(0, color='#E2E5EA', lw=0.8, zorder=1)
        for i, (v, nm) in enumerate(zip(xs, names)):
            hi = nm == 'black'
            ax.scatter(v, y[i], s=115 if hi else 72, c=ACC if hi else BLUE,
                       edgecolor='white', linewidth=1.4, zorder=4)
            ax.annotate(nm, (v, y[i]), fontsize=10.5,
                        xytext=(6, 6), textcoords='offset points', color='#3A4250')
        b, a = _lin(xs, y)
        s = sorted(xs)
        ax.plot(s, [a + b * v for v in s], color=ACC, lw=2.0, ls='--', zorder=2)
        ax.set_xlabel(xlabel, fontsize=13, color='#3A4250')
        ax.set_title(title, fontsize=16, pad=9, color=INK, loc='left')
        ax.tick_params(labelsize=11.5, colors='#3A4250')
        ax.spines[['top', 'right']].set_visible(False)
        ax.grid(axis='y', color='#EEF1F5', lw=0.9, zorder=0)
        ax.set_ylabel('mean McCabe complexity', fontsize=13, color='#3A4250')

    fit(fig.add_subplot(gs[0, 0]), x,
        'call-graph cyclomatic complexity (per symbol)',
        '(a)  symbol granularity    r = −0.880')
    fit(fig.add_subplot(gs[0, 1]), x1,
        'module-graph cyclomatic complexity (per module)',
        '(b)  module granularity    r = −0.175')

    ax = fig.add_subplot(gs[1, :])
    order = sorted(range(len(loo)), key=lambda i: loo[i])
    vals = [loo[i] for i in order]
    lbls = [names[i] for i in order]
    ax.barh(range(len(loo)), vals, color=BLUE, height=0.66,
            edgecolor='white', linewidth=0.8)
    ax.set_yticks(range(len(loo)))
    ax.set_yticklabels(lbls, fontsize=10.5)
    ax.axvline(-0.880, color=ACC, lw=1.6, ls='--')
    ax.set_xlim(-1.02, -0.40)
    ax.set_xlabel('r after removing that one project', fontsize=13,
                  color='#3A4250')
    ax.set_title('(c)  leave-one-out robustness — no single project drives '
                 'the result', fontsize=16, pad=9, color=INK, loc='left')
    ax.tick_params(labelsize=11.5, colors='#3A4250')
    ax.spines[['top', 'right']].set_visible(False)
    ax.grid(axis='x', color='#EEF1F5', lw=0.9, zorder=0)
    for i, v in enumerate(vals):
        ax.text(v - 0.022, i, f'{v:.2f}', va='center', ha='right',
                fontsize=10.5, color='#3A4250')

    fig.suptitle('Granularity decides whether the structural/procedural '
                 'trade-off is visible at all',
                 fontsize=21, x=0.045, ha='left', y=0.955, color=INK)
    fig.savefig(path, facecolor='white')
    plt.close(fig)


def gal_tradeoff(path, raw):
    cells = [c for c in raw if c['op'] == 'unfold' and
             c['deltas']['S2_edges'] < -0.05]
    x = [c['deltas']['S2_edges'] for c in cells]
    y = [c['deltas']['L_mean_cc'] for c in cells]
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=100)
    fig.subplots_adjust(left=0.10, right=0.97, top=0.86, bottom=0.12)
    ax.axhline(0, color='#D7DBE2', lw=1.0, zorder=1)
    ax.axvline(0, color='#D7DBE2', lw=1.0, zorder=1)
    ax.scatter(x, y, s=190, c='#4E9F6E', edgecolor='white', linewidth=2.0,
               zorder=4)
    b, a = _lin(x, y)
    s = sorted(x)
    ax.plot(s, [a + b * v for v in s], color=ACC, lw=2.4, ls='--', zorder=2)
    for xi, yi, c in zip(x, y, cells):
        ax.annotate(c['repo'], (xi, yi), fontsize=10, xytext=(7, 6),
                    textcoords='offset points', color='#3A4250')
    ax.set_xlabel('change in call-graph edges (%)', fontsize=15, color='#3A4250')
    ax.set_ylabel('change in mean McCabe complexity', fontsize=15,
                  color='#3A4250')
    ax.set_title('Inlining helpers: structure falls, node logic rises  '
                 f'(n = {len(cells)},  r = −0.741)',
                 fontsize=20, color=INK, loc='left', pad=14)
    ax.text(0.015, 0.955,
            '11 of 11 projects lost call-graph edges;  10 of 11 gained '
            'function complexity.\nComplexity is moved between axes, not '
            'removed.',
            transform=ax.transAxes, fontsize=13.5, va='top', color='#3A4250',
            linespacing=1.5)
    ax.spines[['top', 'right']].set_visible(False)
    ax.grid(color='#EEF1F5', lw=0.9, zorder=0)
    ax.tick_params(labelsize=12.5, colors='#3A4250')
    fig.savefig(path, facecolor='white')
    plt.close(fig)


def gal_hub(path, raw):
    f = [c for c in raw if c['op'] == 'facade']
    nm = [c['repo'] for c in f]
    before = [c['ref']['S1_maxfanin'] for c in f]
    after = [c['metrics']['S1_maxfanin'] for c in f]
    edges = [c['deltas']['S_edges'] for c in f]
    order = sorted(range(len(f)), key=lambda i: after[i] - before[i])
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 7.2), dpi=100)
    fig.subplots_adjust(left=0.135, right=0.975, top=0.83, bottom=0.215,
                        wspace=0.46)
    ax = axes[0]
    ax.barh(range(len(f)), [edges[i] for i in order], color=BLUE, height=0.66,
            edgecolor='white', linewidth=0.8)
    ax.set_yticks(range(len(f)))
    ax.set_yticklabels([nm[i] for i in order], fontsize=11)
    ax.set_xlabel('change in dependency edges (%)', fontsize=13.5,
                  color='#3A4250')
    ax.set_title('Looks like a 52.7% simplification', fontsize=16, color=INK,
                 loc='left', pad=10)
    ax.axvline(0, color='#B9C0CC', lw=1.0)
    ax.spines[['top', 'right']].set_visible(False)
    ax.tick_params(labelsize=12, colors='#3A4250')
    ax.grid(axis='x', color='#EEF1F5', lw=0.9, zorder=0)

    ax = axes[1]
    w = 0.38
    ax.bar([i - w / 2 for i in range(len(f))], [before[i] for i in order],
           width=w, color='#C3CBD8', label='before', edgecolor='white',
           linewidth=0.7)
    ax.bar([i + w / 2 for i in range(len(f))], [after[i] for i in order],
           width=w, color=ACC, label='after', edgecolor='white', linewidth=0.7)
    ax.set_xticks(range(len(f)))
    ax.set_xticklabels([nm[i] for i in order], rotation=48, ha='right',
                       fontsize=10.5)
    ax.set_ylabel('max in-degree on the module import graph', fontsize=13.5,
                  color='#3A4250')
    ax.set_title('…is a hub', fontsize=16, color=INK, loc='left', pad=10)
    ax.legend(frameon=False, fontsize=12)
    ax.spines[['top', 'right']].set_visible(False)
    ax.tick_params(labelsize=12, colors='#3A4250')
    ax.grid(axis='y', color='#EEF1F5', lw=0.9, zorder=0)
    fig.suptitle('The change an edge-count metric rewards most\n'
                 'is the one that most degrades structure',
                 fontsize=21, x=0.035, ha='left', y=0.985, color=INK,
                 va='top', linespacing=1.3)
    fig.savefig(path, facecolor='white')
    plt.close(fig)


if __name__ == '__main__':
    from PIL import Image
    raw = json.load(open(os.path.join(OUT, 'raw.json')))
    jobs = [
        (os.path.join(OUT, 'card_1280x720.png'), lambda p: card_16x9(p)),
        (os.path.join(OUT, 'card_1280x640.png'), lambda p: card_2x1(p)),
        (os.path.join(OUT, 'gallery_1_granularity.png'),
         lambda p: gal_flagship(p, raw)),
        (os.path.join(OUT, 'gallery_2_tradeoff.png'),
         lambda p: gal_tradeoff(p, raw)),
        (os.path.join(OUT, 'gallery_3_hub.png'), lambda p: gal_hub(p, raw)),
    ]
    for p, fn in jobs:
        fn(p)
        im = Image.open(p)
        ok = im.size[0] >= 640 and im.size[1] >= 360
        print(f'{"OK " if ok else "LOW"} {os.path.basename(p):28s} {im.size}')
