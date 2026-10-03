"""E149 guard: the app shell has a small-screen layout. Below Tailwind's md breakpoint (768px) the sidebar is not in
the page flow — it is an off-canvas menu in the shared Drawer, opened from a header button — and the content column
uses the full width with a 16px gutter, so no page is squeezed beside a 240px sidebar and scrolls sideways at 375px.
The desktop sidebar (resizable, collapsible, both persisted) is unchanged from md up. Overlays trap Tab while open.

The live half of the check (every page at 375px: document.documentElement.scrollWidth <= clientWidth) is the
small-screen walk in docs/ENGINEERING_PROCESS.md (E149)."""
from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "web" / "src"
SHELL = (WEB / "components" / "Shell.tsx").read_text()
OVERLAY = (WEB / "components" / "overlay.ts").read_text()


def _class_of(tag: str) -> str:
    m = re.search(rf"<{tag}\b[^>]*?className=\"([^\"]*)\"", SHELL, re.S)
    assert m, f"Shell.tsx has no <{tag} className=...>"
    return m.group(1)


def test_desktop_sidebar_is_out_of_the_flow_below_md():
    cls = _class_of("aside").split()
    assert "hidden" in cls and "md:flex" in cls, "the <aside> sidebar must be hidden below md (E149)"
    # the persisted desktop preferences are kept
    assert "useResizableWidth('tellumen.navw'" in SHELL and "tellumen.navcollapsed" in SHELL


def test_small_screens_get_the_menu_in_the_shared_drawer():
    header = _class_of("header").split()
    assert "md:hidden" in header, "the small-screen header (menu button) must disappear from md up"
    assert 'aria-label="Open menu"' in SHELL
    assert re.search(r"<Drawer\b[^\n]*placement=\"left\"[^\n]*overlayClassName=\"[^\"]*md:hidden", SHELL, re.S), \
        "the small-screen menu is the shared Drawer (placement=left), never a hand-rolled overlay"
    assert "fixed inset-0" not in SHELL
    # one menu component in both places, so the drawer and the sidebar cannot drift apart
    assert len(re.findall(r"<NavPanel\b", SHELL)) == 2
    # the matchMedia breakpoint is Tailwind's md
    assert "(max-width: 767.98px)" in SHELL


def test_content_has_a_small_screen_gutter():
    main = _class_of("main").split()
    assert "px-4" in main and "md:px-8" in main, "<main> uses a 16px gutter below md (E149)"
    bare = [m for m in re.findall(r"className=\"([^\"]*)\"", SHELL) if re.search(r"(?<![\w:])px-8\b", m)]
    assert not bare, "a 32px gutter in the shell must be md: only:\n" + "\n".join(bare)


def test_overlays_trap_tab():
    assert "e.key === 'Escape'" in OVERLAY and "e.key !== 'Tab'" in OVERLAY, \
        "useOverlay keeps Tab / Shift+Tab inside an open aria-modal panel (E149)"
