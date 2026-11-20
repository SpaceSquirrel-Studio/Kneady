# Changelog

## 1.0.0 (unreleased)

The first release.

- Regions: faces of a mesh, a whole object, or faces a face attribute
  marks. Painted when hovered, with Show Through for regions hidden inside
  something else, which holds the hover a few pixels past its edges.
  Highlight: Outline draws each region's border and its edge against the
  view instead, in the same colors, at a width you choose; where two
  regions meet, each one's color shows on its own side of the line.
- Up to eight buttons per region, arranged in a row, column, grid or circle,
  each with arrows, an image or a modeled shape for its icon, or its name
  as a text button. Arrows from the button's drags, or a set chosen from
  ten. A button is a circle or a square with rounded corners, to tell kinds
  apart. A region's buttons in its color, or one of their own. Button
  names under the circles, in a box bordered in the button's color: on
  hover, always, or off. A name with a button under it goes beside its
  circle, and buttons one under another keep their names on one side, so a
  column's names all sit to its side.
- Toggle buttons: a click switches a boolean, or a number between 0 and 1
  such as an IK / FK switch, and the button stays lit while it is on. The
  spot clicked keeps its region hovered until the mouse moves off it. A
  toggle can set a value of its own instead, lit while the property holds
  it, so several make a choice: a rig's IK parent, Root, Torso, Chest or
  Shoulder, the hand kept where it is as it changes.
- A drag button can switch something with a click too (Click Switches):
  a drag on it runs its commands, a click switches, and the button stays
  lit while on. On a button that opens a menu, opening the menu switches it
  on and closing it with the button or Esc switches it off.
- Gaps: a button that holds a place in a row or a ring and shows nothing,
  to space the others; dashed in Viewport Edit.
- Shift+click on a button pins its region, hovered wherever the mouse goes
  and the only one painted, until a Shift+click on one of its buttons again
  or Esc.
- Viewport Edit: a click on a button in the viewport selects it in the tab,
  having done what it does; Ctrl+click only selects it. The last region
  hovered stays while the mouse goes to the tab, and the button being
  edited is marked in the viewport. Icons at the corners of the buttons add
  and remove one, Rearrange drags them into another order, and Place on
  Surface drags them onto the item.
- Commands for each drag direction, up to sixteen at once, any of them
  removable:
  - Rotate, Move and Scale of an object or bone, following the mouse - along
    its own axes, or the view's: View moves it with the mouse as G does and
    turns it as R pressed twice does; Depth moves it toward you or rolls it.
    Follow the Mouse can be turned off, for commands that go different ways
    at once (fingers spreading).
  - Geometry Nodes modifier inputs
  - any property by its data path, added to or multiplied - the item's shape
    keys and custom properties - on a rig, its pose bones' too, where an
    IK / FK switch lives - listed to pick, and a path copied from a shape
    key or the mesh taken as it is

  Commands on one value add up, so the same commands on both directions
  drive it whichever way the drag goes.
- Beyond the row, made in the panel and played: buttons placed on the
  item, 3D handles - arrows, double arrows, quad arrows, rings, or a mesh
  object's shape - dragged along their direction in the scene or around a
  ring (a Move or Rotate following the mouse), menus built under a button
  (Shift+click pins one, Esc closes it; copied and pasted, sub menus
  included), buttons shown while a switch is on or off, toggles that keep
  the pose as they switch, and a rig's operator on a click. A button on
  the item stays on its surface as it is posed - on a rig whose controls
  aren't what deform the mesh (Rigify's FK forearm while the arm is in IK)
  it rides the bone that does.
- Copy and paste a region's buttons, or one button, onto another region,
  in the same file or another.
- A region's buttons are a list like the region list: + and - add and
  remove them, the arrows reorder them, and the selected one's settings
  show under it.
- Dragging: one direction at a time with Alt to switch, Shift for fine
  control, Ctrl to snap, numbers typed during the drag, values in the
  Adjust Last Operation panel afterward. Every button hides while a drag
  runs.
