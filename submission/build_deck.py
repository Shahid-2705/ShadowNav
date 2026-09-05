"""Build the ShadowNav SIH 2026 idea deck ON the official template.

Every template element is kept: title-page pointer list, per-slide title text,
team-name oval, SIH logo, blue footer bar, slide numbers. Only the body text
box is repurposed and pictures/tiles are added. Slide 7 (instructions) is
deleted, as the instructions themselves require.

Usage: python build_deck.py <template.pptx> <figdir> <out.pptx>
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt

TEMPLATE, FIGDIR, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])

NAVY = RGBColor(0x1F, 0x49, 0x7D)
BLUE = RGBColor(0x00, 0x70, 0xC0)
GREEN = RGBColor(0x2E, 0x9E, 0x5B)
ORANGE = RGBColor(0xF7, 0x96, 0x46)
RED = RGBColor(0xC0, 0x50, 0x4D)
GREY = RGBColor(0x55, 0x5F, 0x6B)
INK = RGBColor(0x1A, 0x1A, 0x1A)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
TILE_BLUE = RGBColor(0xEA, 0xF2, 0xFB)
TILE_GREEN = RGBColor(0xE8, 0xF5, 0xEE)
TILE_ORANGE = RGBColor(0xFF, 0xF4, 0xE5)
TILE_VIOLET = RGBColor(0xEE, 0xF0, 0xFF)

TEAM = "ShadowNav"
FOOTER = "SIH 2026 Idea Submission · ShadowNav"
PS_TITLE = "AI-ML based Intelligent Dead Reckoning system for seamless navigation"
THEME = "Smart Vehicles"

traj = json.loads((FIGDIR / "fig_traj.json").read_text())


# ----------------------------------------------------------------- helpers
def shapes_by_name(slide):
    return {s.name: s for s in slide.shapes}


def set_single_run(shape, text, size=None, bold=None, color=None, font=None):
    """Replace all text in a shape but keep the first run's formatting."""
    tf = shape.text_frame
    first = tf.paragraphs[0]
    for p in list(tf.paragraphs)[1:]:
        p._p.getparent().remove(p._p)
    runs = first.runs
    if runs:
        for r in runs[1:]:
            r._r.getparent().remove(r._r)
        run = runs[0]
    else:
        run = first.add_run()
    run.text = text
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color
    if font:
        run.font.name = font


def no_bullet(p):
    """Strip any bullet/indent the template paragraph carried; we draw our own glyphs."""
    pPr = p._p.get_or_add_pPr()
    for tag in ("a:buNone", "a:buChar", "a:buAutoNum", "a:buFont", "a:buSzPct", "a:buClr"):
        for el in pPr.findall(qn(tag)):
            pPr.remove(el)
    pPr.append(OxmlElement("a:buNone"))
    pPr.set("marL", "0")
    pPr.set("indent", "0")


def write_blocks(tf, blocks, body=14, head=15.5, gap=3):
    """blocks: list of (kind, text). kind: h=heading, b=bullet, p=plain, s=small."""
    tf.clear()
    tf.word_wrap = True
    first = True
    for kind, text in blocks:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        no_bullet(p)
        r = p.add_run()
        if kind == "h":
            r.text = text
            r.font.size, r.font.bold, r.font.color.rgb = Pt(head), True, NAVY
            p.space_before, p.space_after = Pt(gap + 3), Pt(gap)
        elif kind == "b":
            r.text = "•  " + text
            r.font.size, r.font.color.rgb = Pt(body), INK
            p.space_after = Pt(gap)
        elif kind == "s":
            r.text = text
            r.font.size, r.font.color.rgb, r.font.italic = Pt(body - 2.5), GREY, True
            p.space_after = Pt(gap)
        else:
            r.text = text
            r.font.size, r.font.color.rgb = Pt(body), INK
            p.space_after = Pt(gap)
        r.font.name = "Arial"


def place(shape, left, top, width, height):
    shape.left, shape.top, shape.width, shape.height = (
        Inches(left), Inches(top), Inches(width), Inches(height))


