---
name: slicing-ui-sprites
description: Use when asked to shrink, compress or "optimize" a UI PNG in a Unity project (a card, box, panel, frame, header, button or background) to cut build size or atlas space while it must look the same; when an image has flat areas, a stretched gradient or a repeating motif (hearts, stars, diamonds); when weighing 9-slice, Sliced or Tiled Image, sprite borders, RawImage with uvRect, or splitting art into layers.
---

# Slicing UI sprites

## Overview

Remove only pixels a uGUI `Image` can regenerate exactly: lines identical to their neighbours
(**Sliced** stretches them back) or whole periods of a motif (**Tiled** repeats them). Keep **one**
sprite, its GUID and its atlas, so nothing else changes. Measure the result; never eyeball it.

Splitting art into several RawImage layers is the wrong tool: more draw calls, textures leave
the atlas, and a "keep quality" importer setting of `Uncompressed` makes it bigger than before.

## Steps

Scripts are in `scripts/` next to this file (`.claude/skills/slicing-ui-sprites/scripts/` when
installed in a project). Run them with Python 3 (`pip install pillow numpy`) from the Unity project
root, without `-I`.

1. **Back up** the PNG and `.meta` to the scratchpad. Always slice *from the backup*.
2. **Find every user**: `python find_sprite_users.py <png>`. It prints each Image (type, rect
   size, scale), every prefab instance and variant with overrides, and every `.cs` naming the
   sprite. A size of 0 means a stretch anchor or a parent layout group (GridLayoutGroup cell
   size, `childControlWidth`) sets it: read that parent. Also grep scenes for the GUID
   (a scene object the user is editing counts). Inactive instances can be ignored.
3. **Analyze**: `python analyze_sprite.py <png>` prints, per axis, Sliced / Tiled / keep, then the
   `slice_sprite.py` arguments, the `spriteBorder` line and the Image type. A Tiled search on a
   1000 px image takes about a minute. The printed plan assumes the Image is drawn at the
   sprite's native size with today's type Simple.
4. **Check the display size and today's `m_Type` against the plan** (table below). The table
   decides, not the printed plan. Stop and ask the user if no row fits.
5. **Slice in place**: `python slice_sprite.py <backup.png> <asset.png> --x ... --y ...`.
   Overwriting keeps the GUID, so prefabs and the SpriteAtlas need no reference changes.
6. **`.meta`**: set `spriteBorder: {x: L, y: B, z: R, w: T}` and `spriteMeshType: 1` (Full Rect).
7. **Image type**: set `m_Type` on the Image right after its `m_Sprite` line, in the prefab that
   owns it (`1` Sliced, `2` Tiled). Instances and variants inherit unless step 2 showed an
   `m_Type` override.
8. **Builders and tests**: an Editor builder that sets `image.type = Image.Type.Simple` for this
   sprite would undo the change on its next run. Change it, and add
   `Assert.AreEqual(Image.Type.Sliced, image.type, ...)` to that prefab's wiring test.
   Compile the project (see Common mistakes for Git Bash).
9. **Verify**: `python verify_slice.py <backup.png> <asset.png> --border L,B,R,T --type sliced|tiled --size WxH ...`
   at every displayed size from step 2. It renders like uGUI and compares with today's look
   (`--current tiled` when the Image is Tiled today). Accept PSNR `inf` (pixel-exact) or >= 48 dB with tile seams <= 16/255. Run
   any text or lint checks your project requires.
10. **Report**: sprite size before and after, PSNR per size, the screens to look at in Unity, and
    what you did not run (EditMode tests need the clone recipe). Saving only lands in the build
    if the atlas page shrinks: name the atlas and its format (`.spriteatlasv2.meta`
    platform `format`) and ask the user to compare Pack Preview page sizes.

## Does the plan match how it is shown?

Sliced borders and Tiled tiles are drawn at the sprite's native texel size; Simple scales everything.

| Where the Image is shown | Do |
|---|---|
| Native size, or scaled only by `localScale` | The plan as printed |
| Smaller or larger via `sizeDelta`, same aspect | The plan plus `m_PixelsPerUnitMultiplier = native / shown`, verify with `--ppu-mult` |
| Stretched along a **Sliced** axis | Fine: that axis is uniform |
| **Already Tiled** with border 0, sprite in no atlas, `wrapU`/`wrapV` Repeat (a background module) | Crop to one period, keep border 0 (`--x 0,P,0,0`), no prefab edit. uGUI draws one quad and the GPU wraps, so there are no seams. Verify with `--current tiled` |
| Stretched along a **Tiled** axis, or stretched unevenly (full-screen background) | Tiled would change the look. To keep it: Image → RawImage, texture = one period (Wrap Repeat, outside the atlas), `uvRect.width = native / period`. Ask the user first: it removes the sprite from the atlas, and today's stretch may be a bug |

## Unity facts that bite

| Fact | Consequence |
|---|---|
| `spriteBorder` is `{x: left, y: bottom, z: right, w: top}` | Image rows count from the top: top border is `w` |
| `m_Type`: 0 Simple, 1 Sliced, 2 Tiled. Sliced with all borders 0 draws as Simple | Always set a border |
| Tiled starts at the bottom-left inner corner; the last tile on each axis is cut | Make the tiled centre whole periods at native size (the analyzer does) |
| Tiled also tiles the centre on the *other* axis | A 2-line uniform centre would become hundreds of quads: one Image is Sliced **or** Tiled |
| Bilinear samples the neighbour texel at every seam | Centre neighbours must equal the centre (Sliced) or continue the motif (Tiled seams) |
| The atlas compresses in ASTC blocks of 4-8 texels | Keep the centre >= 8 texels from the sprite edge |
| `preserveAspect` is ignored by Sliced and Tiled | Harmless |
| An object of nested instance I from source object S has fileID `(I ^ S) & 0x7fffffffffffffff` | How overrides on variants and nested prefabs are found |

## Common mistakes

| Mistake | Fix |
|---|---|
| A vertical gradient reported as a motif (period 16, repeat error ~2) | A drawn motif repeats at ~0.0x error; anything above 0.5 is a gradient: keep that axis |
| Picking a multiple of the period, or the phase with the best PSNR but a 36/255 seam | Use the analyzer; it takes the smallest period and clean seams first |
| Editing the prefab but not the builder that writes it | Step 8 |
| Missing a scene or popup that uses the sprite directly | Step 2 lists them. A Simple Image showing the cut sprite looks squashed |
| `csc` in Git Bash: `/nostdlib` becomes a path | `MSYS_NO_PATHCONV=1`, and give `csc.dll` as `C:/Program Files/...`, not `/c/...` |
| Committing the art with unrelated changes | One commit per sprite group, e.g. `perf(ui): slice shop card backgrounds` |
