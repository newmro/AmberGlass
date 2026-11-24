#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Składa /workspace/amberglass/products.json: dane ze sklepu, oryginalne opisy, oficjalne zdjęcia."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_feed import (  # noqa: E402
    CATEGORY_URL,
    IMAGE_BASE_DEFAULT,
    abs_url,
    parse_product,
    parse_filename_skus,
    list_official_images,
    sort_key_for_sku,
    SKU_TOKEN,
)

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path("/tmp/amberglass/html-cache")
SOURCE_JSON = Path("/tmp/amberglass/source_products.json")
OUT = ROOT / "products.json"
IMAGES_DIR = ROOT / "images"
IMAGE_BASE = IMAGE_BASE_DEFAULT

# Tytuły: lekko uporządkowane, bez zmyślonych cech. Marka zawsze „Amber Glass”.
TITLES = {
    "3222": "Amber Glass kieliszek degustacyjny do whisky z pokrywką, 102 ml (G100)",
    "3223": "Amber Glass kieliszek degustacyjny do whisky z bursztynową nóżką i pokrywką, 102 ml (G101)",
    "3586": "Amber Glass kieliszek degustacyjny do whisky z pokrywką, 130 ml (G200)",
    "3587": "Amber Glass kieliszek degustacyjny do whisky z bursztynową nóżką i pokrywką, 130 ml (G201)",
    "5826": "Amber Glass kieliszek degustacyjny do whisky, grappy i likieru, 95 ml (G300)",
    "5827": "Amber Glass kieliszek degustacyjny do whisky, 120 ml (G410)",
    "7158": "Amber Glass kieliszek degustacyjny do whisky z bursztynową podstawą i pokrywką, 150 ml (G501)",
    "7159": "Amber Glass kieliszek degustacyjny do whisky z pokrywką, 150 ml (G500)",
    "7160": "Amber Glass zestaw dwóch kieliszków degustacyjnych do whisky z pokrywkami",
    "7377": "Amber Glass czarny kieliszek degustacyjny do whisky, edycja limitowana, 130 ml (G202)",
    "7378": "Amber Glass czarny kieliszek degustacyjny do whisky, edycja limitowana, 100 ml (G102)",
    "7395": "Amber Glass kieliszki degustacyjne do whisky, 102 ml, zestaw 6 szt.",
    "9869": "Amber Glass czarny kieliszek degustacyjny do whisky z pokrywką, 150 ml (G502)",
    "10004": "Amber Glass kieliszek degustacyjny do whisky, 200 ml (G110)",
    "10005": "Amber Glass kieliszek degustacyjny do whisky z bursztynową nóżką, 200 ml (G111)",
    "10167": "Amber Glass kieliszek do whisky, grappy i likieru z bursztynową nóżką, 95 ml (G301)",
    "10502": "Amber Glass kieliszek degustacyjny do whisky, 220 ml (G600)",
    "10503": "Amber Glass kieliszek degustacyjny do whisky z bursztynową nóżką, 220 ml (G601)",
    "10504": "Amber Glass zestaw dwóch szklanek do whisky Amber Box II, 330 ml",
    "10506": "Amber Glass kieliszki do wódki, likieru i tequili, 40 ml, zestaw 6 szt. (V100)",
    "10507": "Amber Glass kieliszki do wódki, likieru i tequili z bursztynową nóżką, 40 ml, zestaw 6 szt. (V101)",
    "10573": "Amber Glass kieliszki do ginu i koktajli, 600 ml, zestaw 2 szt. (CG200)",
    "10574": "Amber Glass kieliszki do koktajli i szampana, 170 ml, zestaw 2 szt. (CG100)",
    "10664": "Amber Glass kieliszek degustacyjny do whisky z bursztynową nóżką, 120 ml (G411)",
    "11008": "Amber Glass kieliszek degustacyjny do whisky ze zdobieniem, 200 ml (G120)",
    "11009": "Amber Glass kieliszek degustacyjny do whisky z pokrywką, 200 ml (G510)",
    "12562": "Amber Glass czarne kieliszki do wódki, likieru i tequili, 40 ml, zestaw 6 szt. (V102)",
    "12563": "Amber Glass kieliszek degustacyjny do whisky z pokrywką, 220 ml (G610)",
    "12564": "Amber Glass czarny kieliszek degustacyjny do whisky z pokrywką, 220 ml (G602)",
    "13049": "Amber Glass zestaw dwóch kryształowych szklanek do whisky NO 1, 330 ml",
    "13050": "Amber Glass zestaw dwóch kryształowych szklanek do whisky NO 2, 330 ml",
    "13051": "Amber Glass zestaw dwóch kryształowych szklanek do whisky NO 3, 330 ml",
    "13052": "Amber Glass zestaw dwóch kryształowych szklanek do whisky NO 4, 330 ml",
    "13055": "Amber Glass zestaw dwóch kryształowych szklanek do whisky NO 7, 240 ml",
    "13056": "Amber Glass zestaw dwóch kryształowych szklanek do whisky NO 8, 240 ml",
    "14080": "Amber Glass zestaw dwóch kieliszków do koniaku, brandy i armaniaku, 480 ml (CG300)",
    "14990": "Amber Glass zestaw dwóch szklanek do whisky Amber Box III, 300 ml",
}

