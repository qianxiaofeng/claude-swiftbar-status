#!/usr/bin/env python3
"""Generate a demo GIF showing ClaudeBar plugin functionality."""

from PIL import Image, ImageDraw, ImageFont

# --- Constants ---
W, H = 800, 400

# Colors (dark theme)
BG = (30, 30, 30)
MENUBAR_BG = (40, 40, 40)
MENUBAR_TEXT = (200, 200, 200)
WINDOW_BG = (45, 45, 50)
WINDOW_BORDER = (70, 70, 75)
TAB_BG = (55, 55, 60)
TAB_ACTIVE_BG = (45, 45, 50)
TAB_TEXT = (180, 180, 180)
TAB_ACTIVE_TEXT = (255, 255, 255)
CAPTION_TEXT = (160, 160, 170)
TERMINAL_TEXT = (0, 200, 0)

# Status colors — match ClaudeBar.sh SF Symbols palette config
GREEN = (50, 215, 75)     # #32D74B — active
ORANGE = (255, 159, 10)   # #FF9F0A — pending
GRAY = (142, 142, 147)    # #8E8E93 — idle

MENUBAR_H = 28
TAB_BAR_Y = 70
TAB_H = 30
TERMINAL_Y = TAB_BAR_Y + TAB_H + 5

# --- Font loading ---
def load_font(size):
    for path in [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSText.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()

font_sm = load_font(12)
font_md = load_font(14)
font_lg = load_font(16)
font_caption = load_font(15)


# --- Drawing helpers ---
def draw_sf_icon(draw, cx, cy, status, color):
    """Draw SF Symbol-like icon centered at (cx, cy).

    Matches ClaudeBar.sh STATUS_MAP:
      active  → bolt.fill (lightning bolt)
      pending → exclamationmark.triangle.fill (warning triangle)
      idle    → moon.fill (crescent moon)
    """
    if status == "active":
        # bolt.fill — lightning bolt polygon
        draw.polygon([
            (cx - 1, cy - 8),
            (cx + 4, cy - 8),
            (cx + 1, cy - 1),
            (cx + 5, cy - 1),
            (cx - 2, cy + 8),
            (cx + 1, cy + 1),
            (cx - 3, cy + 1),
        ], fill=color)
    elif status == "pending":
        # exclamationmark.triangle.fill — filled triangle with "!"
        draw.polygon([
            (cx, cy - 8),
            (cx + 9, cy + 7),
            (cx - 9, cy + 7),
        ], fill=color)
        # Exclamation mark in dark color
        draw.rectangle([cx - 1, cy - 4, cx + 1, cy + 2], fill=MENUBAR_BG)
        draw.rectangle([cx - 1, cy + 4, cx + 1, cy + 6], fill=MENUBAR_BG)
    elif status == "idle":
        # moon.fill — crescent moon (filled circle with dark cutout)
        r = 7
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
        # Cut out a circle offset to the upper-right to create crescent
        draw.ellipse([cx - 2, cy - r - 1, cx + r + 3, cy + 4], fill=MENUBAR_BG)


def draw_menubar(draw, icons):
    """Draw macOS-style menu bar with status icons on the right."""
    draw.rectangle([0, 0, W, MENUBAR_H], fill=MENUBAR_BG)
    draw.text((14, 5), "\u25CF", fill=MENUBAR_TEXT, font=font_md)
    for i, label in enumerate(["File", "Edit", "View"]):
        draw.text((40 + i * 45, 6), label, fill=(140, 140, 140), font=font_sm)
    draw.text((W - 55, 6), "12:34", fill=MENUBAR_TEXT, font=font_sm)

    # ClaudeBar icons (right-to-left, left of time)
    # Each icon is (status, color) where status determines the SF Symbol shape
    icon_x_start = W - 90
    for i, (status, color) in enumerate(reversed(icons)):
        x = icon_x_start - i * 26
        cy = 14  # vertical center
        draw_sf_icon(draw, x, cy, status, color)


def draw_iterm_window(draw, tabs, active_tab_idx):
    """Draw iTerm2-like window with tab bar."""
    draw.rounded_rectangle([30, 50, W - 30, H - 60], radius=10, fill=WINDOW_BG, outline=WINDOW_BORDER)

    for i, color in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        cx = 52 + i * 22
        draw.ellipse([cx - 6, 58, cx + 6, 70], fill=color)

    draw.text((130, 57), "iTerm2", fill=(150, 150, 150), font=font_sm)

    tab_w = 160
    for i, (name, _) in enumerate(tabs):
        x = 32 + i * (tab_w + 2)
        is_active = i == active_tab_idx
        bg = TAB_ACTIVE_BG if is_active else TAB_BG
        text_color = TAB_ACTIVE_TEXT if is_active else TAB_TEXT
        draw.rectangle([x, TAB_BAR_Y, x + tab_w, TAB_BAR_Y + TAB_H], fill=bg)
        if is_active:
            draw.rectangle([x, TAB_BAR_Y + TAB_H - 2, x + tab_w, TAB_BAR_Y + TAB_H], fill=GREEN)
        draw.text((x + 10, TAB_BAR_Y + 7), ">_", fill=(100, 100, 110), font=font_sm)
        draw.text((x + 32, TAB_BAR_Y + 7), name, fill=text_color, font=font_sm)


def draw_terminal_content(draw, lines):
    """Draw terminal text content."""
    y = TERMINAL_Y
    for line_color, text in lines:
        draw.text((50, y), text, fill=line_color, font=font_md)
        y += 22


def draw_caption(draw, text):
    """Draw scene caption at the bottom."""
    bbox = draw.textbbox((0, 0), text, font=font_caption)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, H - 45), text, fill=CAPTION_TEXT, font=font_caption)


