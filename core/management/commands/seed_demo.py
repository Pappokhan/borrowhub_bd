"""Create categories, demo members and sample listings with generated photos."""
import io
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw, ImageFont

from accounts.models import User
from core.models import SiteSetting
from listings.models import Category, Listing, ListingImage

CATEGORIES = [
    ("Projectors & Screens", "projectors", "bi-projector", "#0b7a55"),
    ("Cameras & Lenses", "cameras", "bi-camera", "#1f4e79"),
    ("Audio & Microphones", "audio", "bi-mic", "#8e3b7a"),
    ("Tripods & Lighting", "tripods-lighting", "bi-lightbulb", "#b7791f"),
    ("Laptops & Computers", "laptops", "bi-laptop", "#2d3748"),
    ("Gaming Consoles", "gaming", "bi-controller", "#c0392b"),
    ("Event Equipment", "event", "bi-balloon", "#d6336c"),
    ("Tools & Others", "tools", "bi-tools", "#4a5568"),
]

# title, category slug, brand, price/day, deposit, city, area, condition, delivery, fee, owner index, description
ITEMS = [
    ("Epson Full HD Projector 3600 lumens", "projectors", "Epson EB-W49", 1200, 5000, "Dhaka", "Dhanmondi", "good", True, 200, 0,
     "Bright 3600-lumen projector, perfect for office presentations, birthday movie nights and small events. HDMI + VGA cables and carry bag included."),
    ("Canon EOS 80D DSLR + 18-135mm lens", "cameras", "Canon EOS 80D", 1800, 15000, "Dhaka", "Mirpur", "like_new", True, 250, 1,
     "24MP DSLR with a versatile kit lens, two batteries, charger and a 64GB card. Great for weddings, holud and product shoots."),
    ("Shure SM58 Wired Microphone (x2)", "audio", "Shure SM58", 500, 3000, "Dhaka", "Uttara", "good", False, 0, 2,
     "A pair of legendary SM58 vocal mics with stands and XLR cables. Ideal for programs, gaan-bajna and school events."),
    ("Heavy Duty Camera Tripod 1.8m", "tripods-lighting", "Manfrotto", 300, 1500, "Gazipur", "Tongi", "good", True, 100, 1,
     "Sturdy aluminium tripod with fluid head. Holds up to 8kg — works for DSLRs, video cameras and small projectors."),
    ("JBL PartyBox 310 Bluetooth Speaker", "audio", "JBL PartyBox 310", 2500, 10000, "Chattogram", "GEC Circle", "like_new", True, 300, 2,
     "240W party speaker with light show, 18-hour battery and mic input. Brings the roof down at any gathering."),
    ("MacBook Pro 14\" M1 Pro", "laptops", "Apple MacBook Pro", 2200, 25000, "Dhaka", "Gulshan", "like_new", False, 0, 0,
     "16GB RAM, 512GB SSD. Handy for video editing deadlines, hackathons or when your own laptop is in the shop."),
    ("PlayStation 5 + 2 controllers + 3 games", "gaming", "Sony PS5", 1500, 20000, "Dhaka", "Bashundhara R/A", "good", True, 200, 1,
     "Disc edition PS5 with FIFA, Spider-Man and Gran Turismo. HDMI cable and charging dock included."),
    ("Wedding Stage Light Set (8 PAR LEDs)", "event", "Generic LED PAR", 2000, 8000, "Narayanganj", "Fatullah", "good", True, 400, 2,
     "Eight RGB PAR lights with DMX controller and stands. Transform any hall or rooftop for your event."),
    ("Portable Projector Screen 100\" tripod", "projectors", "Elite Screens", 400, 2000, "Dhaka", "Mohammadpur", "good", True, 100, 0,
     "Quick-setup 100-inch tripod screen with carry bag. Pairs well with our projector listing."),
    ("DJI Ronin-SC Gimbal Stabilizer", "cameras", "DJI Ronin-SC", 1400, 12000, "Sylhet", "Zindabazar", "like_new", False, 0, 1,
     "3-axis gimbal for mirrorless cameras. Get cinematic smooth video for vlogs and wedding films."),
    ("Folding Chairs & Tables Bundle (50 chairs)", "event", "Local", 1800, 5000, "Gazipur", "Joydebpur", "fair", True, 600, 2,
     "50 folding chairs and 6 tables for adda, milad, aqiqah and community programs. Delivery recommended."),
    ("Bosch Drill Machine + Bit Set", "tools", "Bosch GSB 500", 350, 2000, "Dhaka", "Uttara", "good", True, 80, 0,
     "Impact drill with 40-piece bit set. Perfect for weekend furniture assembly or wall mounting."),
]


