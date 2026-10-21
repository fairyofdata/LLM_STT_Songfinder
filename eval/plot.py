"""Charts from eval/results/summary.json.

    venv/Scripts/python eval/plot.py

recall_by_query_type.png - 1200x627 (LinkedIn), Recall@1/5/10 per query type
threshold_tradeoff.png    - text-path accuracy vs negative false accepts over thresholds
"""
import json
import os

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, 'results')

SURFACE = '#fcfcfb'
TEXT_PRIMARY = '#0b0b0b'
TEXT_SECONDARY = '#52514e'
GRID = '#e4e3df'
SERIES = ['#2a78d6', '#eb6834', '#1baf7a']  # categorical slots 1-3, validated (light)

TYPE_LABELS = {
    'exact': 'Exact line\n(sanity check)',
    'half': 'First half only',
    'word_drop': '30% words dropped',
    'typo': '~10% character typos',
    'concat': 'Two adjacent lines,\npartially joined',
}

plt.rcParams.update({
    'font.family': ['Segoe UI', 'DejaVu Sans'],
    'axes.edgecolor': GRID,
    'axes.labelcolor': TEXT_SECONDARY,
    'xtick.color': TEXT_SECONDARY,
    'ytick.color': TEXT_SECONDARY,
})


def rounded_bar(ax, x, width, height, color, rx, ry):
    """Column with a 4px rounded data-end and a square baseline (rx, ry: 4px in data units)."""
    ax.add_patch(FancyBboxPatch((x, 0), width, height, boxstyle=f'round,pad=0,rounding_size={rx}',
                                mutation_aspect=ry / rx, linewidth=0, facecolor=color, zorder=2))
    ax.add_patch(plt.Rectangle((x, 0), width, min(height, ry * 1.5), linewidth=0, facecolor=color, zorder=2))


def recall_chart(summary):
    m = summary['metrics']['unambiguous']
    types = list(TYPE_LABELS)
    ks = [1, 5, 10]
    n_seeds = len(summary['seeds'])
    n_unambiguous = sum(m['pooled']['n'])
    n_songs = summary['n_songs_with_lines']

    fig = plt.figure(figsize=(12, 6.27), dpi=100, facecolor=SURFACE)
    ax_box = [0.065, 0.2, 0.915, 0.53]
    ax = fig.add_axes(ax_box, facecolor=SURFACE)
    y_max = 1.1
    px_x = ax_box[2] * 1200 / len(types)   # pixels per x unit
    px_y = ax_box[3] * 627 / y_max         # pixels per y unit
    bar_w, gap = 24 / px_x, 2 / px_x
    group_w = 3 * bar_w + 2 * gap
    rx, ry = 4 / px_x, 4 / px_y
    for ti, t in enumerate(types):
        for ki, k in enumerate(ks):
            v = m[t][f'recall@{k}']
            x = ti - group_w / 2 + ki * (bar_w + gap)
            rounded_bar(ax, x, bar_w, v['mean'], SERIES[ki], rx, ry)
            ax.errorbar(x + bar_w / 2, v['mean'], yerr=v['std'], fmt='none', ecolor=TEXT_PRIMARY,
                        elinewidth=1.2, capsize=3, capthick=1.2, zorder=3)
            ax.text(x + bar_w / 2, v['mean'] + max(v['std'], 0.004) + 0.012, f"{v['mean'] * 100:.0f}",
                    ha='center', va='bottom', fontsize=9, color=TEXT_PRIMARY, zorder=4)

    ax.set_xlim(-0.5, len(types) - 0.5)
    ax.set_ylim(0, y_max)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(['0%', '25%', '50%', '75%', '100%'], fontsize=11)
    ax.set_xticks(range(len(types)))
    ax.set_xticklabels([TYPE_LABELS[t] for t in types], fontsize=12, color=TEXT_PRIMARY)
    ax.tick_params(axis='both', length=0, pad=8)
    ax.grid(axis='y', color=GRID, linewidth=1, zorder=0)
    for side in ('top', 'right', 'left'):
        ax.spines[side].set_visible(False)
    ax.spines['bottom'].set_color('#c9c8c3')

    fig.text(0.065, 0.93, 'Songfinder: identifying J-POP songs from partial or misspelled lyrics',
             fontsize=21, fontweight='semibold', color=TEXT_PRIMARY)
    fig.text(0.065, 0.875, f'Song-level Recall@K by query type · {n_songs} songs, 22,806 indexed lines · '
             'multilingual MiniLM embeddings + FAISS', fontsize=13, color=TEXT_SECONDARY)

    handles = [plt.Rectangle((0, 0), 1, 1, facecolor=c, linewidth=0) for c in SERIES]
    fig.legend(handles, ['Recall@1', 'Recall@5', 'Recall@10'], loc='upper left',
               bbox_to_anchor=(0.058, 0.85), ncol=3, frameon=False, fontsize=12,
               handlelength=1.1, handleheight=1.1, columnspacing=1.6, labelcolor=TEXT_PRIMARY)
    fig.text(0.98, 0.79, 'error bars: ±1 SD across seeds', ha='right', fontsize=10.5, color=TEXT_SECONDARY)

    fig.text(0.065, 0.068,
             f'Synthetic queries generated from the indexed lyrics, not real user queries. '
             f'{n_seeds} random seeds, {n_unambiguous:,} queries in total (~{round(n_unambiguous / n_seeds):,} per seed).',
             fontsize=10.5, color=TEXT_SECONDARY)
    fig.text(0.065, 0.032,
             'Lines that also occur in another song are excluded here and reported separately. '
             'Measures lyric text only: no humming or melody, no real recordings.',
             fontsize=10.5, color=TEXT_SECONDARY)

    out = os.path.join(RESULTS, 'recall_by_query_type.png')
    fig.savefig(out, dpi=100, facecolor=SURFACE)
    plt.close(fig)
    return out


