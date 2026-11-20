# Writing a tutorial

A Kneady tutorial plays in a panel along the left side of the 3D Viewport,
where the toolbar usually is. The top of the panel shows short vertical
clips of the gesture, or still images. The step's text is below them, and
Back, Reset and Next are at the bottom. When a step refers to something in
Kneady's own Sidebar tab, that part of the tab is highlighted live, so a
tutorial doesn't go out of date when the panel changes. A step can also
watch for what it asks the person to do and mark itself as done.

When Help is set to **Learn** (the default), the top of the Kneady tab has
**Start a Tutorial**, a menu of all tutorials. Next to it is a pencil icon
that turns on **Edit mode**, where you write tutorials. The editor is in
the **Tutorials** panel, which you can collapse by its header like any
Blender panel. Each window remembers this separately, so if you record the
Kneady tab in one window, you can keep the panel collapsed there while you
write in another.

## Writing one in the Kneady tab

1. Set Help to **Learn** and click the pencil next to Start a Tutorial.
2. Click **+** to create a tutorial, or use the dropdown to choose one to
   edit. The trash icon deletes the chosen tutorial (to the Recycle Bin on
   Windows). The folder icon chooses where tutorials are saved (see "Your
   folder" below).
3. Under **Tutorial**, fill in:
   - the title, and the summary shown in its tooltip
   - its order in the menu. Tutorials are numbered in the menu starting
     from 1, or from 0 if the first one has order 0. Order 0 is for a
     tutorial that comes before all the others, like Kneady's own "Learn,
     Inform and Quiet".
   - its practice scene. The file icon makes the open file the practice
     scene, saving a copy of it into the tutorial's folder.
   - where its media are hosted
   - its **Playlist**, for watching it on a phone (see "On a phone").
4. **Shared Media** holds clips and images for every step that doesn't
   have its own.
5. **Steps** is the list of steps, with + and -, and arrows to reorder
   them. For the selected step:
   - **Text:** Its paragraphs. The pencil next to a paragraph opens it in
     a larger box.
   - **Media:** The shared set, the step's own, or none. Each clip or image
     is either **Local** (included in the tutorial's folder) or **Hosted**
     (downloaded when played, see below). The folder icon next to its file
     chooses the clip or image and copies it to the right place. The line
     below it says where the file is and whether it will be included.
     **Hold at End** keeps a clip on its last frame once it has played, or
     keeps an image on screen.
     **Trim** sets which frames play (see "Trimming"). **Watch Link** is
     where the clip can be watched online, such as a YouTube Short, for
     when it can't be shown in Blender.
   - **Highlight:** Fields to highlight in Kneady's panels, including the
     Tutorials panel's editor. To add one, hover over the field, press
     Ctrl+Shift+Alt+C (Copy Full Data Path), then click the paste icon.
   - **Done When:** What marks the step as done. When the person does it,
     the tutorial moves on to the next step a moment later. Next also
     works. The eyedropper fills in a property's current value.
   - **Start:** What the step sets up. **Use Current** takes the mode, the
     selection, the view or the Sidebar tab from the scene as it is now.
6. Problems are listed under Save as you type. **Save** writes the
   tutorial. **Try** saves it and plays it from the selected step, in the
   open file. A step's Start changes that file's scene, and Ctrl+Z puts it
   back. If you click Try while a tutorial is playing in its practice scene
   (as in the Write a Tutorial tutorial), the one you are trying replaces
   it and keeps its Return to My File button. The panel shows your edits as
   you make them, but Start a Tutorial plays the saved version. If you
   start a tutorial that has unsaved edits, Kneady asks whether to **Save
   and Play** or **Play Saved Version**.

**Steps that ask for something.** A step can ask the person to drag or
click a Kneady button, hover a region, click a button in a panel, change a
field, or select an object. Set this under Done When, as one of these:

- **Action:** A Kneady button dragged or clicked, on a given region and
  object. Its How setting says Hauled, Clicked, or Hauled or Clicked. An
  action can also be any other operator, by its name, such as
  `object.mode_set`.
- **Hovered:** A region.
- **Property:** A property that reaches a value, or changes.
- **Mode**, **Active Object**, or what is **Selected**.

The step's Start sets up the scene so that the step can be done, and
Highlight points to the field it is about.

**Previewing as you write.** While Edit mode is on, the tutorial panel
over the view shows the tutorial you are editing, including unsaved
changes, at the step selected in the list. Its header says **Editing**.
When you type a paragraph, add a clip or change what a step highlights,
the panel and Kneady's own panels update a moment later. Selecting a step
in the list shows it in the panel, and **Back** and **Next** in the panel
select it in the list. Moving between steps this way doesn't set anything
up, so editing never changes your scene. Click **Reset** when you want to
set a step up and test its Start. A local clip or image is shown from your
computer, or "not recorded yet" if the file isn't there yet. A hosted one
plays from the copy on your computer, or is downloaded, so you can check
what you have put online. The eye icon next to Save hides the preview, as
does the panel's x. Try plays the tutorial for real, and the preview comes
back when it ends.

**Your folder.** Tutorials are saved in your tutorials folder. In a copy
of Kneady's repository, that is its own `tutorials/` folder. In an
installed Kneady, it is Kneady's folder in Blender's user files, which
updates leave alone. The folder icon chooses a different one. If you
change one of Kneady's own tutorials, a copy is saved in your folder,
along with its practice scene and media, and the copy is the one listed.

The rest of this page describes the files the editor writes, in case you
want to read them or write a tutorial by hand.

## A tutorial is a folder

```
tutorials/quick_start/
    tutorial.json      the steps
    practice.blend     the scene it runs in (optional)
    01_select.mp4      its local clips and images, which ship with it
    where.png

dev/media/quick_start/
    02_region.mp4      copies of its hosted ones, to upload (see below)
```

A tutorial contains only data. Nothing in it runs as Python. Everything a
step checks or sets is a property named by a path, which Blender looks up
the same way it does for a driver. Clips and images are named by their
file name only, never by a path, so a tutorial can only show files in its
own folder.

## Where tutorials come from

**Start a Tutorial** groups tutorials by where they come from:

- **Kneady:** Kneady's own `tutorials/` folder.
- **An add-on:** Any enabled add-on with a `kneady_tutorials/` folder in
  its own folder. These are listed under the add-on's name. The add-on
  doesn't need to call anything in Kneady, so any add-on can include
  tutorials this way.
- **In This File:** Tutorials attached to an item in the open file (see
  below).
- **Yours:** The folder you save tutorials in.

Folders whose names start with `_` or `.` are never treated as tutorials.
For example, a tutorials folder's `_scenes/` folder holds practice scenes
that several tutorials share. If two tutorials have the same folder name,
the one from the later source in this list is shown, so a copy of one of
Kneady's tutorials that you have changed replaces the original.

## Attached to an item, in a file

A rigger can give a rig its own tutorials, which are stored in its file:

1. Open the rig's file and write the tutorial as usual.
2. Select the rig, and in the editor click **Attach to \<name\>**. The
   button is named after the active object, for example Attach to ArmRig.
3. Save the file.

The tutorial, its clips and its images are stored on the object, and go
wherever the object goes. That includes opening the rig's own file, and
appending or linking it into another file, as an animator does when
linking a rig into a shot. Five copies of the rig in a shot list the
tutorial only once. An attached tutorial runs in the file it is in, never
in a practice scene, so its Start settings should change as little as
possible.

- **Where it shows:** Under In This File in Start a Tutorial. It is also
  shown at Help's Inform level, as **Tutorials in This File** at the top of
  the Kneady tab. Quiet shows none.
- **Editing:** Choose it in the editor and edit it as usual. Save writes it
  back to its object, and you then save the file to keep it. Ctrl+Z undoes
  the change. The tutorials of a linked rig are edited in the rig's own
  file.
- **Save to Folder** copies it to your tutorials folder as a separate
  tutorial. **Delete** removes it from the object.
- **Size:** Every clip makes the file bigger. To keep a file small, host
  the clips online (see "Local or hosted"). A hosted clip isn't stored in
  the file.
- **Safety:** An attached tutorial is data, like every tutorial. Opening
  someone else's file that contains tutorials doesn't run anything.

## Clips and images

The clips in Kneady's own tutorials are made by scripts rather than
recorded by hand. In Kneady's repository, `dev/clips/` plays each step in
a Recording Window with simulated input, draws the cursor, and encodes the
MP4. When the interface changes, the clips are made again to match. The
README in that folder explains how.

- **Vertical:** Use 9:16. 4:5 also works, since the panel fits whatever
  shape it gets.
- **720 x 1280** is ideal, and 540 x 960 is the smallest size that stays
  sharp. The panel shows a clip at 234 x 416 pixels times Blender's
  interface scale, which is the Resolution Scale preference times the
  display's own scale (2 on a Retina or 4K display). That is 293 pixels
  wide at 1.25 and 468 at 2, so a 720-wide clip stays sharp up to a scale
  of 3. Each frame is decoded in Blender as it plays, so a larger clip
  costs more without looking better. Only use 1080 x 1920 if the same
  clips also go to Shorts or Reels.
- **Record close up.** Clips are shown small. At an interface scale of
  1.25, a 720-wide recording of the screen is shown at about 40% of its
  size, interface text included. Zoom the view in until the gesture fills
  the frame. For a clip of a panel, set Resolution Scale to 2 while you
  record, then set it back.
- **Clips:** MP4 (H.264), a few seconds long, with no sound. MOV, WebM,
  MKV and AVI files also play.
- **Frame rate:** Any frame rate works, as long as it is constant. Each
  clip plays at its own rate (15, 24 or 30, for example), and one tutorial
  can mix them. The rate must not change within a clip. OBS records at a
  constant rate, but some quick screen recorders don't. 15 fps is enough
  for interface work and halves what Blender has to decode, although a
  fast drag can look a little choppy.
- **File size:** The bitrate decides the file size, not the frame rate. Recorded at a fixed bitrate (CBR in OBS), a 15 fps clip is as
  large as a 30 fps one. Record at a fixed quality instead, such as OBS's
  Recording Quality "High Quality, Medium File Size", or Rate Control CRF
  or CQP. Then a still screen takes up almost no space.
- **Images:** PNG or JPEG, for a moment that doesn't need motion, such as
  where a setting is or what a finished pose looks like.
- Show one gesture per clip. A step can have several clips, for example
  the gesture in the viewport and then where to find something in
  Blender's interface.
- The same clips can be posted to YouTube Shorts, Reels or TikTok without
  changes.

**Recording a clip.** Any screen recorder will do, at the size given
above. With OBS:

1. Make the inside of Blender's window 720 x 1280. You can use a separate
   window for this with View > Area > Duplicate Area into New Window.
2. Add a **Window Capture** source for it, with **Client Area** on (so
   only the inside is captured) and **Capture Cursor** on.
3. In Settings > Video, set both Base and Output Resolution to `720x1280`,
   so nothing is scaled.
4. Record as MPEG-4 or Hybrid MP4 (Settings > Output > Recording Format).
5. Choose the recorded file with the folder icon next to the clip's File.

**Trimming.** A clip's **Trim** sets which frames play, with Trim Start
and Trim End in its settings. They count from 1, and 0 means the clip's
own start or end. Below them, the editor shows how much the trim keeps,
for example "Keeps 2.0 of 10.0 s". The panel loops the kept frames, or
holds on the last one. A trim only marks the frames to play, and the file
itself keeps every frame. If you want a file with only the kept frames,
for example to post it somewhere, cut it in a video editor.

Kneady Pro adds tools for recording: a window sized for capture, OBS
recording from the panel straight into the clip's place, a trim bar under
the clip that you can drag, Apply Trim, and Record What You Do,
which turns what you do into a step's Done When, Start and Highlight. What
these tools make is ordinary tutorial data, and the free Kneady plays it
as it is.

If a file is missing, the panel shows "Clip not recorded yet" or "Image
not added yet" and the file name in its place. This way you can write and
try a tutorial before its media exist.

## Local or hosted

Each clip or image is either local or hosted.

- **Local** (the default): The file is in the tutorial's own folder and is
  included with it. It works offline and without Blender's Allow Online
  Access, so a first tutorial should use only local files. Quick Start
  does.
- **Hosted** (`"hosted": true`): The file is downloaded in the background
  when the tutorial starts, from the tutorial's `media_url` followed by the
  file name, or from the item's own `url`. It is kept in Kneady's folder
  in Blender's user files, so it is only downloaded once. Hosting keeps a
  tutorial small, which helps with long clips or many clips.

Downloading needs **Allow Online Access** to be on (Preferences >
System), as Blender requires for every extension. It is off in a new
installation of Blender, so the panel says so where the clip would be,
and clicking there opens the Preferences. Only `https://` addresses are
used. Certificates are checked against both the computer's own and
Blender's, so it also works on office networks that inspect secure
traffic with their own certificate.

The copy of a hosted file on your computer, which you play while writing
and then upload, is kept in a separate place where it is never included
with the tutorial. In Kneady's repository, that is
`dev/media/<tutorial>/`. In any other tutorials folder, it is
`.hosted/<tutorial>/`. The editor's folder icon puts the file there.

**Watch Link.** Any clip can have a `watch` address, such as its YouTube
Short. Whenever the clip can't be shown in Blender (it isn't recorded,
Online Access is off, the download failed, or this Blender can't play
video), a **Watch on YouTube** button appears in its place and opens it in
the person's browser. For a link to another site, the button says **Watch
Online**.

To publish hosted files:

1. Record into `dev/media/<tutorial>/` and try the tutorial.
2. Run `python dev/publish_media.py <tutorial>`. It writes each file's
   `sha256` fingerprint into tutorial.json, so Kneady refuses any download
   that isn't that exact file. It also lists each file with the address
   where it has to be available.
3. Upload the files to those addresses. A GitHub release of a public
   repository works: create the release, then attach the files to it.
4. To replace a clip, give the new recording **a new file name** (for
   example `01_turn_on_2.mp4`), point the step at it, run the script and
   upload it. People get the new clip with the next Kneady release, which
   includes the new tutorial.json. **Leave the old file online.** Copies of
   Kneady that are already installed still ask for it, and they refuse a
   different file under the old name.

## On a phone

A tutorial's **Playlist** is a link where the whole tutorial can be
watched on a phone: a YouTube playlist of its clips, in order. When a
tutorial has one, the panel's title row has a phone button, which shows
the link as a QR code in place of the clip and the text. The person opens
it with their phone's camera and swipes to the clip they want. Clicking
the code goes back. The clip pauses while the code is shown.

- Make the playlist **Public** or **Unlisted**. A private playlist only
  opens for you.
- Use one link for the whole tutorial rather than one per clip, so the
  person only has to scan once.
- Only an `https://` address is accepted.

## tutorial.json

```json
{
  "format": 1,
  "title": "Quick Start",
  "summary": "One line on what it teaches.",
  "order": 1,
  "practice": "practice.blend",
  "playlist": "https://www.youtube.com/playlist?list=...",
  "media": [
    {"file": "overview.mp4", "label": "In the viewport"}
  ],
  "steps": [
    {
      "title": "Turn Kneady on",
      "text": ["A paragraph.", "Another, the clip's: Properties > Modifiers > Kneady."],
      "media": [
        {"file": "01_turn_on.mp4", "label": "In the 3D view's header", "paragraph": 1, "hold": true,
         "trim": [12, 96],
         "recorded": {"blender": "5.2", "kneady": "1.0.0"},
         "show_me": {"sidebar": "Kneady"}},
        {"file": "where.png", "label": "The Kneady tab", "paragraph": 1, "seconds": 4}
      ],
      "highlight": ["scene.kneady_on"],
      "done_when": [{"path": "scene.kneady_on", "is": true}],
      "start": {"mode": "OBJECT", "select": [], "active": "Arm",
                "set": [{"path": "scene.kneady_on", "value": false}],
                "view": {"location": [0, 0, 1], "rotation": [1, 0, 0, 0], "distance": 6},
                "sidebar": "Kneady"}
    }
  ]
}
```

At the top level, `playlist` is the link for watching the whole tutorial
on a phone, shown as a QR code (see "On a phone").

Everything in a step is optional except `text`.

- **text**: The step's paragraphs. Keep them short, since the panel is
  narrow. Write a path through Blender's interface as a breadcrumb:
  Properties > Modifiers > Kneady > Speed.
- **media**: The step's clips and images. Each has a `file`, a `label`
  saying where to look ("In the viewport", "Properties > Modifiers"), and
  the `paragraph` it goes with, counted from 0. While an item is showing,
  its paragraph is highlighted and scrolled into view. A step's media play
  one after another and then start over. An image stays up for its
  `seconds` (4 if not given) before the next item. A clip that is the only
  item in its step loops.
  - `hold`: Set to true to stay on the last frame once the clip has played
    (or to stay on an image), instead of playing again or moving on to the
    next item. Use it for a clip that ends on the finished result. The arrows and
    dots still move to the next item.
  - `trim`: `[first, last]`, the frames that play, counted from 1. Use 0
    for `last` to play to the end of the clip. This is the clip's Trim in
    the editor (see "Trimming").
  - **Pause and Loop**, in the row under the clip, only affect the item
    that is showing. Pause pauses it (pressing Play on an item held at its
    end starts it over), and Loop plays it over and over, whatever its own
    settings say. The next item starts as its settings say.
  - **A step's own media, or the shared set.** A step with `media` shows
    its own items, and `"media": []` shows none. A step without the key
    shows the tutorial's shared set, which is the `media` at the top of the
    file. Moving from one step that uses the shared set to another keeps
    the current position, so one clip can keep playing over several pages
    of text. A shared item highlights its `paragraph` on any step that has
    that paragraph.
  - `hosted`: True for an item that is downloaded rather than included.
    `url`: Where it is hosted, if not at the tutorial's `media_url`. An
    item with a `url` is always hosted. `sha256`: Its fingerprint, written
    by `publish_media.py`.
  - `watch`: Where to watch it online, for a Watch button when it can't
    be shown in Blender.
  - `recorded`: The Blender and Kneady versions it was made with. The
    refresh icon next to them in the editor fills in the current versions.
    The editor counts the clips and images made with other versions, so
    after an update you can find the ones that may show an old interface.
  - `show_me`: Adds a Show Me button under the clip, which opens the place
    the clip shows. Use `{"sidebar": "Kneady"}` for a Sidebar tab, or
    `{"properties": "MODIFIER", "object": "Arm", "modifier": "GeometryNodes"}`
    for a tab of the Properties Editor, with the object made active and the
    modifier expanded.
- **highlight**: Properties in Kneady's own panels to highlight.
- **done_when**: Conditions that must all be true for the step to be
  marked as done. Each is a path with one test, or a state on its own:

  | Condition | True when |
  |---|---|
  | `{"path": P, "is": V}` | the value is V (numbers are compared with a tiny tolerance; use lists for vectors) |
  | `{"path": P, "is_not": V}` | the value is not V |
  | `{"path": P, "at_least": N}`, `"at_most"` | a number is at least (or at most) N |
  | `{"path": P, "changed": true}` | the value is different from when the step began |
  | `{"path": P, "count_at_least": N}` | a collection has N or more items |
  | `{"operator": "kneady.drag", "with": {"target": "Arm", "region": 1, "button": 0}, "moved": true}` | that Kneady button was dragged since the step began (`"moved": false` for clicked, or leave it out for either). Only what `with` names is checked. |
  | `{"operator": "object.mode_set", "with": {"mode": "POSE"}}` | any other operator was run since the step began, from a button in a panel or a key, as long as Blender keeps it in its history |
  | `{"hovered": "Forearm", "object": "Arm"}` | that region was hovered since the step began (`object` is optional) |
  | `{"mode": "POSE"}` | Blender is in that mode |
  | `{"active": "Arm"}` | that object is active |
  | `{"selected": ["Arm", "ArmRig"]}` | those objects are selected |

  A step without conditions is never marked as done on its own, but Next
  is always available.
- **start**: What the step sets up, each time the step is entered and when
  Reset is clicked, as one undo step. It can contain `mode`, `select`
  (object names; all other objects are deselected), `active`, `set` (paths
  and values), `view` (the 3D Viewport's `location`, `rotation` as w, x,
  y, z, `distance` and `perspective`) and `sidebar` (a tab to open).

**Paths** start at `scene`, `object` (the active object), `objects["Name"]`,
`window_manager` or `space` (the tutorial's 3D Viewport), and continue the
way Blender's data paths do, for example
`objects["ArmRig"].pose.bones["Lower"].rotation_quaternion`. The paste
icon in the editor converts a path copied with Copy Full Data Path into
this form.

## The practice scene

A tutorial with `practice` opens a copy of that file from the temporary
folder. Blender first asks the person to save their own file, with its
usual prompt, and **Return to My File** opens their file again at the end.
Nothing they do in the practice scene is kept.

Opening a file clears Blender's undo history, so the person's work is
saved but their undo steps are not. A tutorial without a practice scene
runs in whatever file is open, so its Start settings should change as
little as possible.

- In the editor, **the file icon (Use This File)** next to Practice Scene
  makes the open file the practice scene. For Kneady's own tutorials, make
  the scene with a script instead, so it can be made again later. The
  shared scenes in `tutorials/_scenes/` are made by scripts in
  `dev/scenes/`:
  - `cube`: Blender's default scene.
  - `shape_cube`: A cube with many faces, a Sphere shape key and a Twist
    modifier input.
  - `arm`: A Rigify left arm and hand.
  - `mannequin`: A full Rigify figure without a face.

  The rigs are generated by Rigify, which comes with Blender, and the
  bodies are built around their bones. Nothing comes from anywhere else.
- Save it with **the oldest Blender version Kneady supports** (4.2), so
  every supported version can open it. The file icon (Use This File) saves
  with the version of Blender that is running, and says so.
- Don't rename its objects, bones or regions, because the steps' checks
  and Start settings refer to them by name.
- Several tutorials can share one scene. Put it in the tutorials folder's
  `_scenes/` folder and set each tutorial's practice to
  `"practice": "../_scenes/arm.blend"`. A practice path can reach a folder
  next to its tutorial's folder, but never above the tutorials folder.
  When a tutorial is copied to your folder for editing, it takes its own
  copy of the scene along.
- Keep it small, since it is included with Kneady.
- Use your own models. Anything made by someone else needs its license
  checked and its attribution included.

## Trying one

- In the editor, click **Try** to save the tutorial and play it from the
  selected step. Or set Help to Learn and choose it from **Start a
  Tutorial**, which opens its practice scene the way a user would see it.
- `tests/test_tutorials.py` checks that every included tutorial can be
  read without problems, and that every path it checks, sets or
  highlights exists in its practice scene.
- `tests/probe_tutorial.py` plays the panel in a real window and clicks
  through it (see TESTING.md for how to run probes).