def make_image(title, color, subtitle, size=(900, 675)):
    w, h = size
    base = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(base)
    for y in range(h):  # soft vertical shade
        shade = int(70 * y / h)
        draw.line([(0, y), (w, y)], fill=(max(0, int(color[1:3], 16) - shade), max(0, int(color[3:5], 16) - shade),
                                          max(0, int(color[5:7], 16) - shade)))
    draw.ellipse([w * 0.58, -h * 0.25, w * 1.2, h * 0.5], fill=tuple(min(255, int(color[i:i + 2], 16) + 35) for i in (1, 3, 5)))
    big, small = ImageFont.load_default(size=54), ImageFont.load_default(size=28)
    words, lines, cur = title.split(), [], ""
    for word in words:
        if len(cur + " " + word) > 24:
            lines.append(cur.strip())
            cur = word
        else:
            cur += " " + word
    lines.append(cur.strip())
    y = h * 0.52 - 30 * len(lines)
    for line in lines[:3]:
        draw.text((60, y), line, font=big, fill="white")
        y += 66
    draw.text((60, h - 90), subtitle, font=small, fill=(255, 255, 255))
    buf = io.BytesIO()
    base.save(buf, "JPEG", quality=85)
    return ContentFile(buf.getvalue())


class Command(BaseCommand):
    help = "Load demo categories, members and listings (safe to run once)."

    def handle(self, *args, **options):
        SiteSetting.load()
        colors = {}
        for i, (name, slug, icon, color) in enumerate(CATEGORIES):
            Category.objects.get_or_create(slug=slug, defaults={"name": name, "icon": icon, "order": i})
            colors[slug] = color

        owners = []
        people = [("rahim", "Rahim", "Uddin", "Dhaka"), ("nusrat", "Nusrat", "Jahan", "Dhaka"),
                  ("tanvir", "Tanvir", "Hasan", "Chattogram")]
        for uname, first, last, city in people:
            user, created = User.objects.get_or_create(username=uname, defaults={
                "email": f"{uname}@example.com", "first_name": first, "last_name": last,
                "phone": "01712345678", "city": city, "area": "Central", "payout_method": "bkash",
                "payout_account": "01712345678", "verification_status": "verified"})
            if created:
                user.set_password("demo12345")
                user.save()
            owners.append(user)
        renter, created = User.objects.get_or_create(username="renter", defaults={
            "email": "renter@example.com", "first_name": "Sabbir", "last_name": "Ahmed",
            "phone": "01812345678", "city": "Dhaka", "area": "Banani", "payout_account": "01812345678"})
        if created:
            renter.set_password("demo12345")
            renter.save()

        made = 0
        for (title, cat, brand, price, dep, city, area, cond, deliv, fee, owner_i, desc) in ITEMS:
            if Listing.objects.filter(title=title).exists():
                continue
            listing = Listing.objects.create(
                owner=owners[owner_i], category=Category.objects.get(slug=cat), title=title, brand=brand,
                description=desc, condition=cond, price_per_day=Decimal(price), security_deposit=Decimal(dep),
                min_days=1, max_days=14, city=city, area=area, pickup_available=True,
                delivery_available=deliv, delivery_fee=Decimal(fee), is_featured=made < 4,
                rules="Handle with care. Return on time and in the same condition. Late return is charged per extra day.")
            img = ListingImage(listing=listing, order=0)
            img.image.save(f"{listing.slug}.jpg", make_image(title, colors[cat], f"৳{price}/day · {city}"), save=True)
            made += 1
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {made} listings. Demo logins (password demo12345): rahim, nusrat, tanvir (owners), renter."))
