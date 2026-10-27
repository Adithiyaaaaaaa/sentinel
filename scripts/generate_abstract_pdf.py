"""Generate the standalone SENTINEL academic abstract PDF."""

from pathlib import Path

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "SENTINEL_Project_Abstract.pdf"
FONT_ROOT = Path("C:/Windows/Fonts")


def register_fonts() -> None:
    fonts = {
        "TimesNewRoman": "times.ttf",
        "TimesNewRoman-Bold": "timesbd.ttf",
        "TimesNewRoman-Italic": "timesi.ttf",
        "TimesNewRoman-BoldItalic": "timesbi.ttf",
    }
    for name, filename in fonts.items():
        path = FONT_ROOT / filename
        if not path.is_file():
            raise FileNotFoundError(f"Required Times New Roman font is missing: {path}")
        pdfmetrics.registerFont(TTFont(name, str(path)))


def footer(canvas, document) -> None:
    canvas.saveState()
    canvas.setFont("TimesNewRoman", 9)
    canvas.setFillColorRGB(0.32, 0.35, 0.39)
    canvas.drawString(document.leftMargin, 0.52 * inch, "SENTINEL Project Abstract")
    canvas.drawRightString(A4[0] - document.rightMargin, 0.52 * inch, f"Page {document.page}")
    canvas.restoreState()


def build() -> None:
    register_fonts()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        rightMargin=0.88 * inch,
        leftMargin=0.88 * inch,
        topMargin=0.72 * inch,
        bottomMargin=0.78 * inch,
        title="SENTINEL Project Abstract",
        author="SENTINEL Project",
        subject="Local AI Code Review and Engineering Intelligence Platform",
    )
    title = ParagraphStyle(
        "Title",
        fontName="TimesNewRoman-Bold",
        fontSize=17,
        leading=21,
        alignment=TA_CENTER,
        spaceAfter=8,
        textColor="#17202A",
    )
    subtitle = ParagraphStyle(
        "Subtitle",
        fontName="TimesNewRoman-Italic",
        fontSize=11.5,
        leading=15,
        alignment=TA_CENTER,
        spaceAfter=17,
        textColor="#3E4A59",
    )
    heading = ParagraphStyle(
        "Heading",
        fontName="TimesNewRoman-Bold",
        fontSize=12,
        leading=15,
        alignment=TA_CENTER,
        spaceAfter=9,
        textColor="#17202A",
    )
    body = ParagraphStyle(
        "Body",
        fontName="TimesNewRoman",
        fontSize=11.5,
        leading=17,
        alignment=TA_JUSTIFY,
        firstLineIndent=0.28 * inch,
        spaceAfter=10,
        textColor="#111820",
    )
    keywords = ParagraphStyle(
        "Keywords",
        fontName="TimesNewRoman",
        fontSize=10.5,
        leading=15,
        alignment=TA_JUSTIFY,
        spaceBefore=4,
        textColor="#263442",
    )

    paragraphs = [
        "SENTINEL - Local AI Code Review and Engineering Intelligence Platform",
        "A privacy-first system for evidence-backed repository analysis and guarded AI assistance",
        "ABSTRACT",
        (
            "Modern software repositories are difficult to understand because source code, dependencies, "
            "architecture, security signals, and review history are spread across separate tools. Generative "
            "AI can accelerate review, but its output may be incorrect, unverifiable, or unsafe to apply. "
            "SENTINEL addresses this problem through a local-first engineering intelligence platform that "
            "combines deterministic static analysis with optional local AI assistance while preserving a "
            "clear boundary between evidence and model opinion."
        ),
        (
            "The platform indexes a permitted repository directory without importing or executing repository "
            "code. It detects files, languages, frameworks, package managers, dependencies, tests, source "
            "entities, and content fingerprints. Python abstract syntax trees and JavaScript, TypeScript, and "
            "TSX syntax trees support a bounded ruleset of security, quality, and performance findings. Each "
            "finding records its file, line range, symbol, risk basis, and structural evidence. A persistent "
            "repository graph and local embedding index add relationship exploration and semantic search."
        ),
        (
            "Optional AI workflows use installed GGUF models through a loopback Ollama service. Context is "
            "bounded, source fingerprints are rechecked, detected secret assignments are redacted, and model "
            "responses are treated as untrusted data. Explanations must satisfy a schema and cite supplied "
            "evidence. Python fix and pytest proposals pass syntax, import, selected-symbol, exact-diff, model "
            "digest, review-hash, and source-fingerprint gates. Approved tests can run only in a pinned Docker "
            "sandbox with no network, a read-only root filesystem, a non-root user, resource limits, and no "
            "host-execution fallback. Applying or rolling back a change requires explicit approval and atomic "
            "fingerprint-checked file operations."
        ),
        (
            "SENTINEL was implemented incrementally across repository indexing, deterministic analysis, local "
            "reasoning, graph and semantic search, and reviewed changes. The verified build passes 117 automated "
            "tests together with Python linting, TypeScript validation, database migration checks, production "
            "builds, a live API smoke scan, and browser workflows. The result is not a claim of complete security "
            "or autonomous remediation. It is an evidence-centered review environment that improves repository "
            "understanding while making uncertainty, coverage, approval, and execution boundaries visible. Future "
            "work includes a safe local GitHub importer, report export, command-line and desktop clients, broader "
            "analysis, scan-to-scan trends, and a hosted edition based on GitHub Apps, durable queues, managed "
            "PostgreSQL, tenant isolation, and disposable analysis workers."
        ),
    ]

    story = [
        Paragraph(paragraphs[0], title),
        Paragraph(paragraphs[1], subtitle),
        Paragraph(paragraphs[2], heading),
    ]
    for paragraph in paragraphs[3:]:
        story.append(Paragraph(paragraph, body))
    story.extend(
        [
            Spacer(1, 4),
            Paragraph(
                "<b>Keywords:</b> static analysis; local AI; code review; repository intelligence; "
                "semantic search; secure sandboxing; software engineering.",
                keywords,
            ),
        ]
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    print(OUTPUT)


if __name__ == "__main__":
    build()
