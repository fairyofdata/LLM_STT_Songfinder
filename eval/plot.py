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
ACCENT_BLUE = SERIES[0]

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


NOISE_LABELS = {
    'function_change': 'Particle swapped / dropped',
    'meaning_sub': 'Synonym (WordNet, in context)',
    'mixed': 'Mixed memory errors',
    'sound_sub': 'Sound-alike word (one mora off)',
    'context_sub': 'Plausible other word (ELECTRA-style)',
    'homophone': 'Same reading, other spelling',
    'drop': 'Word unit dropped',
}
RAMP = ['#86b6ef', '#2a78d6', '#104281']  # sequential blue 250/450/650, validated as ordinal


def noise_chart(noise):
    """Dot plot: Recall@1 per corruption type at three noise levels, common base lines only."""
    c = noise['common_base_lines_all_seeds']
    levels = noise['noise_levels']
    types = sorted(NOISE_LABELS, key=lambda t: -c['metrics'][f'{t}@{levels[1]}']['recall@1'])
    fig, ax = plt.subplots(figsize=(10, 5.4), dpi=100, facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    for yi, t in enumerate(types):
        vals = [c['metrics'][f'{t}@{l}']['recall@1'] for l in levels]
        ax.plot([min(vals), max(vals)], [yi, yi], color=GRID, linewidth=2, zorder=1, solid_capstyle='round')
        for li, (l, v) in enumerate(zip(levels, vals)):
            ci = c['metrics'][f'{t}@{l}']['recall@1_ci']
            ax.plot(ci, [yi, yi], color=RAMP[li], linewidth=1, zorder=2, alpha=0.6)
            ax.scatter([v], [yi], s=90, color=RAMP[li], edgecolor=SURFACE, linewidth=2, zorder=3)
        ax.text(1.02, yi, f'{vals[0] * 100:.0f} → {vals[-1] * 100:.0f}%', va='center', fontsize=10,
                color=TEXT_PRIMARY, transform=ax.get_yaxis_transform())
    ax.set_yticks(range(len(types)))
    ax.set_yticklabels([NOISE_LABELS[t] for t in types], fontsize=11, color=TEXT_PRIMARY)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xticklabels(['0%', '25%', '50%', '75%', '100%'])
    ax.grid(axis='x', color=GRID, linewidth=1, zorder=0)
    ax.tick_params(length=0)
    for side in ('top', 'right', 'left', 'bottom'):
        ax.spines[side].set_visible(False)
    handles = [plt.Line2D([], [], marker='o', linestyle='', markersize=9, markerfacecolor=col,
                          markeredgecolor=SURFACE) for col in RAMP]
    ax.legend(handles, [f'{int(l * 100)}% of word units changed' for l in levels], frameon=False,
              loc='upper left', fontsize=10, labelcolor=TEXT_PRIMARY)
    ax.set_title('Half-remembered lyrics: Recall@1 by kind of memory error', loc='left', fontsize=14,
                 color=TEXT_PRIMARY, fontweight='semibold')
    fig.text(0.01, 0.01, f"Same {c['n_base_lines']:,} base lines (all seeds) for every type; synthetic corruptions "
             f"of indexed lyrics, {len(noise['seeds'])} seeds; thin bars: 95% CI resampling songs.",
             fontsize=9, color=TEXT_SECONDARY)
    fig.tight_layout(rect=(0, 0.03, 0.93, 1))
    out = os.path.join(RESULTS, 'noise_curves.png')
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)
    return out


AUDIO_LABELS = {'A': 'Exact lyric\nnative JP voice', 'B': 'Exact lyric\nKorean reading',
                'C': 'Blurred lyric\nnative JP voice', 'D': 'Blurred lyric\nKorean reading',
                'S': 'One line only\nnative JP voice'}


