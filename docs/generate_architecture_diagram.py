"""Regenerates docs/architecture.png. Run with: python docs/generate_architecture_diagram.py
Requires matplotlib (not a runtime dependency of the app, install separately).
"""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUTPUT_PATH = Path(__file__).resolve().parent / "architecture.png"

BOX_FILL = "#eef2ff"
BOX_EDGE = "#4338ca"
DB_FILL = "#fef3c7"
DB_EDGE = "#b45309"
TEXT_COLOR = "#1a1a1a"


def draw_box(ax, xy, width, height, label, fill=BOX_FILL, edge=BOX_EDGE, fontsize=10):
    x, y = xy
    box = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=1.5,
        edgecolor=edge,
        facecolor=fill,
    )
    ax.add_patch(box)
    ax.text(
        x + width / 2,
        y + height / 2,
        label,
        ha="center",
        va="center",
        fontsize=fontsize,
        color=TEXT_COLOR,
        wrap=True,
    )
    return (x + width / 2, y), (x + width / 2, y + height), (x, y + height / 2), (x + width, y + height / 2)


def draw_arrow(ax, start, end, label=None, rad=0.0):
    arrow = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=14,
        linewidth=1.3,
        color="#555",
        connectionstyle=f"arc3,rad={rad}" if rad else None,
    )
    ax.add_patch(arrow)
    if label:
        mx, my = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
        ax.text(mx, my + 0.12, label, ha="center", fontsize=7.5, color="#555")


def main():
    fig, ax = plt.subplots(figsize=(13, 7.5))
    ax.set_xlim(-0.6, 13)
    ax.set_ylim(0, 9.8)
    ax.axis("off")

    ax.text(6.5, 9.4, "Neostat Document Intelligence -- Architecture", ha="center", fontsize=15, weight="bold")
    ax.text(
        6.5,
        9.0,
        "One FastAPI service: REST API + server-rendered frontend, one deployment",
        ha="center",
        fontsize=9.5,
        color="#555",
    )

    browser_pts = draw_box(ax, (0.4, 7.4), 2.2, 0.9, "Browser\n(upload / dashboard / result pages)")
    api_pts = draw_box(ax, (3.2, 7.4), 2.4, 0.9, "FastAPI app\n(Jinja2 templates + REST API)")
    draw_arrow(ax, browser_pts[3], api_pts[2], "HTTP")

    validation_pts = draw_box(ax, (0.4, 5.0), 2.6, 0.9, "1. File validation\n(type, size, pages, corruption)")
    extraction_pts = draw_box(ax, (3.4, 5.0), 2.6, 0.9, "2. Text extraction\ntext layer OR render + OCR")
    llm_pts = draw_box(ax, (6.4, 5.0), 2.6, 0.9, "3. LLM structured extraction\nGemini 2.5 Flash + Pydantic schema")
    ground_pts = draw_box(ax, (9.4, 5.0), 2.9, 0.9, "4. Grounding check\nvalue must appear in source text")

    draw_arrow(ax, api_pts[0], validation_pts[1])
    draw_arrow(ax, validation_pts[3], extraction_pts[2])
    draw_arrow(ax, extraction_pts[3], llm_pts[2])
    draw_arrow(ax, llm_pts[3], ground_pts[2])

    conf_pts = draw_box(ax, (9.4, 3.3), 2.9, 0.9, "5. Confidence scoring\nrule-based, explainable")
    fin_pts = draw_box(ax, (6.4, 3.3), 2.6, 0.9, "6. Financial validation\nlabel matching + tolerance checks")
    persist_pts = draw_box(ax, (3.4, 3.3), 2.6, 0.9, "7. Persistence\nDocumentRepository -> Postgres")
    response_pts = draw_box(ax, (0.4, 3.3), 2.6, 0.9, "8. JSON response\n+ dashboard / result page")

    draw_arrow(ax, ground_pts[0], conf_pts[1])
    draw_arrow(ax, conf_pts[2], fin_pts[3])
    draw_arrow(ax, fin_pts[2], persist_pts[3])
    draw_arrow(ax, persist_pts[2], response_pts[3])
    draw_arrow(ax, (0.4, 3.75), (0.45, 7.4), label="JSON response", rad=-0.5)

    db_pts = draw_box(ax, (3.6, 1.6), 2.2, 0.9, "Neon Postgres\n(documents table)", fill=DB_FILL, edge=DB_EDGE)
    draw_arrow(ax, persist_pts[0], db_pts[1])

    ocr_pts = draw_box(ax, (6.9, 1.6), 2.0, 0.9, "Tesseract OCR\n(OCRProvider)", fill=DB_FILL, edge=DB_EDGE)
    draw_arrow(ax, extraction_pts[0], ocr_pts[1])

    gemini_pts = draw_box(ax, (9.4, 1.6), 2.2, 0.9, "Gemini API\n(LLMProvider)", fill=DB_FILL, edge=DB_EDGE)
    draw_arrow(ax, llm_pts[0], gemini_pts[1])

    plt.tight_layout()
    fig.savefig(OUTPUT_PATH, dpi=150)
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
