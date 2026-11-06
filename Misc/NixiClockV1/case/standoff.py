"""NixiClockV1 bottom plate with stand-offs. PCB screws down onto it from above (M3 x 16 from the top, M3 nut in the pocket underneath).

Plan view = PCB seen from the top. KiCad y points to the front, so model Y = 60 - (y - 100).
Run with the nixicase venv (CadQuery): python standoff.py
"""
import cadquery as cq

PCB_W, PCB_H = 128.0, 60.0                 # board outline, KiCad origin (100, 100)
HOLES = [(104, 104), (176, 104), (104, 156), (224, 156)]   # M3 holes, KiCad coordinates

PLATE_T = 4.0          # solid plate thickness
POST_H = 8.0           # stand-off height: clears solder joints and trimmed tube / connector leads
POST_D = 7.0           # post outer diameter
HOLE_D = 3.4           # M3 clearance, straight through post and plate
NUT_AF = 5.5 + 0.3     # M3 nut across flats + print clearance
NUT_DEPTH = 2.6        # M3 nut is 2.4 mm thick; pocket is open at the bottom of the plate
CORNER_R = 2.0


def to_model(x, y):
    return x - 100.0, PCB_H - (y - 100.0)


plate = (cq.Workplane("XY").box(PCB_W, PCB_H, PLATE_T, centered=False)
         .edges("|Z").fillet(CORNER_R))

pts = [to_model(x, y) for x, y in HOLES]
posts = (cq.Workplane("XY").workplane(offset=PLATE_T).pushPoints(pts)
         .circle(POST_D / 2).extrude(POST_H))
body = plate.union(posts)

body = (body.faces(">Z").workplane(origin=(0, 0, PLATE_T + POST_H)).pushPoints(pts)
        .hole(HOLE_D))
nuts = (cq.Workplane("XY").pushPoints(pts)
        .polygon(6, NUT_AF / 0.8660254).extrude(NUT_DEPTH))  # polygon() takes the circumscribed diameter
body = body.cut(nuts)

cq.exporters.export(body, "standoff.step")
cq.exporters.export(body, "standoff.stl")
bb = body.val().BoundingBox()
print(f"size {bb.xlen:.1f} x {bb.ylen:.1f} x {bb.zlen:.1f} mm, volume {body.val().Volume()/1000:.1f} cm3, holes {pts}")