def tile(slide, left, top, width, height, title, lines, fill, edge, body=13, head=14.5):
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top),
                                 Inches(width), Inches(height))
    shp.adjustments[0] = 0.08
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    shp.line.color.rgb = edge
    shp.line.width = Pt(1.5)
    shp.shadow.inherit = False
    tf = shp.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.TOP
    tf.margin_left = tf.margin_right = Inches(0.1)
    tf.margin_top = Inches(0.06)
    blocks = [("h", title)] + [("b", l) for l in lines]
    write_blocks(tf, blocks, body=body, head=head, gap=2)
    return shp


def caption(slide, left, top, width, text, size=11):
    tb = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(0.5))
    tf = tb.text_frame
    tf.word_wrap = True
    write_blocks(tf, [("s", text)], body=size + 2.5, gap=0)
    return tb


def picture(slide, name, left, top, width=None, height=None):
    kw = {}
    if width:
        kw["width"] = Inches(width)
    if height:
        kw["height"] = Inches(height)
    return slide.shapes.add_picture(str(FIGDIR / name), Inches(left), Inches(top), **kw)


def brand(slide):
    sh = shapes_by_name(slide)
    for n, s in sh.items():
        if n.startswith("Oval"):
            set_single_run(s, TEAM, size=11, bold=True, color=NAVY)
            tfo = s.text_frame
            tfo.paragraphs[0].alignment = PP_ALIGN.CENTER
            tfo.vertical_anchor = MSO_ANCHOR.MIDDLE
            tfo.margin_left = tfo.margin_right = Inches(0.02)
            tfo.word_wrap = False
        if n.startswith("Footer Placeholder"):
            set_single_run(s, FOOTER, size=11)


# ------------------------------------------------------------------- build
prs = Presentation(str(TEMPLATE))
slides = list(prs.slides)

# --- slide 7: delete the instructions slide (the template asks for this)
sld_ids = prs.slides._sldIdLst
last = list(sld_ids)[6]
prs.part.drop_rel(last.rId)
sld_ids.remove(last)

# --- slide 1: title page pointers, verbatim labels kept
s1 = slides[0]
sh = shapes_by_name(s1)
tb = sh["TextBox 9"]
tf = tb.text_frame
labels = [
    ("Problem Statement ID – ", "SIH26168"),
    ("Problem Statement Title – ", PS_TITLE),
    ("Theme – ", THEME),
    ("PS Category – ", "Software"),
    ("Team ID – ", "[from the SIH portal]"),
    ("Team Name – ", TEAM),
]
paras = list(tf.paragraphs)
for i, (lab, val) in enumerate(labels):
    p = paras[i] if i < len(paras) else tf.add_paragraph()
    for r in list(p.runs):
        r._r.getparent().remove(r._r)
    r1 = p.add_run(); r1.text = lab
    r2 = p.add_run(); r2.text = val
    size = 18 if i == 1 else 22
    for r in (r1, r2):
        r.font.name, r.font.size = "Arial", Pt(size)
    r1.font.bold, r2.font.bold = True, False
    r2.font.color.rgb = NAVY
    p.space_after = Pt(8)
for p in paras[len(labels):]:
    p._p.getparent().remove(p._p)
# the template's first pointer had no bullet while the rest did; make them uniform
p0, p1 = paras[0], paras[1]
if p0._p.pPr is None and p1._p.pPr is not None:
    p0._p.insert(0, copy.deepcopy(p1._p.pPr))
tf.word_wrap = True
place(tb, 0.36, 2.15, 6.9, 5.1)

# --- slide 2: idea title + proposed solution
s2 = slides[1]
sh = shapes_by_name(s2)
set_single_run(sh["Title 1"], "ShadowNav: Dead Reckoning Through GPS Blackouts",
               size=26, bold=True)
