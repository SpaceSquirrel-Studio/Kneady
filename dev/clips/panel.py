"""The actions clip scripts share in Kneady's panel and on the item: picking
a button, opening a drag direction's command, choosing a dropdown's item,
clicking an axis button, picking a search field's suggestion, and a haul.
Every spot is found where it is drawn now (record.Clip's find), so the clips
follow the panel as it changes. The offsets measured here are in Blender's
interface unit, so they scale with it.

A script names its button's settings by a test on the end of the name
Blender gives them: `setting("up.kind")` passes what Blender names for
Button 1's up.kind."""

ROW = "kneady_row"          # what Blender names a row of the tree
HEADER_BELOW = 1.8          # a drag's command header under its On / Off row, in units (measured)
MENU_FIRST, MENU_STEP = 1.16, 1.08      # a dropdown's menu: its first item below it, then each next (measured)
MENU_TITLE = 1.32           # a dropdown's menu headed by its setting's name: its items this much lower (measured)
MENU_ROOM = 7               # units a dropdown needs under it for its menu to open downward
SEARCH_FIRST = 1.55         # a search field's list: its first item below the field's true middle (measured)
SEARCH_ROOM = 12            # units the list needs under it to open downward
KINDS = ("ROTATE", "MOVE", "SCALE", "INPUT", "PROPERTY")   # the Drives menu's order


def kneady(c, name):
    """One of Kneady's modules, as the recorder loaded it. It is found
    through the Clip class's own code, since Blender runs record.py as a
    script, not as a module this file could import."""
    return type(c).kneady_button.__globals__["kneady"](name)


def setting(attr, button=0):
    """A test for button `button`'s setting `attr` ("across.kind"). If
    `attr` is already a test (for a region's or the scene's setting), it is
    returned as it is."""
    if callable(attr):
        return attr
    return lambda name: name.endswith("buttons[%d].%s" % (button, attr))


def ending(path):
    """A test for any setting by the end of its path: "regions[0].arrange",
    "kneady_labels"."""
    return lambda name: name.endswith(path)


def up_top(c, test, what, xs=(0.5,)):
    """Where something near the top of the tab is (the tab's own settings,
    say). If it isn't found, the sidebar is scrolled back up and searched
    again, in case an earlier step left it scrolled down."""
    spot = yield from c.find(test, xs=xs)
    if spot is None:
        yield from c.scroll(-15, c.in_region(0.5, 0.5, "UI"))
        yield from c.wait(0.3)
        spot = yield from c.find(test, xs=xs)
    return c.must(spot, what)


def click_on(c, where, what, expect=None):
    """Move the cursor to what was found, wait until Blender is sure it is
    there (`expect`, what Blender names there), and click."""
    xy = c.must(where, what)
    yield from c.move(xy)
    yield from c.wait(0.12 if expect is not None else 0.3)
    if expect is not None:
        yield from c.settle(expect, what)
    yield from c.click()


def open_command(c, direction, button=0):
    """Open a drag direction's own command. Its header is the row under the
    direction's On / Off, and Blender names nothing there to find it by, so
    it is found from the switch above it."""
    spot = yield from c.find_scrolling(setting(direction + ".enabled", button), xs=(0.4,))
    x, y = c.must(spot, "%s's switch" % direction)
    yield from c.move((x, y - HEADER_BELOW * c.unit))
    yield from c.wait(0.3)
    yield from c.click()
    yield from c.wait(0.5)


def with_room_below(c, test, what, xs=(0.6,), room=MENU_ROOM):
    """Where a dropdown or field is, scrolling the sidebar first if what it
    opens would have no room under it (without room, it opens upward)."""
    spot = yield from c.find_scrolling(test, xs=xs)
    x, y = c.must(spot, what)
    floor = c.region("UI").y + room * c.unit
    if y < floor:
        yield from c.scroll(int((floor - y) / c.unit) + 2, c.in_region(0.5, 0.5, "UI"))
        yield from c.wait(0.3)
        spot = yield from c.find(test, xs=xs)
    return c.must(spot, what)


def drives(c, attr, kind, button=0):
    """Open a command's Drives dropdown (`attr`, "up.kind" or
    "up.more[0].kind") and click `kind` in its menu."""
    test = setting(attr, button)
    spot = yield from with_room_below(c, test, "Drives")
    yield from click_on(c, spot, "Drives", test)
    yield from c.wait(0.5)
    below = MENU_FIRST + KINDS.index(kind) * MENU_STEP
    yield from c.move((spot[0] - 1.5 * c.unit, spot[1] - below * c.unit))
    yield from c.wait(0.25)
    yield from c.click()
    yield from c.wait(0.5)


def axis(c, attr, which, count, button=0):
    """Click the `which`-th of a command's `count` axis buttons (X, Y, Z,
    All), `attr` being its axis setting ("up.axis")."""
    test = setting(attr, button)
    spot = yield from c.find(test, xs=(0.3,))
    _x, y = c.must(spot, "the axis buttons")
    ends = yield from c.span(test, y)
    left, right = c.must(ends, "the axis buttons' ends")
    x = left + (right - left) * (which + 0.5) / count
    yield from c.move((x, y))
    yield from c.wait(0.12)
    yield from c.settle(test, "an axis button")
    yield from c.click()