def audio_chart(audio):
    """Two panels (clean, degraded): accuracy with Whisper language auto vs forced ja, typed as a tick."""
    cells = audio['summary']['cells']
    conds = list(AUDIO_LABELS)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.2), dpi=100, facecolor=SURFACE, sharey=True)
    bar_w = 0.22  # ~24 px at this size
    for ax, ch, title in zip(axes, ['clean', 'phone_reverb_noise'],
                             ['Clean TTS audio', 'Phone band + reverb + noise']):
        ax.set_facecolor(SURFACE)
        for ci, cond in enumerate(conds):
            for li, (lang, col) in enumerate([('auto', SERIES[0]), ('ja', SERIES[1])]):
                cell = cells.get(f'{cond}|{ch}|{lang}')
                if not cell:
                    continue
                x = ci + (li - 0.5) * (bar_w + 0.02)
                ax.bar(x, cell['accuracy'], width=bar_w, color=col, zorder=2)
                lo, hi = cell['accuracy_ci']
                ax.plot([x, x], [lo, hi], color=TEXT_PRIMARY, linewidth=1, zorder=3)
                ax.text(x, hi + 0.015, f"{cell['accuracy'] * 100:.0f}", ha='center', va='bottom',
                        fontsize=9, color=TEXT_PRIMARY)
            typed = cells[f'{cond}|{ch}|auto']['typed_accuracy']
            ax.plot([ci - 0.4, ci + 0.4], [typed, typed], color=TEXT_PRIMARY, linewidth=1.5, linestyle='-',
                    zorder=4)
        ax.set_xticks(range(len(conds)))
        ax.set_xticklabels([AUDIO_LABELS[c] for c in conds], fontsize=9.5, color=TEXT_PRIMARY)
        ax.set_ylim(0, 1.08)
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.set_yticklabels(['0%', '25%', '50%', '75%', '100%'])
        ax.grid(axis='y', color=GRID, linewidth=1, zorder=0)
        ax.tick_params(length=0)
        for side in ('top', 'right', 'left'):
            ax.spines[side].set_visible(False)
        ax.set_title(title, loc='left', fontsize=12, color=TEXT_PRIMARY)
    handles = [plt.Rectangle((0, 0), 1, 1, facecolor=SERIES[0]), plt.Rectangle((0, 0), 1, 1, facecolor=SERIES[1]),
               plt.Line2D([], [], color=TEXT_PRIMARY, linewidth=1.5)]
    fig.legend(handles, ['Whisper detects language (as the app)', 'Whisper forced to Japanese',
                         'Same text typed (no speech)'],
               loc='upper right', ncol=3, frameon=False, fontsize=10, labelcolor=TEXT_PRIMARY)
    fig.suptitle('Voice path: song found (top-1) from TTS speech', x=0.01, ha='left', fontsize=14,
                 color=TEXT_PRIMARY, fontweight='semibold')
    q = audio['summary']['queries']
    fig.text(0.01, 0.01, f"{q['songs']} songs; A-D: 2-6 consecutive lines (median 10 s of speech), S: one line; local TTS "
             f"(18 JP / 11 Korean voices), Whisper large-v3; thin bars: 95% CI resampling songs. Synthetic speech.",
             fontsize=9, color=TEXT_SECONDARY)
    fig.tight_layout(rect=(0, 0.04, 1, 0.92))
    out = os.path.join(RESULTS, 'audio_local.png')
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)
    return out


FIX_LABELS = AUDIO_LABELS
NEUTRAL = '#b9b8b2'


