#!/usr/bin/env python3
"""
Push-Up Surrogate Body Illustration — Apex Coach Card Phase 1
Holographic wireframe style. Surrogate only; replaced by Apex artwork in Phase 2.
Output: static/exercise/pushup-holo.png  (600x380 RGBA, transparent bg)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from PIL import Image, ImageDraw, ImageFilter

W, H = 600, 380

CYAN   = (0, 217, 255)
PURPLE = (155, 89, 255)
CYAN_L = (140, 230, 255)
WHITE_B = (210, 235, 255)

def new():
    return Image.new('RGBA', (W, H), (0, 0, 0, 0))

# ── Core primitive: rotated glowing body segment ──────────────────────────────

def segment(base, cx, cy, sw, sh, angle_deg,
            color, blurs=(45, 22, 9, 3, 0), alphas=(18, 35, 65, 100, 210)):
    """
    Draw a glowing, rotated ellipse (body segment) composited onto base.
    cx, cy = centre of segment in base image coordinates
    sw, sh = width and height of the ellipse BEFORE rotation
    angle_deg = CCW rotation
    """
    pad = (max(blurs) + 4) * 2
    cw = sw + pad
    ch = sh + pad
    tile = new()  # oversized: will be cropped after rotation

    # We work in a local canvas sized to hold the blurred segment
    loc_w = cw + pad * 2
    loc_h = ch + pad * 2
    local = Image.new('RGBA', (loc_w, loc_h), (0, 0, 0, 0))

    for blur, alpha in zip(blurs, alphas):
        l = Image.new('RGBA', (loc_w, loc_h), (0, 0, 0, 0))
        d = ImageDraw.Draw(l)
        r, g, b = color
        margin = blur
        x0 = (loc_w - sw) // 2 - margin
        y0 = (loc_h - sh) // 2 - margin
        x1 = (loc_w + sw) // 2 + margin
        y1 = (loc_h + sh) // 2 + margin
        d.ellipse([x0, y0, x1, y1], fill=(r, g, b, alpha))
        if blur > 0:
            l = l.filter(ImageFilter.GaussianBlur(blur))
        local.alpha_composite(l)

    rotated = local.rotate(-angle_deg, resample=Image.BICUBIC, expand=True)

    # Paste centred at (cx, cy) in base
    px = cx - rotated.width  // 2
    py = cy - rotated.height // 2
    base.alpha_composite(rotated, dest=(max(0, px), max(0, py)),
                         source=(max(0, -px), max(0, -py),
                                 min(rotated.width,  W - px),
                                 min(rotated.height, H - py)))


def ellipse_glow(base, cx, cy, rx, ry, color,
                 blurs=(40, 20, 8, 0), alphas=(20, 40, 80, 210)):
    """Axis-aligned glowing ellipse."""
    for blur, alpha in zip(blurs, alphas):
        l = new()
        d = ImageDraw.Draw(l)
        r, g, b = color
        m = blur
        d.ellipse([cx-rx-m, cy-ry-m, cx+rx+m, cy+ry+m], fill=(r, g, b, alpha))
        if blur > 0:
            l = l.filter(ImageFilter.GaussianBlur(blur))
        base.alpha_composite(l)


# ── Push-up pose landmarks (600×380, head upper-right, feet lower-left) ───────
#
#  The body is nearly horizontal, 3/4 view (slight left-front angle).
#  Near side (viewer's right = person's right) is slightly lower in frame.
#
#  Angle convention for segment(): 0 = horizontal, 90 = vertical-upward
#
#  Body tilt (shoulder→hip line): ~12° from horizontal, descending left.
#  In PIL angle convention we rotate the ellipse so its long axis is along
#  that body line. The long axis of a non-rotated ellipse is horizontal (0°),
#  so we pass the tilt angle directly.

BODY_TILT = 12   # degrees — whole-body diagonal

# Key centres (x, y)
HEAD   = (510, 72)
NECK   = (478, 98)
# Near-side shoulder (right of person)
RSH    = (450, 115)
# Far-side shoulder (left of person, slightly higher)
LSH    = (400, 108)
# Near-side hip
RHIP   = (210, 238)
# Far-side hip
LHIP   = (168, 228)
# Near arm (right): upper arm hangs down at about 78° from horizontal
R_UA   = (435, 205)   # upper arm centre
R_ELB  = (418, 310)   # elbow
R_FA   = (410, 330)   # forearm centre
R_HND  = (400, 368)   # hand
# Far arm (left): slightly smaller, higher
L_UA   = (378, 197)
L_ELB  = (362, 295)
L_FA   = (354, 318)
L_HND  = (344, 353)
# Near leg (right): long, diagonal same as body tilt
R_UL   = (192, 278)
R_KNE  = (148, 330)
R_LL   = (128, 348)
R_FT   = (104, 368)
# Far leg (left): slightly offset
L_UL   = (158, 268)
L_KNE  = (116, 318)
L_LL   = (98,  334)
L_FT   = (75,  353)

img = new()

# ── 1. FAR-SIDE LIMBS (drawn first = behind body) ─────────────────────────────
# Left (far) leg
segment(img, *L_UL,  32, 110, BODY_TILT, CYAN)
segment(img, *L_LL,  22,  85, BODY_TILT, CYAN)
ellipse_glow(img, *L_FT, 26, 10, CYAN)

# Left (far) arm
segment(img, *L_UA,  22,  95,  78, CYAN)
segment(img, *L_FA,  16,  82,  83, CYAN)
ellipse_glow(img, *L_HND, 24, 11, CYAN)

# ── 2. TORSO ──────────────────────────────────────────────────────────────────
segment(img, 320, 175,  105, 230, BODY_TILT, CYAN)

# Chest muscle highlight (bright, wider)
segment(img, 370, 160,  90, 85, BODY_TILT + 2, WHITE_B,
        blurs=(30, 14, 5, 0), alphas=(30, 60, 100, 200))

# Shoulder highlights
ellipse_glow(img, *RSH, 28, 22, PURPLE, blurs=(22, 10, 3, 0), alphas=(50, 90, 130, 220))
ellipse_glow(img, *LSH, 24, 18, PURPLE, blurs=(18, 8,  2, 0), alphas=(40, 75, 110, 180))

# ── 3. NEAR-SIDE LIMBS (drawn over torso = in front) ─────────────────────────
# Right (near) leg
segment(img, *R_UL,  38, 118, BODY_TILT, CYAN)
segment(img, *R_LL,  26,  92, BODY_TILT, CYAN)
ellipse_glow(img, *R_FT, 30, 12, CYAN)

# Right (near) arm — tricep highlight on upper arm
segment(img, *R_UA,  26, 100,  78, CYAN)
# Tricep highlight
segment(img, *R_UA,  14,  90,  78, CYAN_L,
        blurs=(18, 8, 2, 0), alphas=(40, 80, 120, 190))
segment(img, *R_FA,  18,  86,  82, CYAN)
ellipse_glow(img, *R_HND, 27, 12, CYAN)

# Left arm tricep highlight
segment(img, *L_UA,  12,  80,  78, CYAN_L,
        blurs=(14, 6, 1, 0), alphas=(30, 60, 100, 160))

# ── 4. HEAD + NECK ────────────────────────────────────────────────────────────
segment(img, *NECK, 18, 35, 82, CYAN)
ellipse_glow(img, *HEAD, 28, 34, CYAN, blurs=(30, 14, 5, 0), alphas=(25, 50, 90, 200))

# ── 5. MESH GRID overlay (holographic wireframe feel) ─────────────────────────
mesh = new()
md = ImageDraw.Draw(mesh)
# Sparse horizontal lines across the body band
for y in range(60, H, 22):
    md.line([(50, y), (560, y)], fill=(0, 190, 255, 14), width=1)
for x in range(50, 580, 22):
    md.line([(x, 45), (x, H - 20)], fill=(0, 190, 255, 10), width=1)
mesh = mesh.filter(ImageFilter.GaussianBlur(0.8))
img.alpha_composite(mesh)

# ── 6. AMBIENT CORE GLOW (body centre atmosphere) ─────────────────────────────
atmo = new()
ad = ImageDraw.Draw(atmo)
# Centre of mass of push-up body
ad.ellipse([140, 80, 540, 330], fill=(0, 180, 255, 20))
atmo = atmo.filter(ImageFilter.GaussianBlur(60))
img.alpha_composite(atmo)

# ── Save ───────────────────────────────────────────────────────────────────────
out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        'static', 'exercise', 'pushup-holo.png')
img.save(out_path, 'PNG')
print(f'Saved {W}x{H} RGBA -> {out_path}')