def _snapshot(c):
    """The window as it is, unseen (the clip's clock stopped). A generator."""
    c.pause()
    pixels = c._pixels()
    yield 0.05
    c.resume()
    return pixels


MENU_BACK = 0.0941          # a popup menu's back, Blender's factory theme (inner of Menu Back)
TEXT_ABOVE = 0.25           # how much brighter than its back a menu's text is, at least (dimmed items too)


def _around(flags, k, gap=3):
    """The run of True in `flags` that holds `k`, or else the one nearest
    it, bridging gaps of up to `gap`: (first, last), or None."""
    on = [i for i in range(len(flags)) if flags[i]]
    if not on:
        return None
    k = min(on, key=lambda i: abs(i - k))
    lo = hi = k
    while any(flags[j] for j in range(max(lo - gap, 0), lo)):
        lo -= 1
    while any(flags[j] for j in range(hi + 1, min(hi + 1 + gap, len(flags)))):
        hi += 1
    return lo, hi


def popup_rows(c, near):
    """Read the popup menu open at `near`, a point on it in window pixels:
    the mouse, right after the right-click that opened it, or, for a sub
    menu, a little past its parent's edge, level with the item that opened
    it. Returns an x on its items, the middle of each row of text from its
    top (its title first, if it has one), and its box (x0, y0, x1, y1). A
    generator.

    The menu is found by looking, since a popup is no region a script can
    search. With the clip's clock stopped, the window is screenshotted,
    then:

    - the menu's top and bottom are the run of rows around `near` in the
      menu's back color, measured in a narrow band of columns about it, so
      a parent menu beside it doesn't count;
    - its sides are found the same way, within those rows;
    - its items are the rows where text is brighter than its back. Each
      item is a row, dimmed or not; a separator, a thin line, is none.

    Where Blender opens a menu needn't be known: it remembers the item last
    chosen from each menu and opens with that item under the mouse."""
    import numpy as np  # type: ignore
    pixels = yield from _snapshot(c)
    rgb = pixels[..., :3]
    back = np.abs(rgb - MENU_BACK).max(axis=2) < 0.006
    x, y = int(near[0]), int(near[1])
    lo_x, hi_x = max(x - int(2.5 * c.unit), 0), min(x + int(2.5 * c.unit), back.shape[1])
    rows = _around(back[:, lo_x:hi_x].sum(axis=1) > 2 * c.unit, y, gap=int(1.2 * c.unit))
    if rows is None:
        return None, [], None
    y0, y1 = rows
    cols = _around(back[y0:y1 + 1].sum(axis=0) > 0.3 * (y1 - y0), x, gap=1)
    if cols is None:
        return None, [], None
    x0, x1 = cols
    inner = rgb[y0:y1 + 1, x0 + 6:x1 - 5].max(axis=2) > MENU_BACK + TEXT_ABOVE
    lit = inner.sum(axis=1) > 3
    found, run = [], []
    for k, on in enumerate(lit):
        if on:
            run.append(y0 + k)
        elif run:
            found.append(run)
            run = []
    if run:
        found.append(run)
    middles = [0.5 * (r[0] + r[-1]) for r in found if len(r) >= 0.3 * c.unit]   # text, not an underline
    return x0 + 0.4 * (x1 - x0), sorted(middles, reverse=True), (x0, y0, x1, y1)


def _lit_row(c, spot, before, after):
    """The middle of what lit up between two looks at the field's column,
    away from the field itself (its caret blinks). That is the list item
    Down lit, wherever the list opened: under the field, or over it when
    there is no room under. None if nothing lit up."""
    x, y, u = int(spot[0]), int(spot[1]), c.unit
    changed = abs(before[:, x, :3] - after[:, x, :3]).sum(axis=1) > 0.06
    runs, run = [], []
    for k in range(len(changed)):
        if changed[k] and abs(k - y) > 0.8 * u:
            run.append(k)
        elif run:
            runs.append(run)
            run = []
    if run:
        runs.append(run)
    if not runs:
        return None
    best = max(runs, key=len)
    return (spot[0], 0.5 * (best[0] + best[-1]))


def _pick_from_list(c, spot, index=0):
    """Pick the list's item `index`:

    - press Down to it, unseen;
    - move the cursor onto it, found by what Down lit, so wherever the list
      opened;
    - show a click there, and press Enter unseen.

    A simulated click on a list's item picks nothing, and a cursor resting
    on an item lights it in Down's place. So the keys do the picking and the
    cursor goes exactly where they did, while the clip shows what a person
    does."""
    before = yield from _snapshot(c)
    for _ in range(index + 1):
        yield from c.silent_key("DOWN_ARROW")
    yield from c.wait(0.25)
    after = yield from _snapshot(c)
    item = _lit_row(c, spot, before, after) or (spot[0], spot[1] - (SEARCH_FIRST + index * MENU_STEP) * c.unit)
    yield from c.move(item)
    yield from c.wait(0.25)
    yield from c.shown_click()
    yield from c.silent_key("RET")
    yield from c.wait(0.5)


