"""Run a SPICE netlist with the ngspice.dll that ships with KiCad and return the vectors.

    from ngrun import run
    vecs, log = run(netlist_text, ["time", "v(outa)", ...])

Used to check the D-V1 design outside KiCad, and by check_sim.py on the netlist KiCad itself exports.
"""
import ctypes, os, sys
from ctypes import (CFUNCTYPE, POINTER, Structure, c_bool, c_char_p, c_double, c_int, c_short, c_void_p,
                    byref, cast)

DLL = r"C:\Program Files\KiCad\10.0\bin\ngspice.dll"


class VecInfo(Structure):
    _fields_ = [("name", c_char_p), ("type", c_int), ("flags", c_short), ("realdata", POINTER(c_double)),
                ("compdata", c_void_p), ("length", c_int)]


SEND_CHAR = CFUNCTYPE(c_int, c_char_p, c_int, c_void_p)
SEND_STAT = CFUNCTYPE(c_int, c_char_p, c_int, c_void_p)
CTRL_EXIT = CFUNCTYPE(c_int, c_int, c_bool, c_bool, c_int, c_void_p)


def run(netlist, wanted, quiet=True, extra_cmds=("run",), cwd=None):
    """netlist: text (no .end needed).  wanted: vector names.  Returns ({name: list}, log text)."""
    old = os.getcwd()
    os.add_dll_directory(os.path.dirname(DLL))
    lib = ctypes.CDLL(DLL)
    lib.ngGet_Vec_Info.restype = POINTER(VecInfo)
    lib.ngGet_Vec_Info.argtypes = [c_char_p]
    log = []

    def on_char(s, _id, _u):
        log.append(s.decode(errors="replace"))
        return 0

    def on_stat(s, _id, _u):
        return 0

    def on_exit(*a):
        return 0

    cb = (SEND_CHAR(on_char), SEND_STAT(on_stat), CTRL_EXIT(on_exit))
    lib.ngSpice_Init(cb[0], cb[1], cb[2], None, None, None, None)
    if cwd:
        os.chdir(cwd)
    try:
        lines = [l for l in netlist.splitlines()]
        arr = (c_char_p * (len(lines) + 2))()
        for i, l in enumerate(lines):
            arr[i] = l.encode()
        arr[len(lines)] = b".end"
        arr[len(lines) + 1] = None
        lib.ngSpice_Circ(arr)
        for c in extra_cmds:
            lib.ngSpice_Command(c.encode())
        out = {}
        for n in wanted:
            vi = lib.ngGet_Vec_Info(n.encode())
            if not vi:
                out[n] = None
                continue
            v = vi.contents
            out[n] = [v.realdata[i] for i in range(v.length)]
        return out, "".join(log)
    finally:
        os.chdir(old)
