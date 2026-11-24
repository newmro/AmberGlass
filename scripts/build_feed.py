#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Buduje plik XML feedu produktowego marki Amber Glass dla Bestlinkera.

Źródło produktów i zdjęć: https://zlotywidelec.pl/amber-glass

Bestlinker nie publikuje własnej specyfikacji pliku produktowego
(stan na 24.11.2026, https://bestlinker.pl/). Feed jest w formacie
Google Merchant Center RSS 2.0 z przestrzenią nazw g:, powszechnie
przyjmowanym przez polskie sieci reklamowe i importery feedów.

Dokumentacja formatu:
https://support.google.com/merchants/answer/14987622
https://support.google.com/merchants/answer/7052112
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from lxml import etree

BASE = "https://zlotywidelec.pl"
CATEGORY_URL = "https://zlotywidelec.pl/amber-glass"
BRAND = "Amber Glass"
G_NS = "http://base.google.com/ns/1.0"
NSMAP = {"g": G_NS}
IMAGE_BASE_DEFAULT = "https://raw.githubusercontent.com/newmro/AmberGlass/main/images/"
SKU_TOKEN = re.compile(r"^[a-z]{1,3}\d{2,4}$", re.I)
USER_AGENT = (
    "Mozilla/5.0 (compatible; AmberGlass-feed/1.0; +https://zlotywidelec.pl/amber-glass)"
)
CRAWL_DELAY = 1.1
TIMEOUT = 40

AVAILABILITY_MAP = {
    "instock": "in_stock",
    "outofstock": "out_of_stock",
    "soldout": "out_of_stock",
    "discontinued": "out_of_stock",
    "preorder": "preorder",
    "presale": "preorder",
    "backorder": "backorder",
    "limitedavailability": "in_stock",
    "onlineonly": "in_stock",
    "instoreonly": "in_stock",
}


def gtag(name: str) -> str:
    return f"{{{G_NS}}}{name}"


def abs_url(href: str, base: str = BASE) -> str:
    href = (href or "").strip()
    if not href:
        return ""
    return urljoin(base if base.endswith("/") else base + "/", href)


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = unescape(value)
    text = text.replace("\xa0", " ").replace("\u200b", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def html_to_text(el) -> str:
    if el is None:
        return ""
    work = BeautifulSoup(str(el), "lxml")
    for tag in work.find_all(["script", "style"]):
        tag.decompose()
    for br in work.find_all("br"):
        br.replace_with("\n")
    for p in work.find_all(["p", "div", "h1", "h2", "h3", "h4", "li", "tr"]):
        p.append("\n")
    return clean_text(work.get_text("\n"))


def parse_price(value: str | None) -> str | None:
    if not value:
        return None
    text = clean_text(value)
    text = re.sub(r"(?i)(zł|pln|cena regularna:|cena:)", "", text).strip()
    text = text.replace(" ", "")
    if re.search(r"\d+,\d{2}", text) and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    if not m:
        return None
    return f"{float(m.group(1)):.2f}"


def price_with_currency(amount: str, currency: str = "PLN") -> str:
    return f"{amount} {currency}"


def normalize_availability(schema_href: str | None, label: str | None) -> str | None:
    if schema_href:
        key = urlparse(schema_href).path.rstrip("/").split("/")[-1].lower()
        if key in AVAILABILITY_MAP:
            return AVAILABILITY_MAP[key]
    label_l = (label or "").strip().lower()
    if not label_l:
        return None
    if any(x in label_l for x in ("niedostęp", "brak towaru", "wyprzedan")):
        return "out_of_stock"
    if "przedsprzeda" in label_l:
        return "preorder"
    if "zamówienie" in label_l or "sprowadz" in label_l:
        return "backorder"
    if any(
        x in label_l
        for x in ("dostępny", "duża ilość", "na wyczerpaniu", "ostatni", "w magazynie")
    ):
        return "in_stock"
    return None


class Fetcher:
    def __init__(self, cache_dir: Path | None = None) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
            }
        )
        self._last = 0.0
        self.cache_dir = cache_dir
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, url: str) -> requests.Response:
        wait = CRAWL_DELAY - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        resp = self.session.get(url, timeout=TIMEOUT)
        self._last = time.monotonic()
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp

    def get_text(self, url: str) -> str:
        path = None
        if self.cache_dir:
            key = hashlib.sha256(url.encode("utf-8")).hexdigest()
            path = self.cache_dir / f"{key}.html"
            if path.exists():
                return path.read_text(encoding="utf-8")
        text = self.get(url).text
        if path is not None:
            path.write_text(text, encoding="utf-8")
        return text


