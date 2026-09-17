"""Demo catalogue for local development and design work.

Everything here is PLACEHOLDER assortment: maker names, stories and prices are
invented to design against and to exercise the order pipeline. Replace with the
real sourcing sheet before launch (see README, "Catalogue").
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import InventoryBalance, Location, Maker, Product, Variant
from .inventory import receive

SIZES = ["XS", "S", "M", "L", "XL", "XXL"]
KID_SIZES = ["4", "6", "8", "10", "12"]

MAKERS = [
    dict(slug="kosiv-thread", name="Kosiv Thread Workshop", name_uk="Косівська нитка", region="Kosiv, Ivano-Frankivsk oblast",
         region_uk="Косів, Івано-Франківщина", craft="Hand embroidery, nyzynka and cross-stitch", craft_uk="Ручна вишивка, низинка та хрестик",
         founded_year=2009, position=1,
         story="Four embroiderers in a wooden house above the Rybnytsia river. A blouse takes them three to five weeks; they count every stitch on the back of the cloth, the Hutsul way, so the pattern shows on the front in negative.",
         story_uk="Четверо вишивальниць у дерев'яному будинку над Рибницею. Блузу вони роблять три-п'ять тижнів; лічать кожен стібок зі звороту полотна, по-гуцульськи, тож візерунок на лиці виходить у негативі."),
    dict(slug="borshchiv-studio", name="Borshchiv Studio", name_uk="Борщівська студія", region="Borshchiv, Ternopil oblast",
         region_uk="Борщів, Тернопільщина", craft="Black-thread embroidery on home-woven linen", craft_uk="Вишивка чорною ниткою по домотканому льону",
         founded_year=2015, position=2,
         story="Borshchiv shirts are famous for dense black embroidery that was once worn in mourning and stayed as a signature. The studio weaves its own linen on two looms and dyes nothing: the cloth is the colour of the flax.",
         story_uk="Борщівські сорочки славляться щільною чорною вишивкою, яку колись носили в жалобі, а потім залишили як знак. Студія тче свій льон на двох верстатах і нічого не фарбує: полотно кольору самого льону."),
    dict(slug="reshetylivka-linen", name="Reshetylivka Linen", name_uk="Решетилівський льон", region="Reshetylivka, Poltava oblast",
         region_uk="Решетилівка, Полтавщина", craft="White-on-white embroidery, machine and hand", craft_uk="Вишивка білим по білому, машинна та ручна",
         founded_year=1998, position=3,
         story="Reshetylivka whitework is on the UNESCO list. This small factory does the base pattern by machine and finishes the openwork by hand, which is why a shirt costs what it costs and still arrives in three weeks.",
         story_uk="Решетилівське білим по білому — у списку ЮНЕСКО. Ця невелика фабрика робить основу машинкою, а мережку доводить руками, тому сорочка коштує стільки, скільки коштує, і все одно приїжджає за три тижні."),
    dict(slug="opishnia-clay", name="Opishnia Clay", name_uk="Опішнянська глина", region="Opishnia, Poltava oblast",
         region_uk="Опішня, Полтавщина", craft="Wheel-thrown, glazed ceramics", craft_uk="Гончарна кераміка з поливою",
         founded_year=2011, position=4,
         story="Two potters and a wood-fired kiln in the town that has been making pots since the 1600s. Glazes are lead-free and the pieces are dishwasher-tested by their own kids.",
         story_uk="Двоє гончарів і дров'яна піч у містечку, де горщики роблять із 1600-х. Полива без свинцю, а посуд перевіряють у посудомийці власні діти."),
    dict(slug="motanka-house", name="Motanka House", name_uk="Дім мотанки", region="Lviv", region_uk="Львів",
         craft="Motanka dolls wound from cloth, no needle", craft_uk="Ляльки-мотанки, намотані без голки",
         founded_year=2018, position=5,
         story="A motanka has no face and no stitches: it is wound from cloth and thread, with no needle in it. Olena makes each one from a different region's cloth and writes the region on the tag.",
         story_uk="У мотанки немає обличчя і немає стібків: її намотують із тканини та нитки, голка до неї не торкається. Олена робить кожну з тканини іншого регіону і пише регіон на бирці."),
    dict(slug="kyiv-sewing", name="Kyiv Sewing Shop", name_uk="Київська швейна", region="Kyiv", region_uk="Київ",
         craft="Machine-embroidered everyday shirts", craft_uk="Повсякденні сорочки з машинною вишивкою",
         founded_year=2016, position=6,
         story="A twelve-person shop that makes the vyshyvanka you wear to work on a Tuesday. Cotton and viscose, machine embroidery, sizes that follow European charts.",
         story_uk="Цех на дванадцять людей, який шиє вишиванку на роботу у вівторок. Бавовна та віскоза, машинна вишивка, розміри за європейськими таблицями."),
    dict(slug="uamarket-studio", name="UA Market Studio", name_uk="Студія UA Market", region="Canada", region_uk="Канада", country="CA",
         craft="Small gifts designed in Ukraine, produced abroad", craft_uk="Дрібні подарунки, розроблені в Україні, виготовлені за кордоном",
         founded_year=2026, position=7,
         story="Our own line of pins, totes and cards. Designs come from Ukrainian illustrators; the printing and enamel work is done abroad, and we say so on every tag.",
         story_uk="Наша власна лінія значків, торб і листівок. Малюнки від українських ілюстраторів; друк і емаль роблять за кордоном, і ми пишемо це на кожній бирці."),
]


def _shirt(slug, title, title_uk, *, maker, collection, category, origin, price, colours, sizes=SIZES, technique, technique_uk,
           material, material_uk, description, description_uk, origin_note=None, origin_note_uk=None, featured=False, weight_g=380,
           subtitle=None, subtitle_uk=None, attributes=None):
    variants = []
    for ci, (colour, colour_uk) in enumerate(colours):
        for si, size in enumerate(sizes):
            variants.append(dict(
                label=f"{colour} / {size}", options={"colour": colour, "colour_uk": colour_uk, "size": size},
                price=price, weight_g=weight_g, position=ci * 10 + si,
            ))
    return dict(slug=slug, title=title, title_uk=title_uk, subtitle=subtitle, subtitle_uk=subtitle_uk, maker=maker,
                collection=collection, category=category, origin=origin, origin_note=origin_note, origin_note_uk=origin_note_uk,
                technique=technique, technique_uk=technique_uk, material=material, material_uk=material_uk,
                care="Hand wash cold, dry flat, iron inside out." if origin == "HANDMADE_UA" else "Machine wash 30°C, iron inside out.",
                care_uk="Прати вручну в холодній воді, сушити горизонтально, прасувати з вивороту." if origin == "HANDMADE_UA" else "Прати в машинці на 30°C, прасувати з вивороту.",
                description=description, description_uk=description_uk, featured=featured, attributes=attributes or {}, variants=variants)


def _single(slug, title, title_uk, *, maker, collection, category, origin, price, technique, technique_uk, material, material_uk,
            description, description_uk, care=None, care_uk=None, featured=False, weight_g=300, options=None, origin_note=None,
            origin_note_uk=None, subtitle=None, subtitle_uk=None, attributes=None):
    if options:
        variants = [dict(label=o[0], options={"option": o[0], "option_uk": o[1]}, price=o[2], weight_g=weight_g, position=i) for i, o in enumerate(options)]
    else:
        variants = [dict(label="One size", options={}, price=price, weight_g=weight_g, position=0)]
    return dict(slug=slug, title=title, title_uk=title_uk, subtitle=subtitle, subtitle_uk=subtitle_uk, maker=maker,
                collection=collection, category=category, origin=origin, origin_note=origin_note, origin_note_uk=origin_note_uk,
                technique=technique, technique_uk=technique_uk, material=material, material_uk=material_uk,
                care=care, care_uk=care_uk, description=description, description_uk=description_uk, featured=featured,
                attributes=attributes or {}, variants=variants)


PRODUCTS = [
    # ---------------------------------------------------------------- Heritage · women
    _shirt("kosiv-nyzynka-blouse", "Kosiv nyzynka blouse", "Блуза «Косівська низинка»", maker="kosiv-thread", collection="heritage",
           category="women", origin="HANDMADE_UA", price=340, featured=True,
           colours=[("Brick & black", "Цегляна з чорним"), ("Ochre & green", "Вохра з зеленим")], sizes=["S", "M", "L", "XL"],
           technique="Nyzynka (counted-thread embroidery worked from the reverse)", technique_uk="Низинка (лічильна вишивка зі звороту)",
           material="Home-woven linen 100%, cotton thread", material_uk="Домотканий льон 100%, бавовняна нитка",
           origin_note="Hand-embroidered in Kosiv; 3–5 weeks per blouse", origin_note_uk="Вишито руками в Косові; 3–5 тижнів на блузу",
           subtitle="Counted on the reverse, worn on the front", subtitle_uk="Лічена зі звороту, носиться на лиці",
           description="A full-sleeve blouse with the sleeve panel worked in nyzynka: the embroiderer counts stitches on the back of the linen, and the geometric pattern appears on the front as a dense weave. Neckline gathered on a drawstring. Each blouse is signed on the inside hem.",
           description_uk="Блуза з довгим рукавом, уставка вишита низинкою: майстриня лічить стібки зі звороту полотна, а геометричний візерунок проступає на лиці щільним плетивом. Горловина на шнурку. Кожна блуза підписана на внутрішньому підрубі.",
           attributes={"sleeve": "full", "closure": "drawstring neck"}),
    _shirt("borshchiv-black-blouse", "Borshchiv black-thread blouse", "Блуза «Борщівська чорна»", maker="borshchiv-studio", collection="heritage",
           category="women", origin="HANDMADE_UA", price=420, featured=True,
           colours=[("Flax & black", "Лляна з чорним")], sizes=["XS", "S", "M", "L", "XL"],
           technique="Dense black cross-stitch and satin stitch", technique_uk="Щільний чорний хрестик і гладь",
           material="Home-woven linen, wool thread", material_uk="Домотканий льон, вовняна нитка",
           origin_note="Hand-embroidered in Borshchiv; linen woven in-house", origin_note_uk="Вишито руками в Борщеві; льон тканий у студії",
           subtitle="The famous black sleeve", subtitle_uk="Той самий чорний рукав",
           description="Borshchiv sleeves are embroidered so densely that the wool thread stands off the linen like a relief. This blouse follows a 1920s museum piece from the same town, scaled to modern sizes. Heavy, warm, a shirt for a wedding or a winter concert.",
           description_uk="Борщівські рукави вишиті так щільно, що вовняна нитка стоїть над льоном рельєфом. Ця блуза повторює музейний зразок 1920-х із того ж міста, переведений у сучасні розміри. Важка, тепла, сорочка на весілля чи зимовий концерт."),
    _shirt("reshetylivka-whitework-blouse", "Reshetylivka whitework blouse", "Блуза «Решетилівська біла»", maker="reshetylivka-linen",
           collection="heritage", category="women", origin="MADE_UA", price=260,
           colours=[("White on white", "Біле по білому")], sizes=SIZES,
           technique="White-on-white embroidery, hand-finished openwork", technique_uk="Біле по білому, мережка доведена руками",
           material="Linen 100%", material_uk="Льон 100%",
           origin_note="Made in Reshetylivka; base by machine, openwork by hand", origin_note_uk="Зроблено в Решетилівці; основа машинкою, мережка руками",
           description="The quietest vyshyvanka there is: the pattern only shows when light hits the raised stitches. Cut loose with a straight hem, it goes under a blazer as easily as over jeans.",
           description_uk="Найтихіша з вишиванок: візерунок видно лише коли світло падає на рельєфні стібки. Вільний крій із рівним низом: під піджак так само легко, як поверх джинсів."),
    # ---------------------------------------------------------------- Heritage · men
    _shirt("kosiv-mens-shirt", "Kosiv men's shirt", "Чоловіча сорочка «Косів»", maker="kosiv-thread", collection="heritage",
           category="men", origin="HANDMADE_UA", price=360, featured=True,
           colours=[("Flax & brick", "Лляна з цеглою")], sizes=["S", "M", "L", "XL", "XXL"],
           technique="Nyzynka chest panel and cuffs", technique_uk="Низинка на манишці та манжетах",
           material="Home-woven linen 100%", material_uk="Домотканий льон 100%",
           origin_note="Hand-embroidered in Kosiv", origin_note_uk="Вишито руками в Косові",
           description="Stand collar, chest panel and cuffs in nyzynka, side slits. The linen softens with every wash and the embroidery does not fade: the thread is dyed before it is spun.",
           description_uk="Комір-стійка, манишка та манжети низинкою, бічні розрізи. Льон м'якшає з кожним пранням, а вишивка не вигорає: нитку фарбують до прядіння."),
    _shirt("borshchiv-mens-shirt", "Borshchiv men's shirt", "Чоловіча сорочка «Борщів»", maker="borshchiv-studio", collection="heritage",
           category="men", origin="HANDMADE_UA", price=390,
           colours=[("Flax & black", "Лляна з чорним")], sizes=["M", "L", "XL", "XXL"],
           technique="Black cross-stitch, hand-sewn seams", technique_uk="Чорний хрестик, шви вручну",
           material="Home-woven linen, wool thread", material_uk="Домотканий льон, вовняна нитка",
           origin_note="Hand-embroidered in Borshchiv", origin_note_uk="Вишито руками в Борщеві",
           description="A narrow black band on the collar, chest and cuffs. The most restrained shirt from the least restrained embroidery town.",
           description_uk="Вузька чорна смуга на комірі, грудях і манжетах. Найстриманіша сорочка з найнестриманішого вишивального міста."),
    # ---------------------------------------------------------------- Everyday
    _shirt("everyday-linen-shirt-men", "Everyday linen shirt", "Повсякденна лляна сорочка", maker="kyiv-sewing", collection="everyday",
           category="men", origin="MADE_UA", price=119, featured=True,
           colours=[("White / red-black", "Біла, червоно-чорна"), ("Navy / white", "Синя з білим"), ("Sand / ochre", "Пісочна з вохрою")],
           technique="Machine embroidery", technique_uk="Машинна вишивка",
           material="Linen 55%, cotton 45%", material_uk="Льон 55%, бавовна 45%",
           origin_note="Sewn and embroidered in Kyiv", origin_note_uk="Пошито та вишито в Києві",
           subtitle="The one you wear on a Tuesday", subtitle_uk="Та, що на вівторок",
           description="Short stand collar, three buttons, a chest panel of red-and-black cross-stitch done by machine so it survives the washing machine. Cut regular, true to European sizing.",
           description_uk="Короткий комір-стійка, три ґудзики, манишка червоно-чорним хрестиком машинкою, тож витримує пральну машину. Звичайний крій, розміри за європейською таблицею."),
    _shirt("everyday-blouse-women", "Everyday blouse", "Повсякденна блуза", maker="kyiv-sewing", collection="everyday",
           category="women", origin="MADE_UA", price=99,
           colours=[("White / poppies", "Біла, маки"), ("Black / cornflower", "Чорна, волошка"), ("Cream / geometric", "Кремова, геометрія")],
           technique="Machine embroidery", technique_uk="Машинна вишивка",
           material="Viscose 70%, linen 30%", material_uk="Віскоза 70%, льон 30%",
           origin_note="Sewn and embroidered in Kyiv", origin_note_uk="Пошито та вишито в Києві",
           description="Light, drapes well, dries overnight on a hanger. Embroidery on the yoke and cuffs; elastic cuffs so the sleeve can be pushed up.",
           description_uk="Легка, добре драпірується, висихає за ніч на плічках. Вишивка на кокетці та манжетах; манжети на гумці, щоб рукав можна було підкотити."),
    _shirt("everyday-dress-women", "Embroidered linen dress", "Лляна сукня з вишивкою", maker="kyiv-sewing", collection="everyday",
           category="women", origin="MADE_UA", price=149,
           colours=[("Flax", "Лляна"), ("Black", "Чорна")], sizes=["XS", "S", "M", "L", "XL"],
           technique="Machine embroidery, French seams", technique_uk="Машинна вишивка, французькі шви",
           material="Linen 100%", material_uk="Льон 100%", weight_g=520,
           origin_note="Sewn and embroidered in Kyiv", origin_note_uk="Пошито та вишито в Києві",
           description="Midi length, pockets, a wide embroidered band at the hem instead of the usual chest panel. Made to be worn with boots.",
           description_uk="Довжина міді, кишені, широка вишита смуга по низу замість звичної манишки. Зроблена, щоб носити з черевиками."),
    # ---------------------------------------------------------------- Kids
    _shirt("kids-shirt-classic", "Kids' embroidered shirt", "Дитяча вишита сорочка", maker="kyiv-sewing", collection="kids",
           category="kids", origin="MADE_UA", price=54, featured=True,
           colours=[("White / red-black", "Біла, червоно-чорна"), ("White / blue", "Біла, синя")], sizes=KID_SIZES,
           technique="Machine embroidery", technique_uk="Машинна вишивка",
           material="Cotton 100%", material_uk="Бавовна 100%", weight_g=180,
           origin_note="Sewn and embroidered in Kyiv", origin_note_uk="Пошито та вишито в Києві",
           description="Soft cotton, no scratchy backing under the embroidery, a snap at the collar instead of a button. Sizes by age: 4 to 12.",
           description_uk="М'яка бавовна, під вишивкою немає колючої підкладки, на комірі кнопка замість ґудзика. Розміри за віком: 4–12."),
    _shirt("kids-dress", "Kids' embroidered dress", "Дитяча сукня з вишивкою", maker="kyiv-sewing", collection="kids",
           category="kids", origin="MADE_UA", price=64,
           colours=[("White / poppies", "Біла, маки")], sizes=KID_SIZES,
           technique="Machine embroidery", technique_uk="Машинна вишивка",
           material="Cotton 100%", material_uk="Бавовна 100%", weight_g=220,
           origin_note="Sewn and embroidered in Kyiv", origin_note_uk="Пошито та вишито в Києві",
           description="A-line, twirls, pockets. The poppy band sits above the hem, at the height where it shows while the dress is worn.",
           description_uk="А-силует, крутиться, кишені. Смуга з маками над низом, на тій висоті, де її видно, коли сукню носять."),
    # ---------------------------------------------------------------- Home
    _single("rushnyk-wedding-kosiv", "Wedding rushnyk, Kosiv", "Весільний рушник, Косів", maker="kosiv-thread", collection="home",
            category="home", origin="HANDMADE_UA", price=260, featured=True, weight_g=420,
            technique="Hand cross-stitch, both ends", technique_uk="Ручний хрестик, обидва кінці",
            material="Linen 100%, cotton thread", material_uk="Льон 100%, бавовняна нитка",
            origin_note="Hand-embroidered in Kosiv; 2–3 weeks", origin_note_uk="Вишито руками в Косові; 2–3 тижні",
            description="A 2.4 m ritual towel embroidered at both ends with a tree of life and a pair of birds. Used at weddings to stand on, then kept for the rest of a marriage. Comes with a note explaining which motif is which.",
            description_uk="Обрядовий рушник 2,4 м, вишитий з обох кінців деревом життя та парою птахів. На весіллі на нього стають, а потім тримають усе подружнє життя. Додається записка, який мотив що означає.",
            care="Hand wash cold, iron damp on the reverse.", care_uk="Прати вручну в холодній воді, прасувати вологим із вивороту.",
            attributes={"length_cm": 240, "width_cm": 35}),
    _single("table-runner-red", "Embroidered table runner", "Вишита доріжка на стіл", maker="reshetylivka-linen", collection="home",
            category="home", origin="MADE_UA", price=59, weight_g=260,
            technique="Machine cross-stitch", technique_uk="Машинний хрестик",
            material="Linen 100%", material_uk="Льон 100%",
            origin_note="Made in Reshetylivka", origin_note_uk="Зроблено в Решетилівці",
            options=[("Red · 40×140 cm", "Червона · 40×140 см", 59), ("Red · 40×200 cm", "Червона · 40×200 см", 79), ("Black · 40×140 cm", "Чорна · 40×140 см", 59)],
            description="A red or black geometric border along both long edges; hemstitched ends. It has been through our own dishwasher-adjacent dinners for a year.",
            description_uk="Червоний або чорний геометричний бордюр уздовж обох довгих країв; кінці з мережкою. Рік пережила наші власні вечері біля посудомийки.",
            care="Machine wash 40°C, iron damp.", care_uk="Прати в машинці на 40°C, прасувати вологою."),
    _single("rushnyk-whitework", "Whitework rushnyk", "Рушник білим по білому", maker="reshetylivka-linen", collection="home",
            category="home", origin="MADE_UA", price=120, weight_g=380,
            technique="White-on-white embroidery, hand-finished", technique_uk="Біле по білому, доведено руками",
            material="Linen 100%", material_uk="Льон 100%",
            origin_note="Made in Reshetylivka", origin_note_uk="Зроблено в Решетилівці",
            description="For an icon corner or a table under a vase: a 1.8 m towel with whitework ends that show only in raking light.",
            description_uk="Для покутя чи столу під вазу: рушник 1,8 м із білими кінцями, які видно лише в боковому світлі.",
            care="Hand wash cold, iron damp on the reverse.", care_uk="Прати вручну в холодній воді, прасувати вологим із вивороту.",
            attributes={"length_cm": 180, "width_cm": 33}),
    # ---------------------------------------------------------------- Ceramics
    _single("opishnia-mug", "Opishnia mug", "Опішнянська чашка", maker="opishnia-clay", collection="home",
            category="ceramics", origin="HANDMADE_UA", price=38, featured=True, weight_g=420,
            technique="Wheel-thrown, hand-painted underglaze", technique_uk="Гончарний круг, підполивний розпис руками",
            material="Red clay, lead-free glaze", material_uk="Червона глина, полива без свинцю",
            origin_note="Thrown and fired in Opishnia", origin_note_uk="Зроблено і випалено в Опішні",
            options=[("Green vine · 350 ml", "Зелена лоза · 350 мл", 38), ("Brown wheat · 350 ml", "Бура пшениця · 350 мл", 38), ("Green vine · 500 ml", "Зелена лоза · 500 мл", 46)],
            description="A thick-walled mug that keeps tea hot for an hour. Painted with the Opishnia vine in the same three colours the town has used for two centuries. Dishwasher safe.",
            description_uk="Товстостінна чашка, що тримає чай гарячим годину. Розписана опішнянською лозою тими ж трьома кольорами, якими місто малює два століття. Можна в посудомийку.",
            care="Dishwasher safe; avoid thermal shock.", care_uk="Можна в посудомийку; берегти від різкого перепаду температур."),
    _single("opishnia-bowl-set", "Opishnia bowl set", "Набір опішнянських мисок", maker="opishnia-clay", collection="home",
            category="ceramics", origin="HANDMADE_UA", price=110, weight_g=1400,
            technique="Wheel-thrown, hand-painted underglaze", technique_uk="Гончарний круг, підполивний розпис руками",
            material="Red clay, lead-free glaze", material_uk="Червона глина, полива без свинцю",
            origin_note="Thrown and fired in Opishnia", origin_note_uk="Зроблено і випалено в Опішні",
            options=[("Set of 2 · 18 cm", "Набір із 2 · 18 см", 74), ("Set of 4 · 18 cm", "Набір із 4 · 18 см", 138)],
            description="Borshch bowls. Wide, shallow, with a lip that takes a spoon resting on it. Each set is packed in straw.",
            description_uk="Миски для борщу. Широкі, неглибокі, з бортиком, на який лягає ложка. Кожен набір пакуємо в солому.",
            care="Dishwasher safe; avoid thermal shock.", care_uk="Можна в посудомийку; берегти від різкого перепаду температур."),
    _single("opishnia-lion", "Opishnia clay lion", "Опішнянський лев", maker="opishnia-clay", collection="gifts",
            category="ceramics", origin="HANDMADE_UA", price=64, weight_g=900,
            technique="Hand-built, glazed", technique_uk="Ліплений руками, з поливою",
            material="Red clay, lead-free glaze", material_uk="Червона глина, полива без свинцю",
            origin_note="Made in Opishnia", origin_note_uk="Зроблено в Опішні",
            description="The Opishnia lion is a lion that has never seen a lion: round-faced, smiling, with a mane like a sunflower. 18 cm tall, a bookshelf animal.",
            description_uk="Опішнянський лев — це лев, який ніколи не бачив лева: круглолиций, усміхнений, із гривою як соняшник. 18 см, звір на книжкову полицю."),
    # ---------------------------------------------------------------- Dolls
    _single("motanka-classic", "Motanka doll", "Лялька-мотанка", maker="motanka-house", collection="kids",
            category="dolls", origin="HANDMADE_UA", price=58, featured=True, weight_g=160,
            technique="Wound from cloth and thread: no needle touches the doll", technique_uk="Намотана з тканини та нитки: голка ляльки не торкається",
            material="Cotton and linen scraps, wool, thread", material_uk="Клаптики бавовни та льону, вовна, нитка",
            origin_note="Made in Lviv; regional cloth named on the tag", origin_note_uk="Зроблено у Львові; тканина регіону вказана на бирці",
            options=[("Podillia cloth · 22 cm", "Подільська тканина · 22 см", 58), ("Hutsul cloth · 22 cm", "Гуцульська тканина · 22 см", 58), ("Poltava cloth · 30 cm", "Полтавська тканина · 30 см", 82)],
            description="No face, a cross of thread where a face would be, and a skirt of cloth from the region on the tag. A house guardian by tradition and a toy in practice.",
            description_uk="Без обличчя, хрест із нитки там, де мало б бути обличчя, і спідниця з тканини регіону, вказаного на бирці. За традицією оберіг, на практиці іграшка."),
    _single("motanka-mini", "Motanka keychain", "Мотанка-брелок", maker="motanka-house", collection="gifts",
            category="dolls", origin="HANDMADE_UA", price=18, weight_g=30,
            technique="Wound from cloth and thread", technique_uk="Намотана з тканини та нитки",
            material="Cotton, linen, thread, steel ring", material_uk="Бавовна, льон, нитка, сталеве кільце",
            origin_note="Made in Lviv", origin_note_uk="Зроблено у Львові",
            description="A 7 cm motanka on a ring. Fits in an envelope; we ship it as a letter if it is alone in the order.",
            description_uk="Мотанка 7 см на кільці. Влазить у конверт; якщо в замовленні лише вона, відправляємо листом."),
    # ---------------------------------------------------------------- Gifts (designed in UA, made abroad)
    _single("enamel-pin-set", "Enamel pin set", "Набір значків", maker="uamarket-studio", collection="gifts",
            category="gifts", origin="DESIGNED_UA", price=24, weight_g=40,
            technique="Hard enamel", technique_uk="Тверда емаль",
            material="Zinc alloy, enamel", material_uk="Цинковий сплав, емаль",
            origin_note="Designed in Ukraine, made abroad", origin_note_uk="Розроблено в Україні, виготовлено за кордоном",
            options=[("Set of 3 · pysanka, poppy, wheat", "Набір із 3 · писанка, мак, колос", 24), ("Set of 5", "Набір із 5", 36)],
            description="Three or five hard-enamel pins from a Kharkiv illustrator's sketchbook. Butterfly clutches, backing card with the drawings.",
            description_uk="Три або п'ять значків із твердої емалі зі скетчбука харківської ілюстраторки. Застібки-метелики, підкладка з малюнками."),
    _single("tote-bag-embroidery-print", "Tote bag, embroidery print", "Торба з принтом вишивки", maker="uamarket-studio", collection="gifts",
            category="gifts", origin="DESIGNED_UA", price=32, weight_g=180,
            technique="Screen print", technique_uk="Шовкографія",
            material="Cotton canvas 340 g", material_uk="Бавовняний канвас 340 г",
            origin_note="Designed in Ukraine, printed abroad", origin_note_uk="Розроблено в Україні, надруковано за кордоном",
            options=[("Red-black", "Червоно-чорна", 32), ("Blue", "Синя", 32)],
            description="A heavy canvas tote with a printed cross-stitch band. The band is a print, and the label says so.",
            description_uk="Щільна канвасова торба з надрукованою смугою хрестика. Смуга — це друк, і на етикетці так і написано."),
    _single("greeting-cards", "Greeting cards, set of 6", "Листівки, набір із 6", maker="uamarket-studio", collection="gifts",
            category="gifts", origin="DESIGNED_UA", price=16, weight_g=90,
            technique="Offset print", technique_uk="Офсетний друк",
            material="300 g uncoated card, kraft envelopes", material_uk="Картон 300 г без покриття, крафтові конверти",
            origin_note="Designed in Ukraine, printed in Canada", origin_note_uk="Розроблено в Україні, надруковано в Канаді",
            description="Six blank cards with embroidery motifs from six regions, region named on the back. Envelopes included.",
            description_uk="Шість порожніх листівок із мотивами вишивки шести регіонів, регіон підписано ззаду. Конверти в комплекті."),
]


def _label_uk(variant: dict) -> str | None:
    opt = variant["options"]
    if "size" in opt and opt.get("colour_uk"):
        return f"{opt['colour_uk']} / {opt['size']}"
    return opt.get("option_uk")


def _barcode(sku: str) -> str:
    digits = str(int(hashlib.sha1(sku.encode()).hexdigest(), 16))
    return ("48" + digits)[:13]


def _sku(product_slug: str, variant: dict) -> str:
    base = "".join(ch for ch in product_slug.upper() if ch.isalnum() or ch == "-")
    opt = variant["options"]
    if "size" in opt:
        colour = "".join(w[0] for w in opt["colour"].replace("/", " ").replace("&", " ").split())[:3].upper()
        return f"{base}-{colour}-{opt['size']}"
    if "option" in opt:
        return f"{base}-{variant['position'] + 1:02d}"
    return f"{base}-01"


def _stock_qty(sku: str) -> int:
    """Deterministic demo stock: a few SKUs sold out, a few low, most healthy."""
    n = int(hashlib.md5(sku.encode()).hexdigest(), 16) % 17
    if n == 0:
        return 0
    if n in (1, 2):
        return 1
    return 3 + n


def seed_catalog(db: Session, *, with_stock: bool = True, with_media: bool = True) -> dict:
    """Insert the demo catalogue. Insert-only: a row that exists (by slug or SKU) is never changed,
    so running it against a shop whose owner has edited or imported products touches none of them.

    `with_media` also attaches the generated demonstration pictures shipped in
    `app/assets/catalogue/` (see `catalog_media.py`); a product that already carries a
    photo keeps it."""
    from .catalog import ensure_taxonomy

    ensure_taxonomy(db)
    makers: dict[str, Maker] = {}
    for m in MAKERS:
        row = db.scalar(select(Maker).where(Maker.slug == m["slug"]))
        if not row:
            row = Maker(**m)
            db.add(row)
            db.flush()
        makers[m["slug"]] = row

    if with_stock:
        for loc_id, kind in [("A-LANE-01", "A_LANE"), ("B-BIN-001", "B_BIN")]:
            if not db.get(Location, loc_id):
                db.add(Location(id=loc_id, kind=kind))
        db.flush()

    created_products = 0
    created_variants = 0
    for i, p in enumerate(PRODUCTS):
        product = db.scalar(select(Product).where(Product.slug == p["slug"]))
        if not product:
            product = Product(
                slug=p["slug"], title=p["title"], title_uk=p["title_uk"], subtitle=p.get("subtitle"), subtitle_uk=p.get("subtitle_uk"),
                description=p["description"], description_uk=p["description_uk"], category=p["category"], collection=p["collection"],
                maker_id=makers[p["maker"]].id, origin=p["origin"], origin_note=p.get("origin_note"), origin_note_uk=p.get("origin_note_uk"),
                technique=p.get("technique"), technique_uk=p.get("technique_uk"), material=p.get("material"), material_uk=p.get("material_uk"),
                care=p.get("care"), care_uk=p.get("care_uk"), attributes_json=json.dumps(p.get("attributes") or {}, ensure_ascii=False),
                featured=p.get("featured", False), position=i,
            )
            db.add(product)
            db.flush()
            created_products += 1
        for v in p["variants"]:
            sku = _sku(p["slug"], v)
            variant = db.scalar(select(Variant).where(Variant.sku == sku))
            if not variant:
                variant = Variant(
                    sku=sku, name=f"{p['title']} {v['label']}", barcode=_barcode(sku), price_cad=float(v["price"]),
                    product_id=product.id, option_label=v["label"],
                    option_label_uk=_label_uk(v), option_json=json.dumps(v["options"], ensure_ascii=False),
                    weight_g=v.get("weight_g"), position=v["position"],
                )
                db.add(variant)
                db.flush()
                created_variants += 1
            if with_stock:
                has_balance = db.scalar(select(InventoryBalance).where(InventoryBalance.variant_id == variant.id))
                if not has_balance:
                    qty = _stock_qty(sku)
                    if qty > 0:
                        location = "A-LANE-01" if v["position"] % 2 == 0 else "B-BIN-001"
                        receive(db, variant_id=variant.id, location_id=location, qty=qty, reference_id=f"SEED-{sku}")
    db.flush()
    result = {"makers": len(makers), "products_created": created_products, "variants_created": created_variants}
    if with_media:
        from .catalog_media import attach_seed_media
        result.update(attach_seed_media(db))
    return result
