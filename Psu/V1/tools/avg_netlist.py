"""Fast (averaged-power-stage) version of the Lab PSU V1 netlist, ~100x quicker than the 100 ns switching sim.

Usage:
  kicad-cli sch export netlist --format spice -o full.cir V1.kicad_sch
  python avg_netlist.py full.cir fast.cir [tstop=100m] [tmax=5u] [series_R=0.23]
  ngspice -b fast.cir        (or run the netlist from any ngspice front end)

series_R (ohm) is the equivalent power-stage loss, calibrated against the full switching run: 0.23 reproduces the
real converter's marginal ~1 kHz ringing, 0.10 is a pessimistic case. Use both when judging stability.
Removes the two half-bridges, gate drive and the ramp/PWM comparators; replaces them with an algebraic PWM
(ramp window 1.79..3.90 V measured in the switching sim) and an averaged (DC-transformer) model of the legs around L1.
Not modelled: switching ripple, dead time, bootstrap limits. Control, soft-start, timer and relay logic are unchanged.
"""
"""Turn the exported full netlist into a fast averaged-power-stage netlist for control-loop checks.

Removed: both half-bridges + gate drive/bootstrap (switching islands) and the ramp oscillator + PWM comparators.
Added  : algebraic PWM (duty from the comparator inputs vs the measured ramp window) and a DC-transformer
         (averaged PWM-switch) model of the two legs around L1.
"""
import re
import sys

src, dst = sys.argv[1], sys.argv[2]
tstop = sys.argv[3] if len(sys.argv) > 3 else "100m"
tmax = sys.argv[4] if len(sys.argv) > 4 else "5u"
VLO, VHI = 1.79, 3.90
RSER = float(sys.argv[5]) if len(sys.argv) > 5 else 0.0        # ramp window measured in the switching simulation

lines = [l.rstrip("\r\n") for l in open(src, encoding="utf-8")]
# join continuation lines
joined = []
for l in lines:
    if l.startswith("+") and joined:
        joined[-1] += " " + l[1:].strip()
    else:
        joined.append(l)


def nodes_of(l):
    tok = l.split()
    if not tok or tok[0][0] in ".*":
        return None, []
    k = tok[0][0].upper()
    if k in "RCLDVIB":
        return tok[0], tok[1:3]
    if k == "X":
        end = len(tok)
        for i, t in enumerate(tok):
            if "=" in t and i > 1:
                end = i - 1
                break
        return tok[0], tok[1:end - 1] if end == len(tok) else tok[1:end]
    return tok[0], []


def fix_x(l):
    tok = l.split()
    end = len(tok)
    for i, t in enumerate(tok):
        if "=" in t and i > 1:
            end = i
            break
    # subckt name is tok[end-1]
    return tok[0], tok[1:end - 1]


GLOBAL = {"0", "gnd", "+12v", "+3v3", "+3.3va", "/powerstage/hv_bus", "/powerstage/before", "/powerstage/out", "+hv",
          "net-_d2-a_", "/analogctl/drv_in", "/analogctl/drv_in2"}

elems = []
for l in joined:
    tok = l.split()
    if not tok or tok[0][0] in ".*":
        elems.append((l, None, []))
        continue
    if tok[0][0].upper() == "X":
        name, nn = fix_x(l)
    else:
        name, nn = nodes_of(l)
    elems.append((l, name, [n.lower() for n in nn]))

# --- seed: switching legs + ramp/PWM generator
kill_names = {"XU1", "XU9", "XQ1", "XQ2", "XQ4", "XQ5",
              "XU109", "XU110", "XU111", "XQ106", "XQ107", "XQ108", "C108", "R140", "R143", "R144", "R145", "R160", "R161", "R162", "R163", "R164",
              "R146", "R147"}
killed = [e for e in elems if e[1] and e[1].upper() in kill_names]
island = {"net-_q1-s_", "net-_q4-s_", "net-_d4-a_", "net-_d4-k_", "net-_d5-a_", "net-_d5-k_", "net-_d15-a_", "net-_d15-k_",
          "net-_d16-k_", "net-_d17-a_", "net-_d17-k_", "net-_d3-k_", "net-_u1-vb_", "net-_u9-vb_", "net-_c9-pad1_", "net-_c66-pad1_"}
removed = {e[1] for e in killed}
for l, name, nn in elems:
    if not name or name == "L1":
        continue
    if any(n in island for n in nn):
        removed.add(name)

out = []
for l, name, nn in elems:
    if name and name in removed:
        continue
    if name == "L1":
        tok = l.split()
        out.append("L1 %s nIL %s" % (tok[1], tok[3]))
        out.append("RLS nIL nIL2 %g" % max(RSER, 1e-6))
        out.append("VIL nIL2 %s 0" % tok[2])
        continue
    out.append(l)

# --- time control
out = [re.sub(r"^\.tran.*", ".tran %s %s 0 %s" % (tmax, tstop, tmax), l) if l.lower().startswith(".tran") else l for l in out]
out = [re.sub(r"^\.options.*", ".options reltol=1e-3 itl4=100 gmin=1e-10", l) if l.lower().startswith(".options") else l for l in out]

model = f"""
* ---------------- averaged power stage (replaces the two half-bridges + PWM generator) ----------------
* enable = driver SD net (DRV_EN and no fault)
Ben en 0 V = 0.5*(1+tanh((V(net-_d2-a_)-1.8)/0.05))
* duty of the bus-side leg:  DRV_IN high while  D109-A > ramp   (ramp window {VLO}..{VHI} V)
Bd1 d1 0 V = V(en)*min(max((V(net-_d109-a_)-{VLO})/({VHI}-{VLO}),0),1)
* duty of the output-side leg: DRV_IN2 high while ramp > Net-(U110--)
Bd2 d2 0 V = V(en)*min(max(({VHI}-V(net-_u110--_))/({VHI}-{VLO}),0),1)
* leg 1 : bus -> L1 (DC transformer)
Bsw1 net-_q1-s_ 0 V = V(d1)*V(/powerstage/hv_bus)
Bibus /powerstage/hv_bus 0 I = V(d1)*I(VIL)
* leg 2 : L1 -> output (Q4 on = connected to BEFORE, Q5 on = to GND)
Bsw2 net-_q4-s_ 0 V = V(d2)*V(/powerstage/before)
Bibef 0 /powerstage/before I = V(d2)*I(VIL)
"""
# insert before .end
idx = max(i for i, l in enumerate(out) if l.strip().lower() == ".end")
out[idx:idx] = model.strip("\n").split("\n")
open(dst, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
print("removed elements:", len(removed), sorted(removed))
print("island nodes:", sorted(island))
