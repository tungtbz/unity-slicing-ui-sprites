"""Find how far a UI background PNG can shrink as a Sliced (9-slice) or Tiled sprite.

usage: python analyze_sprite.py <png> [--max-border N]

Per axis: the longest run of near-identical lines (columns / rows) -> Sliced, else the
period of a repeating motif -> Tiled, else keep the axis. Prints the slice_sprite.py command,
the spriteBorder line for the .meta and the Image type. Check the result with verify_slice.py.
"""
import argparse
import numpy as np
from PIL import Image

MARGIN = 8           # texels between the stretched/tiled centre and the sprite edge, so ASTC blocks
                     # that hold the centre never mix in atlas padding
GOOD_PSNR = 48.0     # the narrowest tiled plan at or above this (native size) wins
MAX_REPEAT_ERR = 0.5 # mean |line[i+p] - line[i]|: a drawn motif repeats at ~0.0x, a gradient at 2+
MIN_PSNR = 45.0      # a tiled axis must rebuild the original at least this well at the native size
SEAM_OK = 16         # texel mismatch across a tile seam that bilinear filtering cannot make visible


def on_white(a):
    return a[..., :3] * a[..., 3:4] / 255.0 + 255.0 * (1 - a[..., 3:4] / 255.0)


def uniform_run(lines, tol):
    """Longest run of consecutive lines all within tol of the run's middle line: (lo, hi) inclusive."""
    n = len(lines)
    axes = tuple(range(1, lines.ndim))
    step = np.abs(lines[1:] - lines[:-1]).max(axis=axes) <= tol
    best, start = (0, 0), 0
    for i in range(1, n + 1):  # longest chain of near-equal neighbours
        if i == n or not step[i - 1]:
            if i - 1 - start > best[1] - best[0]:
                best = (start, i - 1)
            start = i
    mid = (best[0] + best[1]) // 2  # a slow gradient also chains: keep only lines close to the middle one
    same = np.abs(lines - lines[mid]).max(axis=axes) <= tol
    lo = hi = mid
    while lo > best[0] and same[lo - 1]:
        lo -= 1
    while hi < best[1] and same[hi + 1]:
        hi += 1
    return lo, hi


def sliced_plan(n, lo, hi):
    """A 2-line centre at `first`; both centre neighbours (first-1, n-last) lie in the uniform run."""
    first, last = max(lo + 1, MARGIN), max(n - hi, MARGIN)
    if first + 1 > hi or n - last < lo:
        return None
    return first, 2, last, first