# Oryginalne opisy: fakty ze sklepu, inne zdania niż źródło.
DESCRIPTIONS = {
    "3222": """Kieliszek Amber Glass G100 ma przezroczystą, gładką czaszą o pojemności 102 ml i jest sprzedawany w komplecie z pokrywką typu „outside”. Pokrywka ogranicza dostęp powietrza i pomaga utrzymać aromat, jeśli whisky nie jest pita od razu po nalaniu. Wysokość naczynia to 13,6 cm, średnica 5,8 cm.

Forma tulipana, zwężona ku górze i zakończona węższą szyjką, jest przeznaczona do whisky oraz rumu, także do szczelniej zbudowanych, dymno-torfowych kompozycji. Szkło formowane jest ręcznie; według karty produktu kieliszek można myć w zmywarce, choć przy codziennym użytkowaniu spokojnie sprawdza się też mycie ręczne.

W zestawie jest 1 sztuka, pakowana w kartonik.""",

    "3223": """Model G101 to kieliszek Amber Glass o pojemności 102 ml z kolorową, bursztynową nóżką i pokrywką typu „outside”. Wymiary są takie same jak w wersji jednolitej: 13,6 cm wysokości i 5,8 cm średnicy. Pokrywka przydaje się, gdy trunek ma chwilę poczekać w kieliszku.

Czasza w kształcie tulipana zbiera zapach w górnej części naczynia. Producent przeznacza ten model do whisky i rumu, w tym do cięższych, dymno-torfowych stylów. Szkło jest gładkie i robione ręcznie, barwa w karcie to „kolorowe”.

Kieliszek sprzedawany jest pojedynczo, w pudełku. Dopuszczalne jest mycie w zmywarce.""",

    "3586": """Amber Glass G200 to przezroczysty kieliszek degustacyjny o pojemności 130 ml, z pokrywką typu „inside”. Wysokość wynosi 13,6 cm, średnica 5,8 cm. Pokrywka wchodzi w krawędź naczynia i ogranicza ulatnianie się aromatów między kolejnymi łykami.

Kształt tulipana jest tu przewidziany raczej do lżejszych, owocowo-kwiatowych whisky i rumu niż do mocno torfowych stylów. Szkło gładkie, formowane ręcznie. W karcie zapisano, że można je myć w zmywarce.

Oferta dotyczy 1 sztuki w opakowaniu kartonowym.""",

    "3587": """G201 to kieliszek Amber Glass, który różni się od przezroczystego G200 bursztynową nóżką. Pojemność to 130 ml, wysokość 13,6 cm, średnica 5,8 cm. W zestawie jest pokrywka typu „inside”. Karta określa barwę jako kolorową, motyw jako gładki.

Naczynie ma formę tulipana i jest opisywane jako odpowiednie do lżejszych, owocowo-kwiatowych whisky oraz rumu. Każdy kieliszek powstaje ręcznie. Można go myć w zmywarce.

Sprzedawany pojedynczo, w pudełku.""",

    "5826": """Kieliszek Amber Glass G300 ma smukłą, wysoką nogę i pojemność 95 ml. Wysokość całkowita to 17,8 cm, średnica 5,8 cm. Forma nawiązuje do kieliszka do grappy: czasza zwęża się ku górze, a wąska szyjka kieruje łyk na język.

Model jest przeznaczony do lżejszych, kwiatowo-owocowych trunków — whisky, grappy i likierów. Szkło przezroczyste, gładkie, formowane ręcznie. W zestawie nie ma pokrywki. Dopuszczalne mycie w zmywarce.

Jedna sztuka, pakowana w pudełko.""",

    "5827": """Amber Glass G410 to przezroczysty kieliszek o pojemności 120 ml, wysokości 13,5 cm i średnicy 6 cm. Czasza ma kształt tulipana, bez pokrywki i bez kolorowej nogi.

Producent wskazuje go do whisky oraz rumu, w tym do dymno-torfowych stylów. Szkło jest gładkie i robione ręcznie. W karcie potwierdzono możliwość mycia w zmywarce.

Sprzedaż obejmuje 1 sztukę w opakowaniu.""",

    "7158": """Model G501 to kieliszek Amber Glass o pojemności 150 ml z bursztynową podstawą i pokrywką typu „inside”. Wysokość wynosi 15 cm, średnica 6,8 cm. Karta opisuje barwę jako kolorową, motyw jako gładki.

Kształt tulipana z węższą szyjką ma zbierać aromat; w opisie sklepu pojawiają się zarówno cięższe, dymno-torfowe whisky, jak i lżejsze, owocowo-kwiatowe kompozycje. Szkło jest formowane ręcznie, a w karcie zaznaczono też ręczne dmuchanie. Produkt można myć w zmywarce.

W ofercie jest 1 sztuka.""",

    "7159": """G500 to kieliszek Amber Glass 150 ml z pokrywką typu „inside”, bez bursztynowej podstawy w nazwie modelu. Wymiary: wysokość 15 cm, średnica 6,8 cm. W karcie barwa jest podana jako kolorowa, motyw jako gładki.

Czasza w formie tulipana służy do degustacji whisky i rumu. Szkło powstaje ręcznie, z adnotacją o ręcznym dmuchaniu. Mycie w zmywarce jest dopuszczalne.

Sprzedawany pojedynczo.""",

    "7160": """Zestaw Amber Box zawiera dwa kieliszki degustacyjne Amber Glass z pokrywkami typu „outside”. Pojemność jednego kieliszka to 130 ml, wysokość 17,3 cm, średnica 5,8 cm. W karcie barwa jest kolorowa, motyw gładki.

Oba naczynia mają kształt tulipana i są przeznaczone do whisky oraz rumu, także do dymno-torfowych stylów. Szkło formowane ręcznie. Zestaw można myć w zmywarce.

Dwie sztuki są pakowane razem, w jednym pudełku.""",

    "7377": """G202 to czarny kieliszek Amber Glass z edycji limitowanej, o pojemności 130 ml. Wysokość wynosi 17,1 cm, średnica 5,8 cm. Do kieliszka dołączono pokrywkę typu „inside”.

Naczynie jest przeznaczone do whisky i rumu, w tym do dymno-torfowych kompozycji. Szkło gładkie, barwa w karcie określona jako kolorowa, wykonanie ręczne. Dopuszczalne mycie w zmywarce.

Sprzedaż dotyczy 1 sztuki w opakowaniu.""",

    "7378": """Limitowany model G102 to czarny kieliszek Amber Glass o pojemności 100 ml, wysokości 17,1 cm i średnicy 5,8 cm, z pokrywką typu „inside”. Kształt czaszy to tulipan.

Przeznaczenie: whisky i rum, w tym szczelniej zbudowane, dymno-torfowe style. Szkło formowane ręcznie, powierzchnia gładka. W karcie dopuszczono zmywarkę.

Jedna sztuka, w pudełku.""",

    "7395": """Amber Tasting Set to komplet sześciu kieliszków Amber Glass o pojemności 102 ml każdy. Wysokość pojedynczego naczynia to 13,6 cm, średnica 5,8 cm. Szkło jest przezroczyste i gładkie, bez pokrywek.

Kieliszki mają formę tulipana i są przeznaczone do degustacji whisky oraz rumu, także w wydaniu dymno-torfowym. Każdy egzemplarz jest formowany ręcznie. Zestaw można myć w zmywarce.

Sześć sztuk jest pakowanych razem.""",

    "9869": """G502 to czarny kieliszek Amber Glass o pojemności 150 ml, z pokrywką typu „inside”. Wysokość 15 cm, średnica 6,8 cm. Motyw gładki, barwa w karcie — kolorowa.

Czasza w kształcie tulipana jest opisywana z myślą o lżejszych, owocowo-kwiatowych whisky i rumie. Szkło robione ręcznie. Produkt można myć w zmywarce.

Oferta obejmuje 1 sztukę w opakowaniu.""",

    "10004": """Kieliszek Amber Glass G110 ma pojemność 200 ml, wysokość 17,8 cm i średnicę 6,5 cm. W karcie jest przezroczysty i gładki, bez pokrywki. Kształt czaszy nawiązuje do kieliszka do porto: węższa góra zbiera aromat, a wąska szyjka prowadzi łyk.

Model jest przeznaczony do lżejszych, słodkich i owocowo-kwiatowych whisky, a także innych alkoholi o podobnym profilu. Szkło formowane ręcznie. Można myć w zmywarce.

Sprzedawany pojedynczo, w pudełku.""",

    "10005": """G111 to kieliszek Amber Glass o pojemności 200 ml z bursztynową nóżką. Wysokość 17,8 cm, średnica 6,5 cm. Karta podaje barwę „kolorowe” i motyw „gładkie”. Pokrywki nie ma.

Tak jak pokrewny G110, naczynie jest inspirowane kieliszkiem do porto i przeznaczone do lżejszych, owocowo-kwiatowych whisky. Wykonanie ręczne, mycie w zmywarce dopuszczalne.

Jedna sztuka w opakowaniu.""",

    "10167": """G301 to kieliszek Amber Glass o pojemności 95 ml z bursztynową nóżką, bez pokrywki. Wysokość 17,8 cm, średnica 5,8 cm. Forma odpowiada modelowi do grappy: smukła noga i zwężająca się czasza.

Przeznaczenie obejmuje lżejsze, kwiatowo-owocowe whisky, grappę i likiery. Szkło gładkie, barwa kolorowa, formowanie ręczne. W karcie potwierdzono zmywarkę.

Sprzedaż: 1 sztuka w pudełku.""",

    "10502": """Amber Glass G600 to kieliszek o pojemności 220 ml, wysokości 18 cm i średnicy 7,5 cm. Szkło jest przezroczyste, z wzorem, bez pokrywki i bez kolorowej nogi. Czasza ma kształt tulipana.

Producent wskazuje ten model do whisky i rumu, w tym do dymno-torfowych stylów. Wykonanie ręczne. Można myć w zmywarce.

Jedna sztuka, pakowana w opakowanie.""",

    "10503": """G601 to kieliszek Amber Glass o tych samych wymiarach co G600 — 220 ml, 18 cm wysokości, 7,5 cm średnicy — oraz z bursztynową nóżką. Szkło przezroczyste z wzorem, bez pokrywki. Kształt tulipana.

Przeznaczenie: whisky i rum, także w wariancie dymno-torfowym. Formowanie ręczne, mycie w zmywarce dopuszczalne.

Sprzedawany pojedynczo.""",

    "10504": """Amber Box II to zestaw dwóch szklanek Amber Glass o pojemności 330 ml każda. Wysokość szklanki wynosi 9,5 cm, średnica 8,5 cm. Szkło jest przezroczyste, z wzorem.

Zestaw jest przeznaczony do whisky i rumu. Szklanki są formowane ręcznie. W karcie dopuszczono mycie w zmywarce.

Dwie sztuki są sprzedawane we wspólnym opakowaniu.""",

    "10506": """V100 to zestaw sześciu kieliszków Amber Glass o pojemności 40 ml. Wysokość jednego kieliszka to 11 cm, średnica 3 cm. Szkło przezroczyste, gładkie, bez pokrywek.

Naczynia są przeznaczone do wódki, likieru, grappy i tequili. Każdy kieliszek powstaje ręcznie. Zestaw można myć w zmywarce.

Sześć sztuk pakowanych jest razem.""",

    "10507": """V101 to zestaw kieliszków Amber Glass o tej samej pojemności i wymiarach co V100 — 40 ml, 11 cm wysokości, 3 cm średnicy — ale z bursztynową nóżką. W karcie barwa jest kolorowa, motyw gładki.

Zestaw sześciu kieliszków służy do wódki, likieru, grappy i tequili. Szkło formowane ręcznie, mycie w zmywarce dopuszczalne.

Sprzedaż wyłącznie jako komplet 6 sztuk.""",

    "10573": """CG200 to para kieliszków Amber Glass do ginu i koktajli, każdy o pojemności 600 ml. Wysokość wynosi 20 cm, średnica 10,5 cm. Szkło przezroczyste, z wzorem.

Zestaw jest w karcie przypisany do ginu. Naczynia są robione ręcznie i można je myć w zmywarce.

W opakowaniu znajdują się 2 sztuki.""",

    "10574": """CG100 to zestaw dwóch kieliszków Amber Glass o pojemności 170 ml, wysokości 22 cm i średnicy 10 cm. Szkło przezroczyste, z wzorem. Przeznaczenie w karcie: wino musujące i szampan, a w nazwie pojawiają się też koktajle.

Wykonanie ręczne. Dopuszczalne mycie w zmywarce.

Sprzedawane jako komplet 2 sztuk.""",

    "10664": """G411 to kieliszek Amber Glass 120 ml z bursztynową nóżką. Wysokość 13,5 cm, średnica 6 cm — tak samo jak w przezroczystym G410. Pokrywki nie ma. Barwa w karcie: kolorowa, motyw gładki, kształt tulipana.

Model jest przeznaczony do whisky i rumu, w tym do dymno-torfowych stylów. Szkło formowane ręcznie, zmywarka dopuszczalna.

Jedna sztuka w opakowaniu.""",

    "11008": """G120 to kieliszek Amber Glass o pojemności 200 ml, wysokości 17,8 cm i średnicy 6,5 cm, w wersji przezroczystej ze zdobieniem (w karcie: motyw „z wzorem”). Nie ma pokrywki ani bursztynowej nogi. Kształt czaszy, podobnie jak w G110, nawiązuje do kieliszka do porto.

Przeznaczenie: lżejsze, słodkie i owocowo-kwiatowe whisky oraz podobne alkohole. Formowanie ręczne, mycie w zmywarce możliwe.

Sprzedaż: 1 sztuka.""",

    "11009": """G510 to kieliszek Amber Glass o pojemności 200 ml z pokrywką typu „inside”. Wysokość 18 cm, średnica 7,5 cm. Szkło przezroczyste, z wzorem, w kształcie tulipana.

Producent wskazuje go do whisky i rumu, także dymno-torfowych. Wykonanie ręczne. W karcie jest zgoda na zmywarkę.

Jedna sztuka, w opakowaniu.""",

    "12562": """V102 to czarna wersja zestawu sześciu kieliszków Amber Glass o pojemności 40 ml, do wódki, likieru, grappy i tequili. Wysokość 11 cm, średnica 3 cm. Motyw gładki, barwa w karcie — kolorowa.

Szkło jest formowane ręcznie. Zestaw można myć w zmywarce.

Sprzedawany wyłącznie jako 6 sztuk w jednym opakowaniu.""",

    "12563": """G610 to kieliszek Amber Glass 220 ml z pokrywką (w opisie sklepu nie podano, czy jest typu „inside”, czy „outside”). Wysokość 18 cm, średnica 7,5 cm. Szkło przezroczyste, z wzorem, kształt tulipana.

Przeznaczenie: whisky i rum, w tym style dymno-torfowe. Formowanie ręczne, mycie w zmywarce dopuszczalne.

Oferta dotyczy 1 sztuki.""",

    "12564": """G602 to czarny kieliszek Amber Glass o pojemności 220 ml, z pokrywką. Wymiary: 18 cm wysokości, 7,5 cm średnicy. Czasza w kształcie tulipana, szkło z wzorem. W karcie barwa figuruje jako przezroczysta, natomiast nazwa i opis produktu określają kolor jako czarny.

Model jest przeznaczony do whisky i rumu, także dymno-torfowych. Szkło robione ręcznie, zmywarka dopuszczalna.

Sprzedawany pojedynczo.""",

    "13049": """Zestaw Amber Glass NO 1 zawiera dwie ręcznie robione kryształowe szklanki do whisky o pojemności 330 ml. Wysokość szklanki to 10,5 cm, średnica 8 cm. Szkło przezroczyste, z wzorem. Numer NO 1 oznacza wariant szlifu w tej serii, a nie ocenę produktu.

Przeznaczenie: whisky i rum. W karcie rekomendowane jest mycie ręczne (bez adnotacji o zmywarce).

Komplet 2 sztuk.""",

    "13050": """Amber Glass NO 2 to para kryształowych szklanek do whisky, każda o pojemności 330 ml. Wysokość 10,5 cm, średnica 8 cm. Szkło przezroczyste, zdobione szlifem w wariancie oznaczonym jako NO 2.

Szklanki są formowane ręcznie i przeznaczone do whisky oraz rumu. Producent zaleca mycie ręczne.

Sprzedaż w zestawie 2 sztuk.""",

    "13051": """Wariant NO 3 serii kryształowych szklanek Amber Glass ma pojemność 330 ml, wysokość 10,5 cm i średnicę 8 cm. W zestawie są dwie sztuki. Szkło przezroczyste, z wzorem charakterystycznym dla numeru NO 3.

Przeznaczenie: whisky i rum. Wykonanie ręczne. Rekomendowane mycie ręczne.

Pakowane jako komplet.""",

    "13052": """Zestaw NO 4 obejmuje dwie kryształowe szklanki Amber Glass o pojemności 330 ml. Wymiary: 10,5 cm wysokości, 8 cm średnicy. Przezroczyste szkło z wzorem wariantu NO 4, formowane ręcznie.

Szklanki są przeznaczone do whisky i rumu. W karcie widnieje rekomendacja mycia ręcznego.

Sprzedawane wyłącznie parami.""",

    "13055": """NO 7 to mniejszy wariant kryształowych szklanek Amber Glass: pojemność 240 ml, wysokość 10 cm, średnica 8 cm. Zestaw liczy dwie sztuki. Szkło przezroczyste, z wzorem oznaczonym numerem NO 7.

Przeznaczenie pozostaje to samo — whisky i rum. Wykonanie ręczne, mycie ręczne rekomendowane przez producenta.

Komplet 2 sztuk.""",

    "13056": """Zestaw Amber Glass NO 8 zawiera dwie kryształowe szklanki o pojemności 240 ml, wysokości 10 cm i średnicy 8 cm. Wzór szlifu odpowiada numerowi NO 8 w tej serii.

Szklanki są ręcznie robione, przezroczyste, z wzorem, i przeznaczone do whisky oraz rumu. Zalecane mycie ręczne.

Sprzedaż w parze.""",

    "14080": """CG300 to zestaw dwóch kieliszków Amber Glass do koniaku, brandy i armaniaku, każdy o pojemności 480 ml. Wysokość 14 cm, średnica 7 cm. Szkło przezroczyste, z wzorem; w opisie pojawia się subtelny, pionowy szlif. Czasza jest zaokrąglona, typowa dla tego rodzaju trunków.

Naczynia są formowane ręcznie. W karcie dopuszczono mycie w zmywarce.

Dwie sztuki w jednym opakowaniu.""",

    "14990": """Amber Box III to zestaw dwóch szklanek Amber Glass typu classic tumbler o pojemności 300 ml. Wysokość 10,8 cm, średnica 8 cm. Materiał podany w opisie to szkło sodowe, formowane i dmuchane ręcznie, z ręcznie wykonywanym wzorem. Szkło jest przezroczyste.

Szklanki są przeznaczone do whisky i rumu; szersze dno daje im stabilność. Zestaw jest pakowany w opakowanie o satynowym wykończeniu, z wypełnieniem transportowym. W karcie dopuszczono zmywarkę.

Sprzedaż: komplet 2 sztuk.""",
}