def _opened(c, test, what, xs, room):
    """Find a search field and its true middle, and click on it. A
    generator; returns the spot."""
    spot = yield from with_room_below(c, test, what, xs=xs, room=room)
    spot = yield from c.middle(test, spot)
    yield from click_on(c, spot, what, test)
    return spot


def suggestion(c, attr, what, index=0, button=0, xs=(0.5,)):
    """Click a search field (`attr`, "up.data_path" or "across.input") and
    pick its `index`-th suggestion from the list that opens."""
    spot = yield from _opened(c, setting(attr, button), what, xs, SEARCH_ROOM)
    yield from c.wait(0.6)
    yield from _pick_from_list(c, spot, index)


def search_pick(c, attr, what, typed, button=0, xs=(0.5,), enter=False):
    """Click a search field (`attr`), type `typed` to narrow its list to
    what is wanted, and pick the first item. It is for a field whose list
    is long (a Target's objects, a rig's switches) or whose order isn't
    known.

    - With `enter`: for a list that lights its first match as you type (an
      object's, a Target's). Enter picks it, shown, as a person picks
      there; Down would move past it.
    - Without: for a list that lights nothing until Down (a Path's
      suggestions, a toggle picked for Show When), picked by
      _pick_from_list."""
    spot = yield from _opened(c, setting(attr, button), what, xs, SEARCH_ROOM)
    yield from c.wait(0.5)
    yield from c.type(typed)
    yield from c.wait(0.5)
    if enter:
        yield from c.key("RET", "Enter")
        yield from c.wait(0.5)
        return
    yield from _pick_from_list(c, spot)


def choose(c, attr, items, item, what, button=0, xs=(0.6,), titled=False):
    """Open a dropdown (`attr`) and click `item` in its menu, `items` being
    the menu's order. Set `titled` for a dropdown with no label of its own:
    Blender heads its menu with the setting's name, which puts the items a
    title's height further down."""
    test = setting(attr, button)
    spot = yield from with_room_below(c, test, what, xs=xs, room=MENU_ROOM + (MENU_TITLE if titled else 0))
    yield from click_on(c, spot, what, test)
    yield from c.wait(0.5)
    below = MENU_FIRST + (MENU_TITLE if titled else 0) + items.index(item) * MENU_STEP
    yield from c.move((spot[0], spot[1] - below * c.unit))   # its menu opens under it, at least as wide
    yield from c.wait(0.25)
    yield from c.click()
    yield from c.wait(0.5)


def one_of(c, attr, which, count, what, button=0, xs=(0.3,), top=False):
    """Click the `which`-th of a row of `count` buttons for one setting -
    Drag / Toggle / Gap, say. Set `top` for one near the top of the tab
    (up_top)."""
    test = setting(attr, button)
    spot = yield from (up_top(c, test, what, xs) if top else c.find_scrolling(test, xs=xs))
    _x, y = c.must(spot, what)
    ends = yield from c.span(test, y)
    left, right = c.must(ends, "%s's ends" % what)
    yield from c.move((left + (right - left) * (which + 0.5) / count, y))
    yield from c.wait(0.12)
    yield from c.settle(test, what)
    yield from c.click()


def add_command(c, direction, button=0):
    """Click a direction's Add Command: the first one under the direction's
    On / Off (the one above belongs to the direction before it)."""
    spot = yield from c.find_scrolling(setting(direction + ".enabled", button), xs=(0.4,))
    _x, y = c.must(spot, "%s's switch" % direction)
    test = (lambda name: "kneady.command_add" in name)
    found = yield from c.find(test, xs=(0.5,), start=y - c.unit)
    yield from click_on(c, found, "Add Command", test)
    yield from c.wait(0.6)


def haul(c, obj, hover, moves, button=0, region=0):
    """Haul a button: move onto the item at `hover` (a point in its own
    space), then onto the button, press, go through `moves`, and let go.
    Each move is (dx, dy, seconds) from the button. A key can be held or let
    go between moves, given as ("hold", key, caption) or ("let_go", key)."""
    yield from c.move(c.object(obj, hover))
    yield from c.wait(0.6)
    x, y = c.kneady_button(obj, region, button)
    yield from c.move((x, y))
    yield from c.wait(0.4)
    yield from c.press()
    yield from c.wait(0.1)
    for move in moves:
        if move[0] == "hold":
            yield from c.hold(move[1], move[2])
            yield from c.wait(0.15)
        elif move[0] == "let_go":
            yield from c.let_go(move[1])
            yield from c.wait(0.15)
        else:
            dx, dy, seconds = move
            yield from c.move((x + dx, y + dy), seconds)
    yield from c.wait(0.1)
    yield from c.release()
    yield from c.wait(0.7)
