"""Pictures for the demonstration catalogue.

The seeded assortment used to show a generated cross-stitch chart wherever a
photograph belongs, on every tile and every product page. The chart is honest but
it tells a shopper nothing about the goods, so the demo shop read as unfinished.

This module attaches one picture per seeded product and one per seeded maker from
files carried in `app/assets/catalogue/`. **They are generated demonstration
images, not photographs of goods in stock**: the shop says so in the placeholder
line at the foot of every page, in `/llms.txt`, `/llms-full.txt` and `/api/catalog`,
and each row keeps `seed-generated/<slug>.webp` as its original file name so the
same thing is visible in `/admin`. When the owner uploads a real photograph, the
real one takes position 0 and this one can be deleted like any other.

Insert-only, like the catalogue seed itself: a product that already carries a
photo is never touched, and a maker who already has a picture keeps it.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Maker, Product, ProductImage
from . import media

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "catalogue"

# Alt text is what a person using a screen reader gets instead of the picture, and
# what an answer engine quotes. It describes what is in the frame — the piece, its
# technique and its colours — and never repeats the product title alone.
PRODUCT_ALT: dict[str, tuple[str, str]] = {
    "kosiv-nyzynka-blouse": (
        "A white linen blouse laid flat, sleeves spread; both sleeve panels are worked in dense brick-red and black nyzynka diamonds, the neckline gathered on a drawstring.",
        "Біла лляна блуза розкладена на полотні, рукави розправлені; обидві уставки щільно вишиті цегляно-чорними низинковими ромбами, горловина зібрана на шнурок.",
    ),
    "borshchiv-black-blouse": (
        "A flax linen blouse with sleeves covered in black wool embroidery so dense it stands off the cloth; no second colour anywhere on the piece.",
        "Лляна блуза з рукавами, вкритими чорною вовняною вишивкою такої щільності, що вона стоїть над полотном; іншого кольору на сорочці немає.",
    ),
    "reshetylivka-whitework-blouse": (
        "A white linen blouse embroidered white on white: raised satin stitch and cut openwork show as texture only, with no colour in the pattern.",
        "Біла лляна блуза, вишита білим по білому: рельєфна гладь і мережка видно лише як фактуру, кольору у візерунку немає.",
    ),
    "kosiv-mens-shirt": (
        "A man's flax linen shirt with a stand collar, the chest panel and cuffs worked in brick-red and black geometric nyzynka.",
        "Чоловіча лляна сорочка з коміром-стійкою, манишка й манжети вишиті цегляно-чорною геометричною низинкою.",
    ),
    "borshchiv-mens-shirt": (
        "A man's flax linen shirt with a narrow band of black cross-stitch along the collar, the chest placket and the cuffs.",
        "Чоловіча лляна сорочка з вузькою смугою чорного хрестика по коміру, планці та манжетах.",
    ),
    "everyday-linen-shirt-men": (
        "A plain linen-cotton shirt with a short stand collar, three buttons and a chest panel of red-and-black machine cross-stitch.",
        "Проста сорочка з льону з бавовною: короткий комір-стійка, три ґудзики, манишка з червоно-чорним машинним хрестиком.",
    ),
    "everyday-blouse-women": (
        "A light viscose-linen blouse with red poppies embroidered on the yoke and the elastic cuffs; the cloth drapes in soft folds.",
        "Легка блуза з віскози з льоном: червоні маки вишиті на кокетці та манжетах на гумці, тканина спадає м'якими складками.",
    ),
    "everyday-dress-women": (
        "A flax-coloured linen midi dress laid flat, with a wide embroidered band along the hem and pockets at the side seams.",
        "Лляна сукня міді лляного кольору, розкладена на полотні: широка вишита смуга по низу й кишені в бічних швах.",
    ),
    "kids-shirt-classic": (
        "A child's white cotton shirt with a red-and-black cross-stitch panel on the chest and a snap at the collar.",
        "Дитяча біла бавовняна сорочка з червоно-чорним хрестиком на грудях і кнопкою на комірі.",
    ),
    "kids-dress": (
        "A child's white cotton A-line dress with a band of red poppies embroidered above the hem and small side pockets.",
        "Дитяча біла бавовняна сукня А-силуету зі смугою червоних маків над низом і маленькими бічними кишенями.",
    ),
    "rushnyk-wedding-kosiv": (
        "A long linen rushnyk folded in two; both ends carry a tree of life and a pair of birds in red and black cross-stitch.",
        "Довгий лляний рушник, складений удвоє; на обох кінцях дерево життя й пара птахів червоно-чорним хрестиком.",
    ),
    "table-runner-red": (
        "A narrow linen table runner with a red geometric cross-stitch border down both long edges and hemstitched ends.",
        "Вузька лляна доріжка з червоним геометричним бордюром хрестиком по обох довгих краях і мережкою на кінцях.",
    ),
    "rushnyk-whitework": (
        "A folded linen towel whose ends are embroidered white on white with openwork; the pattern reads as texture in raking light.",
        "Складений лляний рушник із кінцями, вишитими білим по білому з мережкою; візерунок видно як фактуру в боковому світлі.",
    ),
    "opishnia-mug": (
        "A thick-walled wheel-thrown red-clay mug under a glossy glaze, hand-painted with the green Opishnia vine.",
        "Товстостінна гончарна чашка з червоної глини під блискучою поливою, розписана зеленою опішнянською лозою.",
    ),
    "opishnia-bowl-set": (
        "Two wide shallow red-clay borshch bowls with a lipped rim, hand-painted with the same vine pattern.",
        "Дві широкі неглибокі миски для борщу з червоної глини з бортиком, розписані тією ж лозою.",
    ),
    "opishnia-lion": (
        "A hand-built glazed clay lion the size of a hand: round smiling face, a mane shaped like a sunflower, ochre and green glaze.",
        "Ліплений глиняний лев із поливою завбільшки з долоню: круглий усміхнений писок, грива як соняшник, вохриста й зелена полива.",
    ),
    "motanka-classic": (
        "A faceless motanka doll wound from cloth and thread, a cross of red thread where the face would be, a skirt of patterned folk cloth.",
        "Лялька-мотанка без обличчя, намотана з тканини та нитки, хрест із червоної нитки замість обличчя, спідниця з візерунчастої народної тканини.",
    ),
    "motanka-mini": (
        "A seven-centimetre faceless motanka wound from linen and red thread, hanging from a small steel keyring.",
        "Семисантиметрова мотанка без обличчя з льону та червоної нитки на маленькому сталевому кільці.",
    ),
    "enamel-pin-set": (
        "Three hard-enamel pins in a row on a plain card: a decorated pysanka, a red poppy and an ear of wheat.",
        "Три значки з твердої емалі в ряд на простій картці: писанка, червоний мак і колос пшениці.",
    ),
    "tote-bag-embroidery-print": (
        "A heavy natural canvas tote laid flat, a band of red-and-black cross-stitch pattern printed across the front, sturdy handles.",
        "Щільна торба з натурального канвасу, розкладена на полотні: спереду надрукована смуга червоно-чорного хрестика, міцні ручки.",
    ),
    "greeting-cards": (
        "Six blank uncoated cards fanned out, each printed with a small embroidery motif, kraft envelopes beneath them.",
        "Шість порожніх листівок без покриття, розкладених віялом, на кожній невеликий мотив вишивки, під ними крафтові конверти.",
    ),
}


def _asset(kind: str, slug: str) -> Path | None:
    path = ASSETS / kind / f"{slug}.webp"
    return path if path.is_file() else None


def _url_width(processed: media.ProcessedImage) -> int:
    """The width a maker picture is linked at: 960 where it exists, else the largest."""
    return min(processed.widths, key=lambda w: abs(w - 960))


def attach_seed_media(db: Session, *, force: bool = False) -> dict:
    """Give every seeded product and maker its picture. Returns what was written.

    `force` replaces the pictures this module wrote before (same original name /
    same maker URL); a photo the owner uploaded is left alone either way.
    """
    products_done = 0
    for product in db.scalars(select(Product).order_by(Product.position)):
        asset = _asset("products", product.slug)
        if asset is None:
            continue
        existing = list(db.scalars(select(ProductImage).where(ProductImage.product_id == product.id)))
        mine = [i for i in existing if i.original_name.startswith("seed-generated/")]
        if existing and not (force and len(existing) == len(mine)):
            continue
        for image in mine:
            media.remove(product.id, image.id)
            db.delete(image)
        db.flush()
        processed = media.process(asset.read_bytes(), asset.name)
        alt_en, alt_uk = PRODUCT_ALT.get(product.slug, ("", ""))
        image = ProductImage(
            product_id=product.id, position=0, alt_en=alt_en[:300], alt_uk=alt_uk[:300],
            width=processed.width, height=processed.height,
            widths=",".join(str(w) for w in processed.widths),
            original_name=f"seed-generated/{product.slug}.webp", bytes_in=asset.stat().st_size,
        )
        db.add(image)
        db.flush()
        media.write(product.id, image.id, processed)
        products_done += 1

    makers_done = 0
    for maker in db.scalars(select(Maker).order_by(Maker.position)):
        asset = _asset("makers", maker.slug)
        if asset is None:
            continue
        current = (maker.image_url or "").strip()
        if current and not (force or current.startswith("/media/makers/")):
            continue
        processed = media.process(asset.read_bytes(), asset.name)
        media.write_named("makers", maker.slug, processed)
        maker.image_url = f"/media/makers/{maker.slug}-{_url_width(processed)}.webp"
        makers_done += 1

    db.flush()
    return {"product_images": products_done, "maker_images": makers_done}