def fixes_chart(fixes):
    """1200x627: voice path accuracy today vs with both fixes (clean audio)."""
    both = fixes['both_fixes']
    conds = list(FIX_LABELS)
    fig = plt.figure(figsize=(12, 6.27), dpi=100, facecolor=SURFACE)
    ax_box = [0.065, 0.2, 0.915, 0.5]
    ax = fig.add_axes(ax_box, facecolor=SURFACE)
    y_max = 1.0
    px_x = ax_box[2] * 1200 / len(conds)
    px_y = ax_box[3] * 627 / y_max
    bar_w, gap = 34 / px_x, 3 / px_x
    rx, ry = 4 / px_x, 4 / px_y
    for ci, cond in enumerate(conds):
        cell = both[f'{cond}|clean']
        for k, (key, col) in enumerate([('app', NEUTRAL), ('both_fixes', ACCENT_BLUE)]):
            v = cell[key]
            x = ci - bar_w - gap / 2 + k * (bar_w + gap)
            rounded_bar(ax, x, bar_w, v, col, rx, ry)
            lo, hi = cell[f'{key}_ci']
            ax.plot([x + bar_w / 2] * 2, [lo, hi], color=TEXT_PRIMARY, linewidth=1, zorder=3)
            ax.text(x + bar_w / 2, hi + 0.012, f'{v * 100:.0f}', ha='center', va='bottom', fontsize=10.5,
                    color=TEXT_PRIMARY, fontweight='semibold' if key == 'both_fixes' else 'normal')
    ax.set_xlim(-0.5, len(conds) - 0.5)
    ax.set_ylim(0, y_max)
    ax.set_yticks([0, 0.25, 0.5, 0.75])
    ax.set_yticklabels(['0%', '25%', '50%', '75%'], fontsize=11)
    ax.set_xticks(range(len(conds)))
    ax.set_xticklabels([FIX_LABELS[c] for c in conds], fontsize=11.5, color=TEXT_PRIMARY)
    ax.tick_params(axis='both', length=0, pad=8)
    ax.grid(axis='y', color=GRID, linewidth=1, zorder=0)
    for side in ('top', 'right', 'left'):
        ax.spines[side].set_visible(False)
    ax.spines['bottom'].set_color('#c9c8c3')
    fig.text(0.065, 0.93, 'Voice search: two small fixes take Korean-accented speech from 36% to 69%', fontsize=21,
             fontweight='semibold', color=TEXT_PRIMARY)
    fig.text(0.065, 0.875, 'Song found at rank 1 from ~10 s of speech (2-6 lyric lines) or one line; same audio, same '
             'transcripts, 449 songs', fontsize=12.5, color=TEXT_SECONDARY)
    handles = [plt.Rectangle((0, 0), 1, 1, facecolor=NEUTRAL, linewidth=0),
               plt.Rectangle((0, 0), 1, 1, facecolor=ACCENT_BLUE, linewidth=0)]
    fig.legend(handles, ['App today', 'With both fixes'], loc='upper left', bbox_to_anchor=(0.058, 0.85), ncol=2,
               frameon=False, fontsize=12, handlelength=1.1, handleheight=1.1, columnspacing=1.6,
               labelcolor=TEXT_PRIMARY)
    fig.text(0.065, 0.068, 'Fix 1: if Whisper detects Korean, transcribe again as Japanese.  Fix 2: also search '
             'line-sized pieces of the transcript and vote (index is per lyric line).', fontsize=10.5,
             color=TEXT_SECONDARY)
    fig.text(0.065, 0.032, 'Synthetic TTS speech from indexed lyrics, local Whisper large-v3; thin bars: 95% CI '
             'resampling songs. Fix 2 weight confirmed on held-out typed queries.', fontsize=10.5,
             color=TEXT_SECONDARY)
    out = os.path.join(RESULTS, 'voice_fixes.png')
    fig.savefig(out, dpi=100, facecolor=SURFACE)
    plt.close(fig)
    return out


if __name__ == '__main__':
    with open(os.path.join(RESULTS, 'summary.json'), encoding='utf-8') as f:
        s = json.load(f)
    print(recall_chart(s))
    print(threshold_chart(s))
    for name, fn in [('noise_summary.json', noise_chart), ('audio_local.json', audio_chart),
                     ('audio_fixes.json', fixes_chart)]:
        path = os.path.join(RESULTS, name)
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                print(fn(json.load(f)))
