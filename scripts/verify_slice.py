"""Render a sliced sprite the way a uGUI Image does and compare it with the original as drawn today.

usage: python verify_slice.py <original.png> <sliced.png> --border L,B,R,T --type sliced|tiled
                              [--size WxH ...] [--ppu-mult M] [--current simple|tiled] [--save-dir DIR]

--border uses the .meta order (x=left, y=bottom, z=right, w=top). --size is the rect size in canvas
units of each place the Image is shown (default: the original's size); units equal texels when the
sprite's Pixels Per Unit matches the canvas reference (100) and pixelsPerUnitMultiplier is 1.
Tiled follows Image.GenerateTiledSprite: tiles start at the bottom-left inner corner, the last tile
on each axis is cut, keeping its left / bottom part.
"""
import argparse
import os
import numpy as np
from PIL import Image


def stretch(img, w, h):
    return img if img.size == (w, h) else img.resize((w, h), Image.BILINEAR)


def tile(img, w, h):
    """Fill w x h with img from the bottom-left, as uGUI does (image rows grow downwards)."""
    out = Image.new("RGBA", (w, h))
    tw, th = img.size
    for x in range(0, w, tw):
        for y_from_bottom in range(0, h, th):
            cw, ch = min(tw, w - x), min(th, h - y_from_bottom)
            piece = img.crop((0, th - ch, cw, th))  # left part, bottom part
            out.paste(piece, (x, h - y_from_bottom - ch))
    return out


def render(sprite, L, B, R, T, w, h, kind):
    sw, sh = sprite.size
    if L + R > w or T + B > h:
        raise SystemExit(f"rect {w}x{h} is smaller than the borders: uGUI would shrink the corners")
    out = Image.new("RGBA", (w, h))
    xs = [(0, L, 0, L), (L, sw - R, L, w - R), (sw - R, sw, w - R, w)]
    ys = [(0, T, 0, T), (T, sh - B, T, h - B), (sh - B, sh, h - B, h)]
    for i, (sx0, sx1, dx0, dx1) in enumerate(xs):
        for j, (sy0, sy1, dy0, dy1) in enumerate(ys):
            if sx1 <= sx0 or sy1 <= sy0 or dx1 <= dx0 or dy1 <= dy0:
                continue
            piece = sprite.crop((sx0, sy0, sx1, sy1))
            fill = tile if kind == "tiled" and (i == 1 or j == 1) else stretch
            out.paste(fill(piece, dx1 - dx0, dy1 - dy0), (dx0, dy0))
    return out


def on_white(im):
    a = np.asarray(im.convert("RGBA")).astype(float)
    return a[..., :3] * a[..., 3:4] / 255 + 255 * (1 - a[..., 3:4] / 255), a[..., 3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("original")
    ap.add_argument("sliced")
    ap.add_argument("--border", required=True)
    ap.add_argument("--type", choices=("sliced", "tiled"), required=True)
    ap.add_argument("--size", nargs="*", default=[])
    ap.add_argument("--save-dir")
    ap.add_argument("--ppu-mult", type=float, default=1.0, help="Image.pixelsPerUnitMultiplier")
    ap.add_argument("--current", choices=("simple", "tiled"), default="simple",
                    help="how the Image draws the original today (tiled = no border, tiled at 1:1)")
    args = ap.parse_args()
    L, B, R, T = (int(v) for v in args.border.split(","))
    orig = Image.open(args.original).convert("RGBA")
    sprite = Image.open(args.sliced).convert("RGBA")
    sw, sh = sprite.size
    ow_, oh_ = orig.size
    print(f"original {ow_}x{oh_} = {ow_ * oh_} px, sliced {sw}x{sh} = {sw * sh} px "
          f"({100 - 100 * sw * sh / (ow_ * oh_):.1f}% fewer)")

    if args.type == "tiled":
        s, _ = on_white(sprite)
        cw, ch = sw - L - R, sh - T - B
        if L and R and cw > 0:  # texel beside each vertical seam vs the texel that really continues the motif
            seam = max(np.abs(s[:, L + cw] - s[:, L]).max() if R else 0, np.abs(s[:, L - 1] - s[:, L + cw - 1]).max())
            print(f"X seams: neighbour mismatch {seam:.0f}/255 (bilinear blends up to half of it into one texel)")
        if T and B and ch > 0:
            seam = max(np.abs(s[T + ch] - s[T]).max(), np.abs(s[T - 1] - s[T + ch - 1]).max())
            print(f"Y seams: neighbour mismatch {seam:.0f}/255")

    sizes = args.size or [f"{ow_}x{oh_}"]
    for spec in sizes:
        w, h = (int(v) for v in spec.lower().split("x"))
        # a multiplier m draws the sprite's texels 1/m units wide: build at m x the size, then scale down
        m = args.ppu_mult
        rebuilt = render(sprite, L, B, R, T, round(w * m), round(h * m), args.type)
        rebuilt = stretch(rebuilt, w, h)
        ref = render(orig, 0, 0, 0, 0, w, h, "tiled") if args.current == "tiled" else stretch(orig, w, h)
        (a, aa), (b, ba) = on_white(ref), on_white(rebuilt)
        d = np.abs(a - b).max(axis=2)
        mse = ((a - b) ** 2).mean()
        ps = "inf (pixel-exact)" if mse == 0 else f"{10 * np.log10(255 ** 2 / mse):.2f} dB"
        quads = ""
        if args.type == "tiled":
            cw, ch = sw - L - R, sh - T - B
            n = int(np.ceil((w - L - R) / cw)) * int(np.ceil((h - T - B) / ch))
            quads = f"  centre tiles={n}" + ("  <-- too many quads, keep the other axis full size" if n > 200 else "")
        print(f"{w}x{h} vs original as {args.current.title()}: PSNR={ps} max={d.max():.0f}/255 "
              f"px>8={(d > 8).mean() * 100:.3f}% alpha max={np.abs(aa - ba).max():.0f}{quads}")
        if d.max() > 8:
            ys, xs = np.where(d > 8)
            print(f"    differences > 8 inside x {xs.min()}..{xs.max()}, y {ys.min()}..{ys.max()}")
        if args.save_dir:
            os.makedirs(args.save_dir, exist_ok=True)
            rebuilt.save(os.path.join(args.save_dir, f"rebuilt_{w}x{h}.png"))
            Image.fromarray(np.clip(d * 4, 0, 255).astype(np.uint8)).save(os.path.join(args.save_dir, f"diff_{w}x{h}.png"))


if __name__ == "__main__":
    main()