# keep the idea title clear of the team oval (left) and the SIH logo (right)
place(sh["Title 1"], 1.85, 0.0, 8.75, 1.25)
body = sh["TextBox 8"]
place(body, 0.35, 1.2, 6.45, 5.65)
write_blocks(body.text_frame, [
    ("h", "Proposed Solution"),
    ("p", "An Android app that keeps a vehicle's position alive through tunnels, "
          "multi-level parking and urban canyons using only the phone's accelerometer "
          "and gyroscope, then blends back to GPS without a visible jump."),
    ("h", "How it addresses the problem"),
    ("b", "Drift and bias: gyro bias is a filter state, device-to-car alignment is "
          "learned from the drive, a stationary detector freezes drift at halts"),
    ("b", "Outage entry and re-acquisition: a chi-square gate and C/N₀ de-weighting "
          "decide when GPS is trustworthy; a 4-state machine and a damped blend restore it"),
    ("b", "Vehicle physics: non-holonomic and Ackermann curvature/friction bounds keep "
          "the track on a road-like path"),
    ("b", "Calibrated confidence: a 90 % radius the user can act on, calibrated on "
          "held-out routes (coverage 17 % → 97 %)"),
    ("h", "Innovation and uniqueness"),
    ("b", "Any Android 10+ phone: no wheel ticks, CAN bus, magnetometer or vendor SDK, "
          "so it also covers two-wheelers, about 75 % of India's fleet"),
    ("b", "Every number reproduces from a public dataset (IO-VNBD) and a committed seed; "
          "GPS is cut artificially on real drives"),
    ("b", "Learned CNN+GRU speed net is opt-in: ablations showed it hurt at 180 s, so it "
          "is enabled only where it measurably helps"),
    ("b", "Already a live app: 401 Hz IMU on a moto g64, 2.2 MB APK, 182 automated "
          "tests, Kotlin core matches Python to 1e-9"),
], body=13, head=14.5, gap=2)
picture(s2, "fig_traj.png", 6.95, 1.2, width=6.05)
caption(s2, 6.95, 5.78, 6.05,
        f"One of 183 sixty-second outages in the benchmark ({traj['sequence']}, "
        f"{traj['distance_m']:,.0f} m travelled, error {traj['err_ours_m']:,.0f} m). Median across "
        f"all of them: 640 m for ShadowNav, 6.9 km for naive integration.", size=10.5)
brand(s2)

# --- slide 3: technical approach
s3 = slides[2]
sh = shapes_by_name(s3)
body = sh["TextBox 8"]
place(body, 0.35, 1.15, 4.35, 5.7)
write_blocks(body.text_frame, [
    ("h", "Technologies to be used"),
    ("b", "Android / Kotlin app, minSdk 29 (Android 10+); GnssStatus C/N₀ and IRNSS (NavIC) APIs; foreground service"),
    ("b", "Pure-Kotlin estimator module, parity-tested against Python golden vectors"),
    ("b", "Python 3.12, NumPy, PyTorch for training and evaluation; 161 tests"),
    ("b", "CNN+GRU speed net: 128 k params, 0.13 MB, 2.4 ms per window on one CPU core"),
    ("b", "Data: IO-VNBD (CC BY 4.0), 79 drives, 29.7 h, GPS cut at 991 points"),
    ("b", "Hardware: any Android 10+ phone; validated on a moto g64 5G"),
    ("h", "Methodology and process"),
    ("b", "1. Data pipeline, split and drift floor (naive strapdown)"),
    ("b", "2. Kinematic EKF + self-alignment + stationary detection"),
    ("b", "3. GNSS health gate and blackout / blend state machine"),
    ("b", "4. Conformal confidence fitted on validation routes"),
    ("b", "5. Android port, parity tests, 401 Hz on-device validation"),
    ("b", "6. Next: ablations at 401 Hz, heading-only map constraint"),
], body=12, head=14, gap=1.5)
picture(s3, "fig_arch.png", 4.85, 1.15, width=8.2)
picture(s3, "fig_fsm.png", 4.85, 4.95, width=8.2)
brand(s3)