def draw_cursor(draw, x, y):
    """Draw cursor block."""
    draw.rectangle([x, y, x + 9, y + 16], fill=TERMINAL_TEXT)


# --- Build keyframes with durations ---
def build_frames():
    """Return list of (PIL.Image, duration_ms) tuples."""
    keyframes = []

    def make(icons, tabs, active_tab, terminal_lines, caption, cursor_pos=None, extras=None):
        img = Image.new("RGB", (W, H), BG)
        draw = ImageDraw.Draw(img)
        draw_menubar(draw, icons)
        if tabs:
            draw_iterm_window(draw, tabs, active_tab)
        draw_terminal_content(draw, terminal_lines)
        draw_caption(draw, caption)
        if cursor_pos:
            draw_cursor(draw, *cursor_pos)
        if extras:
            extras(draw)
        return img

    # Scene 1a: Empty state - just menu bar, no sessions
    keyframes.append((make(
        icons=[],
        tabs=[],
        active_tab=0,
        terminal_lines=[],
        caption="1. Start first Claude session",
    ), 800))

    # Scene 1b: Tab appears, icon appears
    keyframes.append((make(
        icons=[("active", GREEN)],
        tabs=[("my-app", "active")],
        active_tab=0,
        terminal_lines=[
            (TERMINAL_TEXT, "$ claude"),
            ((180, 180, 180), "  Claude Code v1.0.43"),
        ],
        caption="1. Start first Claude session",
    ), 500))

    # Scene 1c: Working text appears
    keyframes.append((make(
        icons=[("active", GREEN)],
        tabs=[("my-app", "active")],
        active_tab=0,
        terminal_lines=[
            (TERMINAL_TEXT, "$ claude"),
            ((180, 180, 180), "  Claude Code v1.0.43"),
            (TERMINAL_TEXT, "  > Working on my-app..."),
        ],
        caption="1. Start first Claude session",
        cursor_pos=(275, TERMINAL_Y + 44),
    ), 1500))

    # Scene 2a: Second tab appears, 1 icon
    keyframes.append((make(
        icons=[("active", GREEN)],
        tabs=[("my-app", "active"), ("api-server", "active")],
        active_tab=1,
        terminal_lines=[
            (TERMINAL_TEXT, "$ claude"),
            ((180, 180, 180), "  Claude Code v1.0.43"),
        ],
        caption="2. Start second session \u2014 icon per tab",
    ), 500))

    # Scene 2b: Second icon appears
    keyframes.append((make(
        icons=[("active", GREEN), ("active", GREEN)],
        tabs=[("my-app", "active"), ("api-server", "active")],
        active_tab=1,
        terminal_lines=[
            (TERMINAL_TEXT, "$ claude"),
            ((180, 180, 180), "  Claude Code v1.0.43"),
            (TERMINAL_TEXT, "  > Working on api-server..."),
        ],
        caption="2. Start second session \u2014 icon per tab",
        cursor_pos=(325, TERMINAL_Y + 44),
    ), 1500))

    # Scene 3a: Both green still, switch to tab 1
    keyframes.append((make(
        icons=[("active", GREEN), ("active", GREEN)],
        tabs=[("my-app", "active"), ("api-server", "active")],
        active_tab=0,
        terminal_lines=[
            ((180, 180, 180), "  Claude wants to run:"),
            ((255, 200, 100), "    npm install express"),
        ],
        caption="3. Session 1 awaits approval \u2014 turns orange",
    ), 500))

    # Scene 3b: First icon turns orange
    keyframes.append((make(
        icons=[("pending", ORANGE), ("active", GREEN)],
        tabs=[("my-app", "pending"), ("api-server", "active")],
        active_tab=0,
        terminal_lines=[
            ((180, 180, 180), "  Claude wants to run:"),
            ((255, 200, 100), "    npm install express"),
            ((200, 200, 200), "  Allow? [y/n]"),
        ],
        caption="3. Session 1 awaits approval \u2014 turns orange",
        cursor_pos=(185, TERMINAL_Y + 44),
    ), 1500))

    # Scene 4a: Switch to tab 2, still green
    keyframes.append((make(
        icons=[("pending", ORANGE), ("active", GREEN)],
        tabs=[("my-app", "pending"), ("api-server", "active")],
        active_tab=1,
        terminal_lines=[
            ((180, 180, 180), "  Done! Ready for next task."),
            (TERMINAL_TEXT, "  >"),
        ],
        caption="4. Session 2 finishes \u2014 turns gray (idle)",
    ), 500))

    # Scene 4b: Second icon turns gray
    keyframes.append((make(
        icons=[("pending", ORANGE), ("idle", GRAY)],
        tabs=[("my-app", "pending"), ("api-server", "idle")],
        active_tab=1,
        terminal_lines=[
            ((180, 180, 180), "  Done! Ready for next task."),
            (TERMINAL_TEXT, "  >"),
        ],
        caption="4. Session 2 finishes \u2014 turns gray (idle)",
        cursor_pos=(67, TERMINAL_Y + 22),
    ), 1500))

    # Scene 5a: Before swap - show arrow
    def draw_arrow(draw):
        arrow_y = TAB_BAR_Y + TAB_H // 2
        draw.text((350, arrow_y - 5), "\u21c4", fill=(255, 255, 100), font=font_lg)

    keyframes.append((make(
        icons=[("pending", ORANGE), ("idle", GRAY)],
        tabs=[("my-app", "pending"), ("api-server", "idle")],
        active_tab=0,
        terminal_lines=[
            ((180, 180, 180), "  Drag tabs to reorder..."),
        ],
        caption="5. Reorder tabs \u2014 icons follow automatically",
        extras=draw_arrow,
    ), 1200))

    # Scene 5b: After swap
    keyframes.append((make(
        icons=[("idle", GRAY), ("pending", ORANGE)],
        tabs=[("api-server", "idle"), ("my-app", "pending")],
        active_tab=1,
        terminal_lines=[
            ((180, 180, 180), "  Drag tabs to reorder..."),
            ((120, 180, 255), "  Menu bar icons follow tab order!"),
        ],
        caption="5. Reorder tabs \u2014 icons follow automatically",
    ), 2000))

    return keyframes


def generate_gif():
    keyframes = build_frames()
    frames = [kf[0] for kf in keyframes]
    durations = [kf[1] for kf in keyframes]

    frames[0].save(
        "demo.gif",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
    )
    total_dur = sum(durations) / 1000
    print(f"Generated demo.gif ({len(frames)} keyframes, {total_dur:.1f}s total)")


if __name__ == "__main__":
    generate_gif()