def slug(text: str) -> str:
    trans = str.maketrans({
        "ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n", "ó": "o",
        "ś": "s", "ź": "z", "ż": "z",
    })
    s = (text or "").lower().translate(trans)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def load_source_products() -> list[dict]:
    if SOURCE_JSON.exists():
        return json.loads(SOURCE_JSON.read_text(encoding="utf-8"))
    # zapasowo: parsuj cache
    cat = Path("/tmp/amberglass/category.html")
    soup = BeautifulSoup(cat.read_text(encoding="utf-8"), "lxml")
    out = []
    for tile in soup.select(".products .product"):
        pid = tile.get("data-product-id")
        a = tile.select_one("a.prodname[href]")
        url = abs_url(a["href"], CATEGORY_URL)
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        html = (CACHE / f"{key}.html").read_text(encoding="utf-8")
        p = parse_product(html, url, {"id": pid, "url": url, "listing_title": a.get_text(" ", strip=True)})
        p["source_description"] = p.get("description") or ""
        p["attributes"] = [[a_, b_] for a_, b_ in (p.get("attributes") or [])]
        out.append(p)
    return out


def match_images(sku: str, title: str, files: list[str]) -> tuple[list[str], list[str]]:
    """Zwraca (pliki, powody)."""
    chosen: list[str] = []
    reasons: list[str] = []
    sku_u = (sku or "").strip()
    sku_up = sku_u.upper()
    sku_slug = slug(sku_u)

    # 1) typowy kod typu G100 / CG200 / V101
    if sku_up and SKU_TOKEN.match(sku_up):
        dedicated = [f for f in files if parse_filename_skus(f)[0] == [sku_up]]
        shared = [f for f in files if sku_up in parse_filename_skus(f)[0] and f not in dedicated]
        dedicated.sort(key=lambda f: sort_key_for_sku(f, sku_up))
        shared.sort(key=lambda f: sort_key_for_sku(f, sku_up))
        if dedicated:
            chosen.extend(dedicated)
            reasons.append(f"SKU {sku_up} (dedykowane)")
        if shared:
            chosen.extend(shared)
            reasons.append(f"SKU {sku_up} (wspólne)")

    # 2) slug SKU jako prefiks nazwy pliku (Amber Box II, Amber Box III, amber box)
    if sku_slug and not SKU_TOKEN.match(sku_up):
        for f in files:
            stem = Path(f).stem
            if stem == sku_slug or stem.startswith(sku_slug + "-"):
                rest = stem[len(sku_slug):]
                # nie bierz amber-box-ii, gdy SKU to amber-box
                if rest.startswith("-") and re.match(r"-(ii|iii|iv|black|no)\b", rest):
                    continue
                if "black" in stem.split("-") and "black" not in slug(title) and "czarn" not in slug(title):
                    continue
                if f not in chosen:
                    chosen.append(f)
                    reasons.append(f"nazwa SKU {sku_u}")

    title_l = (title or "").lower()

    # 3) szlify kryształowe NO 1–8
    m = re.search(r"\bno\.?\s*([1-8])\b", title_l)
    if m and ("kryształ" in title_l or "krysztal" in slug(title)):
        num = m.group(1)
        for f in files:
            stem = Path(f).stem
            if re.fullmatch(rf"szlif-n[ro]-{num}", stem) or stem.startswith(f"szlif-n") and stem.endswith(f"-{num}"):
                if f not in chosen:
                    chosen.append(f)
                    reasons.append(f"szlif NO {num}")
        # wspólne zdjęcia pudełka Crystal Box
        for f in files:
            if Path(f).stem.startswith("crystal-box") and f not in chosen:
                chosen.append(f)
                reasons.append("opakowanie Crystal Box")

    # 4) zestawy nazwane
    extra_prefixes: list[tuple[str, str]] = []
    if sku_u.lower() == "amber tasting set" or ( "6 szt" in title_l and "102" in title_l):
        extra_prefixes.append(("amber-set", "Amber Set"))
    if "copa" in sku_slug or re.search(r"600\s*ml", title_l) and "gin" in title_l:
        extra_prefixes.append(("copa-gt", "Copa G&T"))
    if re.search(r"170\s*ml", title_l) and ("szampan" in title_l or "koktajl" in title_l):
        extra_prefixes.append(("coupete", "Coupete"))
        extra_prefixes.append(("copa-small", "Copa small"))
    if sku_u.lower() in {"amber box iii", "amber box iii"} or ("300 ml" in title_l and "szklanek" in title_l and "kryształ" not in title_l):
        extra_prefixes.append(("classic-tumblers", "classic tumblers"))

    for prefix, label in extra_prefixes:
        for f in files:
            if Path(f).stem == prefix or Path(f).stem.startswith(prefix + "-"):
                if f not in chosen:
                    chosen.append(f)
                    reasons.append(label)

    # kolejność: najpierw pliki z numerem -1, potem reszta, bez duplikatów
    uniq: list[str] = []
    for f in chosen:
        if f not in uniq:
            uniq.append(f)
    return uniq, reasons


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", (text or "").strip())
    parts = re.split(r"(?<=[\.\!\?])\s+", text)
    out = []
    for p in parts:
        s = p.strip().strip("„”\"' ").lower()
        s = re.sub(r"\s+", " ", s)
        if s:
            out.append(s)
    return out


