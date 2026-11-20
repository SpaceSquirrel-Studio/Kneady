# Tutorial clips made by script

Kneady's own tutorials get their clips from scripts here, not screen
recordings. When Kneady's interface changes, run the script again and every
clip matches it. A clip that no longer does what its step asks says so.

```
python dev/clips/make.py dev/clips/build_a_menu.py            # every clip
python dev/clips/make.py dev/clips/build_a_menu.py 03_add     # some
python dev/clips/make.py all                                   # every tutorial's, in order
```

`all` runs every tutorial's script here in its tutorial's order and ends
with a summary: each tutorial made in full with every step done, or FAIL.
After an interface change, run it, then look over the clips the summary
passed - a step can be done while its clip looks wrong.

Any Python runs `make.py`; Blender's own will do. Set `BLENDER` to use another
Blender. A small window opens on the desktop while the clips play. It ignores
the real mouse, so the desktop stays usable, and it closes at the end. The
MP4s land in the tutorial's folder, named for their clips, and each clip's entry
in tutorial.json is tagged with the Blender and Kneady it was made in.

## What happens

- **`record.py`**, in a window:
  - It opens the practice scene and makes a 720 x 1280 window holding a copy
    of the 3D view, the Recording Window.
  - It starts the tutorial in the main window, out of the clips' sight.
  - It plays the clips in turn, each carrying on from the last, with
    Blender's event simulation. It screenshots every pass and keeps the time.
  - After each clip it reports whether the tutorial's step was done.
  - The mouse buttons and keys show live, as Screencast Keys shows them.