def period_of(lines):
    core = lines[len(lines) // 8: len(lines) - len(lines) // 8]
    errs = [(np.abs(core[p:] - core[:-p]).mean(), p) for p in range(16, max(17, len(core) // 3))]
    best = min(errs)[0]
    err, p = next((e, p) for e, p in errs if e <= best + 0.05)  # the smallest period, not a multiple of it
    return p, err


def tiled_plan(lines, p, max_border):
    """Borders whose centre holds whole periods at the native size, and the best period to copy."""
    n = len(lines)
    found = []
    for first in range(MARGIN, min(max_border, n // 3)):
        last = (n - first) % p
        while last < MARGIN:
            last += p
        for last in range(last, min(max_border, n // 3), p):
            segs = lines[first:n - last]
            segs = segs.reshape(len(segs) // p, p, *segs.shape[1:])
            for c in range(first, n - last - p + 1, p):
                tile = lines[c:c + p]
                diff = segs - tile[None]
                mse = (diff ** 2).sum() / lines.size
                ps = float("inf") if mse == 0 else 10 * np.log10(255 ** 2 / mse)
                seam = max(np.abs(lines[n - last] - tile[0]).max(), np.abs(lines[first - 1] - tile[-1]).max())
                found.append((ps, seam, first, last, c, np.abs(diff).max()))
    if not found:
        return None
    found = [f for f in found if f[1] <= SEAM_OK] or found  # clean seams first: they show once the canvas scales
    for width in sorted({f[2] + f[3] for f in found}):        # narrowest sprite that is still visually lossless
        best = max((f for f in found if f[2] + f[3] == width), key=lambda f: (f[0], -f[1]))
        if best[0] >= GOOD_PSNR:
            return best
    return max(found, key=lambda f: f[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("png")
    ap.add_argument("--max-border", type=int, default=220)
    ap.add_argument("--tol", type=int, default=0, help="per-channel difference still counted as identical")
    args = ap.parse_args()
    o = on_white(np.asarray(Image.open(args.png).convert("RGBA")).astype(float))
    H, W = o.shape[:2]
    print(f"{args.png}: {W}x{H} = {W * H} px")

    plan = {}
    for axis, label, n in ((1, "X", W), (0, "Y", H)):
        lines = np.moveaxis(o, axis, 0)
        lo, hi = uniform_run(lines, args.tol)
        print(f"\n{label}: lines {lo}..{hi} are identical within {args.tol}/255 ({hi - lo + 1} of {n})")
        s = sliced_plan(n, lo, hi) if hi - lo + 1 >= 3 * MARGIN else None
        if s:
            plan[label] = ("sliced",) + s
            print(f"  Sliced: border {s[0]} | centre {s[1]} | border {s[2]}  -> {sum(s[:3])} of {n}, stretched lines differ by <= {args.tol}/255")
            continue
        p, err = period_of(lines)
        print(f"  repeating motif: period {p}px, mean repeat error {err:.2f}/255")
        t = tiled_plan(lines, p, args.max_border) if err <= MAX_REPEAT_ERR else None
        if t and t[0] < MIN_PSNR:
            print(f"  best tiled plan reaches only {t[0]:.1f} dB (< {MIN_PSNR}): a gradient, not a motif")
            t = None
        if not t:
            plan[label] = ("keep",)
            print("  keep this axis at full size (no uniform run, no clean period)")
            continue
        ps, seam, first, last, c, mx = t
        plan[label] = ("tiled", first, p, last, c)
        print(f"  Tiled: border {first} | period {p} copied from {c} | border {last}  -> {first + p + last} of {n}; "
              f"native PSNR {ps:.2f} dB, max {mx:.0f}/255, seam {seam:.0f}/255")

    kinds = {plan["X"][0], plan["Y"][0]}
    if kinds == {"keep"}:
        print("\nPLAN: nothing to gain, leave the sprite as it is")
        return
    if kinds == {"tiled", "sliced"}:
        # One Image is either Sliced or Tiled. Tiled would also tile the uniform axis' 2-line centre into
        # hundreds of quads, so keep whichever axis saves less at full size.
        size = lambda k: sum(plan[k][1:4])
        n = {"X": W, "Y": H}
        loser = min(("X", "Y"), key=lambda k: n[k] / size(k))
        print(f"\nnote: X is {plan['X'][0]}, Y is {plan['Y'][0]}; one Image cannot do both, keeping {loser} full size")
        plan[loser] = ("keep",)
        kinds = {plan["X"][0], plan["Y"][0]}
    image_type = "Tiled (m_Type: 2)" if "tiled" in kinds else "Sliced (m_Type: 1)"
    arg = lambda k: "" if plan[k][0] == "keep" else f"--{k.lower()} {plan[k][1]},{plan[k][2]},{plan[k][3]},{plan[k][4]}"
    border = lambda k: (0, 0) if plan[k][0] == "keep" else (plan[k][1], plan[k][3])
    (l, r), (t, b) = border("X"), border("Y")
    print("\nPLAN")
    print(f"  Image type   : {image_type}")
    print(f"  slice        : python slice_sprite.py <backup.png> <asset.png> {arg('X')} {arg('Y')}".rstrip())
    print(f"  .meta        : spriteBorder: {{x: {l}, y: {b}, z: {r}, w: {t}}}   (x=left y=bottom z=right w=top)")
    print(f"  verify       : python verify_slice.py <backup.png> <asset.png> --border {l},{b},{r},{t} "
          f"--type {'tiled' if 'tiled' in kinds else 'sliced'} --size <W>x<H> per displayed size")


if __name__ == "__main__":
    main()
