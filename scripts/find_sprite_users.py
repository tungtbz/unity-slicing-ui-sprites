"""List every uGUI Image that shows a sprite, at what size and type, and every script that names it.

usage: python find_sprite_users.py <path/to/Sprite.png>     (run from the Unity project root)

Follows the sprite into prefab instances, nested prefabs and variants (an object of instance I
from source object S has fileID (I ^ S) & 0x7fff...), and prints for each place the Image's
m_Type / preserveAspect / pixelsPerUnitMultiplier, its RectTransform size and scale, and any
instance override of those. Ends with the .cs files (Editor builders, tests) naming the sprite.
"""
import glob
import os
import re
import sys

MASK = 0x7FFFFFFFFFFFFFFF
DOC = re.compile(r"^--- !u!(\d+) &(-?\d+)( stripped)?[^\n]*\n(.*?)(?=^--- |\Z)", re.S | re.M)
MOD = re.compile(r"- target: \{fileID: (-?\d+), guid: (\w+), type: 3\}\n\s+propertyPath: ([^\n]+)\n"
                 r"\s+value: ([^\n]*)\n\s+objectReference: ([^\n]*)")
WATCH = re.compile(r"^(m_Sprite|m_Type|m_PreserveAspect|m_PixelsPerUnitMultiplier|m_SizeDelta\.\w|m_LocalScale\.\w|"
                   r"m_Anchor(Min|Max)\.\w|m_IsActive)$")


def field(body, key):
    m = re.search(rf"^\s*{key}: ([^\n]*)", body, re.M)
    return m.group(1) if m else "?"


def load(path, cache={}):
    if path not in cache:
        txt = open(path, encoding="utf-8", errors="replace").read()
        cache[path] = {m.group(2): (m.group(1), m.group(4), bool(m.group(3))) for m in DOC.finditer(txt)}
    return cache[path]


def guid_of(path):
    return re.search(r"guid: (\w+)", open(path + ".meta", encoding="utf-8").read()).group(1)


def rt_of_go(docs, go):
    for fid, (t, b, _) in docs.items():
        if t == "224" and f"m_GameObject: {{fileID: {go}}}" in b:
            return fid
    return None


def describe_image(path, docs, fid):
    b = docs[fid][1]
    go = field(b, "m_GameObject").strip("{}").split(": ")[-1]
    name = field(docs[go][1], "m_Name") if go in docs else "?"
    rt = rt_of_go(docs, go)
    size = f"size {field(docs[rt][1], 'm_SizeDelta')} anchors {field(docs[rt][1], 'm_AnchorMin')}-" \
           f"{field(docs[rt][1], 'm_AnchorMax')} scale {field(docs[rt][1], 'm_LocalScale')}" if rt else ""
    print(f"  {path}: Image on '{name}' m_Type={field(b, 'm_Type')} preserveAspect={field(b, 'm_PreserveAspect')} "
          f"ppuMultiplier={field(b, 'm_PixelsPerUnitMultiplier')} {size}")
    if rt and re.search(r"[xy]: 0[,}]", field(docs[rt][1], "m_SizeDelta")):
        print("      a size of 0 means a stretch anchor or a parent layout group (cell size, child control) sets it")
    return rt


def main():
    png = sys.argv[1].replace("\\", "/")
    guid = guid_of(png)
    name = os.path.splitext(os.path.basename(png))[0]
    files = [f.replace("\\", "/") for ext in ("prefab", "unity") for f in glob.glob(f"Assets/**/*.{ext}", recursive=True)]
    prefab_guid = {}
    for f in files:
        if f.endswith(".prefab") and os.path.exists(f + ".meta"):
            prefab_guid[guid_of(f)] = f

    print(f"sprite {png} guid {guid}\n\nImages that reference it directly or by override:")
    targets = []  # (prefab guid, image fileID, rect fileID) whose instances must be checked
    for f in files:
        if guid not in open(f, encoding="utf-8", errors="replace").read():
            continue
        docs = load(f)
        for fid, (t, b, stripped) in docs.items():
            if t == "114" and not stripped and f"guid: {guid}" in field(b, "m_Sprite"):
                rt = describe_image(f, docs, fid)
                if f.endswith(".prefab"):
                    targets.append((guid_of(f), fid, rt))
            if t == "1001":
                for tid, tguid, prop, val, ref in MOD.findall(b):
                    if prop == "m_Sprite" and guid in ref:
                        src = prefab_guid.get(tguid, tguid)
                        print(f"  {f}: override on instance &{fid} of {src}, Image &{tid}")
                        rt = None
                        if src.endswith(".prefab"):
                            sd = load(src)
                            if tid in sd:
                                rt = describe_image(src + " (source)", sd, tid)
                        if f.endswith(".prefab"):
                            mine = lambda x: str((int(fid) ^ int(x)) & MASK) if x else None
                            targets.append((guid_of(f), mine(tid), mine(rt)))

    print("\nInstances / variants of those prefabs (overrides on that Image or its RectTransform):")
    seen = set()
    while targets:
        pg, img, rt = targets.pop()
        if (pg, img) in seen:
            continue
        seen.add((pg, img))
        for f in files:
            docs = load(f)
            for fid, (t, b, _) in docs.items():
                if t != "1001" or f"m_SourcePrefab: {{fileID: 100100000, guid: {pg}," not in b:
                    continue
                inst = re.search(r"propertyPath: m_Name\n\s+value: ([^\n]*)", b)
                print(f"  {f}: instance &{fid} of {prefab_guid.get(pg, pg)} ({inst.group(1) if inst else '-'})")
                for tid, tguid, prop, val, ref in MOD.findall(b):
                    if tguid == pg and tid in (img, rt) and WATCH.match(prop):
                        print(f"      {'Image' if tid == img else 'Rect'}.{prop} = {val} {ref if 'guid' in ref else ''}")
                if f.endswith(".prefab"):
                    targets.append((guid_of(f), str((int(fid) ^ int(img)) & MASK),
                                    str((int(fid) ^ int(rt)) & MASK) if rt else None))

    print("\nScripts naming the sprite (Editor builders reset Image.type when re-run; tests may assert it):")
    for cs in glob.glob("Assets/**/*.cs", recursive=True):
        txt = open(cs, encoding="utf-8", errors="replace").read()
        for i, line in enumerate(txt.splitlines(), 1):
            if name in line or guid in line:
                print(f"  {cs.replace(os.sep, '/')}:{i}: {line.strip()[:140]}")


if __name__ == "__main__":
    main()