def listing_page_url(category_url: str, page: int) -> str:
    if page <= 1:
        return category_url
    return category_url.rstrip("/") + f"/{page}"


def collect_listing(fetcher: Fetcher, category_url: str) -> list[dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    page = 1
    empty_pages = 0
    while page <= 50:
        url = listing_page_url(category_url, page)
        print(f"Lista produktów, strona {page}: {url}", flush=True)
        soup = BeautifulSoup(fetcher.get_text(url), "lxml")
        tiles = soup.select(".products .product[data-product-id], .products .product")
        new_on_page = 0
        for tile in tiles:
            pid = (tile.get("data-product-id") or "").strip()
            if not pid:
                fav = tile.select_one('a[href*="/fav/add/"]')
                if fav:
                    m = re.search(r"/fav/add/(\d+)", fav.get("href", ""))
                    pid = m.group(1) if m else ""
            if not pid:
                continue
            if pid in found:
                continue
            name_a = tile.select_one("a.prodname[href], a.prodimage[href]")
            href = name_a.get("href") if name_a else ""
            if not href or "/fav/" in href or href.rstrip("/") == "/amber-glass":
                for a in tile.find_all("a", href=True):
                    h = a["href"]
                    if "/fav/" in h or h.rstrip("/") in ("/amber-glass", "/", ""):
                        continue
                    href = h
                    break
            if not href:
                continue
            found[pid] = {
                "id": pid,
                "url": abs_url(href, url),
                "listing_title": clean_text(
                    (tile.select_one(".productname") or tile).get_text(" ", strip=True)
                ),
            }
            new_on_page += 1

        print(f"  nowe: {new_on_page}, łącznie: {len(found)}", flush=True)
        if new_on_page == 0:
            empty_pages += 1
            if page == 1:
                raise RuntimeError(f"Nie znaleziono produktów na {url}")
            break

        paginator = soup.select_one(".paginator")
        next_links = []
        if paginator:
            for a in paginator.find_all("a", href=True):
                next_links.append(a["href"])
        if not next_links:
            # Brak paginacji — wszystkie produkty są na jednej stronie.
            break
        page += 1

    return [found[k] for k in sorted(found, key=lambda x: int(x) if x.isdigit() else x)]


def first_itemprop(soup: BeautifulSoup, name: str, attr: str | None = None) -> str:
    el = soup.find(attrs={"itemprop": name})
    if not el:
        return ""
    if attr:
        return (el.get(attr) or "").strip()
    return (el.get("content") or el.get("href") or el.get("src") or el.get_text(" ", strip=True) or "").strip()


def all_itemprop_links(soup: BeautifulSoup, name: str) -> list[str]:
    out: list[str] = []
    for el in soup.find_all(attrs={"itemprop": name}):
        val = (el.get("href") or el.get("src") or el.get("content") or "").strip()
        if val and val not in out:
            out.append(val)
    return out


def parse_product(html: str, page_url: str, listing: dict[str, str]) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    canonical = soup.find("link", rel="canonical")
    url = (canonical.get("href") if canonical else "") or first_itemprop(soup, "url") or page_url
    url = abs_url(url, page_url)

    body = soup.body
    pid = listing["id"]
    if body:
        for cls in body.get("class") or []:
            m = re.search(r"shop_product(\d+)$", cls)
            if m:
                pid = m.group(1)
                break

    title_el = soup.select_one("h1.name, h1[itemprop=name], h1")
    title = clean_text(title_el.get_text(" ", strip=True) if title_el else "") or listing.get(
        "listing_title", ""
    )

    sku = first_itemprop(soup, "sku") or first_itemprop(soup, "mpn")
    if not sku:
        code = soup.select_one(".row.code, .code")
        if code:
            m = re.search(r"(?:Kod produktu|SKU|Kod)\s*:\s*(\S+)", code.get_text(" ", strip=True), re.I)
            if m:
                sku = m.group(1)

    gtin = first_itemprop(soup, "gtin") or first_itemprop(soup, "gtin13") or first_itemprop(soup, "gtin14")
    if gtin:
        gtin = re.sub(r"\s+", "", gtin)

    brand = first_itemprop(soup, "brand") or BRAND
    brand = clean_text(brand) or BRAND

    currency = first_itemprop(soup, "priceCurrency") or "PLN"
    current = parse_price(first_itemprop(soup, "price"))
    regular = None
    regular_p = soup.select_one("p.price__regular")
    if regular_p and "none" not in (regular_p.get("class") or []):
        regular = parse_price(regular_p.get_text(" ", strip=True))

    price = current
    sale_price = None
    if current and regular:
        try:
            if float(regular) > float(current):
                price = regular
                sale_price = current
        except ValueError:
            pass

    schema_av = ""
    av_el = soup.find("link", itemprop="availability") or soup.find(attrs={"itemprop": "availability"})
    if av_el:
        schema_av = (av_el.get("href") or av_el.get("content") or "").strip()
    av_label = ""
    av_row = soup.select_one(".row.availability .second, .availability .row.availability .second")
    if av_row:
        av_label = av_row.get_text(" ", strip=True)
    availability = normalize_availability(schema_av, av_label)

    crumbs: list[str] = []
    bc = soup.select_one(".breadcrumbs")
    if bc:
        for a in bc.find_all("a"):
            t = clean_text(a.get_text(" ", strip=True))
            if t and t.lower() not in {"jesteś w:", "jesteś w", "strona główna", "home"}:
                crumbs.append(t)
        # ostatni okruszek to zwykle nazwa produktu — pomijamy
        if crumbs and title and crumbs[-1].lower() == title.lower():
            crumbs = crumbs[:-1]
    product_type = " > ".join(crumbs) if crumbs else ""

    images: list[str] = []
    gal = soup.select_one("#galeria")
    if gal:
        for a in gal.select("a.gallery[href], a.js__gallery-anchor-image[href]"):
            href = a.get("href") or ""
            if "productGfx_" in href:
                images.append(abs_url(href, page_url))
    if not images:
        for href in all_itemprop_links(soup, "image"):
            if "productGfx_" in href:
                images.append(abs_url(href, page_url))
    # unikalne, pełny rozmiar (już _0_0 z galerii)
    uniq_images: list[str] = []
    for img in images:
        if img not in uniq_images:
            uniq_images.append(img)

    desc_el = soup.select_one("[itemprop=description]") or soup.select_one("#box_description .innerbox")
    description = html_to_text(desc_el)

    attributes: list[tuple[str, str]] = []
    data_box = soup.select_one("#box_productdata table")
    if data_box:
        for tr in data_box.find_all("tr"):
            name_td = tr.select_one("td.name")
            val_td = tr.select_one("td.value")
            if not name_td or not val_td:
                continue
            an = clean_text(name_td.get_text(" ", strip=True))
            av = clean_text(val_td.get_text(" ", strip=True))
            if an and av:
                attributes.append((an, av))

    return {
        "id": pid,
        "title": title,
        "description": description,
        "link": url,
        "images": uniq_images,
        "availability": availability,
        "price": price,
        "sale_price": sale_price,
        "currency": currency or "PLN",
        "brand": brand,
        "gtin": gtin,
        "mpn": sku,
        "product_type": product_type,
        "attributes": attributes,
        "condition": "new",
    }


def cdata(text: str) -> etree.CDATA:
    # Rozdzielamy sekwencję zamykającą CDATA, gdyby wystąpiła w treści.
    safe = (text or "").replace("]]>", "]] >")
    return etree.CDATA(safe)


def append_g(parent, name: str, value: str | None, use_cdata: bool = False) -> None:
    if value is None or value == "":
        return
    el = etree.SubElement(parent, gtag(name))
    if use_cdata:
        el.text = cdata(value)
    else:
        el.text = value


def build_rss(products: list[dict[str, Any]], category_url: str) -> etree._Element:
    warsaw = timezone(timedelta(hours=1))
    now = datetime.now(warsaw).strftime("%Y-%m-%d %H:%M %Z")

    rss = etree.Element("rss", version="2.0", nsmap=NSMAP)
    channel = etree.SubElement(rss, "channel")
    title = etree.SubElement(channel, "title")
    title.text = cdata("Amber Glass — Złoty Widelec")
    link = etree.SubElement(channel, "link")
    link.text = category_url
    desc = etree.SubElement(channel, "description")
    desc.text = cdata(
        "Oferta marki Amber Glass ze sklepu zlotywidelec.pl. "
        f"Wygenerowano {now}. Format: Google Merchant Center RSS 2.0."
    )

    for p in products:
        item = etree.SubElement(channel, "item")
        append_g(item, "id", p["id"])
        append_g(item, "title", p["title"], use_cdata=True)
        append_g(item, "description", p["description"], use_cdata=True)
        append_g(item, "link", p["link"])
        images = p.get("images") or []
        if images:
            append_g(item, "image_link", images[0])
            for extra in images[1:]:
                append_g(item, "additional_image_link", extra)
        append_g(item, "availability", p.get("availability"))
        currency = p.get("currency") or "PLN"
        if p.get("price"):
            append_g(item, "price", price_with_currency(p["price"], currency))
        if p.get("sale_price"):
            append_g(item, "sale_price", price_with_currency(p["sale_price"], currency))
        append_g(item, "brand", p.get("brand") or BRAND, use_cdata=True)
        append_g(item, "gtin", p.get("gtin"))
        append_g(item, "mpn", p.get("mpn"))
        append_g(item, "condition", p.get("condition") or "new")
        append_g(item, "product_type", p.get("product_type"), use_cdata=True)
        for name, value in p.get("attributes") or []:
            detail = etree.SubElement(item, gtag("product_detail"))
            append_g(detail, "section_name", "Dane techniczne", use_cdata=True)
            append_g(detail, "attribute_name", name, use_cdata=True)
            append_g(detail, "attribute_value", value, use_cdata=True)
    return rss


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
    doc = etree.parse(str(path))
    items = doc.findall("channel/item")
    if not items:
        raise RuntimeError("Feed nie zawiera żadnych elementów item")
    required = [gtag("id"), gtag("title"), gtag("link"), gtag("price"), gtag("image_link")]
    for item in items:
        missing = [r for r in required if item.find(r) is None or not (item.find(r).text or "")]
        if missing:
            pid = item.findtext(gtag("id"))
            raise RuntimeError(f"Produkt {pid} nie ma wymaganych pól: {missing}")
    return len(items)



def parse_filename_skus(filename: str) -> tuple[list[str], str]:
    """Z nazwy pliku (np. g100-g101-1.jpg) wyciąga kody SKU i resztę (numer zdjęcia)."""
    stem = Path(filename).stem.lower()
    parts = stem.split("-")
    skus: list[str] = []
    i = 0
    while i < len(parts) and SKU_TOKEN.match(parts[i]):
        skus.append(parts[i].upper())
        i += 1
    rest = "-".join(parts[i:])
    return skus, rest


def list_official_images(images_dir: Path) -> list[str]:
    if not images_dir.exists():
        return []
    return sorted(f.name for f in images_dir.iterdir() if f.suffix.lower() in {".jpg", ".jpeg"} and f.is_file())


def sort_key_for_sku(filename: str, sku: str) -> tuple:
    skus, rest = parse_filename_skus(filename)
    sku_u = sku.upper()
    nums: list[int] = []
    if rest:
        nums = [int(x) if x.isdigit() else 50 for x in rest.split("-") if x]
    if skus == [sku_u]:
        return (0, nums or [0], filename)
    if sku_u in skus:
        return (1, nums or [0], filename)
    return (2, nums or [0], filename)


def product_name_groups(product: dict[str, Any]) -> list[str]:
    """Dodatkowe etykiety dopasowania po nazwie, gdy brakuje SKU w pliku."""
    title = (product.get("title") or "").lower()
    groups: list[str] = []
    m = re.search(r"\bno\.?\s*([1-8])\b", title)
    if m and "kryształ" in title.replace("talow", "tał"):
        groups.append(f"SZLIF-{m.group(1)}")
    elif m and "krysztal" in title:
        groups.append(f"SZLIF-{m.group(1)}")
    # ujednolicenie bez ogonków
    title_ascii = (
        title.replace("ą", "a")
        .replace("ć", "c")
        .replace("ę", "e")
        .replace("ł", "l")
        .replace("ń", "n")
        .replace("ó", "o")
        .replace("ś", "s")
        .replace("ź", "z")
        .replace("ż", "z")
    )
    if re.search(r"\bno\.?\s*([1-8])\b", title_ascii) and "krysztal" in title_ascii:
        num = re.search(r"\bno\.?\s*([1-8])\b", title_ascii).group(1)
        tag = f"SZLIF-{num}"
        if tag not in groups:
            groups.append(tag)
    if "gin" in title_ascii or (re.search(r"600\s*ml", title_ascii) and "koktajl" in title_ascii):
        groups.append("COPA-GT")
    if "szampan" in title_ascii or "coupe" in title_ascii or (
        re.search(r"170\s*ml", title_ascii) and "koktajl" in title_ascii
    ):
        groups.append("COUPE")
    if "sakhrani" in title_ascii:
        if "kieliszek" in title_ascii or "koktajl" in title_ascii:
            groups.append("SAKHRANI-KIELISZEK")
        if "szklanka" in title_ascii:
            groups.append("SAKHRANI-SZKLANKA")
        if "SAKHRANI-KIELISZEK" not in groups and "SAKHRANI-SZKLANKA" not in groups:
            groups.append("SAKHRANI")
    if "highball" in title_ascii:
        groups.append("HIGHBALL")
    if "tartan" in title_ascii:
        groups.append("TARTAN")
    if re.search(r"szklan(ka|ek|ki).*whisky", title_ascii) and "krysztal" not in title_ascii:
        if re.search(r"330\s*ml", title_ascii) or re.search(r"300\s*ml", title_ascii):
            groups.append("CLASSIC-TUMBLERS")
    if "woda" in title_ascii or "water glass" in title_ascii:
        groups.append("WATER-GLASS")
    # Zestawy z pokrywkami / pudełka — ostrożnie, tylko wyraźne nazwy
    if "zestaw" in title_ascii and "pokrywk" in title_ascii:
        groups.append("AMBER-SET")
    return groups


def file_name_groups(filename: str) -> list[str]:
    stem = Path(filename).stem.lower()
    groups: list[str] = []
    m = re.match(r"szlif-n[ro]-([1-8])$", stem)
    if m:
        groups.append(f"SZLIF-{m.group(1)}")
    if stem.startswith("classic-tumblers"):
        groups.append("CLASSIC-TUMBLERS")
    if stem.startswith("copa-gt"):
        groups.append("COPA-GT")
    if stem.startswith("copa-small") or stem.startswith("coupete"):
        groups.append("COUPE")
    if "sakhrani" in stem and "kieliszek" in stem:
        groups.append("SAKHRANI-KIELISZEK")
    elif "sakhrani" in stem and "szklanka" in stem:
        groups.append("SAKHRANI-SZKLANKA")
    elif "sakhrani" in stem:
        groups.append("SAKHRANI")
    if stem.startswith("highball"):
        groups.append("HIGHBALL")
    if "tartanu" in stem or "tartan" in stem:
        groups.append("TARTAN")
    if stem.startswith("water-glass"):
        groups.append("WATER-GLASS")
    if stem.startswith("amber-set"):
        groups.append("AMBER-SET")
    return groups


def match_official_images(
    products: list[dict[str, Any]],
    images_dir: Path,
    image_base: str,
) -> dict[str, Any]:
    files = list_official_images(images_dir)
    image_base = image_base.rstrip("/") + "/"
    # indeks SKU -> pliki
    by_sku: dict[str, list[str]] = {}
    by_group: dict[str, list[str]] = {}
    assigned: dict[str, set[str]] = {}  # file -> product ids

    for fn in files:
        skus, _rest = parse_filename_skus(fn)
        for sku in skus:
            by_sku.setdefault(sku, []).append(fn)
        for g in file_name_groups(fn):
            by_group.setdefault(g, []).append(fn)

    report_items = []
    used_files: set[str] = set()

    for p in products:
        sku = (p.get("mpn") or "").strip().upper()
        chosen: list[str] = []
        reasons: list[str] = []
        if sku and sku in by_sku:
            dedicated = [f for f in by_sku[sku] if parse_filename_skus(f)[0] == [sku]]
            shared = [f for f in by_sku[sku] if f not in dedicated]
            dedicated.sort(key=lambda f: sort_key_for_sku(f, sku))
            shared.sort(key=lambda f: sort_key_for_sku(f, sku))
            chosen.extend(dedicated + shared)
            if dedicated:
                reasons.append(f"SKU {sku} (zdjęcia dedykowane)")
            if shared:
                reasons.append(f"SKU {sku} (zdjęcia wspólne)")
        for g in product_name_groups(p):
            for fn in by_group.get(g, []):
                if fn not in chosen:
                    chosen.append(fn)
                    reasons.append(f"nazwa/{g}")
        # unikalne, zachowując kolejność
        uniq: list[str] = []
        for fn in chosen:
            if fn not in uniq:
                uniq.append(fn)
        chosen = uniq
        if chosen:
            p["shop_images"] = list(p.get("images") or [])
            p["images"] = [image_base + fn for fn in chosen]
            p["official_files"] = chosen
            p["image_source"] = "official"
            for fn in chosen:
                used_files.add(fn)
                assigned.setdefault(fn, set()).add(p["id"])
        else:
            p["image_source"] = "shop"
            p["official_files"] = []
        report_items.append(
            {
                "id": p["id"],
                "sku": sku or None,
                "title": p.get("title"),
                "source": p["image_source"],
                "files": chosen,
                "reasons": reasons,
            }
        )

    unmatched_files = [fn for fn in files if fn not in used_files]
    products_without_official = [
        {"id": p["id"], "sku": p.get("mpn"), "title": p.get("title")}
        for p in products
        if p.get("image_source") != "official"
    ]
    return {
        "official_total": len(files),
        "used_files": sorted(used_files),
        "unmatched_files": unmatched_files,
        "products_without_official": products_without_official,
        "items": report_items,
    }



def main() -> int:
    parser = argparse.ArgumentParser(description="Buduje feed XML Amber Glass dla Bestlinkera.")
    root_default = Path(__file__).resolve().parents[1]
    parser.add_argument("--category", default=CATEGORY_URL, help="Adres listy produktów Amber Glass")
    parser.add_argument(
        "--output",
        default=str(root_default / "bestlinker.xml"),
        help="Ścieżka pliku wynikowego XML",
    )
    parser.add_argument(
        "--cache-dir",
        default="/tmp/amberglass/html-cache",
        help="Katalog pamięci podręcznej stron HTML",
    )
    parser.add_argument(
        "--images-dir",
        default=str(root_default / "images"),
        help="Katalog oficjalnych zdjęć marki",
    )
    parser.add_argument(
        "--image-base-url",
        default=IMAGE_BASE_DEFAULT,
        help="Publiczny prefiks URL zdjęć w repozytorium",
    )
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir) if args.cache_dir else None
    fetcher = Fetcher(cache_dir=cache_dir)
    listing = collect_listing(fetcher, args.category)
    products: list[dict[str, Any]] = []
    errors: list[str] = []

    for i, entry in enumerate(listing, 1):
        print(f"[{i}/{len(listing)}] {entry['id']} {entry['url']}", flush=True)
        try:
            html = fetcher.get_text(entry["url"])
            product = parse_product(html, entry["url"], entry)
            if not product.get("title") or not product.get("price") or not product.get("link"):
                raise RuntimeError(
                    f"Brak podstawowych danych (title/price/link) dla {entry['id']}"
                )
            products.append(product)
            extra = f", zdjęć: {len(product.get('images') or [])}"
            ean = product.get("gtin") or "brak EAN"
            print(f"    {product['title'][:70]} | {product.get('price')} {ean}{extra}", flush=True)
        except Exception as exc:  # noqa: BLE001 — zbieramy błąd i idziemy dalej
            msg = f"{entry['id']} {entry['url']}: {exc}"
            errors.append(msg)
            print(f"    BŁĄD: {exc}", flush=True)

    if errors:
        print("Nie udało się pobrać niektórych produktów:", file=sys.stderr)
        for e in errors:
            print("  -", e, file=sys.stderr)
        if len(products) < len(listing) * 0.9:
            return 1

    # stała kolejność po identyfikatorze sklepu
    products.sort(key=lambda p: int(p["id"]) if str(p["id"]).isdigit() else p["id"])

    images_dir = Path(args.images_dir)
    match_report = match_official_images(products, images_dir, args.image_base_url)
    report_path = Path(args.output).resolve().parent / "image-matching.json"
    # zbiory nie wchodzą do JSON — zamieniamy
    serializable = dict(match_report)
    serializable["items"] = match_report["items"]
    report_path.write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Oficjalne zdjęcia: {match_report['official_total']}, "
        f"użyte: {len(match_report['used_files'])}, "
        f"niedopasowane pliki: {len(match_report['unmatched_files'])}, "
        f"produkty bez zdjęcia z archiwum: {len(match_report['products_without_official'])}",
        flush=True,
    )
    if match_report["unmatched_files"]:
        print("Niedopasowane pliki:", ", ".join(match_report["unmatched_files"]), flush=True)
    if match_report["products_without_official"]:
        print(
            "Produkty bez oficjalnego zdjęcia:",
            ", ".join(
                f"{x['id']}/{x.get('sku') or '-'}"
                for x in match_report["products_without_official"]
            ),
            flush=True,
        )

    out = Path(args.output)
    write_xml(build_rss(products, args.category), out)
    count = validate_xml(out)
    print(f"Zapisano {count} produktów do {out}", flush=True)

    no_ean = [p["id"] for p in products if not p.get("gtin")]
    no_sku = [p["id"] for p in products if not p.get("mpn")]
    no_img = [p["id"] for p in products if not p.get("images")]
    no_desc = [p["id"] for p in products if not p.get("description")]
    no_av = [p["id"] for p in products if not p.get("availability")]
    if no_ean:
        print(f"Bez EAN/GTIN ({len(no_ean)}): {', '.join(no_ean)}")
    if no_sku:
        print(f"Bez kodu produktu/SKU ({len(no_sku)}): {', '.join(no_sku)}")
    if no_img:
        print(f"Bez zdjęć ({len(no_img)}): {', '.join(no_img)}")
    if no_desc:
        print(f"Bez opisu ({len(no_desc)}): {', '.join(no_desc)}")
    if no_av:
        print(f"Bez dostępności ({len(no_av)}): {', '.join(no_av)}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
