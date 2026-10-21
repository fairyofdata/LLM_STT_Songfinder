"""Diagrams for the project overview (docs/PORTFOLIO.md, LinkedIn, portfolio pages).

    venv/Scripts/python docs/figures.py

Writes docs/assets/architecture.png and docs/assets/eval_design.png (1200x627).
Facts mirror app.py and eval/; no lyric text.
"""
import os

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, 'assets')

SURFACE = '#fcfcfb'
TEXT_PRIMARY = '#0b0b0b'
TEXT_SECONDARY = '#52514e'
BOX = '#f1f0ec'
BOX_EDGE = '#c9c8c3'
ACCENT = '#2a78d6'       # categorical slot 1 (same as the charts)
ACCENT_FILL = '#e6f0fb'
ACCENT_2 = '#eb6834'     # slot 2

plt.rcParams.update({'font.family': ['Segoe UI', 'DejaVu Sans']})


def canvas(title, subtitle):
    fig = plt.figure(figsize=(12, 6.27), dpi=100, facecolor=SURFACE)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 120)
    ax.set_ylim(0, 62.7)
    ax.axis('off')
    ax.text(3, 58.6, title, fontsize=19, fontweight='semibold', color=TEXT_PRIMARY, va='center')
    ax.text(3, 54.6, subtitle, fontsize=11.5, color=TEXT_SECONDARY, va='center')
    return fig, ax


def box(ax, x, y, w, h, title, lines=(), fill=BOX, edge=BOX_EDGE, title_color=TEXT_PRIMARY, size=10.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0,rounding_size=1.2',
                                facecolor=fill, edgecolor=edge, linewidth=1.2, zorder=2))
    ax.text(x + 1.4, y + h - 1.9, title, fontsize=size, fontweight='semibold', color=title_color,
            va='top', zorder=3)
    for i, line in enumerate(lines):
        ax.text(x + 1.4, y + h - 5.0 - i * 2.75, line, fontsize=size - 1.5, color=TEXT_SECONDARY, va='top', zorder=3)


def arrow(ax, x0, y0, x1, y1, color=TEXT_SECONDARY, style='-|>', ls='-'):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle=style, mutation_scale=12, color=color,
                                 linewidth=1.3, linestyle=ls, zorder=1, shrinkA=0, shrinkB=0))


def architecture():
    fig, ax = canvas('Songfinder: say or type a half-remembered J-POP lyric, get the song',
                     'My module in the 6-person team project URFIT. Angular frontend, FastAPI backend.')
    # evaluated scope
    ax.add_patch(FancyBboxPatch((25.5, 14.0), 47.5, 37.0, boxstyle='round,pad=0,rounding_size=1.6',
                                facecolor=ACCENT_FILL, edgecolor=ACCENT, linewidth=1.6, linestyle=(0, (5, 3)),
                                zorder=1))
    ax.text(26.8, 49.2, 'Measured in this repo (eval/): which song is identified', fontsize=10.5,
            color=ACCENT, fontweight='semibold', va='top')

    box(ax, 3, 36, 19, 10, 'Voice query', ['browser recording', '5-15 s, rejected under 5 s'])
    box(ax, 3, 21, 19, 10, 'Typed query', ['a lyric fragment', 'in any language'])
    box(ax, 27.5, 33, 19, 13, 'Speech to text', ['OpenAI whisper-1', 'language auto-detected'])
    box(ax, 51.5, 33, 19.5, 13, 'Embed + search', ['multilingual MiniLM, 384-d', 'FAISS exact inner product',
                                                    '22,806 lines, 461 summaries'])
    box(ax, 27.5, 16, 43.5, 13, 'Song decision', ['voice: song of the top-1 lyric line',
                                                  'text: top-1 line vs top-1 summary, accept if > 0.4',
                                                  'otherwise "not found"'])
    box(ax, 77, 33, 19.5, 13, 'Recommend 3 songs', ['song + summary + lyric', 'similarity, tag bonus,',
                                                     'one per artist'])
    box(ax, 77, 16, 19.5, 13, 'Playlist text', ['GPT-3.5 writes a', 'title and description'])
    box(ax, 100, 24.5, 17, 13, 'Spotify', ['OAuth login,', 'playlist creation,', 'web playback'])
    box(ax, 3, 3, 114, 8, 'Offline data pipeline (notebooks)',
        ['J-POP chart crawl  ->  lyrics cleaning, language filter, de-duplication  ->  '
         'LLM tags and summaries  ->  embeddings  ->  461 songs'])

    arrow(ax, 22, 41, 27.5, 41)
    arrow(ax, 46.5, 39.5, 51.5, 39.5)
    arrow(ax, 22, 26, 51.5, 33, ls=(0, (4, 3)))
    arrow(ax, 61, 33, 61, 29)
    arrow(ax, 71, 24, 77, 37)
    arrow(ax, 86.75, 33, 86.75, 29)
    arrow(ax, 96.5, 39.5, 100, 33)
    arrow(ax, 96.5, 22.5, 100, 28)
    arrow(ax, 49, 11, 49, 14, color=TEXT_SECONDARY)
    ax.text(50, 12.5, 'builds the indexes', fontsize=8.5, color=TEXT_SECONDARY, va='center')
    ax.text(27.5, 31.3, 'text skips speech to text', fontsize=8.5, color=TEXT_SECONDARY)
    out = os.path.join(ASSETS, 'architecture.png')
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)
    return out


