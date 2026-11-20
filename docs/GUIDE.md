# Kneady guide

Kneady puts controls directly on the surface of a mesh. You divide the mesh
into **regions**, which are groups of its faces or the whole object. Each
region has **buttons**, and each button has **commands** that say what
happens when you drag up and down or left and right. To use the controls,
hover over the mesh and drag.

This guide describes each part in the order you are likely to need it.

- [Turning Kneady on](#turning-kneady-on)
- [Regions](#regions)
- [Buttons](#buttons)
- [Commands](#commands)
- [Dragging](#dragging)
- [Posing and keying](#posing-and-keying)
- [Notes for common rigs](#notes-for-common-rigs)
- [Beyond the row: placed buttons, 3D handles and menus](#beyond-the-row-placed-buttons-3d-handles-and-menus)
- [Tutorials](#tutorials)
- [Files, copies and linked characters](#files-copies-and-linked-characters)
- [Modifiers](#modifiers)
- [Large meshes](#large-meshes)
- [Limits](#limits)
- [Troubleshooting](#troubleshooting)

## Turning Kneady on

Kneady is in the 3D Viewport's Sidebar (press N), on the **Kneady** tab.
The **Kneady** button at the top of the tab turns it on and off. You can
also use the Kneady icon on the right side of the viewport header. Kneady
works in Object Mode and Pose Mode.

**Help**, below the Kneady button, sets how much Kneady explains as you
work. There are three levels:

- **Learn:** The default. Tips show every drag and click a button responds
  to, plus the keys that work on every button: Ctrl to snap, Shift for
  finer steps, Alt to switch direction, and Shift+Click to pin. The top of
  the tab also lists the tutorials (see [Tutorials](#tutorials)). The first
  one, "0. Learn, Inform and Quiet", demonstrates all three levels.
- **Inform:** Tips show what each drag and click does and what the button
  is for. The keys that work on every button appear only in the status
  bar.
  The tutorial menu isn't shown, but tutorials saved in the open file
  still are.
- **Quiet:** No tips and no tutorials. Button names and the status bar
  still appear.

Help is a personal setting, not part of the file. Kneady stores it in
Blender's configuration folder, so it stays the same in every file you
open, including files made by other people. The small arrow next to the
header icon gives you the same two settings: Kneady on or off, and Help.

**Button Size** sets the size of the button circles, from small to large,
for all of Kneady. It
also follows Blender's Resolution Scale preference, so buttons keep the
same apparent size on high-resolution displays.

**Labels** sets when button names are shown. Each name appears in a small
box with a thin border in its region's color.

- **On Hover:** The default. Only the name of the button under the mouse is
  shown, and nothing else moves.
- **Always:** Every button's name is shown, and the circles are spaced out
  to make room. This is useful while you are learning a character's
  controls, and for screenshots.
- **Off:** No names are shown. At the Learn and Inform levels, a button's
  tip still gives its name and what it drives.

Names are never left out for lack of room. Kneady places each name where
it covers as few other buttons as possible. A name normally sits under its
circle. If another button is there, the name moves to the right of the
circle (or the left, if that side is taken too), or above it. When a button is surrounded
on all sides, its name is drawn over the lower half of the button itself.
In a column, the top button's name goes above it, the bottom button's name
goes below it, and the names in between go to one side. In an open menu
with three or more buttons around it, the button that opened the menu
shows no name, which keeps the ring compact. The other names in the ring
sit on its outside.

At the Learn and Inform levels, resting the mouse on a button for half a
second shows its tip: what each drag and click does, and what the button
is for. See [Tips](#tips).

**Highlight** sets how the regions of the hovered object are drawn. Each
region uses its own color and opacity, and the region under the mouse is
drawn brighter than the others.

- **Fill:** The default. Each region is painted over its faces.
- **Outline:** Each region is drawn as an outline, along its border with
  the rest of the object and along the edges where the surface turns away
  from view. **Outline Width** sets the line thickness in pixels (6 by
  default, from 2 to 16). Where two regions meet, the line is split down
  the middle, so each half shows its own region's color. A region with
  Show Through turned on has its outline drawn on top of anything in front
  of it, the same as its fill.

While a region is pinned, it is the only region drawn.

## Regions

When you select a mesh, the Kneady tab shows a tree for it, similar to the
Outliner. The regions are the top-level rows. A region's buttons are listed
under it, and the buttons in a menu are listed under the button that opens
the menu. A row that contains other rows has a triangle to expand or
collapse it, and all rows start collapsed. Below the tree are the settings
of the selected row, which is either a region or a button.

The buttons next to the tree work like those of Blender's other lists:

- **+** adds a button under the selected row. With a region selected, the
  button is added to that region. To add a region, use **Add Region** in
  the **Copy / Paste** menu (the down arrow below **-**). When the object
  has no regions yet, **+** adds a region.
- **-** removes the selected row. Removing a region also removes its
  buttons, and removing a button also removes the buttons in its menu.
  Kneady asks for confirmation before removing a region, or a button that
  has a menu.
- The arrows move the selected row up or down among its neighbors: a
  region among the regions, or a button among the buttons next to it.
- Double-click a name to rename it.

Removing a region also clears it from its faces.

### Which faces

A region can get its faces in one of three ways:

- **Faces you assign:** Click **Edit Faces** to enter Edit Mode with face
  selection. Select faces, click **Assign**, then click **Done** to return.
  **Remove** takes the selected faces out of the region. **Select** and
  **Deselect** select or deselect the region's faces, as they do for vertex
  groups. While Kneady is on, the regions are shown in Edit Mode, with the
  active region drawn stronger.
- **The whole object:** **Whole Object** gives the region every face of the
  object that is not in another region.
- **A face attribute:** This is for meshes generated by Geometry Nodes,
  whose faces can't be assigned by hand. Enter the name of an integer or
  boolean face attribute in **From Attribute**, and set **Value** to the
  value the attribute has on the region's faces.

### Faces from a rig

For a mesh that is deformed by a rig, Edit Faces offers two shortcuts:

- **Select Faces of \<bone\>** appears when the region's first button
  rotates a bone. It selects the faces that bone deforms, found by the
  names of the mesh's vertex groups.
  - A deform bone uses its own vertex group.
  - A control bone uses the groups of its deform bones. For example,
    Rigify's `forearm_fk.L` uses `DEF-forearm.L` and `DEF-forearm.L.001`,
    and Auto-Rig Pro's `c_forearm_fk.l` uses `forearm_stretch.l` and
    `forearm_twist.l`.
  - A limb that is split into segments is selected as a whole, including
    the seams between the segments.

  The report at the bottom of the window lists the groups that were used.
  If none are found, choose a group by hand.
- **A vertex group field and Select Faces** select the faces that are
  mostly weighted to the group you choose.

Both shortcuts add to the current selection. Click **Assign** to add it to
the region.

A new region on a rigged mesh starts out rotating the rig's **active bone**
(the bone you last clicked in Pose Mode), and is named after that bone. If
no bone is active, it rotates the object, as on any other mesh.

### How it looks

- **Color** and **Opacity** set how the region is drawn. When you hover an
  object, the region under the mouse is drawn at its opacity, and the
  object's other regions are drawn fainter.
- **Show Through** is for a region that is hidden inside something else,
  such as a joint tucked into the next part. Once you hover its object, you
  can hover this region too, and it is drawn on top of whatever covers it.
  It stays that way until the mouse moves onto something else.

  A region like this often shows only as a thin sliver, such as a cap seen
  past the part it is tucked into, so Kneady gives it some extra room:
  - It stays hovered until the mouse is a few pixels past its edge, which
    makes its buttons easy to reach even where it is thin.
  - If the mouse leaves the object within a few pixels of the region, the
    hover goes to the region rather than to whatever is next to it.
  - Moving onto it from the rest of its object takes effect immediately.

## Buttons

A region can have up to eight buttons. They are the rows under the region
in the tree.

- With the region selected, **+** adds a button after the others.
- With a button selected, **+** adds a button to that button's menu and
  turns on its **Opens Menu** setting. This works for any of the region's
  own buttons and for any button in a menu. A button in a sub menu can't
  open a menu of its own, so there **+** adds the new button next to it, in
  the same sub menu.
- **-** removes the selected button, along with the buttons in its menu.
  If it has any, Kneady asks first.
- The up and down arrows move the selected button. This also changes where
  its circle appears in the row, column or circle.
- Double-click a name to rename it. The selected button's settings are
  shown below the tree.

When the region's row is selected, its settings end with **Its Buttons**,
which holds **Arrange** (described below) and **Override Color**. All the
buttons in a region have the same color, which is normally the region's
color. Turn on Override Color to pick a different one in the color swatch
next to it, which starts at the region's color. The buttons' outlines,
arrows, hover fill and name borders all use this color, and so do 3D
handles. If you turn the setting off and on again, the color you picked is
kept.

When you hover the region, its buttons appear as circles in the middle of
it:

- Dragging from a circle runs that button's commands. Clicking a toggle's
  circle switches it (see [Toggles](#toggles)).
- Dragging anywhere else on the region runs the first button that drags,
  skipping toggles. This button is marked with a pointer in the tree. To
  change which button a drag on the region runs, move a different drag
  button above it.
- A narrow band around the circles also counts as part of the region, so
  you don't lose the hover as you move between circles.

**Arrange** sets how the circles are laid out:

- **Row:** Left to right.
- **Column:** Top to bottom.
- **Row + Column:** From four buttons up, two columns filled in rows of
  two. With an odd number, the last button is centered above the others.
  For example, five buttons make two rows with the fifth on top, and eight
  make four rows.
- **Circle:** Around a ring, starting at the top and going clockwise.

Each button has these settings:

- **Name:** Shown under the circle and in the tip (see Labels in
  [Turning Kneady on](#turning-kneady-on)). The eye icon next to it hides
  the button's circle.
- **Drag**, **Toggle** or **Gap:** What the button does. A drag button runs
  its commands while you drag. A toggle switches something on or off when
  you click it. A gap shows nothing and only holds a place in the row or
  in a menu's ring, to space out the buttons around it. For example, two
  gaps in a ring of four let you put the other two buttons exactly where
  you want them. Viewport Edit shows a gap as a dashed circle, so you can
  select it and move it.
- **Icon:** What the circle shows.
  - **Arrows:** With **From Drags**, an arrow is drawn for each direction
    the button drives, curved for a rotation and straight for anything
    else. You can also choose a set: Left and Right, Up and Down, Four
    Ways, curved versions of these, Diagonal, Outward (four arrows pointing
    to the corners, for scaling up) or Spin (arrows around a circle, for a
    twist). A toggle shows a ring, with a dot in it while it is on.
  - **Image:** Any image.
  - **Object:** The faces of a mesh object. Model it flat, facing any view.
  - **Text:** The button's name in a rounded box instead of a circle. The
    box is as wide as the name and about as tall as its letters. A region
    can mix text buttons with icon buttons, and the row makes room for
    each.
- **Shape:** Below the icon. **Circle**, or **Square**, which is the same
  size with rounded corners like a text button's box. Use it to tell kinds
  of buttons apart at a glance, for example square toggles and round drag
  buttons. The whole square responds to clicks, including its corners. A
  text button always uses the box around its name.
- **Drags Prefer Single Direction:** On by default. Once a drag has moved
  a few pixels in one direction, it drives only that direction, so only
  one thing changes at a time. See [Dragging](#dragging) for switching
  directions with Alt.
- **Left / Right** and **Up / Down:** A command for each drag direction.
  Check a direction to use it. Each direction you turn on gets its own
  section. Collapsing it with the arrow on its left hides the commands but
  leaves the direction on.
- **Tip:** The last setting. What the button's tip says (see below).

### Tips

When you rest the mouse on a button for half a second, its tip appears
below its name. Every tip uses the same layout:

```
 Drag ↕          Curl
 Drag ↔          Spread
 Click           More controls: Move, Length, Sides
 Shift+Click     Keep these controls up
 ─────────────────────────────────────
 Bends the finger at its knuckle.
```

- **One row per input.** The left column shows the key or mouse action,
  and the right column shows what it does on this button. Kneady fills in
  both from the button's commands. "Drag ↕" is Up / Down and "Drag ↔" is
  Left / Right. A 3D handle has a single **Drag** row (**Drag around** for
  a ring). When one drag drives several things, the tip sums them up: four
  sides of one end become **Sides**, and both ends become **Start and End
  Sides**. A button that opens a menu lists the first few buttons in it. A
  key held during a drag is written after it, as in **Drag+Alt**. This is
  because with Maya-style navigation, holding Alt before you press orbits
  the view, so you press Alt once the drag has started.
- **The author's message** appears below a line and says what the button
  is for.

The drags and the click are always shown. At the Inform level, the keys
that work on every button (Ctrl to snap, Shift for finer steps, Alt to
switch direction during a drag) are hidden, since they would be repeated
on every tip and soon ignored. Shift+Click to pin is hidden too, except on
buttons that open a menu. At the Learn level these rows are shown as well,
unless the author has hidden them. If a tip would only repeat the button's
name, no tip is shown. The status bar always lists every key, in the same
words. Blender's own tooltip doesn't appear over Kneady's buttons, since
the tip replaces it, but it still appears over the Viewport Edit icons.

To write a button's tip, expand **Tip** at the end of its settings:

- Each row shows its key, followed by a field with Kneady's description in
  gray. Type your own text, such as "Curl" for a Rotate X, and the row uses
  it in both the tip and the status bar. Clear the field to go back to
  Kneady's text.
- The eye icon next to a row shows or hides it in the tip.
- The field below the rows holds the message.

The key itself can't be edited, because it comes from the button's
commands. That way the tip stays correct when the commands change. Your
text is stored with the row it belongs to (a drag direction, or the
click), so reordering or adding commands keeps it. If you remove a command
and add it back, its row gets your text back. Copying and pasting a button
includes its tip. **Paste Commands** brings over the rows' text, since it
describes the commands, but leaves the message as it was.

### Toggles

A **Toggle** button switches something on and off when you click it, and
its circle stays lit while it is on. Under **Click Switches**, choose what
it switches: a **Modifier Input** (a boolean or a number) or a
**Property**, given by its data path.

- A boolean switches between off and on.
- A number switches between 0 and 1. Typical uses are a rig's IK/FK
  switch, a visibility factor, or a constraint's influence.
- **Invert: Lit at 0** lights the button when the value is 0 instead.
- **Sets a Value**, together with the value next to it, makes the button
  one of several choices. Clicking it sets that value, and the button is
  lit while the property has that value. For example, a rig's IK parent
  switch (0 Root, 1 Torso, 2 Chest, 3 Shoulder) can be four such buttons,
  often in a menu. Clicking the button that is already lit does nothing.
  If the hand control is in Keep Pose's Keep list, the hand stays in place
  as its parent changes.
- **Add Command** lets one click switch several things. The first command
  decides whether the button is lit.

If several objects share the region and the toggle drives the hovered
object (Deform Hovered Object), the circle shows the state of the object
you are hovering. Each click is one undo step, and Auto Keying keys
whatever was switched. As with any button, pressing and then dragging off
the circle doesn't switch anything. If the switch changes which buttons
are shown, the spot you clicked keeps its region hovered until you move
the mouse away, so a different region under that spot can't take over the
hover.

### Copy and paste

The **Copy / Paste** menu next to the tree (the down arrow below **-**)
has these options:

- **Copy Button** and **Paste Button** copy the selected button, and paste
  it over the selected button.
- **Copy Commands** and **Paste Commands** copy only what a button drives:
  whether it is a drag button or a toggle, the commands of each direction
  or of its click, and any operator its click runs. The button you paste
  onto keeps its name, icon, shape, position and menu.
- **Copy All Buttons** copies all of a region's buttons, the menus they
  open, and how they are arranged. **Paste All Buttons** puts them on
  another region, replacing its buttons. The region you paste onto keeps
  its own name, faces, color and opacity.

The copy goes on the system clipboard, so you can paste it into another
Blender file. In that file, targets are matched by name: a command that
drives the `Lower` bone of `ArmRig` drives that file's `ArmRig`, if it has
one.

### Viewport Edit

**Viewport Edit**, at the top of the tab, lets you edit buttons directly
in the viewport, where you can see them:

- Clicking a button does what it normally does (a toggle switches, a menu
  button opens its menu) and also selects its row in the tree, expanding
  its parent rows. Its settings appear below the tree.
- **Ctrl+Click** selects a button without doing anything else, so you can
  edit a menu button without opening its menu.
- Clicking a region's faces selects the region's row.
- Icons appear just outside the corners of the square around the hovered
  region's buttons (its row, or the open menu):
  - At the top right, **+** adds a button to the ones shown and selects it.
    **-** next to it removes the selected button, along with the buttons
    in its menu. It only appears while the selected button is one of those
    shown.
  - At the top left, a grip of six dots turns **Rearrange** on and off. It
    is blue while on. The same toggle is in the tab, below Viewport Edit.

  The icons stay in place while you add, remove and rearrange buttons, and
  only move outward if the buttons would reach them. The whole square, out
  to the icons, keeps the region hovered, so you can move the mouse to
  them.
- With **Rearrange** on, dragging a button in the row or in a menu's ring
  picks it up instead of running its commands. The button follows the
  mouse, and the other buttons move aside as it passes them: along a row
  or column, across a grid, or around a ring or circle. Release to keep the
  new order as one undo step, or press Esc to put it back. This is the same
  order the tree shows, and that its arrows change. Clicks still work as usual, so you can open a menu
  and rearrange what is in it. Buttons placed on the item stay where they
  are, and a menu's own button stays in the center of its ring. Moving a
  different drag button to the front changes which button a drag on the
  region runs.
- **Right-clicking** a button or a region opens a menu of what you can do
  with it: copy and paste the button, its commands, or all of the region's
  buttons, the same as in the menu next to the tree. Elsewhere, right-click
  works as usual.
- The last region you hovered stays hovered, with any menu in it still
  open, while you move the mouse across empty space to the Sidebar.
  Hovering another region switches to that one.
- The button selected in the tree has a dashed ring around it in the
  viewport, whether you picked it there or in the tree, so you can see
  which one you are editing.

## Commands

A command says what one drag direction drives.

Each command starts out collapsed to a single line, which shows what it
drives: the input (which you can change on that line), the property path,
or a short description of the rotation, move or scale, such as **Rotate X
on Upper**. A warning icon on the line means the command can't run with
its current settings. Expand it to see why. Click the arrow to see the
rest of its settings.

**Drives:**

| Kind | What it does |
|---|---|
| **Rotate** | Rotates the target around one of its own axes, following the mouse. |
| **Move** | Moves the target along one of its own axes, following the mouse. |
| **Scale** | Scales the target along one axis, or **All** three. Dragging right or up makes it larger. |
| **Modifier Input** | Changes an input of a Geometry Nodes modifier, by name. Dragging right or up increases it. Leave **Modifier** empty to use the target's first Geometry Nodes modifier. **Input** lists the inputs shown in the modifier's panel. |
| **Property** | Changes any property, given by its data path. Dragging right or up increases it. To get a path, right-click a field and choose **Copy Data Path**. A custom property stays within its own minimum and maximum. |

Other add-ons can add a kind of command of their own, for things only that
add-on knows how to drive. It appears as a button below the Drives choice,
and may use modifier keys of its own, which the status bar lists. Click
the button again to go back to the Drives choice. Along a 3D handle, this
kind of command follows the mouse like a Move or Rotate. Elsewhere it
changes at its Speed.

**What it drives:**

- **Deform Hovered Object:** On by default. The command drives the object
  you are hovering.
- With Deform Hovered Object off, the command drives its **Target**. For an
  armature, also choose a **Bone**.
- If another add-on provides groups of objects, **Object** and **Group**
  options appear when Deform Hovered Object is off. With **Group**, the
  command drives whichever of the group's objects the drag is on (the
  add-on decides which), so one set of buttons can serve all of them.
- **Use \<Rig\>** fills in the armature that deforms the mesh.
- **Use \<bone\>** fills in that armature's active bone.

**How it moves:**

- **Axis:** X, Y or Z of the target's own axes, for a rotation, move or
  scale. A rotation or a move can also use the view:
  - **View:** A Move follows the mouse across and up the screen, as G does,
    whichever way the target faces. A Rotate turns the target as if the
    mouse were rolling it, as pressing R twice does. To move or rotate
    freely in one drag, give the button both directions and turn off Drags
    Prefer Single Direction.
  - **Depth:** A Move goes toward or away from you, and a Rotate rolls the
    target around your line of sight.

  Locked channels of the target don't change.
- **Location Channels** (object Move only): Moves the object along its
  Location channels, which follow its parent's axes, the same as typing
  values in the Item panel. Without it, the object moves along its own
  rotated axes.
- **Speed:** How far it goes for each 100 pixels of drag.
  - For a rotation, an angle.
  - For a move, a distance in scene units, regardless of the target's own
    scale. An FBX rig at a scale of 0.01 still moves the way you expect.
  - For a scale, a growth factor: 0.3 is about a third larger.
- **Ctrl Step:** The step that holding Ctrl snaps to.
- **Invert:** Drives it in the opposite direction.
- **Follow the Mouse** (Rotate and Move, on by default): The target moves
  the way the mouse moves, in any view. When it is off, dragging right and
  up drives it in the positive direction, and Invert reverses that. Turn it
  off for commands that should go different ways at the same time, such as
  fingers spreading apart.
- **Multiply** (inputs and properties): Multiplies the value instead of
  adding to it. Values driven together this way keep their proportions.

**Add Command** adds another command to a direction, up to sixteen per
direction.
That is enough for a fist, which curls twelve finger bones. A single drag
moves all of them, each at its own speed. For example, a drag can change
two shape keys together, or a bone and a material value. A new command
starts expanded so you can set it up. Once a direction has two or more
commands, each one has a trash icon to remove it, and removing the first
moves the next one up. To stop a direction from driving anything, uncheck
it.

If you give Left / Right and Up / Down the same commands, the value
follows whichever way you drag, which makes a button that scales the same
in either direction. When two commands drive the same value, their effects
add up (or multiply, with Multiply), so a drag that uses both directions
changes the value by both amounts.

A command that can't run shows the reason in red below it. Common reasons
are:

- a locked channel ("Its rotation is locked")
- a driver ("... is set by a driver")
- a name that no longer exists ("ArmRig has no bone Lower: renamed? Choose
  it again")
- a linked character that has no library override

If a constraint or an IK chain holds the result in place, it is named as
well. The drag still changes the channel underneath, which is useful for
when the constraint is turned off.

## Dragging

Hover over a region, press the mouse button, and drag:

- **Rotate and Move follow the mouse.** The surface under the cursor moves
  with it, whichever way the object faces.
- Hold **Shift** to slow the drag to a tenth of its speed.
- Hold **Ctrl** to snap to each command's Ctrl Step.
- Hold **Alt** to hand the drag to the other direction, when Drags Prefer
  Single Direction is on. Releasing Alt hands it back. Each direction keeps
  the change the other one made, so you can build up several changes in a
  single drag and a single undo step.
- Press **Esc** or right-click to cancel and put everything back.
- **Clicking** without dragging selects:
  - in Object Mode, the object (Shift+Click on the region adds it to or
    removes it from the selection)
  - in Pose Mode, the bones the button drives
- **Shift+Click** on a button pins its region. The region stays hovered,
  with its buttons shown, wherever the mouse goes. This helps with small or
  thin regions that are hard to stay on. To unpin it, Shift+Click one of
  its buttons again, or press **Esc**. The status bar shows when a region
  is pinned. Clicks elsewhere still go to Blender.

During a drag, the status bar shows what is being driven. When only one
direction is active, it also shows what holding Alt would switch to.

While you hover, the status bar shows what the mouse can do there, with
Blender's key icons:

- On a region's faces, which button a drag will run.
- On a button, its drag, its click (opening its menu, or going back), and
  Shift+Click to pin.
- On a 3D handle, its drag and the keys that change it, including Ctrl to
  snap and Shift for finer steps. Add-ons can list their own keys here.
  Digit's Side handles, for example, use Alt for both sides of an axis and
  Alt+Shift for all four.

Holding a key highlights what it does and dims the rest. This works during
a drag too, so you can see which mode is active even with Maya-style
navigation, where holding Alt before a click orbits the view. Over a
handle, holding a key also lights up the other handles its drag would
move. The hint disappears when the mouse leaves the 3D Viewport.

You can type a number during a drag to set an exact value, the same as
with G, R and S:

- Type digits and a decimal point. Minus flips the sign, and Backspace
  deletes.
- The number goes to the first command of the direction you are dragging.
  The other commands on that direction follow and keep their relation to
  it.
- Press Enter or release the mouse to confirm.

After a drag, the Adjust Last Operation panel shows the value each command
reached: degrees for a rotation, a factor for Multiply, or the value
itself for an input or property. Type in any field and the drag is redone
to match it, with the other commands following.

If the mesh under the mouse hasn't moved after a short drag, the status
bar says so. An IK/FK switch or a constraint may be holding what you are
driving. Some rigs blend IK and FK in ways no setting shows, so Kneady also
checks whether the surface itself has moved.

## Posing and keying

Kneady also works in Pose Mode. Select the armature and switch to Pose
Mode, then hover and drag the meshes it deforms as you would in Object
Mode. A click selects the bones the button drives, so their keys appear in
the Graph Editor and the Dope Sheet.

With Auto Keying on, whatever a drag changes is keyed on the current
frame. Kneady follows Blender's keying settings:

- **Only Insert Available** and **Only Insert Needed**
- **Visual Keying** and **Cycle-Aware Keying**
- **Replace** mode
- **Only Active Keying Set**, which keys only what the active keying set
  contains

If these settings prevent anything from being keyed, a warning says which
setting stopped it.

Transform channels you have locked in Blender stay locked, and the command
says so.

Each drag is one undo step, and so is each change to a region.

## Notes for common rigs

Most rigs switch an arm or leg between FK and IK with a custom property.
The simplest way to control this is with a [toggle](#toggles):

1. Set a button to **Toggle** and choose **Property**.
2. Turn off Deform Hovered Object and set the rig as the **Target**.
3. Paste the path of the rig's switch.

Clicking the button then switches the limb between IK (0) and FK (1), and
the button is lit in FK. To blend between the two instead, use a drag
button with a **Property** command on the same path. The property's own
range keeps it between FK and IK.

| Rig | Arm's IK/FK switch (left arm) |
|---|---|
| Rigify | `pose.bones["upper_arm_parent.L"]["IK_FK"]` |
| Auto-Rig Pro | `pose.bones["c_hand_ik.l"]["ik_fk_switch"]` |
| Rain (Blender Studio, CloudRig) | `pose.bones["Properties_IKFK"]["ik_arm_left"]` |

- **FK controls don't move the arm while it is in IK.** When Kneady can
  tell what holds them, as with Rigify, it names the constraint. When it
  can't (Auto-Rig Pro blends through helper bones), the status bar says
  that nothing has moved.
- **Auto-Rig Pro** locks some axes, such as the X and Y axes of an FK
  forearm. A command on a locked axis says so. Use Z instead.
- **Mixamo** characters are plain FK, so drive the `mixamorig:` bones
  directly. The 0.01 scale of the FBX rig is taken into account.
- **MPFB2** humans work with both their standard rig and a generated
  Rigify rig.
- **Shape keys**, on any mesh, use Property commands on the mesh itself
  (with Deform Hovered Object on), with a path such as
  `data.shape_keys.key_blocks["Smile"].value`. Copy Data Path gives only
  the part starting at `key_blocks`, so add `data.shape_keys.` in front of
  it. A shape key stays within its Range Min and Max.

## Beyond the row: placed buttons, 3D handles and menus

A button doesn't have to sit in its region's row. It can be placed at its
own point on the item, appear as a 3D handle, open a menu of more buttons,
or appear only while something is switched on. A toggle can also keep the
pose as it switches. To set these up:

- **Where a button shows** is chosen in its settings: **In Row** (**In
  Ring** in a menu), **On Item** or **3D Handle**. The icon in the
  button's row in the tree switches between the row and the item with a
  click.
- **Place on Surface** is how you position placed buttons. Turn it on
  below **Rearrange** in Viewport Edit, or with its icon at the top left of
  the buttons in the viewport. The region stays on screen while you drag
  its buttons onto the item, or back to the row. Blender's snapping
  applies, and holding Ctrl turns it on or off. **Done Placing** keeps all
  the changes as one undo step, and Esc undoes them.
- **A menu:** Turn on **Opens Menu** in a button's settings, then click
  **Add to Its Menu**. The menu's buttons are the rows under that button
  in the tree, and a sub menu's buttons are one level further in. **Copy
  Menu** and **Paste Menu**, in the tree's Copy / Paste menu, copy a menu
  and its sub menus to another button or region. **Move To** moves a
  button, together with its menu, somewhere else.
- **Show**, in a button's settings, sets whether the button is always
  shown, or only while a toggle in its region or a property is on (or
  off).
- **Keep Pose on Switch**, and an operator for a click to run, are in a
  toggle's settings.

These are ordinary settings, so scripts can set them too. The rest of this
section describes how each one works.

- **Placed buttons** sit at their own point on the item instead of in the
  row, and stay there as you orbit the view and pose the character. They
  follow the bone that the region's first button drives. If that bone is a
  control that doesn't move any of the region's faces (such as a Rigify FK
  forearm while the arm is in IK), they follow the deform bone that moves
  those faces the most. The region's **Behind** setting decides how a
  placed button looks when it is on the far side of the item: hidden (the
  default), faint, or shown normally. Where two placed buttons overlap, the
  nearer one is drawn on top and gets the click, and the other is drawn
  faint.
- **3D handles:** A placed drag button can also appear as a 3D handle.
  Unlike a button, a handle keeps its direction in the scene as you orbit.
  It can be:
  - an arrow, or a box on a shaft (for a scale), in **Short**, **Medium**,
    **Long** or **Extra Long**, either starting at the button's position or
    **Centered** on it (a box stays square to what it follows)
  - a double arrow, with a head at each end to show that it goes either
    way
  - a **Quad Arrow** or a **ring** (both described below)
  - the shape of a mesh object in the file, modeled pointing along +Y, like
    a bone's custom shape

  To use a handle, drag along it, whichever way it points on screen. When
  the handle points the way a Move or Rotate goes, the target follows the
  mouse exactly, as if you were dragging an empty. Any other command changes
  at its Speed. By default a handle points along what it drives: a Move's
  axis, the direction a Rotate moves the point under the handle, or
  straight out from the surface. You can also choose an axis for it. When a handle points
  straight at you, it dims and can't be dragged, but it stays visible so
  you know a control is there. Orbit the view to reach it. Its head (an
  arrowhead or a box) responds to a press a few pixels outside its
  outline. Its name is shown below it.

  A handle follows the bone the region's first button drives (or that
  bone's deform bone, as described above). So if a bone needs handles,
  give them a region of their own, or attach them to an anchor (see
  below). Toggles are always
  shown as screen buttons.

  These settings change how handles look:
  - **Handle Size**, next to Button Size, sets the size of all handles.
    **Halo**, next to it, gives their lines a thin dark edge, so they stand
    out against a light surface or a wireframe.
  - Each handle has its own **Size** on top of that.
  - **Own Color** gives a handle a color of its own, such as an axis color
    for a handle that moves along that axis. Pick a color, or choose
    **Theme X**, **Theme Y** or **Theme Z** to use the axis colors from
    Blender's theme (Preferences > Themes > User Interface). These are
    drawn the way Blender draws its own Move, Rotate and Scale gizmos, at
    60% strength at rest and full strength under the mouse, so the handles
    match the gizmos and follow any theme you have made easier to see.
    With Own Color on, the handle's edge is drawn slightly brighter than its
    color, as on buttons.
  - **Interior** and **Interior Opacity** set the fill. At 0 opacity the
    fill is transparent and only the edges are drawn.
  - **Opacity** sets the opacity of the whole handle.
  - **Shaft Falloff** fades the shaft from solid near the head toward the
    root. At 1 it is gone at the root. The two halves of a double arrow
    each fade toward the middle. Only the visible part of the shaft
    responds to a press.
  - **Hover Color** fills the handle with a color while the mouse is over
    it, with a lighter edge.
  - **Behind** sets how the handle is shown when something is in front of
    its head, either because it is inside the item or on its far side:
    **Ghost Behind** (faint, but you can still grab it), hidden, or shown
    normally. **As Region** uses the region's Behind setting.

  A placed button can also sit at an **anchor** instead of on the surface.
  An anchor is a point the button follows exactly as things move: the head
  or tail of a bone the region's buttons drive, the object's origin, or a
  point that an add-on provides for the objects it creates. On an object
  that doesn't have that point, the button isn't shown, since it would
  have nothing to drive. Where handles overlap, such as an arrow passing
  through a ring at the same anchor, the one nearest the mouse gets the
  press.

  A **Quad Arrow** is two double arrows crossing at the button's position,
  one for each of the button's directions. One arrow drives the Up / Down
  commands and the other drives the Left / Right commands, each pointing
  the way its commands go. A drag is split between the two arrows as they appear on
  screen, so a diagonal drag drives both. With Drags Prefer Single
  Direction on, it drives only the one you start along, and Alt switches
  to the other. An arrow that points at you dims on its own.

  A handle can also be a **ring** around the axis a Rotate turns on. Move
  the mouse around its center and the Rotate turns by the angle you swept,
  as with R. When the ring is seen nearly edge-on, it turns like a wheel
  as you drag along its rim. Only the ring itself responds to a press, so
  you can still reach the item through its middle.
- **Menus:** A button with a small circle at its upper right opens a menu.
  Click it to show the menu's buttons in a ring around it, with the other
  buttons hidden. Click it again to go back one level, press **Esc** to
  close the whole menu, or move the mouse off the item. Dragging the menu
  button still runs its own commands. **Shift+Click** opens a menu pinned,
  so it stays open wherever the mouse goes until you close it all the way
  or press Esc. Undo and redo leave it pinned. If the region was pinned
  before the menu opened, it stays pinned when the menu closes. A menu with
  **Stays Open** turned on is pinned by a normal click, and also closes
  when you click in empty space. This is meant for menus of 3D handles,
  which you often reach across other objects.
- **Buttons that come and go:** A button can be shown only while a toggle
  in its region, or a property, is on, or only while it is off. For
  example, an arm's FK buttons can appear in FK and its IK buttons in IK. A
  drag on the region runs the first visible drag button.
- **Keeping the pose:** A toggle can switch without the pose jumping, as
  in an IK/FK switch. Each bone in a list takes its partner's pose as the
  switch happens, and the IK pole is placed where the elbow or knee
  points.
- **An operator on a click:** A button can run a rig's own operator.
  Operators that open, save or run files or scripts, or change Blender's
  settings, are never run from a button.

The tree marks placed buttons and buttons that open a menu. A menu's
buttons can be given one color. A menu without its own color uses the
color of the button that opens it.

## Tutorials

When Help is set to **Learn**, the top of the Kneady tab has **Start a
Tutorial**, a menu of all the tutorials. Each tutorial's tooltip says what
it teaches. The menu isn't shown at Inform or Quiet.

A tutorial plays in a panel along the left side of the 3D Viewport, where
the toolbar usually is. The toolbar comes back when you collapse the panel
with its ^ button.

- The top of the panel shows short clips of the gesture, or still images.
  Use the arrows below them, or the dots, to move from one to the next.
  Between the arrows, **Pause** (or a click on the clip) pauses the clip
  that is showing, and **Loop** plays it over and over. A clip that has
  stopped on its last frame starts over when you press Play. **Show Me**,
  below a clip, opens the place it shows, either a Sidebar tab or a tab of
  the Properties Editor. Rest the mouse on a clip to see it at twice the
  size, over the text and the view, until you move the mouse away.
- If a tutorial has a playlist, a phone icon appears in its title row. It
  shows a QR code you can scan with your phone's camera to watch the whole
  tutorial there. Click the code to go back.
- Below the clips is the step's text. The paragraph that goes with the
  current clip is highlighted and scrolled into view. You can scroll the
  text with the mouse wheel.
- At the bottom are **Back**, **Reset** (which sets the step up again) and
  **Next**. A step that checks for what it asks you to do marks itself
  **Done** when you do it. Next turns blue, and half a second later the
  next step starts on its own. A step that was already done when you
  reached it waits for you to click Next. When the last step is done, the
  panel says **Completed!** Each new step flashes briefly, so you notice
  the change.

The fields a step is about are highlighted in Kneady's panels. If the
tutorial has a **practice scene**, Kneady opens a copy of it. Blender asks
you to save your file first, as it does before opening any file, and
**Return to My File** (or the panel's x) opens your file again. Nothing you
do in the practice scene is kept. Opening a file clears Blender's undo
history, so your earlier undo steps are not available when you come back.

Most clips and images are included with Kneady. Some tutorials keep theirs
online. These are downloaded when the tutorial starts and then kept, so
each one is only downloaded once. Downloading needs **Allow Online
Access** (Preferences > System), which is off in a new installation of
Blender. Until it is on, the panel says so where the clip would be, and
clicking there opens the Preferences. If a clip can't be shown, a **Watch
on YouTube** button may appear in its place, which opens the clip in your
browser. For a clip hosted somewhere other than YouTube, the button says
**Watch Online**.

To write tutorials, click the pencil next to Start a Tutorial to turn on
**Edit mode**. There you can create and delete tutorials and edit every
part of a tutorial and its steps. **Use Current** fills in a part from the
scene as it is now, and the panel over the view shows the tutorial as you
write it. A clip's Trim sets which of its frames play. Click **Save**, then
**Try** to play it. The [tutorial guide](TUTORIALS.md) has the details.

## Files, copies and linked characters

Regions are stored on the object. Which faces belong to which region is
stored in a face attribute on the mesh, `kneady_region`.

- **Saving and appending:** The regions stay with the mesh.
- **Duplicating:** Shift+D copies the regions along with the mesh. Alt+D
  shares the mesh's faces, but the copy has its own list of regions. A
  command that drives the hovered object drives whichever copy you drag.
- **Joining:** Blender keeps only the active object's region settings,
  but the joined faces keep their marks. The panel lists faces that carry
  regions the object doesn't have, and **Make Them Regions** turns them
  back into regions. You then set up their buttons again.
- **Renaming:** Renaming an object doesn't affect anything. If you rename a
  bone, modifier input or property that a command uses, the command still
  points to the old name and says so. Choose it again.
- **Linked characters:** Create the regions in the character's own file.
  Link the character into a shot and make a library override (Object >
  Library Override > Make). The override's mesh has the regions, and their
  commands drive the override's rig.

  Blender doesn't keep regions added to an override; they are gone when the
  file is reopened. For this reason, **+** doesn't work on a linked or
  overridden object (it tells you why), and the region settings are grayed
  out.

## Modifiers

Kneady reads regions from the mesh as it is displayed, after its
modifiers.

- **Subdivision Surface, Multiresolution, Mirror, Solidify, Bevel and
  Triangulate** keep every face's region.
- **Decimate** keeps the regions on the faces it keeps. Where it merges
  faces across a region's edge, the merged face takes the region of one
  side, so the region's edge can shift.
- **Remesh** creates new faces, so no regions are available while it is
  enabled.

Applying a modifier keeps the regions the same way the modifier did.

## Large meshes

- Hovering takes about 2 ms per mouse move on a mesh with a million faces.
- The first time you hover a very dense mesh, or the first time after it
  changes, Kneady prepares the region display. This takes about a second
  for a million faces, and a few hundredths of a second for a typical
  character.
- Edit Faces prepares its display when you enter it and after each
  Assign, not on every redraw.
- Regions aren't drawn during animation playback, so hovering an animated
  character doesn't slow playback down.

## Limits

- Regions can only be added to **mesh objects**. Curves, text and surfaces
  can't have regions, but a command on a mesh can drive them.
- A linked character's regions have to be made in its own file (see
  above).
- Remesh hides regions while it is enabled, and Decimate can shift their
  edges.

## Troubleshooting

- **Nothing is highlighted when I hover.** Check that Kneady is on, that
  you are in Object Mode or Pose Mode, that the object is visible, and that
  it has regions with faces assigned. The panel shows "No faces yet" for a
  region without faces.
- **Dragging does nothing.** Look for a message in red under the command in
  the panel, and check the status bar during the drag. The most common
  cause is dragging an FK control while the limb is in IK.
- **Kneady turned itself off.** Another add-on may include its own copy of
  Kneady. While that add-on is enabled, it turns this Kneady off and tells
  you, so the two never run at the same time. Your regions and buttons work
  the same in either one. This Kneady turns back on when the other add-on
  is disabled.
- **Paste Button or Paste All Buttons is grayed out.** Nothing of that kind
  has been copied yet. A copy made during this Blender session stays
  available to paste. A copy made in another Blender session is only on the
  system clipboard until something else is copied.
