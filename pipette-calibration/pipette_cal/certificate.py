"""PDF calibration certificate (reportlab, A4, exactly two pages).

The layout follows the certificate format the lab approved in the original
project (LifeGene / Gilson style):

Page 1  logo + address | navy "Pipette / Calibration Certificate" banner
        info bar: Document No. | Operator | Calibration date | CALIBRATION RESULT
        three columns: Pipettes data | Environmental conditions | Calibration
        AVERAGE RESULTS: one block per test volume (LOW / MID / HIGH) with
        volume / first weight / normalised limits, the results row
        ("Canal 1") with the A / CV marks, and the individual weights.
Page 2  signature block + contact details, decision-rule notes, the bold
        scope-of-calibration notice in a blue box, end of report, footer.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (HRFlowable, Image, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from . import __version__
from .models import Level, short_model_name
from .stats import CalibrationResult, LevelResult

log = logging.getLogger(__name__)

COMPANY = "LifeGene Ltd."
COMPANY_ADDRESS = "Mevo Horon, Israel"
COMPANY_PHONE = "+972-(0)8-6444314"
COMPANY_EMAIL = "info@lifegene.co.il"
COMPANY_WEB = "www.LifeGene.co.il"
COMPANY_TAGLINE = "Supporting Science"

CALIBRATION_METHOD = "Gravimetric - For academic / internal use only"
DATE_FMT = "%d/%m/%Y"

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

NOTES = (
    "Accounting for the uncertainty will be taken to mean that at a 95 % confidence level "
    "the measurement results plus and minus the expanded uncertainty (k = 2) shall be "
    "totally within the specification limits and the risk of false acceptance / rejection "
    "will not be greater than 2.5 %.",
    "A binary decision rule is used for the statement of conformity according to the ILAC "
    "Guidelines on Decision Rules and Statements of Conformity (ILAC-G8:09/2019).",
    "The systematic error (A) is the difference between the mean delivered volume and the "
    "nominal test volume; the random error (CV) is the standard deviation of the replicate "
    "deliveries. Weights were converted to volume with the Z factor (density of water at "
    "the test temperature, corrected for air buoyancy).",
)
NOTE_PASS = ("We certify that the instrument stated above meets the acceptance limits "
             "published in this certificate at the time of testing.")
NOTE_FAIL = ("The instrument stated above does NOT meet the acceptance limits published in "
             "this certificate at one or more test volumes and should be serviced and "
             "re-calibrated before further use.")

# ---- brand colours (sampled from the LifeGene logo) -----------------------
LOGO_BLUE = colors.HexColor("#2e7db6")
LOGO_GREEN = colors.HexColor("#77b957")
NAVY = colors.HexColor("#1A2535")
BLUE = colors.HexColor("#1E6FBA")
LGREY = colors.HexColor("#F2F2F2")
MGREY = colors.HexColor("#D9D9D9")
DGREY = colors.HexColor("#595959")
BDGREY = colors.HexColor("#CCCCCC")
HDRGREY = colors.HexColor("#AAAAAA")
PASS_FG = colors.HexColor("#1E7E34")
FAIL_FG = colors.HexColor("#C82333")
PASS_BG = colors.HexColor("#D4EDDA")
FAIL_BG = colors.HexColor("#F8D7DA")
STMT_BG = colors.HexColor("#EFF6FF")
STMT_FG = colors.HexColor("#1A3A6B")
TEXT = colors.HexColor("#222222")

MARGIN_X = 1.5 * cm
CONTENT_W = A4[0] - 2 * MARGIN_X


@dataclass
class CertificateInfo:
    document_no: str
    calibration_date: date
    next_calibration_date: date
    serial_no: str
    tip: str
    operator: str = "Dmitri Trakhtman"
    balance_id: str = ""
    place: str = "LifeGene Lab, Mevo Horon, Israel"
    comments: str = ""
    series: str = "Classic"          # PIPETMAN series: Classic / Neo / L / Multi
    procedure: str = ""              # "Standard" line, printed when set
    customer: str = ""               # customer / department, printed when set
    logo_path: Path | None = None
    signature_path: Path | None = None   # image of the operator's signature (optional)
    signer_name: str = ""                # printed next to the signature; defaults to operator


# ---- symbol font for the check marks -----------------------------------------
_SYMBOL_FONT: str | None = None


def _symbol_font() -> str | None:
    """Register a TrueType font that contains U+2713/U+2717 (once); None if unavailable."""
    global _SYMBOL_FONT
    if _SYMBOL_FONT is not None:
        return _SYMBOL_FONT or None
    candidates = (
        Path("C:/Windows/Fonts/seguisym.ttf"), Path("C:/Windows/Fonts/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
        Path("/Library/Fonts/Arial Unicode.ttf"), Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    )
    for path in candidates:
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont("CertSymbols", str(path)))
                _SYMBOL_FONT = "CertSymbols"
                return _SYMBOL_FONT
            except Exception as exc:  # noqa: BLE001
                log.debug("font %s not usable: %s", path, exc)
    _SYMBOL_FONT = ""
    return None


def _mark(ok: bool, style: ParagraphStyle) -> Paragraph:
    colour = (PASS_FG if ok else FAIL_FG).hexval()
    font = _symbol_font()
    if font:
        glyph = "\u2713" if ok else "\u2717"
        return Paragraph(f'<font name="{font}" color="{colour}"><b>{glyph}</b></font>', style)
    return Paragraph(f'<font color="{colour}"><b>{"OK" if ok else "X"}</b></font>', style)


def _ps(name: str, size: float = 8, colour=TEXT, align=TA_LEFT, bold: bool = False,
        leading: float | None = None, italic: bool = False) -> ParagraphStyle:
    font = "Helvetica-BoldOblique" if bold and italic else "Helvetica-Bold" if bold \
        else "Helvetica-Oblique" if italic else "Helvetica"
    return ParagraphStyle(name, fontName=font, fontSize=size, textColor=colour,
                          alignment=align, leading=leading or size * 1.25)


def _logo(info: CertificateInfo):
    st_addr = _ps("addr", 7, DGREY)
    if info.logo_path and Path(info.logo_path).exists():
        try:
            img = Image(str(info.logo_path))
            ratio = img.imageWidth / float(img.imageHeight)
            img.drawHeight = 12 * mm
            img.drawWidth = min(12 * mm * ratio, 7.5 * cm)
            img.hAlign = "LEFT"
            head = img
        except Exception as exc:  # noqa: BLE001
            log.warning("logo not usable, using text logo: %s", exc)
            head = None
    else:
        head = None
    if head is None:
        head = Paragraph(f'<font color="{LOGO_GREEN.hexval()}"><b>LIFE</b></font>'
                         f'<font color="{LOGO_BLUE.hexval()}"><b>GENE</b></font>'
                         f'<br/><font size="7" color="{LOGO_GREEN.hexval()}"><i>{COMPANY_TAGLINE}</i></font>',
                         _ps("lg", 20, leading=22))
    rows = [[head], [Paragraph(COMPANY_ADDRESS, st_addr)],
            [Paragraph(f"{COMPANY_PHONE}  |  {COMPANY_EMAIL}", st_addr)],
            [Paragraph(COMPANY_WEB, st_addr)]]
    t = Table(rows, colWidths=[8 * cm])
    t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    return t


def _signature_image(info: CertificateInfo):
    """Signature image scaled to fit 40 x 18 mm (the height of the signature line area), or None."""
    if not info.signature_path or not Path(info.signature_path).exists():
        return None
    try:
        img = Image(str(info.signature_path))
    except Exception as exc:  # noqa: BLE001
        log.warning("signature image not usable: %s", exc)
        return None
    max_w, max_h = 40 * mm, 18 * mm
    scale = min(max_w / img.imageWidth, max_h / img.imageHeight)
    img.drawWidth, img.drawHeight = img.imageWidth * scale, img.imageHeight * scale
    img.hAlign = "LEFT"
    return img


def _info_column(title: str, pairs: list[tuple[str, str]]):
    st = _ps("ic", 8, TEXT, leading=11)
    rows = [[Paragraph(f"<b>{title}</b>", _ps("ih", 9, bold=True))]]
    rows += [[Paragraph(f'<font color="{DGREY.hexval()}">{k}</font>  <b>{v}</b>', st)] for k, v in pairs]
    t = Table(rows, colWidths=[CONTENT_W / 3 - 3 * mm])
    t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                           ("BOTTOMPADDING", (0, 0), (0, 0), 3)]))
    return t


def _level_block(lv: LevelResult) -> KeepTogether:
    cw = [2.1 * cm, 2.3 * cm, 1.9 * cm, 1.9 * cm, 1.9 * cm, 1.9 * cm, 2.4 * cm, 1.6 * cm]
    scale = CONTENT_W / sum(cw)
    cw = [w * scale for w in cw]
    st_vh = _ps("vh", 7.5, bold=True)
    st_vol = _ps("vol", 10, bold=True)
    st_body = _ps("b", 8)
    st_hdr = _ps("hk", 7.5, align=TA_CENTER, bold=True)
    st_cell = _ps("c", 8, align=TA_CENTER)
    st_cell_l = _ps("cl", 8)
    st_mean = _ps("mn", 8, align=TA_CENTER, bold=True)
    nom = lv.nominal_ul
    nom_fmt = f"{nom:.0f}" if nom >= 10 else f"{nom:.1f}"

    r0 = Table([[Paragraph("Volume [\u00b5L]", st_vh), Paragraph(nom_fmt, st_vol),
                 Paragraph("Weight [g]", st_vh), Paragraph(f"{lv.weights_g[0]:.6f}", st_body),
                 Paragraph("Norm. systematic error [\u00b5L]", st_vh), Paragraph(f"\u00b1 {lv.sys_limit_ul:g}", st_body),
                 Paragraph("Norm. random error [\u00b5L]", st_vh), Paragraph(f"\u2264 {lv.rnd_limit_ul:g}", st_body)]],
               colWidths=[w * scale for w in (2.5 * cm, 1.8 * cm, 2.0 * cm, 2.0 * cm, 3.5 * cm, 1.5 * cm, 3.1 * cm, 1.6 * cm)])
    r0.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), LGREY), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("GRID", (0, 0), (-1, -1), 0.5, HDRGREY)]))

    headers = ("Canal No /<br/>Weighings", "Average<br/>volume [\u00b5L]", "Syst. err.<br/>[%]",
               "Syst. err.<br/>[\u00b5L]", "Rand. err.<br/>[%]", "Rand. err.<br/>[\u00b5L]",
               "Measurement<br/>uncertainty [\u00b5L]", "Result<br/>A &nbsp;&nbsp; CV")
    r1 = Table([[Paragraph(h, st_hdr) for h in headers]], colWidths=cw)
    r1.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), MGREY), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                            ("LEFTPADDING", (0, 0), (-1, -1), 2), ("GRID", (0, 0), (-1, -1), 0.5, HDRGREY)]))

    marks = Table([[_mark(lv.systematic_pass, st_cell), _mark(lv.random_pass, st_cell)]],
                  colWidths=[cw[7] / 2 - 2, cw[7] / 2 - 2])
    marks.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    r2 = Table([[Paragraph(f"Canal 1<br/><font size='6.5' color='{DGREY.hexval()}'>n = {len(lv.weights_g)}</font>", st_cell_l),
                 Paragraph(f"{lv.mean_ul:.4f}", st_mean),
                 Paragraph(f"{lv.systematic_error_pct:+.4f}", st_cell),
                 Paragraph(f"{lv.systematic_error_ul:+.4f}", st_cell),
                 Paragraph(f"{lv.random_error_pct:.4f}", st_cell),
                 Paragraph(f"{lv.random_error_ul:.4f}", st_cell),
                 Paragraph(f"\u00b1 {lv.uncertainty_ul:.4f}", st_cell),
                 marks]], colWidths=cw)
    r2.setStyle(TableStyle([("BACKGROUND", (1, 0), (1, 0), PASS_BG if lv.passed else FAIL_BG),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                            ("LEFTPADDING", (0, 0), (-1, -1), 3), ("GRID", (0, 0), (-1, -1), 0.5, BDGREY)]))

    wt = "   ".join(f"{w:.6f}" for w in lv.weights_g)
    vols = "   ".join(f"{v:.3f}" for v in lv.volumes_ul)
    r3 = Table([[Paragraph(f'<font color="{DGREY.hexval()}"><i>Individual weights (g):</i></font>  {wt}'
                           f'&nbsp;&nbsp;&nbsp;&nbsp;<font color="{DGREY.hexval()}"><i>volumes (\u00b5L):</i></font>  {vols}',
                           _ps("wt", 7, leading=9))]], colWidths=[sum(cw)])
    r3.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("LINEBELOW", (0, 0), (-1, -1), 0.5, BDGREY)]))
    return KeepTogether([r0, r1, r2, r3, Spacer(1, 2.5 * mm)])


def build_certificate(path: str | Path, info: CertificateInfo, result: CalibrationResult) -> Path:
    """Render the certificate PDF to *path* and return the path."""
    path = Path(path)
    spec, env = result.spec, result.environment
    res_colour = PASS_FG if result.passed else FAIL_FG
    res_bg = PASS_BG if result.passed else FAIL_BG
    cal_date = info.calibration_date.strftime(DATE_FMT)
    st_body = _ps("body", 8)
    st_bold = _ps("bold", 8, bold=True)
    story: list = []

    # ---- header -----------------------------------------------------------
    title = Table([[Paragraph("Pipette", _ps("t1", 14, colors.white, TA_CENTER, bold=True))],
                   [Paragraph("Calibration Certificate", _ps("t2", 11, colors.white, TA_CENTER, bold=True))]],
                  colWidths=[9.5 * cm])
    title.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("TOPPADDING", (0, 0), (0, 0), 16), ("BOTTOMPADDING", (0, 1), (0, 1), 16),
                               ("TOPPADDING", (0, 1), (0, 1), 2), ("BOTTOMPADDING", (0, 0), (0, 0), 2)]))
    hdr = Table([[_logo(info), title]], colWidths=[CONTENT_W - 9.5 * cm, 9.5 * cm])
    hdr.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    story += [hdr, Spacer(1, 4 * mm)]

    # ---- info bar -----------------------------------------------------------
    bar = Table([[Paragraph("Document No.", st_bold), Paragraph("Operator", st_bold),
                  Paragraph("Calibration date", st_bold),
                  Paragraph("CALIBRATION RESULT", _ps("cr", 8, colors.white, TA_CENTER, bold=True))],
                 [Paragraph(info.document_no, st_body), Paragraph(info.operator or "-", st_body),
                  Paragraph(cal_date, st_body),
                  Paragraph(result.verdict, _ps("res", 14, res_colour, TA_CENTER, bold=True))]],
                colWidths=[4 * cm, 4.3 * cm, 4 * cm, CONTENT_W - 12.3 * cm])
    bar.setStyle(TableStyle([("BACKGROUND", (0, 0), (2, 0), LGREY), ("BACKGROUND", (3, 0), (3, 0), NAVY),
                             ("BACKGROUND", (3, 1), (3, 1), res_bg), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                             ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                             ("LEFTPADDING", (0, 0), (-1, -1), 6), ("GRID", (0, 0), (-1, -1), 0.5, BDGREY)]))
    story += [bar, Spacer(1, 4 * mm)]

    # ---- three info columns --------------------------------------------------
    cal_pairs = ([("Customer:", info.customer.strip())] if info.customer.strip() else []) + \
                [("Place of calibration:", info.place), ("Calibration method:", CALIBRATION_METHOD),
                 ("Measurements:", f"{len(result.levels[0].weights_g)} per test volume"), ("Mass unit:", "g")]
    if info.procedure.strip():
        cal_pairs.append(("Standard:", info.procedure.strip()))
    cal_pairs.append(("Recommended next calibration:", info.next_calibration_date.strftime(DATE_FMT)))
    cols = Table([[
        _info_column("Pipettes data", [
            ("Manufacturer:", "GILSON"), ("Model:", short_model_name(spec, info.series)),
            ("Range:", spec.range_label.replace("uL", "\u00b5L")),
            ("Channels:", str(spec.channels)), ("Tip:", info.tip or "-"), ("Serial No:", info.serial_no or "-")]),
        _info_column("Environmental conditions", [
            ("Air temperature [\u00b0C]", f"{env.air_t:.2f}"), ("Pressure [hPa]", f"{env.pressure_hpa:.1f}"),
            ("Humidity [%]", f"{env.humidity_pct:.1f}"), ("Temp. of water [\u00b0C]", f"{env.temperature_c:.2f}"),
            ("Z factor [mL/g]", f"{result.z:.6f}"),
            ("Balance:", info.balance_id or "RADWAG analytical balance")]),
        _info_column("Calibration", cal_pairs),
    ]], colWidths=[CONTENT_W / 3] * 3)
    cols.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm), ("TOPPADDING", (0, 0), (-1, -1), 2),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    story += [cols, Spacer(1, 2 * mm), HRFlowable(width="100%", thickness=1.2, color=BLUE),
              Spacer(1, 1 * mm), Paragraph("AVERAGE RESULTS", _ps("ar", 10, align=TA_CENTER, bold=True)),
              Spacer(1, 3 * mm)]
    for lv in result.levels:
        story.append(_level_block(lv))

    # ---- page 2 ------------------------------------------------------------
    story.append(PageBreak())
    story += [HRFlowable(width="100%", thickness=0.75, color=HDRGREY), Spacer(1, 3 * mm)]
    left = [Paragraph(f"Calibrated by:  <b>{info.operator or '-'}</b>", st_body), Spacer(1, 2 * mm)]
    sig_img = _signature_image(info)
    signer = info.signer_name.strip() or info.operator or ""
    # one signature row: the name at the left, the signature image to its right,
    # both standing on the signature line
    line_w = 8 * cm
    name_cell = Paragraph(f"<b>{signer}</b>", _ps("sn", 9, bold=True))
    row = Table([[name_cell, sig_img if sig_img is not None else ""]],
                colWidths=[4.2 * cm, line_w - 4.2 * cm],
                rowHeights=[max(18 * mm, (sig_img.drawHeight + 1 * mm) if sig_img is not None else 0)])
    row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("ALIGN", (1, 0), (1, 0), "LEFT"),
                             ("LINEBELOW", (0, 0), (-1, 0), 0.6, HDRGREY),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                             ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    left += [row, Paragraph(f"Authorized Signature{'' if sig_img is None else '  -  signed electronically'}"
                            f"   {cal_date}", _ps("as", 7, DGREY))]
    if info.comments.strip():
        left += [Spacer(1, 3 * mm), Paragraph(f"Comments:  {info.comments.strip()}", st_body)]
    right = [Paragraph(f"<b><font color='{BLUE.hexval()}'>{COMPANY}</font></b>", _ps("co", 10, bold=True)),
             Paragraph(COMPANY_ADDRESS, st_body), Paragraph(COMPANY_PHONE, st_body),
             Paragraph(COMPANY_EMAIL, st_body), Paragraph(COMPANY_WEB, st_body)]
    pad = TableStyle([("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                      ("LEFTPADDING", (0, 0), (-1, -1), 0)])
    sig = Table([[Table([[i] for i in left], colWidths=[9.5 * cm], style=pad),
                  Table([[i] for i in right], colWidths=[8 * cm], style=pad)]], colWidths=[9.5 * cm, 8 * cm])
    sig.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [sig, Spacer(1, 4 * mm), HRFlowable(width="100%", thickness=0.5, color=BDGREY), Spacer(1, 2 * mm)]
    st_disc = _ps("disc", 6.8, DGREY, leading=9.5, italic=True)
    for line in NOTES + ((NOTE_PASS if result.passed else NOTE_FAIL),):
        story += [Paragraph(line, st_disc), Spacer(1, 1 * mm)]
    story += [Spacer(1, 3 * mm), HRFlowable(width="100%", thickness=1.0, color=BLUE), Spacer(1, 2 * mm)]
    box = Table([[Paragraph(SCOPE_STATEMENT, _ps("acad", 8, STMT_FG, bold=True, leading=11))]], colWidths=[CONTENT_W])
    box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), STMT_BG), ("TOPPADDING", (0, 0), (-1, -1), 8),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 8)]))
    story += [box, Spacer(1, 2 * mm), HRFlowable(width="100%", thickness=1.0, color=BLUE), Spacer(1, 6 * mm),
              Paragraph("End of report", _ps("eor", 8, DGREY, TA_CENTER))]

    def _footer(canvas, doc_):
        canvas.saveState()
        canvas.setStrokeColor(BDGREY)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN_X, 1.15 * cm, A4[0] - MARGIN_X, 1.15 * cm)
        canvas.setFont("Helvetica-Oblique", 6.5)
        canvas.setFillColor(DGREY)
        canvas.drawCentredString(A4[0] / 2, 0.75 * cm,
                                 f"Copyright \u00a9 {COMPANY}  Calibration certificate shall not be reproduced "
                                 f"except in full.   Document {info.document_no}   Date of issue: {cal_date}   "
                                 f"Page {doc_.page} of 2")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=A4, topMargin=1.2 * cm, bottomMargin=1.6 * cm,
                            leftMargin=MARGIN_X, rightMargin=MARGIN_X,
                            title=f"Pipette Calibration Certificate {info.document_no}", author=COMPANY,
                            subject=f"Gilson {spec.model} S/N {info.serial_no}",
                            creator=f"LifeGene Pipette Calibration v{__version__}")
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return path


def default_filename(info: CertificateInfo, model: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in info.serial_no) or "NA"
    return f"{info.document_no}_{model}_{safe}_{info.calibration_date:%Y%m%d}.pdf"
