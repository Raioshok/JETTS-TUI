"""Reusable surgical edits for the nous removal. Deterministic, boundary-safe.

Usage:
  python _surg.py delfn <file> <fnname> [<fnname> ...]     delete top-level def(s)
  python _surg.py delimport <file> <symbol> [<symbol> ...] drop `symbol` from any
                                                           import (line or tuple member)
  python _surg.py dropmember <file> <token>               drop "token" from a set/
                                                           list/frozenset literal
  python _surg.py rmlines <file> <regex>                  delete lines matching regex
"""
import re
import sys


def read(path):
    return open(path, encoding="utf-8").read()


def write(path, s):
    open(path, "w", encoding="utf-8", newline="").write(s)


def delfn(path, names):
    lines = read(path).split("\n")
    for name in names:
        start = None
        for i, l in enumerate(lines):
            if re.match(rf"(async )?def {re.escape(name)}\s*\(", l) and not l[:1].isspace():
                start = i
                break
        if start is None:
            print(f"  ! {name}: not found (skipped)")
            continue
        # absorb a decorator/comment block immediately above
        while start > 0 and (lines[start - 1].startswith("@") or lines[start - 1].startswith("#")):
            start -= 1
        end = len(lines)
        for j in range(
            (i := next(k for k, l in enumerate(lines) if re.match(rf"(async )?def {re.escape(name)}\s*\(", l))) + 1,
            len(lines),
        ):
            if lines[j] and not lines[j][0].isspace() and not lines[j].startswith(")"):
                end = j
                break
        # trim trailing blank lines that belonged to the fn
        while end - 1 > start and lines[end - 1].strip() == "":
            end -= 1
        del lines[start:end]
        print(f"  - {name}: removed lines {start+1}..{end}")
    write(path, "\n".join(lines))


def delimport(path, symbols):
    text = read(path)
    for sym in symbols:
        # tuple member on its own line:  `    SYM,`  inside from-import parens
        text = re.sub(rf"(?m)^[ \t]*{re.escape(sym)},[ \t]*(#.*)?\n", "", text)
        # single-name import line:  `from x import SYM` / `import SYM`
        text = re.sub(rf"(?m)^[ \t]*from [\w.]+ import {re.escape(sym)}[ \t]*(#.*)?\n", "", text)
        text = re.sub(rf"(?m)^[ \t]*import {re.escape(sym)}([ \t]+as [\w]+)?[ \t]*(#.*)?\n", "", text)
    write(path, text)
    print(f"  delimport {symbols}: done")


def dropmember(path, token):
    text = read(path)
    # "token", | 'token', | , "token" | {"token"}  — remove the literal + a comma
    for pat in (rf'"{re.escape(token)}",\s*', rf"'{re.escape(token)}',\s*",
                rf',\s*"{re.escape(token)}"', rf",\s*'{re.escape(token)}'"):
        text = re.sub(pat, "", text)
    write(path, text)
    print(f"  dropmember {token!r}: done")


def rmlines(path, regex):
    rx = re.compile(regex)
    lines = read(path).split("\n")
    kept = [l for l in lines if not rx.search(l)]
    write(path, "\n".join(kept))
    print(f"  rmlines /{regex}/: removed {len(lines)-len(kept)}")


if __name__ == "__main__":
    op = sys.argv[1]
    path = sys.argv[2]
    rest = sys.argv[3:]
    {"delfn": lambda: delfn(path, rest),
     "delimport": lambda: delimport(path, rest),
     "dropmember": lambda: dropmember(path, rest[0]),
     "rmlines": lambda: rmlines(path, rest[0])}[op]()
