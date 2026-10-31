"""Minimal S-expression reader/writer for KiCad files.

Atoms are kept as raw text: quoted strings keep their quotes, so writing a parsed tree back gives the
same tokens.  Lists are Python lists.
"""
import re

_TOK = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')


def parse(text):
    stack = [[]]
    for m in _TOK.finditer(text):
        t = m.group(0)
        if t == "(":
            stack.append([])
        elif t == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(t)
    return stack[0]


def dump(node, indent=0):
    if not isinstance(node, list):
        return node
    if all(not isinstance(c, list) for c in node):
        return "(" + " ".join(node) + ")"
    pad = "\t" * (indent + 1)
    parts = []
    head = []
    for c in node:
        if isinstance(c, list):
            break
        head.append(c)
    out = "(" + " ".join(head)
    for c in node[len(head):]:
        out += "\n" + pad + dump(c, indent + 1)
    return out + "\n" + "\t" * indent + ")"


def q(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def unq(s):
    return s[1:-1].replace('\\"', '"').replace("\\\\", "\\") if s.startswith('"') else s


def find(node, key):
    """First child list whose head is `key`."""
    for c in node:
        if isinstance(c, list) and c and c[0] == key:
            return c
    return None


def find_all(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]