def ngrams(text: str, n: int = 8) -> set[str]:
    words = re.findall(r"[a-ząćęłńóśźż0-9]+", (text or "").lower())
    return {" ".join(words[i:i + n]) for i in range(0, max(0, len(words) - n + 1))}


def uniqueness_report(products: list[dict]) -> dict:
    issues = []
    for p in products:
        src = p.get("source_description") or ""
        dst = p.get("description") or ""
        src_sent = set(split_sentences(src))
        copied = []
        for s in split_sentences(dst):
            # pomijamy bardzo krótkie urywki typu „Komplet 2 sztuk.”
            if len(s) >= 40 and s in src_sent:
                copied.append(s)
        src_ng = ngrams(src, 8)
        overlap = [g for g in ngrams(dst, 8) if g in src_ng]
        # odfiltruj ngramy będące suchymi faktami technicznymi (pojemność 102 ml itd.)
        overlap_interesting = [
            g for g in overlap
            if not re.fullmatch(r"(pojemność|wysokość|średnica|wymiary).{0,40}", g)
        ]
        if copied or len(overlap_interesting) >= 2:
            issues.append({
                "id": p["id"],
                "copied_sentences": copied,
                "shared_8grams": overlap_interesting[:8],
            })
    return {"ok": not issues, "issues": issues}