def threshold_chart(summary):
    sweep = summary['threshold_sweep']
    th = [s['threshold'] for s in sweep]
    fig, ax = plt.subplots(figsize=(9, 5), dpi=100, facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    series = [
        # current and fixed variants coincide on lyric queries (the summary branch never wins)
        ('Lyric queries: correct song returned', [s['unambiguous']['accuracy_fixed']['mean'] for s in sweep], SERIES[0]),
        ('Lyric queries: any song returned', [s['unambiguous']['pass_rate']['mean'] for s in sweep], SERIES[1]),
        ('Negative controls: any song returned (false accept)', [s['negative_false_accept_rate'] for s in sweep], SERIES[2]),
    ]
    for label, ys, c in series:
        ax.plot(th, ys, color=c, linewidth=2, solid_capstyle='round', marker='o', markersize=7,
                markeredgecolor=SURFACE, markeredgewidth=2, label=label, zorder=3)
        ax.text(th[-1] + 0.008, ys[-1], f'{ys[-1] * 100:.0f}%', va='center', fontsize=10, color=TEXT_PRIMARY)
    ax.axvline(summary['text_threshold'], color=TEXT_SECONDARY, linewidth=1, zorder=1)
    ax.text(summary['text_threshold'] + 0.004, 1.03, 'app.py threshold', fontsize=10, color=TEXT_SECONDARY)
    ax.set_xlim(th[0] - 0.02, th[-1] + 0.05)
    ax.set_ylim(0, 1.08)
    ax.set_xticks(th)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(['0%', '25%', '50%', '75%', '100%'])
    ax.set_xlabel('Threshold on max(summary score, lyric score)')
    ax.grid(axis='y', color=GRID, linewidth=1, zorder=0)
    ax.tick_params(length=0)
    for side in ('top', 'right', 'left'):
        ax.spines[side].set_visible(False)
    ax.legend(frameon=False, loc='lower left', fontsize=10, labelcolor=TEXT_PRIMARY)
    ax.set_title('Text search path: accuracy vs false accepts', loc='left', fontsize=14,
                 color=TEXT_PRIMARY, fontweight='semibold')
    fig.text(0.01, 0.01, f"Accuracy on unambiguous synthetic queries, mean of {len(summary['seeds'])} seeds; "
             f"negatives: {summary['negatives']['n']} everyday sentences not in the DB.",
             fontsize=9, color=TEXT_SECONDARY)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    out = os.path.join(RESULTS, 'threshold_tradeoff.png')
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)
    return out


if __name__ == '__main__':
    with open(os.path.join(RESULTS, 'summary.json'), encoding='utf-8') as f:
        s = json.load(f)
    print(recall_chart(s))
    print(threshold_chart(s))
