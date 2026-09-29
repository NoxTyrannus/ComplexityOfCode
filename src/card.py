"""Card (560x280) and gallery figure for the Kaggle writeup."""
import json, os, math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'out')
INK = '#11151C'
ACC = '#C44E52'
BLUE = '#4C72B0'
GREY = '#6B7280'


def card(path):
    fig = plt.figure(figsize=(5.6, 2.8), dpi=100)
    fig.patch.set_facecolor(INK)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_facecolor(INK)
    ax.axis('off')

    ax.text(0.055, 0.855, 'GEMMA 4 DEVELOPER AGENT  ·  PAPER TRACK',
            color='#7DD3FC', fontsize=7.4, fontweight='bold',
            family='DejaVu Sans', va='top')
    ax.text(0.055, 0.66, 'COMPLEXITY\nIS CONSERVED',
            color='white', fontsize=25, fontweight='heavy',
            family='DejaVu Sans', va='top', linespacing=1.02)
    ax.text(0.055, 0.235,
            'structure  ↓   ⇒   node logic  ↑',
            color='#FCA5A5', fontsize=10.5, fontweight='bold',
            family='DejaVu Sans', va='top')
    ax.text(0.055, 0.075,
            'r = −0.88 across 14 mature Python projects',
            color=GREY, fontsize=6.6, family='DejaVu Sans', va='bottom')

    # mini visual: the anti-correlation
    ox, oy, ow, oh = 0.655, 0.20, 0.30, 0.50
    xs = [0.08, 0.16, 0.22, 0.30, 0.38, 0.46, 0.55, 0.63, 0.72, 0.80, 0.88]
    ys = [0.90, 0.78, 0.66, 0.58, 0.50, 0.44, 0.38, 0.30, 0.24, 0.16, 0.10]
    ax.add_patch(FancyBboxPatch((ox - 0.03, oy - 0.04), ow + 0.06, oh + 0.08,
                                boxstyle='round,pad=0.012',
                                facecolor='#171C26', edgecolor='#2A3140',
                                linewidth=0.8, zorder=1))
    px = [ox + v * ow for v in xs]
    py = [oy + v * oh for v in ys]
    ax.plot(px, py, color=ACC, lw=1.5, ls='--', zorder=2, alpha=0.9)
    ax.scatter(px, py, s=17, color='white', zorder=3,
               edgecolor=ACC, linewidths=1.0)
    ax.text(ox + ow / 2, oy + oh + 0.035, 'edges  vs  function complexity',
            color=GREY, fontsize=5.9, ha='center', va='bottom')
    # add_patch can trigger autoscale and push the data limits outside [0,1],
    # which silently moves every text object off-canvas. Pin them.
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    fig.savefig(path, facecolor=INK)
    plt.close(fig)


def gallery(path):
    """Flagship figure: granularity dependence + leave-one-out robustness."""
    an = json.load(open(os.path.join(OUT, 'analysis.json')))
    rows = an['natural']
    x = [r['S2'] for r in rows]
    y = [r['Lcc'] for r in rows]
    x1 = [r['S1'] for r in rows]
    names = [r['repo'] for r in rows]
    loo = an.get('loo', [])

    fig, axes = plt.subplots(1, 3, figsize=(10.6, 3.15),
                             gridspec_kw={'width_ratios': [1, 1, 0.92]})

    def fit(ax, xs, ys, xlabel, title):
        ax.axhline(0, color='#DDD', lw=0.7, zorder=1)
        for v, lbl, hi in zip(xs, names, [n == 'black' for n in names]):
            ax.scatter(v, ys[names.index(lbl)], s=52 if hi else 34,
                       c=ACC if hi else BLUE, edgecolor='white',
                       linewidth=1.0, zorder=4)
            ax.annotate(lbl, (v, ys[names.index(lbl)]), fontsize=6.4,
                        xytext=(4, 4), textcoords='offset points',
                        color='#444')
        b, a = _lin(xs, ys)
        s = sorted(xs)
        ax.plot(s, [a + b * v for v in s], color=ACC, lw=1.3, ls='--', zorder=2)
        ax.set_xlabel(xlabel, fontsize=8)
        ax.set_title(title, fontsize=9.5, pad=5)
        ax.tick_params(labelsize=7.5)

    fit(axes[0], x, y, 'call-graph complexity\n(per symbol)',
        '(a) symbol granularity   r = −0.88')
    fit(axes[1], x1, y, 'module-graph complexity\n(per module)',
        '(b) module granularity   r = −0.18')

    ax = axes[2]
    if loo:
        order = sorted(range(len(loo)), key=lambda i: loo[i])
        ax.barh(range(len(loo)), [loo[i] for i in order], color=BLUE,
                height=0.62, edgecolor='white', linewidth=0.6)
        ax.set_yticks(range(len(loo)))
        ax.set_yticklabels([names[i] for i in order], fontsize=6.2)
        ax.axvline(-0.880, color=ACC, lw=1.2, ls='--')
        ax.set_xlim(-1.0, 0.1)
        ax.set_xlabel('r with one project removed', fontsize=8)
        ax.set_title('(c) leave-one-out robustness', fontsize=9.5, pad=5)
        ax.tick_params(labelsize=7.5)
        for i, v in zip(range(len(loo)), [loo[j] for j in order]):
            ax.text(v + 0.02, i, f'{v:.2f}', va='center', fontsize=6.0,
                    color='#333')

    fig.tight_layout()
    fig.savefig(path, bbox_inches='tight', dpi=170)
    plt.close(fig)


def _lin(xs, ys):
    n = len(xs); mx = sum(xs) / n; my = sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    den = sum((a - mx) ** 2 for a in xs)
    b = num / den if den else 0.0
    return b, my - b * mx


if __name__ == '__main__':
    card(os.path.join(OUT, 'card_560x280.png'))
    gallery(os.path.join(OUT, 'fig_granularity.png'))
    from PIL import Image
    for f in ('card_560x280.png', 'fig_granularity.png'):
        im = Image.open(os.path.join(OUT, f))
        print(f, im.size)
