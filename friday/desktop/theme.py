"""Visual constants for the FRIDAY desktop HUD.

Palette — steel + ice cyan. A cold Stark-lab-at-night feel, not the
warm helmet-interior amber. The orb is silver-white at the core and
ice-blue through the body, sitting in a near-black workshop with cyan
HUD chrome. Amber is reserved for alert states only (recording, error
warnings, "responding" mode flash).
"""

from PySide6.QtGui import QColor

# Backdrop — deep near-black, slight cool tilt.
BG_BASE       = QColor(3, 6, 11, 240)
BG_PANEL      = QColor(6, 10, 16, 220)
BG_INPUT      = QColor(8, 12, 20, 235)
BG_RAIL       = QColor(4, 8, 13, 230)
BORDER_DIM    = QColor(0, 180, 210, 85)
BORDER_WARM   = QColor(110, 194, 255, 70)      # legacy name kept; now ice
GRID_LINE     = QColor(0, 180, 210, 14)
SCANLINE      = QColor(0, 0, 0, 28)

# Orb — steel + ice. Names kept for backward compat with orb.py code
# paths; what's "warm" in the old code is now cold.
ORB_CORE      = QColor(240, 248, 255)          # silver-white
ORB_MID       = QColor(110, 194, 255)          # ice blue body
ORB_DEEP      = QColor(48, 128, 200)           # steel-blue shoulder
ORB_DARK      = QColor(30, 64, 96)             # deep steel outer
ORB_HALO      = QColor(79, 184, 255)           # cool cyan halo
ORB_LISTEN    = QColor(80, 240, 220)           # cool teal shift while listening
ORB_THINK     = QColor(150, 130, 255)          # violet shift while reasoning

# HUD chrome.
HUD_CYAN      = QColor(0, 229, 255)
HUD_CYAN_DIM  = QColor(0, 180, 210, 200)
HUD_AMBER     = QColor(255, 170, 80)           # reserved for alerts only
HUD_GREEN     = QColor(80, 230, 140)
HUD_RED       = QColor(255, 70, 95)
HUD_VIOLET    = QColor(190, 140, 255)
HUD_ICE       = QColor(110, 194, 255)

# Text.
TEXT_BRIGHT   = QColor(225, 238, 248)
TEXT_DIM      = QColor(120, 150, 170)
TEXT_FAINT    = QColor(70, 95, 115)
TEXT_USER     = QColor(150, 215, 255)          # boss prompt text — ice cyan
TEXT_ACCENT   = QColor(110, 194, 255)          # was warm amber → now ice
TEXT_DANGER   = QColor(255, 90, 110)
TEXT_OK       = QColor(80, 230, 140)
TEXT_PROMPT   = QColor(0, 229, 255)

# Fonts.
FONT_HUD      = "Menlo, Monaco, monospace"
FONT_MONO     = FONT_HUD
FONT_BODY     = FONT_HUD

# Sizes.
WINDOW_W      = 1340
WINDOW_H      = 780
CORNER_RADIUS = 10
PANEL_WIDTH   = 380
RAIL_WIDTH    = 230
TOPBAR_H      = 32
CMDBAR_H      = 42