- Undo: a pick from a search field - an input, a bone, a modifier, a vertex
  group - is its own undo step, so undoing a test drag keeps it.
- Object mode and Pose mode. Auto Keying with Blender's keying settings.
  Transform locks respected.
- Reasons shown when something can't move: locks, drivers, constraints, IK
  chains, missing bones or inputs, linked data. A warning when a drag moves
  nothing.
- Starting from a rig: a new region turns the bone last clicked in Pose
  mode. Select Faces of \<bone\> finds its faces from the vertex groups.
  Use \<Rig\> and Use \<bone\> point a command in one click.
- Regions survive saving, appending, duplicating and library overrides.
  Make Them Regions recovers the regions of joined objects. A file whose
  controls a newer Kneady made opens safely: those objects are left exactly
  as they are, unused, with a note saying so, until Kneady is updated.
- An error Kneady catches so you can keep working is printed once to
  Blender's console with its details, for a bug report.
- Other tools' handles over a region work: another add-on's gizmo lying
  over a region takes the mouse before the region does, though never
  before one of its buttons. An add-on can say where its handles are, and
  over them the item they belong to stays hovered, its menu open, and the
  item beneath does not light up. While an add-on's handle is dragged,
  Kneady draws nothing; an add-on can hide its handles while a Kneady drag runs.
- Add-ons can give a kind of command of their own, chosen beside Modifier
  Input and Property for what a click switches, with its own settings. An
  add-on can keep the region its button was clicked on hovered while what it
  showed is up, and is told when Esc lets it go.
- Add-ons can give a kind of command a drag drives, too, written its own way
  and reading the modifier keys it needs; along a 3D handle it follows the
  mouse.
- Add-ons can add to the tutorial panel - a strip under the clip, a button
  on it, words under it, controls in the clip's place for a while, a frame
  of the clip to show - and rows to the tutorial editor.
- Anchors: a placed button or handle can sit at a point it follows - a
  bone's head or tail, the object's origin, or a point an add-on gives -
  instead of on the surface. Where handles overlap, the nearest takes the
  press.
- A menu can Stay Open: a click pins it, and a click in empty space closes
  it, as Esc does.
- A Move of an object can go along its Location channels instead of its own
  turned axes.
- 3D handles: an arrow, or a box on a shaft for a scale, each Short,
  Medium, Long or Extra Long and from its place or centered on it; each
  handle's own size, opacity, color, interior color and interior opacity
  (0: its edges alone), shaft falloff (fading from near its head toward
  its root), color under the mouse, and what shows of
  it behind the item (ghost, hide or show - as its region, or its own),
  and a Handle Size
  apart from Button Size, with a Halo: a thin dark edge round their lines.
  Their own color can be the theme's X, Y or Z axis color. A faded shaft
  takes a press only where it shows; a head, a few pixels past its outline. An arrow's head is a flat triangle with some
  depth, a box square to what it rides, a shaft one solid line in the
  handle's color; their edges are drawn smooth.
  Viewport Edit's icons sit clear of the handles a menu shows.
- Hovering is quicker: what is under the mouse, a region's buttons on screen
  and an add-on's anchors are worked out once a frame, not once for every
  region - with a menu of 3D handles open, a mouse move went from over half
  a second to under 10 ms.
- Hints in the status bar, with Blender's key icons: what a drag and a click
  do where the mouse is, and the keys that change them; a key held makes
  what it does stand out, during a drag too, and lights the handles a drag
  would move with it. An add-on's drags give their own.
- Tips: rest the mouse on a button and its tip shows under its name - a row
  for each drag and click saying what it does there, then a message from
  the layout's author. Kneady words each row from the button's commands;
  the author can reword a row, hide or show it, and write the message, in
  the button's Tip settings. The status bar says the same rows in the same
  words. Blender's own tooltip, the
  drag's description, no longer shows beside them; Viewport Edit's icons
  keep theirs.