def eval_design():
    fig, ax = canvas('How the identification step was evaluated',
                     'Synthetic queries from the indexed lyrics, run through the app\'s own decision logic. '
                     'No lyric text is stored in results.')
    top, bottom, h_top, h_bottom = 31.5, 11.5, 17, 18.5
    box(ax, 3, bottom, 17, top + h_top - bottom, 'Indexed lyrics',
        ['450 songs with lines', 'lines sampled per song,', 'seeds 0-4', 'lines shared across',
         'songs reported apart'])
    box(ax, 23.5, top, 24, h_top, 'Typed queries', ['5 edits: exact, half, word drop,', 'typo, two adjacent lines',
                                                    '7 memory errors x 20/40/60%', '90 out-of-DB sentences'],
        fill=ACCENT_FILL, edge=ACCENT, title_color=ACCENT)
    box(ax, 23.5, bottom, 24, h_bottom, 'Spoken queries', ['A exact x native JP voice', 'B exact x Korean reading',
                                                           'C blurred x native JP voice',
                                                           'D blurred x Korean reading', 'S one line only'],
        fill='#fdeee6', edge=ACCENT_2, title_color=ACCENT_2)
    box(ax, 51, bottom, 21, h_bottom, 'LocalTTS + channel', ['18 JP / 11 Korean voices',
                                                             'Kokoro, Supertonic, Windows',
                                                             'Hangul reading of Japanese', 'clean, or phone band',
                                                             '+ reverb + noise'])
    box(ax, 75.5, bottom, 19, h_bottom, 'Transcribe', ['Whisper large-v3 (local)', 'language: auto (as app)',
                                                      'or forced Japanese', 'whisper-1 API: 1,341 clips'])
    box(ax, 75.5, top, 19, h_top, 'App decision logic', ['re-implemented,', 'checked 140/140', 'against app.py'])
    box(ax, 98, bottom, 19, top + h_top - bottom, 'Metrics',
        ['Recall@1/5/10, MRR', 'identification accuracy', 'false-accept rate', 'threshold sweep',
         'song-level bootstrap CI', 'McNemar (paired)', 'blind human check'])
    box(ax, 3, 2.5, 114, 7.5, 'Not measured',
        ["real users' recordings, singing or humming; recommendation quality; Spotify and UI flows"])

    y_top, y_bottom = top + h_top / 2, bottom + h_bottom / 2
    arrow(ax, 20, y_top, 23.5, y_top)
    arrow(ax, 20, y_bottom, 23.5, y_bottom)
    arrow(ax, 47.5, y_top, 75.5, y_top, color=ACCENT)
    arrow(ax, 47.5, y_bottom, 51, y_bottom, color=ACCENT_2)
    arrow(ax, 72, y_bottom, 75.5, y_bottom, color=ACCENT_2)
    arrow(ax, 85, bottom + h_bottom, 85, top, color=ACCENT_2)
    arrow(ax, 94.5, y_top, 98, y_top)
    out = os.path.join(ASSETS, 'eval_design.png')
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)
    return out


if __name__ == '__main__':
    os.makedirs(ASSETS, exist_ok=True)
    print(architecture())
    print(eval_design())
