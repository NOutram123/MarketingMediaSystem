"""Build the illustrated Marketing Media System user manual."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageOps
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs/user-manual/assets"
SHOTS = ROOT / "docs/user-manual/screenshots"
OUT = ROOT / "output/pdf/USER_MANUAL.pdf"

W, H = A4
M = 42
INK = colors.HexColor("#0D171E")
PANEL = colors.HexColor("#12242D")
TEAL_DARK = colors.HexColor("#123B3A")
TEAL = colors.HexColor("#32AFA6")
TEAL_LIGHT = colors.HexColor("#9FE7E4")
COPPER = colors.HexColor("#C97943")
CREAM = colors.HexColor("#F2EADF")
MIST = colors.HexColor("#DCE7E5")
WHITE = colors.white
MUTED = colors.HexColor("#61777E")
PALE = colors.HexColor("#EEF4F3")
RED = colors.HexColor("#AA4D5B")


def register_fonts():
    candidates = {
        "UI": Path("C:/Windows/Fonts/segoeui.ttf"),
        "UI-Bold": Path("C:/Windows/Fonts/segoeuib.ttf"),
        "UI-Semibold": Path("C:/Windows/Fonts/seguisb.ttf"),
    }
    for name, path in candidates.items():
        if path.exists():
            pdfmetrics.registerFont(TTFont(name, str(path)))
    return (
        "UI" if "UI" in pdfmetrics.getRegisteredFontNames() else "Helvetica",
        "UI-Bold" if "UI-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold",
        "UI-Semibold" if "UI-Semibold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold",
    )


FONT, BOLD, SEMI = register_fonts()


STYLES = {
    "body": ParagraphStyle("body", fontName=FONT, fontSize=9.2, leading=13.2, textColor=INK),
    "small": ParagraphStyle("small", fontName=FONT, fontSize=7.8, leading=10.8, textColor=MUTED),
    "body_dark": ParagraphStyle("body_dark", fontName=FONT, fontSize=9.2, leading=13.2, textColor=CREAM),
    "small_dark": ParagraphStyle("small_dark", fontName=FONT, fontSize=7.8, leading=10.8, textColor=MIST),
    "card": ParagraphStyle("card", fontName=FONT, fontSize=8.4, leading=11.8, textColor=INK),
    "card_dark": ParagraphStyle("card_dark", fontName=FONT, fontSize=8.4, leading=11.8, textColor=CREAM),
}


def clean(text: str) -> str:
    return (text.replace("\u2018", "'").replace("\u2019", "'")
            .replace("\u201c", '"').replace("\u201d", '"')
            .replace("\u2013", "-").replace("\u2014", "-")
            .replace("\u00a0", " "))


def rich(text: str) -> str:
    text = clean(text)
    safe = escape(text)
    safe = safe.replace("[[", "<b>").replace("]]", "</b>")
    safe = safe.replace("\n", "<br/>")
    return safe


def para(c, text, x, y, w, style="body", gap=6):
    p = Paragraph(rich(text), STYLES[style])
    _, h = p.wrap(w, H)
    p.drawOn(c, x, y - h)
    return y - h - gap


def bullets(c, items, x, y, w, style="body", gap=4, accent=TEAL):
    for item in items:
        c.setFillColor(accent)
        c.circle(x + 3, y - 6, 2.2, fill=1, stroke=0)
        y = para(c, item, x + 13, y, w - 13, style, gap)
    return y


def footer(c, page, dark=False):
    colour = colors.HexColor("#739097") if dark else colors.HexColor("#819398")
    c.setStrokeColor(colors.HexColor("#29404A") if dark else colors.HexColor("#CFDAD8"))
    c.line(M, 28, W - M, 28)
    c.setFont(FONT, 7.2)
    c.setFillColor(colour)
    c.drawString(M, 16, "MARKETING MEDIA SYSTEM | USER MANUAL | SEPTEMBER 2026")
    c.setFont("Helvetica-Bold", 7.5)
    c.drawRightString(W - M, 16, f"{page:02d}")


def page(c, page_no, kicker, title, intro=None, dark=False):
    c.setFillColor(INK if dark else CREAM)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(TEAL_LIGHT if dark else TEAL_DARK)
    c.setFont(SEMI, 8.2)
    c.drawString(M, H - 48, kicker.upper())
    c.setFillColor(CREAM if dark else INK)
    title_size = 25
    while title_size > 18 and pdfmetrics.stringWidth(title, BOLD, title_size) > W - 2 * M:
        title_size -= 1
    c.setFont(BOLD, title_size)
    c.drawString(M, H - 78, title)
    y = H - 100
    if intro:
        y = para(c, intro, M, y, W - 2 * M, "body_dark" if dark else "body", 8)
    footer(c, page_no, dark)
    return y


def pill(c, text, x, y, fill=TEAL_DARK, text_color=CREAM):
    size = 7.5
    width = pdfmetrics.stringWidth(text, SEMI, size) + 18
    c.setFillColor(fill)
    c.roundRect(x, y - 17, width, 17, 8.5, fill=1, stroke=0)
    c.setFillColor(text_color)
    c.setFont(SEMI, size)
    c.drawString(x + 9, y - 12, text)
    return width


def card(c, x, y, w, h, title, body, accent=TEAL, dark=False, number=None):
    bg = PANEL if dark else WHITE
    fg = CREAM if dark else INK
    c.setFillColor(bg)
    c.setStrokeColor(colors.HexColor("#38545D") if dark else colors.HexColor("#CFDAD8"))
    c.roundRect(x, y - h, w, h, 12, fill=1, stroke=1)
    if number is not None:
        c.setFillColor(accent)
        c.circle(x + 22, y - 24, 13, fill=1, stroke=0)
        c.setFillColor(INK if dark else WHITE)
        c.setFont(BOLD, 9)
        c.drawCentredString(x + 22, y - 27, str(number))
        tx = x + 43
    else:
        tx = x + 16
    c.setFillColor(fg)
    c.setFont(SEMI, 10.5)
    c.drawString(tx, y - 22, title)
    para(c, body, x + 16, y - 38, w - 32, "card_dark" if dark else "card", 0)


def callout(c, x, y, w, title, body, tone="teal", dark=False):
    palette = {
        "teal": (colors.HexColor("#DDF0ED"), TEAL_DARK),
        "copper": (colors.HexColor("#F6E7DA"), colors.HexColor("#6B371E")),
        "warning": (colors.HexColor("#F7E5E0"), colors.HexColor("#7E3440")),
        "dark": (PANEL, TEAL_LIGHT),
    }
    bg, fg = palette[tone]
    p = Paragraph(rich(body), ParagraphStyle("call", parent=STYLES["card_dark" if dark or tone == "dark" else "card"], textColor=CREAM if tone == "dark" else fg))
    _, ph = p.wrap(w - 30, H)
    h = ph + 42
    c.setFillColor(bg)
    c.roundRect(x, y - h, w, h, 10, fill=1, stroke=0)
    c.setFillColor(fg)
    c.setFont(BOLD, 8.5)
    c.drawString(x + 15, y - 18, title.upper())
    p.drawOn(c, x + 15, y - 30 - ph)
    return y - h - 8


def crop_reader(path: Path, width_px: int, height_px: int, anchor=(0.5, 0.5)):
    with Image.open(path) as source:
        image = ImageOps.fit(source.convert("RGB"), (width_px, height_px), method=Image.Resampling.LANCZOS, centering=anchor)
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=92)
    buffer.seek(0)
    return ImageReader(buffer)


def draw_crop(c, path, x, y, w, h, anchor=(0.5, 0.5), radius=12, border=True):
    reader = crop_reader(Path(path), max(600, int(w * 3)), max(400, int(h * 3)), anchor)
    c.saveState()
    clip = c.beginPath()
    clip.roundRect(x, y - h, w, h, radius)
    c.clipPath(clip, stroke=0, fill=0)
    c.drawImage(reader, x, y - h, width=w, height=h, preserveAspectRatio=False, mask="auto")
    c.restoreState()
    if border:
        c.setStrokeColor(colors.HexColor("#38545D"))
        c.roundRect(x, y - h, w, h, radius, fill=0, stroke=1)


def draw_contain(c, path, x, y, w, h, bg=WHITE, radius=10):
    with Image.open(path) as im:
        iw, ih = im.size
    scale = min(w / iw, h / ih)
    dw, dh = iw * scale, ih * scale
    c.setFillColor(bg)
    c.roundRect(x, y - h, w, h, radius, fill=1, stroke=0)
    c.drawImage(str(path), x + (w - dw) / 2, y - h + (h - dh) / 2, width=dw, height=dh, mask="auto")
    c.setStrokeColor(colors.HexColor("#38545D"))
    c.roundRect(x, y - h, w, h, radius, fill=0, stroke=1)


def number_marker(c, x, y, number, colour=COPPER):
    c.setFillColor(colour)
    c.circle(x, y, 10, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont(BOLD, 8)
    c.drawCentredString(x, y - 3, str(number))


def marker_link(c, x, y, number, target_x, colour=COPPER):
    c.setStrokeColor(colour)
    c.setLineWidth(1.2)
    c.line(x + 10, y, target_x - 6, y)
    number_marker(c, x, y, number, colour)


def table(c, x, y, widths, rows, row_heights, header=True, dark=False, font_size=7.6, leading=10):
    total = sum(widths)
    current_y = y
    for row_index, row in enumerate(rows):
        rh = row_heights[row_index] if isinstance(row_heights, list) else row_heights
        bg = TEAL_DARK if header and row_index == 0 else (PANEL if dark else WHITE)
        c.setFillColor(bg)
        c.rect(x, current_y - rh, total, rh, fill=1, stroke=0)
        cx = x
        for index, value in enumerate(row):
            c.setStrokeColor(colors.HexColor("#46606A") if dark else colors.HexColor("#D5DEDC"))
            c.rect(cx, current_y - rh, widths[index], rh, fill=0, stroke=1)
            style = "card_dark" if dark or (header and row_index == 0) else "card"
            text_colour = CREAM if dark or (header and row_index == 0) else INK
            pstyle = ParagraphStyle(f"cell-{row_index}-{index}", parent=STYLES[style], fontName=SEMI if row_index == 0 else FONT, textColor=text_colour, fontSize=font_size, leading=leading)
            p = Paragraph(rich(value), pstyle)
            _, ph = p.wrap(widths[index] - 12, rh - 8)
            p.drawOn(c, cx + 6, current_y - rh + (rh - ph) / 2)
            cx += widths[index]
        current_y -= rh
    return current_y


def flow_arrow(c, x1, x2, y, colour=TEAL):
    c.setStrokeColor(colour)
    c.setLineWidth(2)
    c.line(x1, y, x2 - 7, y)
    c.setFillColor(colour)
    p = c.beginPath()
    p.moveTo(x2, y)
    p.lineTo(x2 - 8, y + 5)
    p.lineTo(x2 - 8, y - 5)
    p.close()
    c.drawPath(p, fill=1, stroke=0)


def flow_down_arrow(c, x, y_top, y_bottom, colour=TEAL):
    c.setStrokeColor(colour)
    c.setLineWidth(2)
    c.line(x, y_top, x, y_bottom + 8)
    c.setFillColor(colour)
    p = c.beginPath()
    p.moveTo(x, y_bottom)
    p.lineTo(x - 5, y_bottom + 8)
    p.lineTo(x + 5, y_bottom + 8)
    p.close()
    c.drawPath(p, fill=1, stroke=0)


def workflow_card(c, x, y, w, h, number, title, body, accent=TEAL):
    c.setFillColor(PANEL)
    c.setStrokeColor(colors.HexColor("#38545D"))
    c.roundRect(x, y - h, w, h, 12, fill=1, stroke=1)
    centre_y = y - h / 2
    c.setFillColor(accent)
    c.circle(x + 25, centre_y, 13, fill=1, stroke=0)
    c.setFillColor(INK)
    c.setFont(BOLD, 9)
    c.drawCentredString(x + 25, centre_y - 3, str(number))
    c.setFillColor(CREAM)
    c.setFont(SEMI, 10.5)
    c.drawString(x + 48, centre_y + 6, title)
    para(c, body, x + 48, centre_y - 2, w - 64, "card_dark", 0)


def build():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUT), pagesize=A4, pageCompression=1)
    c.setTitle("Marketing Media System - User Manual")
    c.setAuthor("Marketing Media System")
    c.setSubject("Illustrated guide to planning, storyboarding and reviewing marketing media")

    # 01 - Cover
    c.setFillColor(INK); c.rect(0, 0, W, H, fill=1, stroke=0)
    draw_crop(c, ASSETS / "northstar-lifestyle.png", 0, H, W, 365, anchor=(0.65, 0.52), radius=0, border=False)
    c.setFillColor(colors.Color(13/255, 23/255, 30/255, alpha=0.58)); c.rect(0, H - 365, W, 365, fill=1, stroke=0)
    c.setFillColor(TEAL_LIGHT); c.setFont(SEMI, 16); c.drawString(M, H - 58, "MARKETING MEDIA SYSTEM")
    c.setFillColor(CREAM); c.setFont(BOLD, 35); c.drawString(M, H - 105, "USER MANUAL")
    c.setFont(FONT, 14); c.drawString(M, H - 136, "From brief to 15-60 second YouTube video")
    pill(c, "WINDOWS 11 + NVIDIA CUDA", M, H - 167, COPPER, WHITE)
    draw_crop(c, ASSETS / "northstar-product.png", W - 206, 420, 155, 285, anchor=(0.5, 0.5), radius=18)
    y = 400
    c.setFillColor(CREAM); c.setFont(BOLD, 19); c.drawString(M, y, "Plan. Direct. Review.")
    y = para(c, "A practical, visual guide to the five-stage studio workflow, with worked examples from the fictional Northstar Flow campaign.", M, y - 16, 300, "body_dark", 10)
    c.setFillColor(TEAL_LIGHT); c.setFont(SEMI, 9); c.drawString(M, 72, "FIRST EDITION | 29 SEPTEMBER 2026")
    footer(c, 1, True); c.showPage()

    # 02 - At a glance
    y = page(c, 2, "Start here", "What this system is for", "Turn a marketing objective, brand rules and optional source images into an approved concept, timed storyboard and reviewable video draft.")
    card(c, M, y, 244, 105, "Local-first creative workstation", "The studio keeps project state, references and local draft generation on this Windows PC. OpenAI planning and Higgsfield evaluation are optional provider paths.", TEAL)
    card(c, M + 263, y, 244, 105, "Review before generation", "Brief, concept and storyboard gates make decisions visible. Paid cloud generation requires a separate estimate and approval.", COPPER)
    y -= 127
    y = callout(c, M, y, W - 2*M, "Current output policy", "Every local output and the Higgsfield evaluation path are [[AI-generated, non-commercial drafts]]. The current system does not provide a commercial final export path.", "warning") - 4
    c.setFillColor(TEAL_DARK); c.setFont(BOLD, 13); c.drawString(M, y, "Inside this guide")
    y -= 17
    contents = [
        ("01", "Brief & brand", "Define the assignment and the rules."),
        ("02", "Existing images", "Upload and describe references."),
        ("03", "Concept & script", "Shape the idea and one continuous narration."),
        ("04", "Storyboard", "Time scenes, prompts and reference assignments."),
        ("05", "Review paths", "Create a local rough cut or quote a cloud evaluation."),
    ]
    for num, title, desc in contents:
        c.setFillColor(TEAL_DARK); c.setFont(BOLD, 10); c.drawString(M, y, num)
        c.setFillColor(INK); c.drawString(M + 32, y, title)
        c.setFont(FONT, 8.4); c.setFillColor(MUTED); c.drawString(M + 152, y, desc)
        c.setStrokeColor(colors.HexColor("#D5DEDC")); c.line(M, y - 8, W - M, y - 8)
        y -= 34
    c.showPage()

    # 03 - Workflow map
    y = page(c, 3, "The route", "One project, five controlled stages", "Work from the top of the studio downward. Approve only when the current stage is ready to drive the next one.", dark=True)
    steps = [
        (1, "Brief & brand", "Goal, audience, claims, look, CTA and length"),
        (2, "Existing images", "Product, character, style and location references"),
        (3, "Concept & script", "Creative direction and continuous voiceover"),
        (4, "Storyboard", "Variable scene timing, prompts and references"),
        (5, "Review paths", "Local rough cut or approved cloud evaluation"),
    ]
    card_h = 70
    card_gap = 23
    for i, title, body in steps:
        workflow_card(c, M, y, W - 2*M, card_h, i, title, body, COPPER if i == 5 else TEAL)
        if i < 5:
            flow_down_arrow(c, W/2, y - card_h - 4, y - card_h - card_gap + 4, TEAL_LIGHT)
        y -= card_h + card_gap
    callout(c, M, y + 10, W - 2*M, "Approval rule", "An approval is a checkpoint, not a permanent lock. Request changes when needed; the studio resets dependent work so older outputs are not mistaken for the current version.", "dark", dark=True)
    c.showPage()

    # 04 - Interface anatomy
    y = page(c, 4, "Orientation", "How to move around the studio", "Projects stay in the left sidebar. The working area follows the numbered stages from top to bottom.")
    draw_crop(c, SHOTS / "00-studio-overview.png", M, y, 300, 500, anchor=(0.33, 0.08), radius=10)
    number_marker(c, M + 28, y - 40, 1); number_marker(c, M + 250, y - 48, 2); number_marker(c, M + 245, y - 180, 3)
    x = M + 320; cy = y
    card(c, x, cy, 187, 87, "1. Project list", "Open an existing project or start a new one. Project data is stored locally.", TEAL, number=None)
    card(c, x, cy - 101, 187, 87, "2. Draft status", "The header reminds you that generated outputs are AI drafts for non-commercial review.", COPPER)
    card(c, x, cy - 202, 187, 87, "3. Numbered stages", "Complete, revise and approve each stage before moving to downstream generation.", TEAL)
    cy -= 315
    callout(c, x, cy, 187, "Good habit", "Name projects by campaign and version, for example: [[Northstar Flow - Launch 01]].", "teal")
    callout(c, x, cy - 112, 187, "Setup access", "Use [[Setup & Diagnostics]] to add API keys or repair the local foundation later.", "copper")
    c.showPage()

    # 05 - Step 1 screenshot
    y = page(c, 5, "01 / Input", "Brief & brand", "This stage defines what the film must achieve and the boundaries the plan must respect.")
    draw_contain(c, SHOTS / "02-brief-brand.png", M, y, 292, 570, bg=INK)
    x = M + 311; cy = y
    marker_link(c, M + 272, cy - 43, 1, x)
    marker_link(c, M + 272, cy - 150.5, 2, x)
    marker_link(c, M + 272, cy - 263, 3, x)
    marker_link(c, M + 272, cy - 371, 4, x)
    card(c, x, cy, 196, 86, "1. Target length", "Choose 15, 30, 45 or 60 seconds. All scene timings must later add up to this target.", TEAL)
    card(c, x, cy - 98, 196, 105, "2. The assignment", "State the audience, objective, single message, tone, must-show content, exclusions and deliverable. Put a supplied script or timed treatment in Existing treatment.", COPPER)
    card(c, x, cy - 215, 196, 96, "3. Brand controls", "Describe the product and visual style. Add only claims and wording that a responsible reviewer has checked.", TEAL)
    card(c, x, cy - 323, 196, 96, "4. CTA and approval", "Tell viewers what to do next, then approve the brief when every required rule is represented.", COPPER)
    callout(c, x, cy - 434, 196, "Impact", "Saving changes to the brief, brand or target length resets the current plan and approvals. Uploaded reference images remain available.", "warning")
    c.showPage()

    # 06 - Brief anatomy
    y = page(c, 6, "Write better inputs", "What a strong brief can include", "The brief may be concise or detailed. Useful specificity improves the plan; repeated slogans and contradictory instructions create noise.")
    items = [
        ("Audience", "Who should care, what they already know, and where they will watch."),
        ("Objective", "The one change in understanding or action the film should create."),
        ("Key message", "The single thought viewers should remember."),
        ("Product and proof", "Features, approved evidence and exact permitted claim wording."),
        ("Tone", "Emotional register, pace, voice and qualities to avoid."),
        ("Visual direction", "Lighting, palette, environments, product treatment and camera feel."),
        ("Must show", "Product moments, people, locations, end card, CTA and disclaimers."),
        ("Restrictions", "Prohibited claims, imagery, competitors, unsafe actions or visual cliches."),
        ("Format", "Target length, 16:9 output, platform context and review purpose."),
    ]
    col_w = 244
    for index, (title, body) in enumerate(items):
        col = index % 2; row = index // 2
        card(c, M + col * 263, y - row * 96, col_w, 82, title, body, TEAL if col == 0 else COPPER)
    y -= 5 * 96
    callout(c, M, y, W - 2*M, "Brief versus treatment", "Use the [[brief]] for the assignment and rules. Use [[Existing treatment]] for supplied concepts, scripts, shot lists or timed storyboards. The two remain separately editable.", "teal")
    y -= 76
    callout(c, M, y, W - 2*M, "How long can it be?", "The brief accepts substantial detail, but every sentence should change a decision. Prefer clear headings and exact approved wording. Move scene-by-scene direction into the treatment or storyboard.", "copper")
    c.showPage()

    # 07 - Sample briefs 15/30
    y = page(c, 7, "Copy, adapt, improve", "Sample briefs: 15 and 30 seconds", "These examples show the level of specificity that helps without prescribing every frame.")
    card(c, M, y, W - 2*M, 230, "15-second product teaser - Ember Oat Latte", "[[Audience:]] Busy commuters aged 20-35.\n[[Objective:]] Make the new canned oat latte feel like a convenient morning treat.\n[[Key message:]] Barista-style flavour, ready from the fridge.\n[[Tone:]] Bright, tactile and energetic.\n[[Must show:]] Can opening, creamy pour, pack front and end-card CTA.\n[[Avoid:]] Health claims, exaggerated steam and coffee-shop logos.\n[[Approved claim:]] Made with British oats.\n[[CTA:]] Find your nearest stockist at ember.example.\n[[Deliverable:]] 15-second 16:9 launch teaser with three fast scenes.", COPPER)
    y -= 246
    card(c, M, y, W - 2*M, 285, "30-second worked example - Northstar Flow", "[[Audience:]] Active urban professionals aged 25-45 who move between commuting, work and weekend adventures.\n[[Objective:]] Introduce Northstar Flow as one dependable companion from city to trail.\n[[Key message:]] Cold all day. Ready anywhere.\n[[Tone:]] Capable, calm, optimistic and premium without feeling exclusive.\n[[Must show:]] Deep-teal bottle, copper cap, city-to-hill progression, tactile details and the approved 24-hour cold claim.\n[[Avoid:]] Health promises, carbon-neutral claims, disposable-plastic imagery and extreme-sport cliches.\n[[Approved claims:]] Keeps drinks cold for up to 24 hours; made with recycled stainless steel.\n[[Disclaimer:]] Performance varies with use and conditions.\n[[CTA:]] Choose your route at northstarflow.example.\n[[Deliverable:]] 30-second 16:9 website and social film.", TEAL)
    y -= 300
    callout(c, M, y, W - 2*M, "Notice", "The 15-second version is narrower and faster. The 30-second version has room for a visual journey, two approved claims and a calmer close.", "teal")
    c.showPage()

    # 08 - Sample briefs 45/60
    y = page(c, 8, "More examples", "Sample briefs: 45 and 60 seconds", "Longer films need a reason to be longer: demonstration, explanation, testimony or a more developed emotional turn.")
    card(c, M, y, W - 2*M, 245, "45-second software explainer - LedgerLoop", "[[Audience:]] Owners of small creative agencies who lose time reconciling project costs.\n[[Objective:]] Demonstrate a simple weekly workflow and encourage a free trial.\n[[Key message:]] Know where every project stands before Friday.\n[[Tone:]] Clear, calm and practical; no futuristic AI cliches.\n[[Must show:]] Import, project health view, one alert and final summary. Use supplied UI screenshots as references only in the scenes that show the product.\n[[Avoid:]] Guaranteed savings, fake customer names and unreadable interface text.\n[[CTA:]] Start a 14-day trial at ledgerloop.example.\n[[Deliverable:]] 45-second 16:9 explainer with continuous narration and six scenes.", TEAL)
    y -= 261
    card(c, M, y, W - 2*M, 270, "60-second local service story - BrightNest Heating", "[[Audience:]] Homeowners considering a heat-pump survey.\n[[Objective:]] Reduce uncertainty about the survey process and invite qualified enquiries.\n[[Key message:]] A clear plan begins with a careful home assessment.\n[[Tone:]] Reassuring, knowledgeable and neighbourly.\n[[Must show:]] Engineer arrival, room measurements, existing system inspection, homeowner discussion, written recommendation and booking CTA.\n[[Avoid:]] Guaranteed savings, exact grant promises, unsafe equipment access and identifiable real addresses.\n[[Required disclaimer:]] Eligibility, costs and performance depend on the property and assessment.\n[[CTA:]] Book an assessment at brightnest.example.\n[[Deliverable:]] 60-second 16:9 information film with eight scenes and a measured pace.", COPPER)
    y -= 285
    callout(c, M, y, W - 2*M, "Adapt safely", "Replace every fictional claim, URL and disclaimer with wording that has been checked for the real campaign. AI suggestions are candidates, not evidence.", "warning")
    c.showPage()

    # 09 - Length
    y = page(c, 9, "Timing decisions", "Length changes the creative job", "The application offers 15, 30, 45 and 60 seconds. It shows a rough script allowance of about 2.4 words per second; treat that as a ceiling, not a target.")
    rows = [
        ["Length", "Useful starting shape", "Script ceiling", "Typical pressure"],
        ["15s", "3-4 scenes; one message", "about 36 words", "Fast recognition and one action"],
        ["30s", "4-6 scenes; simple arc", "about 72 words", "Balance story, claim and CTA"],
        ["45s", "6-8 scenes; demonstration", "about 108 words", "Keep every step visually distinct"],
        ["60s", "7-10 scenes; explanation", "about 144 words", "Protect pace and viewer attention"],
    ]
    y = table(c, M, y, [56, 153, 85, 213], rows, [30, 45, 45, 45, 45]) - 18
    c.setFillColor(TEAL_DARK); c.setFont(BOLD, 13); c.drawString(M, y, "What length affects")
    y -= 20
    y = bullets(c, [
        "[[Narration:]] more time permits context, but pauses and emphasis still need space.",
        "[[Scene count:]] more scenes create more prompts, reference choices and review decisions.",
        "[[Scene duration:]] every scene must be 2-30 seconds and the total must exactly match the film target.",
        "[[Local preview:]] scenes longer than about five seconds use time-stretched preview motion; timing and continuous narration remain correct.",
        "[[Cloud cost:]] longer billable duration and higher resolution generally increase the estimate.",
        "[[Consistency risk:]] more generated scenes create more opportunities for product, person and location drift.",
    ], M, y, W - 2*M)
    y -= 4
    callout(c, M, y, W - 2*M, "Practical rule", "Start with the shortest length that can carry the objective, proof and CTA clearly. Add time only when it improves understanding or feeling.", "copper")
    c.showPage()

    # 10 - Step 2 screenshot
    y = page(c, 10, "02 / Sources", "Existing images", "Upload reusable visual references, describe what matters, then choose them scene by scene.")
    draw_contain(c, SHOTS / "03-existing-images.png", M, y, 305, 570, bg=INK)
    x = M + 324; cy = y
    marker_link(c, M + 280, cy - 46, 1, x)
    marker_link(c, M + 280, cy - 157, 2, x)
    marker_link(c, M + 280, cy - 274.5, 3, x)
    card(c, x, cy, 183, 92, "1. Upload", "Accepted reference types are PNG, JPEG and WebP. Use a clear, relevant image rather than a crowded contact sheet.", TEAL)
    card(c, x, cy - 105, 183, 104, "2. Role + description", "Choose character, product, style, location or other. Describe the identity, attributes and visual qualities worth preserving.", COPPER)
    card(c, x, cy - 222, 183, 105, "3. Reusable library", "Saved images remain available across the project. Select a card to revise its role or description.", TEAL)
    callout(c, x, cy - 341, 183, "Important", "Uploading does not apply an image to every scene. Assign it only where its influence is useful.", "warning")
    callout(c, x, cy - 454, 183, "Deletion", "Removing a linked image also removes it from those scenes and forces their downstream approvals back to review.", "copper")
    c.showPage()

    # 11 - Reference roles
    y = page(c, 11, "Reference strategy", "Choose the right role and file", "The role tells reviewers why the image exists. The description tells planning and local generation what should carry forward.")
    roles = [
        ("Product", "Shape, materials, colour, packaging details and distinctive marks.", "Use a clean packshot with minimal background."),
        ("Character", "Face, outfit, silhouette or mascot identity.", "Use one clear subject; state which features matter."),
        ("Style", "Lighting, palette, texture, composition or photographic treatment.", "Avoid recognisable products you do not want copied."),
        ("Location", "Architecture, geography, layout and atmosphere.", "Use a view that shows spatial relationships."),
        ("Other", "A prop, graphic motif or reference that does not fit the standard roles.", "Explain its exact purpose in the description."),
    ]
    for i, (title, purpose, tip) in enumerate(roles):
        yy = y - i * 96
        c.setFillColor(WHITE); c.roundRect(M, yy - 82, W - 2*M, 82, 10, fill=1, stroke=0)
        c.setFillColor(TEAL_DARK); c.setFont(BOLD, 11); c.drawString(M + 16, yy - 22, title)
        para(c, purpose, M + 110, yy - 12, 230, "card", 0)
        c.setFillColor(colors.HexColor("#F6E7DA")); c.roundRect(M + 355, yy - 68, 140, 53, 8, fill=1, stroke=0)
        para(c, "[[Tip:]] " + tip, M + 365, yy - 25, 120, "small", 0)
    y -= 5 * 96 + 6
    callout(c, M, y, W - 2*M, "Description pattern", "[[Identity]] + [[specific traits]] + [[what may change]]. Example: 'Exact bottle shape, teal finish and copper cap. Background and surface may change to match the scene.'", "teal")
    c.showPage()

    # 12 - Local vs cloud
    y = page(c, 12, "Reference impact", "Local prompts and cloud pixels behave differently", "The same scene assignment has a different technical effect in the two review paths.", dark=True)
    card(c, M, y, 244, 225, "Local rough cut", "The local planner uses the reference [[role, description and scene guidance]] to inform image and motion prompts. The uploaded pixels are not used as the first frame. Appearance may vary between scenes.\n\nUse descriptions that name the features to preserve and write the scene environment separately.", TEAL, dark=True)
    card(c, M + 263, y, 244, 225, "Higgsfield evaluation", "Selected images are uploaded and used as actual visual references for that scene. Scenes with no selected image use text-to-video.\n\nThe source background, lighting, clothing or other photographed details may influence the result even when your prompt asks for something else.", COPPER, dark=True)
    y -= 250
    draw_crop(c, ASSETS / "northstar-product.png", M, y, 150, 210, anchor=(0.5, 0.5), radius=12)
    flow_arrow(c, M + 162, M + 228, y - 105, TEAL_LIGHT)
    draw_crop(c, ASSETS / "northstar-lifestyle.png", M + 240, y, 267, 210, anchor=(0.67, 0.5), radius=12)
    y -= 228
    callout(c, M, y, W - 2*M, "Scene guidance example", "'Keep the exact bottle proportions, teal finish, copper cap and contour motif. Use the scene's kitchen setting, not the product-photo background.'", "dark", dark=True)
    y -= 90
    y = bullets(c, [
        "Use the fewest references that solve the scene.",
        "Do not attach a lifestyle photo when only product identity is needed.",
        "Review people, locations and backgrounds for rights and suitability before cloud upload.",
        "Character and product consistency are goals, not guarantees.",
    ], M, y, W - 2*M, "body_dark", 3, TEAL_LIGHT)
    c.showPage()

    # 13 - Step 3
    y = page(c, 13, "03 / Direction", "Concept & script", "Turn the approved brief into one creative idea and one continuous narration track.")
    draw_contain(c, SHOTS / "04-concept-script.png", M, y, 300, 555, bg=INK)
    x = M + 320; cy = y
    marker_link(c, M + 277, cy - 44, 1, x)
    marker_link(c, M + 277, cy - 151.5, 2, x)
    marker_link(c, M + 277, cy - 263.5, 3, x)
    marker_link(c, M + 277, cy - 372, 4, x)
    card(c, x, cy, 187, 88, "1. Concept", "Explain what happens, the visual progression and why it supports the objective.", TEAL)
    card(c, x, cy - 101, 187, 101, "2. Continuous script", "Write one narration across the whole film. The storyboard later divides timing cues by scene.", COPPER)
    card(c, x, cy - 215, 187, 97, "3. Planning preview", "Check duration, expected shot count, input size and warnings before a paid planning request.", TEAL)
    card(c, x, cy - 325, 187, 94, "4. Generate or edit", "Enter your own direction, extract a supplied treatment without an API call, or request an OpenAI-generated first version.", COPPER)
    callout(c, x, cy - 433, 187, "Approval", "Approve only when the concept and narration express the approved brief. Request changes to reopen editing.", "warning")
    c.showPage()

    # 14 - Voiceover and treatment
    y = page(c, 14, "Direction craft", "Write narration that leaves room to breathe", "The app's rough allowance is about 2.4 words per second. Natural delivery often needs fewer words, especially with claims, unfamiliar names or dramatic pauses.")
    rows = [
        ["Do", "Avoid"],
        ["Read the script aloud and time it.", "Filling every second with speech."],
        ["Use one thought per sentence.", "Repeating the visual description word for word."],
        ["Place exact approved claims carefully.", "Turning a feature into a new unsupported promise."],
        ["Leave space for the CTA and disclaimer.", "Rushing legal or qualifying language."],
        ["Keep one continuous narrative voice.", "Writing each scene as a disconnected advert."],
    ]
    y = table(c, M, y, [253, 254], rows, [30, 47, 47, 47, 47, 47], font_size=9.2, leading=12) - 18
    callout(c, M, y, W - 2*M, "Northstar example - 41 words", "'Your day rarely follows one route. From the first train to the last climb, Northstar Flow keeps drinks cold for up to twenty-four hours. Made with recycled stainless steel, it is ready when plans change. Choose your route with Northstar Flow.'", "teal")
    y -= 115
    c.setFillColor(TEAL_DARK); c.setFont(BOLD, 13); c.drawString(M, y, "Using an existing treatment")
    y -= 20
    y = bullets(c, [
        "Paste concepts, scripts, shot lists and timings into [[Existing treatment]] in Step 1.",
        "Use [[Extract concept & voiceover from treatment]] for a free structured starting point.",
        "Review the extraction warnings and edit the result; extraction does not approve creative decisions.",
        "If the treatment contains timed scenes, Step 4 can extract them after concept approval.",
    ], M, y, W - 2*M)
    callout(c, M, y - 4, W - 2*M, "Paid planning", "Generating or regenerating direction and scenes uses the configured OpenAI API. Review the planning preview before submitting.", "copper")
    c.showPage()

    # 15 - Step 4
    y = page(c, 15, "04 / Sequence", "Storyboard", "Break the approved direction into timed scenes. Each scene combines intent, visuals, camera direction, narration timing and generation prompts.")
    draw_contain(c, SHOTS / "05-storyboard.png", M, y, 327, 590, bg=INK)
    x = M + 346; cy = y
    marker_link(c, M + 305, cy - 41.5, 1, x)
    marker_link(c, M + 305, cy - 143.5, 2, x)
    marker_link(c, M + 305, cy - 257, 3, x)
    marker_link(c, M + 305, cy - 369, 4, x)
    card(c, x, cy, 161, 83, "1. Sequence tools", "Revise all scenes together or edit one scene in place.", TEAL)
    card(c, x, cy - 95, 161, 97, "2. Scene intent", "Purpose, visual and duration should make the scene's job clear before prompt detail.", COPPER)
    card(c, x, cy - 204, 161, 106, "3. Reference choices", "Suggestions are optional. Select only the references this scene needs, then add specific guidance.", TEAL)
    card(c, x, cy - 322, 161, 94, "4. Linked reference", "The green tag records the active assignment and guidance.", COPPER)
    callout(c, x, cy - 430, 161, "Timing", "The total must exactly equal the project target before storyboard approval.", "warning")
    c.showPage()

    # 16 - Scene fields
    y = page(c, 16, "Storyboard craft", "What every scene field controls", "Write each field for its own purpose. Repeating the same sentence everywhere gives models less useful direction.")
    fields = [
        ("Purpose", "Why the scene exists in the story.", "Open with product recognition."),
        ("Duration", "How long it occupies in the final timeline.", "4 seconds."),
        ("Visual", "What the viewer should see, including setting and action.", "Condensation on the bottle as a hand lifts it beside keys."),
        ("Camera", "Framing, lens feel and movement.", "Slow 50 mm push-in; match cut on the copper cap."),
        ("Narration", "The phrase or timing cue that lands during the scene.", "Your day rarely follows one route."),
        ("Image prompt", "Composition, subject, light, material and still-image detail.", "Premium dawn product photograph; tactile condensation; calm kitchen."),
        ("Video prompt", "Movement through time for subject, camera and environment.", "Hand enters naturally and lifts the bottle; keep proportions stable."),
        ("Negative prompt", "Specific defects or content to suppress.", "Warped bottle, extra fingers, changed colour, illegible mark."),
    ]
    for i, (name, job, example) in enumerate(fields):
        col = i % 2; row = i // 2
        x = M + col * 263; yy = y - row * 128
        card(c, x, yy, 244, 116, name, job + "\n\n[[Example:]] " + example, TEAL if col == 0 else COPPER)
    y -= 4 * 128
    callout(c, M, y, W - 2*M, "Prompt pattern", "Subject + action + setting + composition + light + materials + constraints. Put motion in the video prompt and stable appearance requirements in the reference guidance.", "teal")
    c.showPage()

    # 17 - Assigning references
    y = page(c, 17, "Scene control", "Assign references with intent", "A reference becomes active only after you choose it, add optional guidance and select Use in scene.", dark=True)
    draw_crop(c, SHOTS / "05-storyboard.png", M, y, W - 2*M, 310, anchor=(0.5, 0.22), radius=12)
    number_marker(c, M + 112, y - 132, 1)
    number_marker(c, M + 330, y - 202, 2)
    number_marker(c, W - M - 42, y - 244, 3)
    y -= 333
    card(c, M, y, 158, 118, "1. Suggestions", "The studio compares roles and descriptions with the scene. A suggestion is a shortcut, not an instruction.", TEAL, dark=True)
    card(c, M + 174, y, 158, 118, "2. Guidance", "State what to preserve and what may change. Mention conflicts between source background and the intended scene.", COPPER, dark=True)
    card(c, M + 348, y, 159, 118, "3. Linked tag", "Confirm the role and guidance. Remove the tag when that influence is no longer wanted.", TEAL, dark=True)
    y -= 141
    callout(c, M, y, W - 2*M, "Good assignment", "Product packshot + 'Keep bottle proportions, teal finish and copper cap. Replace the studio background with the scene environment.'", "dark", dark=True)
    y -= 90
    callout(c, M, y, W - 2*M, "Risky assignment", "Lifestyle photo + no guidance. A cloud model may carry over the photographed person, clothing, skyline and light when you only wanted the bottle.", "warning", dark=True)
    c.showPage()

    # 18 - 5a
    y = page(c, 18, "05A / Local review", "Rough cut", "Use local compute to review structure, timing, narration, captions and visual direction before considering cloud spend.")
    draw_contain(c, SHOTS / "06-rough-cut.png", M, y, 300, 500, bg=INK)
    x = M + 320; cy = y
    marker_link(c, M + 278, cy - 47.5, 1, x)
    marker_link(c, M + 278, cy - 155.5, 2, x)
    marker_link(c, M + 278, cy - 262.5, 3, x)
    card(c, x, cy, 187, 95, "1. Video model", "Choose an installed local model. LTX 2B is the known fast-preview route; other models require their weights and machine validation.", TEAL)
    card(c, x, cy - 108, 187, 95, "2. Narration voice", "Choose an installed English voice. Saving a new voice keeps video clips but requires a new rough-cut assembly.", COPPER)
    card(c, x, cy - 216, 187, 93, "3. Generate", "Create storyboard frames, motion clips, narration, captions and an assembled rough cut, then review it in the player.", TEAL)
    callout(c, x, cy - 323, 187, "Review for", "Message order, scene timing, narration pace, caption sense, product drift and any reference influence that feels too strong.", "copper")
    y -= 522
    callout(c, M, y, W - 2*M, "Local limitation", "Uploaded image pixels are not used as first frames in the current local path. Longer scenes use time-stretched preview motion. The rough cut is for creative review, not commercial use.", "warning")
    c.showPage()

    # 19 - 5b
    y = page(c, 19, "05B / Cloud evaluation", "Higgsfield video test", "This optional path prepares one Seedance 2.5 clip per storyboard scene, then assembles them with the local narration and captions.")
    draw_contain(c, SHOTS / "07-higgsfield.png", M, y, 304, 570, bg=INK)
    x = M + 324; cy = y
    marker_link(c, M + 282, cy - 43.5, 1, x)
    marker_link(c, M + 282, cy - 151.5, 2, x)
    marker_link(c, M + 282, cy - 269.5, 3, x)
    marker_link(c, M + 282, cy - 384, 4, x)
    card(c, x, cy, 183, 87, "1. Model + format", "The current route uses Seedance 2.5 at 16:9, with a 480p or 720p choice.", TEAL)
    card(c, x, cy - 99, 183, 105, "2. Estimate first", "Requesting an estimate may upload selected references, but it does not submit paid video generation.", COPPER)
    card(c, x, cy - 216, 183, 107, "3. Prepared scenes", "Review each duration and reference count. Prompt-only scenes use text-to-video.", TEAL)
    card(c, x, cy - 335, 183, 98, "4. Approve spend", "The estimate is approximate and before discounts. Approve the specific quote before rendering.", COPPER)
    callout(c, x, cy - 447, 183, "Cloud warning", "A reference includes its photographed background. Character and product consistency are not guaranteed.", "warning")
    c.showPage()

    # 20 - Revision map
    y = page(c, 20, "Iterate without confusion", "What changes reset downstream work", "The studio invalidates dependent approvals and outputs so that the current state remains traceable.")
    rows = [
        ["Change", "What remains", "What needs review again"],
        ["Brief, brand or target length", "Uploaded references", "Concept, storyboard, rough cut, cloud quote"],
        ["Concept or narration", "Brief approval and references", "Storyboard, rough cut, cloud quote"],
        ["Scene timing or prompt", "Brief and concept", "Storyboard approval and generated drafts"],
        ["Reference metadata or assignment", "Source image", "Affected scene outputs and downstream approvals"],
        ["Narration voice", "Generated video clips", "Narration, captions and rough-cut assembly"],
        ["Cloud resolution", "Storyboard", "A fresh matching estimate"],
    ]
    y = table(c, M, y, [150, 155, 202], rows, [32, 55, 55, 55, 55, 55, 48]) - 18
    c.setFillColor(TEAL_DARK); c.setFont(BOLD, 13); c.drawString(M, y, "A reliable revision loop")
    y -= 25
    for i, text in enumerate(["Identify the failing scene or decision.", "Change the smallest relevant input.", "Recheck references, timing and claims.", "Reapprove the stage.", "Regenerate only what the change invalidated."]):
        x = M + i * 101
        c.setFillColor(TEAL if i < 4 else COPPER); c.circle(x + 14, y, 14, fill=1, stroke=0)
        c.setFillColor(WHITE); c.setFont(BOLD, 8); c.drawCentredString(x + 14, y - 3, str(i + 1))
        para(c, text, x, y - 24, 88, "small", 0)
        if i < 4: flow_arrow(c, x + 34, x + 96, y, TEAL_DARK)
    y -= 110
    callout(c, M, y, W - 2*M, "Avoid", "Do not regenerate the whole campaign to fix one weak scene. Edit that scene's visual, camera, prompts or reference assignment first.", "copper")
    c.showPage()

    # 21 - Costs and limitations
    y = page(c, 21, "Know before you submit", "Costs, approvals and practical limits", "The studio separates planning, local compute and cloud rendering so each decision is visible.", dark=True)
    card(c, M, y, 244, 150, "OpenAI planning", "Used for paid direction, scene generation and claim candidates when configured. The preview reports size and warnings before submission. Manually entered direction remains available without it.", TEAL, dark=True)
    card(c, M + 263, y, 244, 150, "Local generation", "Uses your machine, Pinokio, ComfyUI, local models, Kokoro, Whisper and FFmpeg. There is no provider charge, but rendering consumes time, storage and GPU resources.", COPPER, dark=True)
    y -= 170
    card(c, M, y, 244, 170, "Higgsfield evaluation", "The estimate is based on prepared scenes, billable duration and resolution. It is approximate, before discounts and not a spending cap. The app stops if the published estimate rises before submission.", COPPER, dark=True)
    card(c, M + 263, y, 244, 170, "Human responsibility", "Confirm claims, rights, privacy, brand accuracy, disclaimers and suitability. Check the provider console if submission state is uncertain; never replay an ambiguous paid request blindly.", TEAL, dark=True)
    y -= 194
    c.setFillColor(TEAL_LIGHT); c.setFont(BOLD, 13); c.drawString(M, y, "Current limits to remember")
    y -= 22
    y = bullets(c, [
        "All generated outputs are non-commercial drafts in this release.",
        "LTX content must retain an intelligible AI-generated disclaimer wherever displayed or shared.",
        "A reference can guide identity but cannot guarantee consistency.",
        "An API key proves configuration, not available credit or model access.",
        "Website subscription credits may differ from API billing.",
    ], M, y, W - 2*M, "body_dark", 4, TEAL_LIGHT)
    callout(c, M, y - 2, W - 2*M, "Decision point", "Approve a cloud estimate only after the storyboard, selected references, resolution and account context are correct.", "dark", dark=True)
    c.showPage()

    # 22 - Troubleshooting
    y = page(c, 22, "When something does not look right", "Fast troubleshooting", "Start with the visible stage that failed. Avoid changing several upstream inputs at once.")
    rows = [
        ["Symptom", "Check first", "Action"],
        ["Planning button disabled", "Brief approval, API key, preview blockers", "Approve or resolve the named warning."],
        ["Storyboard cannot approve", "Scene total versus target", "Adjust durations until the totals match exactly."],
        ["Wrong product appearance", "Reference role, description and scene link", "Use a clean product image and explicit guidance."],
        ["Reference background appears", "Cloud reference contains that background", "Use a cleaner source or state what to replace."],
        ["Narration feels rushed", "Word count and pauses", "Shorten the script; regenerate narration and assembly."],
        ["Local draft button disabled", "Storyboard approval and model readiness", "Approve the storyboard or install/select a ready model."],
        ["Cloud estimate disabled", "Higgsfield key, errors, uncertain run", "Open Setup, fix preflight, or reconcile the earlier request."],
        ["Interrupted paid submission", "Higgsfield API console", "Recover by request ID or confirm no request exists."],
    ]
    y = table(c, M, y, [130, 175, 202], rows, [30, 48, 48, 48, 48, 48, 48, 54, 54]) - 16
    callout(c, M, y, W - 2*M, "Diagnostics", "Open [[Setup & Diagnostics]] to recheck the local foundation, API configuration and model readiness. Export diagnostics when you need a shareable technical record; review it before sending.", "teal")
    y -= 98
    callout(c, M, y, W - 2*M, "Do not guess", "When a paid cloud request was interrupted, use the provider console and the recovery controls. Do not resubmit until you know whether the first request exists.", "warning")
    c.showPage()

    # 23 - Final checklist
    y = page(c, 23, "Ready to work", "Pre-render checklist", "Use this list before local generation and again before approving cloud spend.")
    checks = [
        "The objective, audience and key message agree.",
        "Claims and disclaimers use reviewed wording.",
        "The CTA is clear and appropriate for the deliverable.",
        "The concept supports the brief without adding unsupported promises.",
        "The narration reads naturally within the target time.",
        "Scene durations total exactly 15, 30, 45 or 60 seconds.",
        "Every scene has a distinct purpose and usable image/video prompts.",
        "Only useful references are assigned, with scene-specific guidance.",
        "Source-image rights, privacy and cloud-upload suitability are checked.",
        "The selected local model or cloud resolution matches the review goal.",
        "The latest estimate matches the current storyboard and references.",
        "A human reviewer understands that the output is a non-commercial AI draft.",
    ]
    for i, item in enumerate(checks):
        col = i % 2; row = i // 2
        x = M + col * 263; yy = y - row * 52
        c.setFillColor(WHITE); c.roundRect(x, yy - 39, 244, 39, 8, fill=1, stroke=0)
        c.setStrokeColor(TEAL_DARK); c.rect(x + 12, yy - 26, 13, 13, fill=0, stroke=1)
        para(c, item, x + 34, yy - 8, 198, "small", 0)
    y -= 6 * 52 + 12
    c.setFillColor(TEAL_DARK); c.setFont(BOLD, 13); c.drawString(M, y, "Useful terms and locations")
    y -= 20
    rows = [
        ["Term", "Meaning"],
        ["Reference", "An uploaded source image that can be assigned to selected scenes."],
        ["Guidance", "Scene-specific instruction describing how a reference should influence output."],
        ["Rough cut", "Locally assembled draft video for structural and creative review."],
        ["Evaluation", "Optional Higgsfield cloud draft, still non-commercial in this release."],
        ["Project files", "Stored under the studio data/projects folder; use the studio to preserve lineage."],
    ]
    y = table(c, M, y, [110, 397], rows, [28, 38, 38, 38, 38, 42]) - 12
    callout(c, M, y, W - 2*M, "Keep beside the studio", "Return to Step 1 when the assignment changes, Step 4 when a scene needs work, and Setup & Diagnostics when local tools or provider access change.", "copper")
    c.setFillColor(TEAL_DARK); c.setFont(BOLD, 10); c.drawRightString(W - M, 45, "NORTHSTAR FLOW DEMO ASSETS ARE FICTIONAL")
    c.showPage()

    c.save()
    print(OUT)


if __name__ == "__main__":
    build()