- Help: how much Kneady tells you - Learn, every tip complete; Inform, the
  tips; Quiet, none, the names and the status bar still showing. Yours, not
  the file's: it stays the same in every file. Under the Kneady button at
  the top of the tab, and in a dropdown beside its icon in the viewport
  header.
- Tutorials, started from the top of the Kneady tab at Help's Learn. Each plays in a panel
  down the 3D view's left side: short clips of the gesture and still images
  - a step's own, or a set shared by every step without its own, which plays
  on from step to step - the step's text with each one's paragraph lit, and
  Back, Reset and Next, each new step flashing in. The clip grows to twice
  its size while the mouse rests on it. Pause and Loop under the clip, for the
  one showing;
  a clip can stay on its last frame when it has played (Hold at End). A
  tutorial's playlist shows as a QR code behind a phone button, to watch the
  whole tutorial on a phone. The fields a
  step is about light up in Kneady's own panels, and a step ticks itself off
  when it's done, moving on to the next half a second later; the last says
  Completed! A tutorial with a practice scene opens a copy of it, after
  Blender asks to save your file, and Return to My File takes you back.
  Clips and images ship with a tutorial, or are hosted online and downloaded
  in the background when it starts, then kept - only while Blender's Allow
  Online Access is on, each checked against its fingerprint. A clip that
  can't be shown can offer Watch on YouTube instead. Edit mode, the pencil beside the
  menu, makes, changes and deletes them in the same panel, the tutorial's
  panel over the view showing each change as it is made; one started with
  edits not saved yet asks to Save and Play or Play Saved Version. A clip's
  Trim, typed in its settings, is the frames that play, and says what it
  keeps. The Tutorials panel folds away by its header. Build a Menu shows
  how to give a button a menu, add buttons to it and choose how they look,
  its clips made by script (dev/clips), so they follow the interface as it
  changes. Kneady starts at Help's Learn, so the tutorials are there from
  the first; tutorial 0, Learn, Inform and Quiet, shows each level - a tip
  complete, shorter, or none, and the tutorials offered or not - so the
  first thing learned is how to have Kneady say less. Quick Start, 1, starts
  from Blender's default scene: a region on the cube, and a button dragged.
  Change the Default Controls
  follows it: the button's own commands, a slide and a grow, at a speed
  chosen. Drive More Than Bones: a shape key, a modifier input, two
  commands on one drag, and Alt to switch mid-drag. Build a Menu gives a
  button a menu; Menus in Use pins it, keeps it open, and puts a menu
  inside it. Toggles and Show When switches a Rigify arm between IK and FK
  and shows each mode's buttons only in it. The Look of Your Buttons lines
  them up in a column, shows their names, makes one a word, squares them,
  and outlines the region. Buttons on the Item puts one on the arm, drags it
  into place, and shows it riding the pose and seen from behind. 3D Handles
  makes it a Quad Arrow dragged along an arm, and a turn a Ring swept
  around. Viewport Edit, on a whole figure, picks a button where it shows,
  adds one and rearranges the row, and removes a menu with Ctrl+click and -.
  Copy and Reuse pastes one button's commands onto another, tucks a button
  into a menu with Move To, and gives a region another's buttons. Tips for
  Your Buttons reads a tip, words its drag row, adds a message, and sets
  Help. Write a Tutorial, the last, makes one in Edit mode - a step, a
  check that ticks it off - and tries it; Try pressed inside a tutorial's
  practice scene keeps Return to My File for the one it plays, and a step
  can light the editor's own fields. The tutorials are numbered, from 0
  when a source's first has order 0. Writing one: docs/TUTORIALS.md.
- Tutorials come with Kneady, with any add-on that has a `kneady_tutorials`
  folder, and with files: a tutorial attached to an item - a rig, say -
  carries its clips and images in the file, and goes wherever the item goes,
  appended or linked into another file. The menu lists each under where it
  comes from; a file's own show at Inform too, as Tutorials in This File.
  Several tutorials can share one practice scene.
- Button Size slider. Scales with Blender's Resolution Scale.
- Blender 4.2 and newer.
