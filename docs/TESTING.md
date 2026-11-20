# Helping test Kneady

Thank you for helping. There are two ways to help, and you only need one.

- **[Run the automatic checks](#run-the-automatic-checks).** No 3D
  knowledge needed. You run one command on a Linux computer or a Mac, wait
  about 45 minutes, and send back one file.
- **[Try it by hand](#try-it-by-hand).** For Blender users: about an hour
  with your own character, telling us what works, what doesn't, and what
  confused you.

## Run the automatic checks

The checks download four versions of Blender, run Kneady's tests in each,
and open Blender windows to try things the way a person would: dragging
with the mouse, undoing, taking screenshots. Your computer is left as it
was. Nothing is installed, and everything goes into one folder that you can
delete afterward.

**You need:**
- a Linux computer (64-bit Intel or AMD) with a desktop, or a Mac
- about 2.5 GB of free disk space
- an internet connection
- about 45 minutes in which you don't need the computer's screen

**Steps:**

1. **Get Kneady's files.** Greg will send you a zip file or a link.
   Unzip it anywhere, for example into your Downloads folder.
2. **Open a terminal.**
   - On Linux: your terminal application.
   - On a Mac: press Cmd+Space, type Terminal, and press Return.
3. **Go into the Kneady folder.** Type `cd ` with a space after it, drag
   the unzipped folder from your file manager onto the terminal window,
   and press Return.
4. **Start the checks:**

   ```
   bash tests/platform_check.sh
   ```

5. **Wait.** It downloads each Blender version, about 350 MB each, then
   runs the checks.
   - Blender windows will open and close by themselves for a few minutes
     at a time.
   - Your mouse and keyboard don't affect them, but please don't close
     them.
   - When it finishes, the last lines say "Please send this file to Greg"
     and give a file name ending in `.tar.gz`.
6. **Send Greg that file.** It holds the results, the logs, some
   screenshots, and a description of your system (operating system,
   graphics card). It holds nothing else from your computer.
7. **Free the space afterward** by deleting the `kneady-check` folder in
   your home folder.

**If something goes wrong,** send Greg whatever the terminal shows. A
screenshot or a copy of the text is fine.

**To test only one version** (faster, one download):

```
KNEADY_VERSIONS="5.3" bash tests/platform_check.sh
```

**Notes:**
- On an Intel Mac, Blender 5.2 and 5.3 have no download, so the checks
  skip them and say so.
- On Linux, the window checks need a desktop session. Over SSH without a
  display they are skipped.

## Try it by hand

For someone who uses Blender. Greg will send you `kneady-1.0.0.zip`.

**Install:** in Blender 4.2 or newer, open Edit > Preferences > Get
Extensions. Open the ⌄ menu at the top right, choose **Install from
Disk**, and pick the zip. A **Kneady** tab appears in the 3D viewport's
sidebar (N).

**First, the tutorials.** At the top of the Kneady tab, open **Start a
Tutorial** (Kneady starts at Help's **Learn**, which offers them) and play
all 14 in order, from 0. Learn, Inform and Quiet. Each opens a practice
scene (save your own file first) and
every step ticks itself off when it's done - so a step that doesn't tick
off when you think you've done it is just what we want to hear about, as
is a clip that shows something other than what you see, or text that
sends you looking for something you can't find. Tutorial 13 leaves a
tutorial called Haul the Cube in your tutorials folder; the bin in Edit
mode (the pencil beside Start a Tutorial) deletes it.

**Then your own character.** Use your usual keymap, mouse, tablet or
trackpad, and display scaling: those are what we can't test ourselves. For
each, note whether it did what the "Expect" column says.

| # | Try | Expect |
|---|---|---|
| 1 | Follow the README's "Start in two minutes": click a bone in Pose mode, then on the mesh press +, then Edit Faces > Select Faces of \<bone\> > Assign > Done, and turn Kneady on | a region named after the bone, its faces from the bone's vertex groups; hovering paints it, a drag turns the bone |
| 2 | Drag up and down, then left and right; then with Shift, and with Ctrl | the bone turns, the surface following your mouse; Shift finer, Ctrl in steps |
| 3 | Drag, and hold Alt partway, then let it go | holding Alt switches to the other direction, letting go switches back, each keeping what the other did |
| 4 | Start a drag, then press Esc. Try again and right-click | everything back where it was |
| 5 | During a drag, type a number and press Enter; after one, change the value in the Adjust Last Operation panel | the bone turns exactly that far; the drag redone to the new value |
| 6 | Undo (Ctrl+Z) and redo (Ctrl+Shift+Z) several drags and edits | each drag is one step |
| 7 | Select the armature, enter Pose mode, then hover and drag the mesh | works as in Object mode. A click selects the bones the button drives |
| 8 | Turn on Auto Keying, drag, change frames | the pose is keyed where you dragged |
| 9 | Drag a region whose bone can't move that way: a locked channel, a constraint or IK, a driven property | the status bar says what is holding it |
| 10 | Make a button for an IK/FK switch or a shape key (see the guide's "Notes for common rigs") | the switch or shape key moves within its range |
| 11 | Build the controls you'd want for one limb, with what the tutorials showed: menus, a toggle with Show When, a placed button or a 3D handle, your own tips | tell us what was easy, what was hard, and what you missed |
| 12 | Copy a region's buttons onto another region, and into another file | they arrive; the region keeps its own name, faces and color |
| 13 | Save, close Blender, reopen the file; append the character into a new file; link it into a shot with a library override | the regions there and working in each; in the linked one, new regions refused with a reason |
| 14 | Use it in a heavy scene: a dense sculpt, several characters, playback | tell us anything that feels slow |
| 15 | Anything else you'd naturally try | tell us |

**What to send Greg:**
- Your Blender version, operating system, and how you work: mouse,
  tablet or trackpad, keymap, display scaling.
- For anything that didn't match: what you did, what you expected, and
  what happened. A screenshot or short screen recording helps most.
- Anything that confused you, even if it worked in the end.
