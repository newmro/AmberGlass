#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Buduje plik XML produktów Amber Glass dla Luxury Products Marketplace.

Format wynika z publicznego panelu sprzedawcy Luxury Products
(https://seller.myluxuryproducts.com/) oraz tłumaczeń API:
https://seller.myluxuryproducts.com/backend/api/translations/pl

Oficjalny szablon (wymaga logowania do panelu) pobiera się jako
product-import-template.xml z:
  GET https://seller.myluxuryproducts.com/backend/api/file-import/template?format=xml

W panelu (Import produktów z pliku) pola szablonu to:
  group_id, title*, price*, sale_price, stock, sku, ean,
  manufacturer_code, image_urls, description, short_description,
  tax, category_path, manufacturer, variant_label
Gwiazdką oznaczono jedyne pola wymagane przy mapowaniu: title i price.

Panel automatycznie rozpoznaje też profil Google Shopping.
Akceptowane formaty pliku: CSV, XML, JSON.

Dostarczenie feedu:
  - wgranie pliku w panelu sprzedawcy po rejestracji
    (https://seller.myluxuryproducts.com/register), albo
  - stały URL feedu w konfiguracji „Automatyczny feed (URL)”
    (synchronizacja co 1 / 6 / 12 / 24 godziny).
Regulamin partnerów (https://www.luxuryproducts.pl/regulamin-wspolpracy-dla-partnerow-platformy.html)
wymaga, by plik XML leżał na serwerze partnera, nie na darmowym hostingu plików,
i może być też podany w formularzu zgłoszeniowym. Mechanizm serwisu pobiera
go automatycznie (w regulaminie: raz na dobę).
Wsparcie integracji: developers@myluxuryproducts.com

Ten skrypt składa XML w układzie oficjalnego szablonu: korzeń <products>,
rekord <product>, nazwy elementów identyczne z kluczami pól powyżej.
Brakujących wartości nie wymyśla — pomija puste elementy.
Opisy i tytuły bierze z products.json (wersje oryginalne, nie sklepowe).
"""

from __future__ import annotations

import argparse
import json
import sys
from math import floor
from pathlib import Path
from typing import Any

from lxml import etree

IMAGE_MAX_BYTES = 1024 * 1024  # limit zdjęcia w panelu (products.picturesHint)
IMAGE_URL_SEP = ", "

# Ścieżki z breadcrumbów luxuryproducts.pl (bez „Strona główna”).
CAT_WHISKY = "Dom i ogród > Wyroby kryształowe i szklane > Szklanki do whisky"
CAT_VODKA_SET = (
    "Dom i ogród > Wyroby kryształowe i szklane > Komplety do alkoholu "
    "> Komplety kieliszków do wódki"
)
CAT_CHAMPAGNE = (
    "Dom i ogród > Wyroby kryształowe i szklane > Kieliszki do alkoholu "
    "> Kieliszki do szampana"
)
CAT_DRINKS = (
    "Dom i ogród > Wyroby kryształowe i szklane > Kieliszki do alkoholu "
    "> Kieliszki do likieru, drinków, inne"
)
CAT_COGNAC = (
    "Dom i ogród > Wyroby kryształowe i szklane > Kieliszki do alkoholu "
    "> Kieliszki do koniaku"
)

# product_type ze źródłowego products.json -> kategoria Luxury Products
CATEGORY_BY_TYPE = {
    "Szkło > Szklanki i kieliszki do whisky, koniaku i rumu": CAT_WHISKY,
    "Szkło > Kieliszki do wódki, likierów, grappy i tequili": CAT_VODKA_SET,
    "Szkło > Szklanki do Drinków i Koktajli": CAT_DRINKS,
    "Szkło > Kieliszki do Szampana": CAT_CHAMPAGNE,
}

# Węższe dopasowanie po przeznaczeniu, gdy typ jest ogólny (whisky/koniak w jednej grupie).
CATEGORY_BY_PURPOSE = {
    "Koniak": CAT_COGNAC,
}

# Kolejność elementów jak w mapowaniu pól panelu sprzedawcy.
FIELD_ORDER = [
    "group_id",
    "title",
    "price",
    "sale_price",
    "stock",
    "sku",
    "ean",
    "manufacturer_code",
    "image_urls",
    "description",
    "short_description",
    "tax",
    "category_path",
    "manufacturer",
    "variant_label",
]

REQUIRED_IMPORT_FIELDS = ("title", "price")

# Pola szablonu, których nie ma w products.json (nie wymyślamy wartości).
OMITTED_TEMPLATE_FIELDS = [
    "group_id",
    "stock",
    "manufacturer_code",
    "short_description",
    "tax",
    "variant_label",
]


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").replace("\r", "\n").strip()


def markup(value: Any) -> str:
    # ceny +20% wzgledem zlotywidelec.pl, zaokraglenie w gore do ,90.
    text = clean_text(value)
    if not text:
        return ""
    x = float(text) * 1.20
    n = floor(x) + 0.9
    if n < x:
        n += 1
    return f"{n:.2f}"


def append_field(parent: etree._Element, name: str, value: str, *, cdata: bool = False) -> None:
    text = clean_text(value)
    if not text:
        return
    el = etree.SubElement(parent, name)
    if cdata and "]]>" not in text:
        el.text = etree.CDATA(text)
    else:
        el.text = text


def map_category(product: dict[str, Any]) -> str:
    purpose = clean_text((product.get("attributes") or {}).get("Przeznaczenie"))
    if purpose in CATEGORY_BY_PURPOSE:
        return CATEGORY_BY_PURPOSE[purpose]
    ptype = clean_text(product.get("product_type"))
    return CATEGORY_BY_TYPE.get(ptype, "")


def product_fields(product: dict[str, Any]) -> dict[str, str]:
    images = [clean_text(u) for u in (product.get("images") or []) if clean_text(u)]
    fields: dict[str, str] = {
        "title": clean_text(product.get("title")),
        "price": markup(product.get("price")),
        "sale_price": markup(product.get("sale_price")),
        "sku": clean_text(product.get("sku")),
        "ean": clean_text(product.get("gtin")),
        "image_urls": IMAGE_URL_SEP.join(images),
        "description": clean_text(product.get("description")),
        "category_path": map_category(product),
        "manufacturer": clean_text(product.get("brand")) or "Amber Glass",
    }
    return {k: v for k, v in fields.items() if v}


def build_xml(products: list[dict[str, Any]]) -> etree._Element:
    root = etree.Element("products")
    for product in products:
        node = etree.SubElement(root, "product")
        fields = product_fields(product)
        for name in FIELD_ORDER:
            if name not in fields:
                continue
            append_field(node, name, fields[name], cdata=(name == "description"))
    return root


def write_xml(root: etree._Element, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    xml_bytes = etree.tostring(
        root,
        encoding="UTF-8",
        xml_declaration=True,
        pretty_print=True,
    )
    path.write_bytes(xml_bytes)


def validate_xml(path: Path) -> int:
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    tree = etree.parse(str(path), parser)
    root = tree.getroot()
    if root.tag != "products":
        raise ValueError(f"Nieoczekiwany korzeń: <{root.tag}>")
    items = root.findall("product")
    if not items:
        raise ValueError("Brak elementów <product>")
    for i, item in enumerate(items, 1):
        title = (item.findtext("title") or "").strip()
        price = (item.findtext("price") or "").strip()
        if not title or not price:
            raise ValueError(f"Produkt #{i} bez wymaganego title/price")
    return len(items)


def oversized_images(products: list[dict[str, Any]], images_dir: Path) -> list[tuple[str, str, int]]:
    found: list[tuple[str, str, int]] = []
    if not images_dir.is_dir():
        return found
    for product in products:
        sku = clean_text(product.get("sku")) or clean_text(product.get("id"))
        for filename in product.get("image_files") or []:
            file_path = images_dir / filename
            if file_path.is_file():
                size = file_path.stat().st_size
                if size > IMAGE_MAX_BYTES:
                    found.append((sku, filename, size))
    return found


def report(
    products: list[dict[str, Any]],
    images_dir: Path,
) -> None:
    def missing(field: str) -> list[str]:
        out = []
        for product in products:
            fields = product_fields(product)
            sku = fields.get("sku") or clean_text(product.get("id"))
            if field not in fields:
                out.append(sku)
        return out

    print("Pola szablonu Luxury Products (wymagane przy imporcie: title, price):")
    for name in FIELD_ORDER:
        star = " (wymagane)" if name in REQUIRED_IMPORT_FIELDS else ""
        skipped = missing(name)
        if not skipped:
            print(f"  {name}{star}: komplet ({len(products)})")
        elif name in OMITTED_TEMPLATE_FIELDS:
            print(f"  {name}{star}: pominięte u wszystkich — brak danych, nie wymyślam")
        else:
            print(f"  {name}{star}: brak u {len(skipped)}: {', '.join(skipped)}")

    currencies = sorted({clean_text(p.get("currency")) for p in products if clean_text(p.get("currency"))})
    if currencies:
        print(
            "Waluta cen w danych źródłowych: "
            + ", ".join(currencies)
            + " (szablon importu nie ma pola waluty — walutę ustawia się w panelu)."
        )

    big = oversized_images(products, images_dir)
    if big:
        print(
            f"Zdjęcia powyżej limitu panelu 1 MB ({len(big)} w pliku, i tak trafiają do XML):"
        )
        for sku, filename, size in big:
            print(f"  {sku}: {filename} ({size / 1024:.0f} KB)")

    print("Poza szablonem XML, do publikacji w panelu potrzebne są jeszcze:")
    print("  — szablon wysyłki (ustawiany w koncie sprzedawcy, nie w pliku),")
    print("  — ostrzeżenia bezpieczeństwa i dane GPSR (nie ma ich w szablonie importu),")
    print("  — potwierdzenie kategorii, jeśli ścieżka nie zmapuje się automatycznie.")


def load_products(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        products = data.get("products")
        if not isinstance(products, list):
            raise ValueError(f"{path} nie zawiera listy products")
        return products
    if isinstance(data, list):
        return data
    raise ValueError(f"Nieoczekiwany format {path}")


def main() -> int:
    root_default = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Buduje XML Amber Glass dla Luxury Products Marketplace."
    )
    parser.add_argument(
        "--input",
        default=str(root_default / "products.json"),
        help="Ścieżka products.json z oryginalnymi opisami",
    )
    parser.add_argument(
        "--output",
        default=str(root_default / "luxuryproducts.xml"),
        help="Ścieżka wynikowego XML",
    )
    parser.add_argument(
        "--images-dir",
        default=str(root_default / "images"),
        help="Katalog zdjęć do sprawdzenia rozmiaru",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    images_dir = Path(args.images_dir)

    if not input_path.is_file():
        print(f"Brak pliku wejściowego: {input_path}", file=sys.stderr)
        return 1

    products = load_products(input_path)
    if not products:
        print("Brak produktów w pliku wejściowym.", file=sys.stderr)
        return 1

    write_xml(build_xml(products), output_path)
    count = validate_xml(output_path)
    print(f"Zapisano {count} produktów do {output_path}")
    report(products, images_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