# --- slide 4: feasibility and viability
s4 = slides[3]
sh = shapes_by_name(s4)
picture(s4, "fig_drift.png", 0.3, 1.15, width=6.1)
body = sh["TextBox 8"]
place(body, 0.35, 5.05, 6.05, 1.85)
write_blocks(body.text_frame, [
    ("h", "Analysis of feasibility: what is already true"),
    ("b", "Built and measured: 1.7× to 43× lower error than naive integration across 991 outages"),
    ("b", "Real time on the phone: 401 Hz IMU, filter step well under 1 ms, speed net 2.4 ms (30 ms budget)"),
    ("b", "Low-end target: Android 10+, 2.2 MB, no GPU, no cloud, no extra hardware"),
], body=12, head=13.5, gap=1.5)
tile(s4, 6.65, 1.15, 6.35, 2.75, "Potential challenges and risks", [
    "Drift is still 77–108 % of distance at 60–180 s; the AVNet field reference is 0.64 %",
    "The benchmark logs IMU at 10 Hz, which capped the strapdown filter and the learned speed net",
    "Heading drifts in long straight tunnels: without turns nothing corrects the gyro",
    "NavIC has 3 operational satellites today, below the 4 needed for a fix",
    "Battery and thermal load on low-end phones over a 2 h trip are unmeasured",
], TILE_ORANGE, ORANGE, body=11.5, head=13.5)
tile(s4, 6.65, 4.0, 6.35, 2.85, "Strategies for overcoming these challenges", [
    "The phone delivers 401 Hz, 40× the dataset: re-run strapdown and speed-net ablations on-device",
    "Opportunistic calibration during every turn and speed change, not a fixed pre-tunnel window",
    "Heading-only map constraint from OpenStreetMap, never lateral, so a wrong road cannot pull the track",
    "NavIC treated as instrumentation now, a measurement source once the constellation recovers",
    "Trip recorder logs battery and thermal state; INT8 inference if the 30 ms budget is threatened",
], TILE_GREEN, GREEN, body=11.5, head=13.5)
brand(s4)

# --- slide 5: impact and benefits
s5 = slides[4]
sh = shapes_by_name(s5)
body = sh["TextBox 8"]
place(body, 0.35, 1.1, 6.3, 0.45)
write_blocks(body.text_frame, [("h", "Potential impact on the target audience")], head=14.5, gap=0)
aud = [
    ("Drivers and riders", ["Position holds through tunnels and parking decks", "Two-wheelers included: no CAN bus needed"], TILE_BLUE, BLUE),
    ("Fleets, ride-hailing, logistics", ["Continuous trip tracking without hardware adapters", "One 2.2 MB app on phones drivers already own"], TILE_VIOLET, RGBColor(0x5B, 0x5B, 0xD6)),
    ("Emergency and public safety", ["A location plus an honest radius when GPS is gone", "Calibrated 90 % circle, never a false certainty"], TILE_ORANGE, ORANGE),
    ("ISRO and the NavIC ecosystem", ["Sovereign stack, open evaluation on a public benchmark", "NavIC visibility built in; measurement-ready later"], TILE_GREEN, GREEN),
]
for k, (t, lines, f, e) in enumerate(aud):
    col, row = k % 2, k // 2
    tile(s5, 0.35 + col * 3.2, 1.6 + row * 1.5, 3.1, 1.4, t, lines, f, e, body=11, head=12.5)
tb = s5.shapes.add_textbox(Inches(0.35), Inches(4.65), Inches(6.3), Inches(0.45))
write_blocks(tb.text_frame, [("h", "Benefits of the solution")], head=14.5, gap=0)
ben = [
    ("Social", ["Safer navigation where GPS fails most", "Works on the cheapest phones"], TILE_BLUE, BLUE),
    ("Economic", ["Zero added hardware", "No per-device SDK licence"], TILE_GREEN, GREEN),
    ("Environmental", ["No extra devices to make", "All compute on-device, no cloud"], TILE_ORANGE, ORANGE),
    ("Strategic", ["No foreign vendor SDK", "Reproducible, auditable results"], TILE_VIOLET, RGBColor(0x5B, 0x5B, 0xD6)),
]
for k, (t, lines, f, e) in enumerate(ben):
    tile(s5, 0.35 + k * 1.6, 5.1, 1.5, 1.75, t, lines, f, e, body=10.5, head=12)
picture(s5, "fig_coverage.png", 6.9, 1.15, width=3.1)
picture(s5, "app_shot.png", 10.25, 1.15, height=3.1)
caption(s5, 6.9, 4.3, 6.1,
        "Left: the filter's own 90 % circle covered 17 % of true positions on held-out routes; conformal "
        "inflation brings it to 97 %, reported as empirically calibrated, never guaranteed. "
        "Right: the live app on a moto g64 5G, 401 Hz IMU, 48 satellites visible.", size=10.5)