def main() -> int:
    source = load_source_products()
    files = list_official_images(IMAGES_DIR)
    warsaw = timezone(timedelta(hours=1))
    now = datetime.now(warsaw).strftime("%Y-%m-%d %H:%M %Z")

    missing_text = [p["id"] for p in source if p["id"] not in DESCRIPTIONS or p["id"] not in TITLES]
    if missing_text:
        raise SystemExit(f"Brak przepisanych tekstów dla: {missing_text}")

    used_files: set[str] = set()
    products = []
    for p in sorted(source, key=lambda x: int(x["id"]) if str(x["id"]).isdigit() else x["id"]):
        pid = p["id"]
        sku = p.get("mpn") or ""
        official, reasons = match_images(sku, p.get("title") or "", files)
        shop_images = list(p.get("images") or [])
        if official:
            images = [IMAGE_BASE.rstrip("/") + "/" + f for f in official]
            image_source = "official"
            used_files.update(official)
        else:
            images = shop_images
            image_source = "shop"
        attrs = p.get("attributes") or []
        if attrs and isinstance(attrs[0], (list, tuple)):
            attrs_obj = {k: v for k, v in attrs}
        else:
            attrs_obj = dict(attrs)
        products.append({
            "id": pid,
            "sku": sku or None,
            "gtin": p.get("gtin") or None,
            "title": TITLES[pid],
            "title_source": p.get("title"),
            "description": DESCRIPTIONS[pid].strip() + "\n",
            "description_source": p.get("source_description") or p.get("description") or "",
            "link": p.get("link"),
            "price": p.get("price"),
            "sale_price": p.get("sale_price"),
            "currency": p.get("currency") or "PLN",
            "availability": p.get("availability"),
            "brand": "Amber Glass",
            "condition": "new",
            "product_type": p.get("product_type"),
            "attributes": attrs_obj,
            "images": images,
            "image_files": official,
            "image_source": image_source,
            "image_match_reasons": reasons,
            "shop_images": shop_images if image_source == "shop" else [],
        })

    # kontrola unikalności wobec tekstu źródłowego (bez pola description_source w evencie — porównujemy lokalnie)
    check_payload = [
        {"id": p["id"], "source_description": next(s.get("source_description") or s.get("description") or "" for s in source if s["id"] == p["id"]), "description": p["description"]}
        for p in products
    ]
    report = uniqueness_report(check_payload)
    if not report["ok"]:
        print("UWAGA: znaleziono podobieństwa do źródła:", json.dumps(report, ensure_ascii=False, indent=2))
        # nie przerywamy zapisu, ale zgłaszamy — po poprawkach można puścić ponownie

    unmatched = [f for f in files if f not in used_files]
    without_official = [
        {"id": p["id"], "sku": p.get("sku"), "title": p["title"]}
        for p in products if p["image_source"] != "official"
    ]

    # description_source zostawiamy w pliku roboczym? Lepiej nie — drugi worker nie potrzebuje kopii sklepu.
    public_products = []
    for p in products:
        q = dict(p)
        q.pop("description_source", None)
        public_products.append(q)

    doc = {
        "generated_at": now,
        "brand": "Amber Glass",
        "source": "https://zlotywidelec.pl/amber-glass",
        "image_base_url": IMAGE_BASE,
        "product_count": len(public_products),
        "products": public_products,
        "image_matching": {
            "official_files_total": len(files),
            "used_files": sorted(used_files),
            "used_count": len(used_files),
            "unmatched_files": unmatched,
            "products_without_official_photos": without_official,
        },
        "uniqueness_check": {"copied_sentences_found": not report["ok"], "issues": report["issues"]},
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Zapisano {len(public_products)} produktów do {OUT}")
    print(f"Oficjalne zdjęcia: {len(files)}, użyte: {len(used_files)}, niedopasowane: {len(unmatched)}")
    if without_official:
        print("Bez zdjęcia z archiwum:", ", ".join(f"{x['id']}/{x.get('sku')}" for x in without_official))
    if unmatched:
        print("Niedopasowane pliki:")
        for f in unmatched:
            print(" ", f)
    if report["ok"]:
        print("Kontrola unikalności: brak skopiowanych zdań ze źródła.")
    else:
        print(f"Kontrola unikalności: {len(report['issues'])} produktów do poprawy.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
