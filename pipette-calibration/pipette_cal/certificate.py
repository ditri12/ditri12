"""PDF calibration certificate (reportlab, 2 pages, A4).

Page 1: logo + title banner, info bar, three info columns, the three
        results tables (LOW / MID / HIGH).
Page 2: signature block + LifeGene contact details, disclaimer and the bold
        scope-of-calibration notice.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from . import __version__
from .models import Level
from .stats import CalibrationResult, LevelResult

COMPANY = "LifeGene Ltd."
COMPANY_ADDRESS = "LifeGene, Mevo Horon, Israel"
COMPANY_PHONE = "+972-(0)8-6444314"
COMPANY_EMAIL = "info@lifegene.co.il"
COMPANY_TAGLINE = "Supporting Science"

CALIBRATION_METHOD = "Gravimetric - for academic / internal use only"

SCOPE_STATEMENT = (
    "IMPORTANT NOTICE - SCOPE OF CALIBRATION: This calibration certificate is issued "
    "for internal quality-control and academic reference purposes only. The calibration "
    "was performed using a gravimetric method and reflects the performance of the "
    "instrument at the time of testing under the environmental conditions recorded "
    "herein. This certificate does not represent accredited calibration and has not "
    "been issued under any national or international accreditation standard "
    "(including ISO/IEC 17025 or equivalent). The results shall not be used as a "
    "substitute for accredited calibration where regulatory or legal compliance "
    "requires one. LifeGene Ltd. assumes no liability for decisions made solely on the "
    "basis of this document beyond its stated internal use."
)

DISCLAIMER = (
    "The results reported in this certificate relate only to the instrument identified "
    "above, as received and tested on the calibration date. Measurements were taken "
    "with distilled water at the recorded ambient conditions and converted to volume "
    "using the density of water and an air-buoyancy correction (Z factor). The "
    "systematic error is the difference between the mean delivered volume and the "
    "nominal test volume; the random error is the standard deviation of the "
    "replicate deliveries. The reported expanded uncertainty is based on a coverage "
    "factor k = 2 (approximately 95 % confidence). The next calibration date is a "
    "recommendation; the user remains responsible for the suitability of the "
    "instrument for its intended use."
)

BLUE = colors.HexColor("#1f5fa8")
GREEN = colors.HexColor("#2e9e5b")
RED = colors.HexColor("#c0392b")
GREY = colors.HexColor("#6b7280")
LIGHT = colors.HexColor("#f3f4f6")
LINE = colors.HexColor("#d1d5db")
LEVEL_COLORS = {Level.LOW: colors.HexColor("#2563eb"),
                Level.MID: colors.HexColor("#0891b2"),
                Level.HIGH: colors.HexColor("#7c3aed")}


@dataclass
class CertificateInfo:
    document_no: str
    calibration_date: date
    next_calibration_date: date
    serial_no: str
    tip: str
    operator: str = ""
    balance_id: str = ""
    place: str = "LifeGene Lab, Mevo Horon, Israel"
    comments: str = ""
    logo_path: Path | None = None


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    s = {
        "title": ParagraphStyle("title", parent=base["Title"], fontName="Helvetica-Bold",
                                fontSize=17, leading=20, textColor=colors.white,
                                alignment=TA_CENTER, spaceAfter=0, spaceBefore=0),
        "h": ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=9.5, leading=12,
                            textColor=BLUE, spaceAfter=2),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=8.2, leading=10.5),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=7.4, leading=9.5,
                                textColor=GREY),
        "label": ParagraphStyle("label", fontName="Helvetica", fontSize=7.6, leading=9.5,
                                textColor=GREY),
        "value": ParagraphStyle("value", fontName="Helvetica-Bold", fontSize=8.4, leading=10.5),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8, leading=9.8,
                               alignment=TA_CENTER),
        "cellb": ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=8, leading=9.8,
                                alignment=TA_CENTER),
        "scope": ParagraphStyle("scope", fontName="Helvetica-Bold", fontSize=8.4, leading=11,
                                alignment=TA_LEFT),
        "legal": ParagraphStyle("legal", fontName="Helvetica", fontSize=8, leading=10.5),
        "logo_a": ParagraphStyle("logo_a", fontName="Helvetica-Bold", fontSize=20, leading=22,
                                 textColor=BLUE),
        "logo_b": ParagraphStyle("logo_b", fontName="Helvetica-Oblique", fontSize=7.5,
                                 leading=9, textColor=GREEN),
    }
    return s


def _fmt(x: float, nd: int = 3) -> str:
    return f"{x:.{nd}f}"


def _logo_flowable(info: CertificateInfo, st) -> object:
    if info.logo_path and Path(info.logo_path).exists():
        try:
            img = Image(str(info.logo_path))
            ratio = img.imageWidth / float(img.imageHeight)
            img.drawHeight = 16 * mm
            img.drawWidth = 16 * mm * ratio
            return img
        except Exception:  # noqa: BLE001 - fall back to the text logo
            pass
    text = (f'<font color="{BLUE.hexval()}">LIFE</font>'
            f'<font color="{GREEN.hexval()}">GENE</font>')
    return [Paragraph(text, st["logo_a"]), Paragraph(COMPANY_TAGLINE, st["logo_b"])]


def _level_table(lv: LevelResult, st) -> Table:
    colour = LEVEL_COLORS[lv.level]
    ok = lambda b: Paragraph(  # noqa: E731
        f'<font color="{(GREEN if b else RED).hexval()}"><b>{"PASS" if b else "FAIL"}</b></font>',
        st["cell"])
    header = [Paragraph(f"<b>{lv.level.value}  -  nominal {lv.nominal_ul:g} uL</b>", st["cellb"]),
              "", "", "", "", ""]
    rows = [
        header,
        [Paragraph("<b>Average volume (uL)</b>", st["cell"]),
         Paragraph("<b>Systematic error (uL)</b>", st["cell"]),
         Paragraph("<b>Systematic error (%)</b>", st["cell"]),
         Paragraph("<b>Random error SD (uL)</b>", st["cell"]),
         Paragraph("<b>CV (%)</b>", st["cell"]),
         Paragraph("<b>Uncertainty U (uL)</b>", st["cell"])],
        [Paragraph(_fmt(lv.mean_ul), st["cellb"]),
         Paragraph(f"{lv.systematic_error_ul:+.3f}", st["cell"]),
         Paragraph(f"{lv.systematic_error_pct:+.2f}", st["cell"]),
         Paragraph(_fmt(lv.random_error_ul), st["cell"]),
         Paragraph(_fmt(lv.cv_pct, 2), st["cell"]),
         Paragraph(f"&#177; {_fmt(lv.uncertainty_ul)}", st["cell"])],
        [Paragraph("Limit", st["small"]),
         Paragraph(f"&#177; {lv.sys_limit_ul:g}", st["cell"]), ok(lv.systematic_pass),
         Paragraph(f"&#8804; {lv.rnd_limit_ul:g}", st["cell"]), ok(lv.random_pass),
         Paragraph("k = 2", st["small"])],
        [Paragraph("Weights (g)", st["small"])] +
        [Paragraph(f"{w:.6f}", st["cell"]) for w in lv.weights_g] +
        [Paragraph("", st["cell"])] * (5 - len(lv.weights_g)),
        [Paragraph("Volumes (uL)", st["small"])] +
        [Paragraph(_fmt(v), st["cell"]) for v in lv.volumes_ul] +
        [Paragraph("", st["cell"])] * (5 - len(lv.volumes_ul)),
    ]
    width = (A4[0] - 30 * mm)
    t = Table(rows, colWidths=[width / 6] * 6)
    t.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("BACKGROUND", (0, 0), (-1, 0), colour),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 1), (-1, 1), LIGHT),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    # header row text must be white
    rows[0][0] = Paragraph(
        f'<font color="white"><b>{lv.level.value}  -  nominal {lv.nominal_ul:g} uL</b></font>',
        st["cellb"])
    return t


def _info_block(title: str, pairs: list[tuple[str, str]], st, width: float) -> Table:
    body = [[Paragraph(title, st["h"])]]
    for label, value in pairs:
        body.append([Paragraph(f'<font color="{GREY.hexval()}">{label}</font><br/>'
                               f'<b>{value or "-"}</b>', st["body"])])
    t = Table(body, colWidths=[width])
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (0, 0), 0.8, BLUE),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def build_certificate(path: str | Path, info: CertificateInfo, result: CalibrationResult) -> Path:
    """Render the certificate PDF to *path* and return the path."""
    path = Path(path)
    st = _styles()
    page_w = A4[0]
    margin = 15 * mm
    content_w = page_w - 2 * margin
    env = result.environment
    verdict_colour = GREEN if result.passed else RED

    doc = SimpleDocTemplate(
        str(path), pagesize=A4, leftMargin=margin, rightMargin=margin,
        topMargin=12 * mm, bottomMargin=12 * mm,
        title=f"Pipette Calibration Certificate {info.document_no}",
        author=COMPANY, subject=f"{result.spec.model} S/N {info.serial_no}",
        creator=f"LifeGene Pipette Calibration v{__version__}")

    story: list = []

    # ---- banner: logo | title ------------------------------------------
    banner = Table([[_logo_flowable(info, st),
                     Paragraph("Pipette Calibration Certificate", st["title"])]],
                   colWidths=[42 * mm, content_w - 42 * mm], rowHeights=[20 * mm])
    banner.setStyle(TableStyle([
        ("BACKGROUND", (1, 0), (1, 0), BLUE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("LEFTPADDING", (1, 0), (1, 0), 6),
        ("RIGHTPADDING", (1, 0), (1, 0), 6),
    ]))
    story += [banner, Spacer(1, 4 * mm)]

    # ---- info bar -------------------------------------------------------
    def kv(label, value, colour=None):
        v = f'<font color="{colour.hexval()}">{value}</font>' if colour else value
        return Paragraph(f'<font color="{GREY.hexval()}" size="7">{label}</font><br/>'
                         f'<b><font size="9.5">{v}</font></b>', st["body"])
    bar = Table([[kv("DOCUMENT No.", info.document_no),
                  kv("CALIBRATED BY", info.operator or "-"),
                  kv("CALIBRATION DATE", info.calibration_date.strftime("%d.%m.%Y")),
                  kv("CALIBRATION RESULT", result.verdict, verdict_colour)]],
                colWidths=[content_w / 4] * 4)
    bar.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("LINEAFTER", (0, 0), (-2, -1), 0.5, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story += [bar, Spacer(1, 4 * mm)]

    # ---- three info columns ---------------------------------------------
    col_w = content_w / 3 - 3 * mm
    spec = result.spec
    cols = Table([[
        _info_block("Pipette data", [
            ("Manufacturer / model", f"Gilson {spec.model}"),
            ("Type", "Multichannel" if spec.family == "multi" else "Single channel"),
            ("Volume range", spec.range_label),
            ("Serial number", info.serial_no),
            ("Tip", info.tip),
        ], st, col_w),
        _info_block("Environmental conditions", [
            ("Water temperature", f"{env.temperature_c:.1f} &#176;C"),
            ("Relative humidity", f"{env.humidity_pct:.0f} %"),
            ("Air pressure", f"{env.pressure_hpa:.1f} hPa"),
            ("Z factor (uL/mg)", f"{result.z:.5f}"),
            ("Balance", info.balance_id or "RADWAG analytical balance"),
        ], st, col_w),
        _info_block("Calibration", [
            ("Method", CALIBRATION_METHOD),
            ("Replicates", f"{len(result.levels[0].weights_g)} per test volume"),
            ("Place of calibration", info.place),
            ("Next calibration", info.next_calibration_date.strftime("%d.%m.%Y")),
            ("Comments", info.comments.strip() or "-"),
        ], st, col_w),
    ]], colWidths=[content_w / 3] * 3)
    cols.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm)]))
    story += [cols, Spacer(1, 4 * mm)]

    # ---- results --------------------------------------------------------
    story.append(Paragraph("AVERAGE RESULTS", st["h"]))
    for lv in result.levels:
        story.append(KeepTogether([_level_table(lv, st), Spacer(1, 2.5 * mm)]))

    # ---- page 2 ---------------------------------------------------------
    story.append(PageBreak())
    sig = Table([
        [Paragraph("Calibrated by", st["label"]), Paragraph("Approved by", st["label"]),
         Paragraph("Contact", st["label"])],
        [Paragraph(f"<b>{info.operator or '____________________'}</b>", st["body"]),
         Paragraph("____________________", st["body"]),
         Paragraph(f"<b>{COMPANY}</b><br/>{COMPANY_ADDRESS}<br/>"
                   f"Call us now: {COMPANY_PHONE}<br/>Email: {COMPANY_EMAIL}", st["body"])],
        [Paragraph(f"Date: {info.calibration_date.strftime('%d.%m.%Y')}", st["small"]),
         Paragraph("Date: ______________", st["small"]), Paragraph("", st["small"])],
    ], colWidths=[content_w / 3] * 3)
    sig.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 0.8, BLUE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story += [
        Paragraph("Signatures", st["h"]), sig, Spacer(1, 8 * mm),
        Paragraph("Notes", st["h"]), Paragraph(DISCLAIMER, st["legal"]), Spacer(1, 6 * mm),
        Paragraph(SCOPE_STATEMENT, st["scope"]), Spacer(1, 10 * mm),
        Paragraph("- End of report -", ParagraphStyle("end", parent=st["small"],
                                                      alignment=TA_CENTER)),
    ]

    def _footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        canvas.drawString(margin, 7 * mm,
                          f"{COMPANY}  |  {info.document_no}  |  Gilson {spec.model} S/N {info.serial_no}")
        canvas.drawRightString(page_w - margin, 7 * mm, f"Page {doc_.page} of 2")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return path


def default_filename(info: CertificateInfo, model: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in info.serial_no) or "NA"
    return f"{info.document_no}_{model}_{safe}_{info.calibration_date:%Y%m%d}.pdf"