- **`finish.py`**, in the background:
  - It puts the frames at an even 15 a second by their times (half of 30:
    smaller files, the encoder's settings as they were).
  - It draws the cursor on, smoothly, along the path `record.py` kept, with a
    ring at each click.
  - It encodes H.264 MP4 with Blender's Video Sequencer and the Standard view
    transform, so colors are the screen's.

## A clip script

A script, `dev/clips/<tutorial>.py`, gives:

- `FOLDER`, `TUTORIAL`, `PRACTICE`: where the tutorial and its practice scene
  are.
- `SETUP(c)`: run unseen before the first clip, for example to open the
  sidebar's tab and frame the item.
- `CLIPS`: in order, `{"01_name": fn}`, where each `fn(c)` is a generator
  that drives `c`, a `Clip`.
- Helpers several scripts share go in a module of their own, listed in
  `make.py`'s `SKIP` so it isn't taken for a tutorial's script:
  `forearm.py` (the Rigify arm's Forearm: a resting spot clear of every
  button and handle, the view close on it, its 3D handles as Kneady draws
  them). `panel.kneady(c, "pick")` reaches any of Kneady's modules as the
  recorder loaded it - Viewport Edit's icons, say (`viewport_edit.py`).
- `BEFORE` (if needed): `{"01_name": fn}`, each run unseen just before that
  clip starts - the view centered again on something an earlier clip moved,
  say. Each clip is a video of its own, so it may begin from a new view.
- `TUTORIALS_PANEL = True` (if needed): the Tutorials panel shown in the
  clips' sidebar. It is kept out of them otherwise - the tutorial plays in
  the main window - but Write a Tutorial is about the editor inside it.
- `TEARDOWN()` (if needed): run at the end, whatever happened, to take away
  what the clips made outside Blender - Write a Tutorial's tutorials folder,
  a public one (`C:\Users\Public\Documents\Kneady Tutorials`), since the
  clips show its path and no one's name may be in it.

What a `Clip` gives (window pixels, from the lower left):

| | |
|---|---|
| `c.move(xy)`, `c.place(xy)` | the cursor eased there, or put there |
| `c.click()`, `c.rename_click()`, `c.drag(xy)` | a click; Ctrl+click (a list's rename); press, move, release |
| `c.key("TAB", "Tab")`, `c.type("Twist")` | a key with its caption; text typed, shown as the word |
| `c.hold("LEFT_ALT", "Alt")`, `c.let_go("LEFT_ALT")` | a key held across moves (Alt mid-drag), its name shown while held |
| `c.span(test, y)` | the ends of a row of buttons for one setting (X, Y, Z, All), to click one |
| `c.middle(test, xy)` | a field's true middle, found slowly: something measured from it (a search list) needs it |
| `c.shown_click(then)`, `c.silent_key("RET")` | a click shown but not sent, for what simulation can't click; a key sent unseen |

`panel.py` holds what scripts do in Kneady's panel - a command opened, a
Drives choice, an axis, a search field's suggestion, Add Command, a haul -
so each tutorial's script reads as its steps.
| `c.wait(s)`, `c.scroll(n, xy)` | time passing; the wheel |
| `c.object(name, local)`, `c.point(fx, fy)`, `c.in_region(fx, fy, "UI")` | where things are |
| `c.kneady_button(obj, region, index)` | where Kneady draws a button over the item |
| `c.find(path_or_test)`, `c.find_scrolling(...)` | a field or button in the sidebar, by what Blender names it: its data path, or an operator's Python command |
| `c.tree_row(owner, arrow=False)` | a row of Kneady's tree, or its fold arrow |
| `c.settle(test, what)` | Blender sure the mouse is on it, before a click that matters |
| `c.frame(names, fill, at)`, `c.sidebar("Kneady")` | the view framed; the sidebar's tab |
| `c.tab("Kneady")`, `c.click_tab("Kneady")` | where a tab is on the sidebar's edge; a click on it, shown, the tab opened by script |
| `c.unit` | Blender's interface unit in pixels: a row's height |

## Things learned the hard way

- **Blender notices where the mouse is a moment late.** A finder that moved
  and asked at once reported what it had just left, and a click went to the
  last thing it saw. So a find waits longer at its first spot, confirms what
  it found by resting there, and tries once more slowly if it missed. Clicks
  that matter `settle` first.
- **A rename that never started sends its letters to the view as
  shortcuts.** N hid the sidebar. Rename only after `settle`.
- **A list's rows all name the list's selection** (`kneady_row`). So rows are
  found from the list's top edge and Blender's row height, never by hovering
  their parts.
- **The sidebar overlaps the view**, so the view's region lies under the
  sidebar too. Ask the sidebar first.
- **A wheel turned over a sidebar too short to scroll goes on to the view and
  zooms it.** Scroll only when something shows at the sidebar's foot.
- **Event simulation sends no double-click**, so lists are renamed with
  Ctrl+click.
- **A popup doesn't close when a simulated mouse moves off it.** Click away
  to close it.
- **Popups can't be searched by hovering.** An enum's menu items and the
  color picker's wheel are reached by offsets measured from a frame, in
  `c.unit`, so they scale with the interface. **A confirm opens in the
  middle of the window**, wherever the click that asked for it was, so its
  button is an offset from there (`viewport_edit.confirm`). **A right-click
  menu opens with the item last chosen from it under the mouse**, so its
  items are found by looking instead: `panel.popup_rows` screenshots the
  window and reads the menu's box and rows of text from its back's color
  (`copy_reuse.py`, a sub menu too). `c.unit` is Blender's interface unit in
  the recording window - 25 px there, not 20 - so measure offsets in it.
  **A dropdown with no label of its own** (`text=""`) heads its menu with
  the setting's name, so its items are lower: `panel.choose(...,
  titled=True)`. **An operator's dialog opens with its first field under
  the mouse**: a click there edits it, all its text selected. Enter keeps
  what was typed and leaves the dialog open, so its OK is clicked, found by
  its blue under the field (`write_tutorial.ok_below`). The
  `layout.activate_init` that should make a dialog's field ready to type in
  did nothing for an operator's dialog here (5.2, simulated input).
- **A new window's sidebar shows its first tab.** Open the tab in `SETUP`,
  or show it being clicked (below).
- **The view orbits about its middle, which with Region Overlap on (the
  default) is under the sidebar's edge**, not in the part seen. A clip that
  orbits turns it off in `SETUP` (`preferences.system.use_region_overlap`;
  factory settings, so nothing is saved) and puts the view's middle on what
  it orbits (`on_item.py`). The view is narrower then, so `c.frame` frames
  the item smaller: set the view's distance instead.
- **A simulated click doesn't pick from a search field's list**, nor does
  Enter with the mouse resting on the item; Down and Enter do. The clip
  shows the click on the item while Down and Enter are sent unseen
  (`panel.suggestion`).
- **A quick find's middle sits low**: Blender names what the mouse has just
  left, so a run of hits reads on past its foot. Clicking it is fine;
  measuring from it is not - use `c.middle` first.
- **A simulated click doesn't open a sidebar tab**, and clicking down the
  tab strip to find one crashed Blender 5.2. A tab is found by looking:
  opened by script and the window screenshotted, then the tab before, and
  the stretch of the edge that lights up is the tab (`c.tab`). The clip's
  click on it is shown while the script opens it (`c.click_tab`).
