"""render.py [x0 y0 x1 y1 dpi name]  -> render/<name>.png ; coordinates in sheet units (2.54 mm)"""
import sys, glob, os
import fitz
H = os.path.dirname(os.path.abspath(__file__)); R = os.path.join(H, "..", "render")
d = fitz.open(glob.glob(os.path.join(R, "*.svg"))[0]); page = d[0]
if len(sys.argv) > 1:
    x0, y0, x1, y1, dpi, name = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), int(float(sys.argv[5])), sys.argv[6]
    k = 2.54 / 25.4 * 72
    clip = fitz.Rect(x0 * k, y0 * k, x1 * k, y1 * k)
else:
    clip, dpi, name = page.rect, 24, "full"
pix = page.get_pixmap(dpi=dpi, clip=clip)
pix.save(os.path.join(R, name + ".png")); print(name, pix.width, pix.height, page.rect)