tile(s5, 6.9, 5.35, 6.1, 1.5, "Numbers that matter", [
    "2.2 MB APK, Android 10+, 0 extra hardware, 0 cloud calls",
    "1.7× to 43× lower blackout error than naive integration on 991 real-drive outages",
], TILE_BLUE, BLUE, body=11.5, head=12.5)
brand(s5)

# --- slide 6: research and references
s6 = slides[5]
sh = shapes_by_name(s6)
body = sh["TextBox 8"]
place(body, 0.35, 1.1, 6.6, 5.8)
write_blocks(body.text_frame, [
    ("h", "Research and reference work"),
    ("b", "Qian et al., AVNet: attitude and velocity for vehicular dead reckoning with an invariant EKF, Satellite Navigation 2025, doi 10.1186/s43020-025-00168-7"),
    ("b", "Feng et al., GNIO: Gated Neural Inertial Odometry, arXiv:2603.15281, 2026"),
    ("b", "Onyekpe et al., IO-VNBD vehicle inertial dataset, arXiv:2005.01701; github.com/onyekpeu/IO-VNBD (CC BY 4.0)"),
    ("b", "Brossard, Barrau, Bonnabel, AI-IMU Dead-Reckoning, github.com/mbrossar/ai-imu-dr (MIT)"),
    ("b", "Liu et al., TLIO: Tight Learned Inertial Odometry, IEEE RA-L 2020, arXiv:2007.01867"),
    ("b", "PiDR: Physics-Informed Inertial Dead Reckoning for Autonomous Platforms, arXiv:2601.03040, 2026"),
    ("b", "Android GnssStatus and GnssMeasurement reference, developer.android.com/reference/android/location/GnssStatus"),
    ("b", "Project code, tests, evaluation JSON and this deck: [repository link]"),
], body=11.5, head=14, gap=2)
tb = s6.shapes.add_textbox(Inches(7.15), Inches(1.1), Inches(5.9), Inches(0.45))
write_blocks(tb.text_frame, [("h", "Comparison with existing approaches")], head=14, gap=0)
rows = [
    ["Capability", "Map-app tunnel modes\n(Baidu VDR, Amap)", "Industrial\nGNSS-INS units", "Typical SIH\nrepos", "ShadowNav"],
    ["Phone only, no extra hardware", "✗ SDK / hardware gated", "✗", "✓", "✓"],
    ["Two-wheeler capable", "✗", "✗", "partial", "✓"],
    ["Calibrated confidence radius", "✗", "✓", "✗", "✓"],
    ["Public benchmark, reproducible", "✗", "✗", "rare", "✓"],
    ["Low-end Android 10+ target", "✗", "n/a", "varies", "✓"],
    ["Smooth GPS re-acquisition", "✓", "✓", "some", "✓"],
]
tbl = s6.shapes.add_table(len(rows), 5, Inches(7.15), Inches(1.6), Inches(5.9), Inches(3.9)).table
widths = [1.85, 1.25, 0.95, 0.85, 1.0]
for c, wdt in enumerate(widths):
    tbl.columns[c].width = Inches(wdt)
for r, row in enumerate(rows):
    for c, val in enumerate(row):
        cell = tbl.cell(r, c)
        cell.text = val
        cell.margin_left = cell.margin_right = Inches(0.05)
        cell.margin_top = cell.margin_bottom = Inches(0.03)
        for p in cell.text_frame.paragraphs:
            p.alignment = PP_ALIGN.LEFT if c == 0 else PP_ALIGN.CENTER
            for run in p.runs:
                run.font.size = Pt(10.5 if r else 10)
                run.font.name = "Arial"
                run.font.bold = (r == 0) or (c == 4)
                run.font.color.rgb = WHITE if r == 0 else (GREEN if (c == 4 and val == "✓") else INK)
        cell.fill.solid()
        cell.fill.fore_color.rgb = NAVY if r == 0 else (TILE_GREEN if c == 4 else (WHITE if r % 2 else TILE_BLUE))
caption(s6, 7.15, 5.6, 5.9,
        "Comparison from the project research dossier (§10 live SIH26168 repos, §13 market landscape); "
        "re-verify each cell before the finale.", size=10)
brand(s6)

prs.save(str(OUT))
print("saved", OUT, "slides:", len(prs.slides))
