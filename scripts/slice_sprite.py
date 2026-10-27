"""Cut a UI background PNG down to border + centre + border, pixel for pixel (no resampling).

usage: python slice_sprite.py <src.png> <dst.png> [--x LEFT,CENTRE,RIGHT,START] [--y TOP,CENTRE,BOTTOM,START]

Each axis keeps src[0:LEFT] + src[START:START+CENTRE] + src[n-RIGHT:n]. START is where the centre
is copied from (for Tiled: the period with the cleanest seams, as analyze_sprite.py reports).
An axis without a flag is kept whole. Y is in image rows from the top: TOP is spriteBorder.w,
BOTTOM is spriteBorder.y. Write src from a backup, never from the asset you overwrite.
"""
import argparse
import numpy as np
from PIL import Image


def keep(n, spec):
    if not spec:
        return np.arange(n)
    first, centre, last, start = (int(v) for v in spec.split(","))
    if first + last > n or start + centre > n:
        raise SystemExit(f"slice {spec} does not fit {n} lines")
    return np.concatenate([np.arange(first), np.arange(start, start + centre), np.arange(n - last, n)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--x")
    ap.add_argument("--y")
    args = ap.parse_args()
    a = np.asarray(Image.open(args.src).convert("RGBA"))
    out = a[keep(a.shape[0], args.y)][:, keep(a.shape[1], args.x)]
    Image.fromarray(out, "RGBA").save(args.dst, optimize=True)
    print(f"{args.src} {a.shape[1]}x{a.shape[0]} -> {args.dst} {out.shape[1]}x{out.shape[0]}")


if __name__ == "__main__":
    main()
