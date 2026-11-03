"""Draws the simple scene diagrams for the synthetic cases. They are illustrations made for the demo, not photographs, and are labelled as such."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
W, H = 1100, 760
PAPER, INK, WALL, ACCENT, SOFT = "#f6f3ea", "#1f2937", "#374151", "#b91c1c", "#9ca3af"


def font(size):
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def canvas(title):
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    d.text((30, 20), title, fill=INK, font=font(26))
    d.text((30, 56), "Illustration for a fictional case. Not a photograph, not to scale.", fill=SOFT, font=font(16))
    return img, d


def room(d, x, y, w, h, label, sub=None):
    d.rectangle([x, y, x + w, y + h], outline=WALL, width=5, fill="#ffffff")
    d.text((x + 10, y + 8), label, fill=INK, font=font(20))
    if sub:
        d.text((x + 10, y + 34), sub, fill=SOFT, font=font(15))


def door(d, x, y, horizontal, label=None):
    if horizontal:
        d.rectangle([x, y - 4, x + 60, y + 4], fill=PAPER)
        d.line([x, y, x + 60, y], fill=ACCENT, width=3)
    else:
        d.rectangle([x - 4, y, x + 4, y + 60], fill=PAPER)
        d.line([x, y, x, y + 60], fill=ACCENT, width=3)
    if label:
        d.text((x + 6, y + 8), label, fill=ACCENT, font=font(14))


def item(d, x, y, w, h, label, fill="#d1d5db"):
    d.rectangle([x, y, x + w, y + h], outline=INK, width=2, fill=fill)
    d.text((x + 4, y + 2), label, fill=INK, font=font(13))


def burglary():
    img, d = canvas("Kestrel Trade Supplies, Unit 4 (fictional) - ground floor")
    room(d, 100, 440, 400, 280, "Showroom / trade counter", "about 8 m x 6 m")
    room(d, 100, 120, 500, 320, "Stockroom", "about 10 m x 8 m")
    room(d, 600, 120, 200, 200, "Office", "about 4 m x 4 m")
    item(d, 130, 160, 60, 270, "racking", "#e5e7eb")
    item(d, 735, 130, 55, 55, "safe", "#9ca3af")
    item(d, 620, 220, 90, 40, "desk")
    door(d, 280, 440, True, "internal door")
    door(d, 600, 200, False, "office door")
    door(d, 280, 720, True, "customer door")
    d.rectangle([95, 270, 105, 330], fill=ACCENT)
    d.text((20, 335), "side window (entry)", fill=ACCENT, font=font(16))
    d.rectangle([595, 330, 605, 390], fill=SOFT)
    d.text((610, 395), "roller loading door (locked)", fill=SOFT, font=font(14))
    d.text((20, 120), "service lane", fill=SOFT, font=font(16))
    img.save(HERE / "burglary_warehouse" / "00_floor_diagram.png")


def road():
    img, d = canvas("Harbour Road / Mill Street crossroads (fictional)")
    d.rectangle([0, 300, W, 460], fill="#4b5563")
    d.rectangle([470, 90, 630, H], fill="#4b5563")
    d.rectangle([470, 300, 630, 460], fill="#6b7280")
    for x in range(40, 440, 60):
        d.line([x, 380, x + 30, 380], fill="#fbbf24", width=3)
    for x in range(660, 1060, 60):
        d.line([x, 380, x + 30, 380], fill="#fbbf24", width=3)
    for y in range(120, 280, 50):
        d.line([550, y, 550, y + 25], fill="#fbbf24", width=3)
    for y in range(500, 740, 50):
        d.line([550, y, 550, y + 25], fill="#fbbf24", width=3)
    item(d, 300, 320, 90, 36, "parked van", "#e5e7eb")
    item(d, 560, 340, 70, 34, "V1 hatchback (westbound)", "#1d4ed8")
    item(d, 497, 150, 26, 60, "V2", "#f59e0b")
    d.text((20, 470), "Harbour Road (east-west)", fill="#ffffff", font=font(18))
    d.text((640, 120), "Mill Street (north-south)", fill="#ffffff", font=font(18))
    d.text((60, 250), "signals on all four arms, crossing on the south arm", fill=INK, font=font(16))
    d.line([497, 460, 497, 690], fill="#ef4444", width=4)
    d.text((300, 700), "braking mark 11.5 m from the northbound stop line", fill=ACCENT, font=font(16))
    img.save(HERE / "road_accident_junction" / "00_junction_diagram.png")


def assault():
    img, d = canvas("Halcyon Design Studio, second floor (fictional)")
    room(d, 80, 300, 540, 380, "Open-plan studio", "about 9 m x 7 m")
    room(d, 80, 180, 540, 120, "Corridor", "1.5 m wide, about 9 m long")
    room(d, 620, 180, 200, 200, "Storeroom", "about 3 m x 3 m")
    room(d, 620, 380, 200, 200, "Kitchenette", "about 3 m x 3 m")
    item(d, 760, 190, 55, 80, "cabinet", "#9ca3af")
    item(d, 640, 300, 90, 40, "shelves", "#e5e7eb")
    door(d, 620, 220, False, "storeroom door")
    door(d, 300, 300, True, "studio door")
    door(d, 620, 440, False, "kitchen door")
    d.text((90, 140), "stair + lift lobby (west), glass entrance door", fill=SOFT, font=font(16))
    d.rectangle([75, 190, 85, 250], fill=ACCENT)
    d.ellipse([100, 215, 118, 233], outline=INK, width=3)
    d.text((124, 215), "camera CAM-CORR-01 looks east", fill=INK, font=font(14))
    img.save(HERE / "indoor_assault_office" / "00_floor_diagram.png")


if __name__ == "__main__":
    burglary()
    road()
    assault()
    print("diagrams written")
