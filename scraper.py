#!/usr/bin/env python3
"""
Gold benchmark and buyer-comparison scraper.

The scraper only records prices parsed from public sources. If a source cannot be
read, it is represented as unavailable rather than estimated.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup


AED_PER_USD = 3.6725
TROY_OUNCE_GRAMS = 31.1034768
TOLA_GRAMS = 11.6638038
REQUEST_TIMEOUT = 14

UNIT_GRAMS = {
    "gram": 1.0,
    "10g": 10.0,
    "tola": TOLA_GRAMS,
    "troy_ounce": TROY_OUNCE_GRAMS,
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}


@dataclass(frozen=True)
class SourceConfig:
    rate_id: str
    market: str
    source_name: str
    source_type: str
    source_url: str
    purity: str
    fineness: int
    currency: str
    unit: str
    labels: tuple[str, ...]
    minimum: float
    maximum: float
    cadence: str
    notes: str


DIGITAL_AND_JEWELLERY_SOURCES = [
    SourceConfig(
        "safegold-999",
        "India Retail",
        "SafeGold",
        "Digital",
        "https://www.safegold.com/",
        "24K",
        999,
        "INR",
        "gram",
        ("24K", "999", "gold price", "buy price"),
        3000,
        25000,
        "Live retail quote when available",
        "Digital/home-delivery bullion source. Parsed only if a live quote is present in public page text.",
    ),
    SourceConfig(
        "augmont-999",
        "India Retail",
        "Augmont",
        "Digital",
        "https://www.augmont.com/",
        "24K",
        999,
        "INR",
        "gram",
        ("24K", "999", "gold rate", "buy gold"),
        3000,
        25000,
        "Live retail quote when available",
        "Digital gold source. Parsed only if a live quote is present in public page text.",
    ),
    SourceConfig(
        "tanishq-999",
        "India Jewellery",
        "Tanishq",
        "Jewellery",
        "https://www.tanishq.co.in/shop/gold-rate?lang=en_IN",
        "24K",
        999,
        "INR",
        "gram",
        ("24K", "999", "Bengaluru", "Bangalore"),
        3000,
        25000,
        "Retail jewellery page",
        "Retail jewellery context. Final purchase price may include GST, making charges, and SKU-level pricing.",
    ),
    SourceConfig(
        "tanishq-916",
        "India Jewellery",
        "Tanishq",
        "Jewellery",
        "https://www.tanishq.co.in/shop/gold-rate?lang=en_IN",
        "22K",
        916,
        "INR",
        "gram",
        ("22K", "916", "Bengaluru", "Bangalore"),
        2500,
        23000,
        "Retail jewellery page",
        "Retail jewellery context. Final purchase price may include GST, making charges, and SKU-level pricing.",
    ),
    SourceConfig(
        "caratlane-999",
        "India Jewellery",
        "CaratLane",
        "Jewellery",
        "https://www.caratlane.com/gold-rate",
        "24K",
        999,
        "INR",
        "gram",
        ("24K pure digital gold", "999"),
        3000,
        25000,
        "Retail jewellery page",
        "Retail jewellery context. Final purchase price may include GST, making charges, and SKU-level pricing.",
    ),
    SourceConfig(
        "caratlane-916",
        "India Jewellery",
        "CaratLane",
        "Jewellery",
        "https://www.caratlane.com/gold-rate",
        "22K",
        916,
        "INR",
        "gram",
        ("22ct", "22 ct", "22K", "916"),
        2500,
        23000,
        "Retail jewellery page",
        "Retail jewellery context. Final purchase price may include GST, making charges, and SKU-level pricing.",
    ),
]

MMTC_PAMP_SOURCE = SourceConfig(
    "mmtc-pamp-9999",
    "India Retail",
    "MMTC-PAMP",
    "Retail",
    "https://www.mmtcpamp.com/gold-silver-rate-today",
    "24K",
    999,
    "INR",
    "gram",
    ("999.9", "24K", "gold"),
    3000,
    25000,
    "Live retail bullion page when available",
    "Actual MMTC-PAMP bullion/coin/bar retail context. Prices may exclude GST and product-specific charges.",
)

ALL_INDIA_BULLION_SOURCES = [
    SourceConfig(
        "aib-mumbai-retail-999",
        "India Retail",
        "All India Bullion Mumbai Retail 999",
        "Retail",
        "https://allindiabullion.com/gold-rate/maharashtra/mumbai",
        "24K",
        999,
        "INR",
        "10g",
        ("RETAIL 999 GOLD",),
        50000,
        250000,
        "Live Mumbai bullion page",
        "Mumbai city retail 999 quote. GST and charges depend on the displayed product/transaction type.",
    ),
    SourceConfig(
        "aib-mumbai-rtgs-999",
        "India Retail",
        "All India Bullion Mumbai RTGS 999",
        "Retail",
        "https://allindiabullion.com/gold-rate/maharashtra/mumbai",
        "24K",
        999,
        "INR",
        "10g",
        ("RTGS 999 GOLD",),
        50000,
        250000,
        "Live Mumbai bullion page",
        "Mumbai RTGS 999 quote. Shown separately because it can differ from retail counter pricing.",
    ),
    SourceConfig(
        "aib-mumbai-gst-999",
        "India Retail",
        "All India Bullion Mumbai 999 with GST",
        "Retail",
        "https://allindiabullion.com/gold-rate/maharashtra/mumbai",
        "24K",
        999,
        "INR",
        "10g",
        ("999 WITH GST GOLD",),
        50000,
        250000,
        "Live Mumbai bullion page",
        "Mumbai 999 quote including GST as labeled by All India Bullion.",
    ),
]

CONSUMER_PORTAL_SOURCES = [
    SourceConfig(
        "upstox-999",
        "India Retail",
        "Upstox India Gold Rate 24K",
        "Consumer",
        "https://upstox.com/gold-rates/",
        "24K",
        999,
        "INR",
        "gram",
        ("price24k", "24 Carat"),
        3000,
        25000,
        "Consumer gold-rate reference page",
        "India consumer reference rate. Shown as buyer context, not an official bullion benchmark.",
    ),
    SourceConfig(
        "upstox-916",
        "India Retail",
        "Upstox India Gold Rate 22K",
        "Consumer",
        "https://upstox.com/gold-rates/",
        "22K",
        916,
        "INR",
        "gram",
        ("price22k", "22 Carat"),
        2500,
        23000,
        "Consumer gold-rate reference page",
        "India consumer reference rate. Shown as jewellery context, not an official bullion benchmark.",
    ),
    SourceConfig(
        "goodreturns-chandigarh-999",
        "India Retail",
        "Goodreturns Chandigarh 24K",
        "Consumer",
        "https://www.goodreturns.in/gold-rates/chandigarh.html",
        "24K",
        999,
        "INR",
        "gram",
        ("24K Gold /g", "24 karat gold"),
        3000,
        25000,
        "Localized consumer gold-rate page",
        "Chandigarh city reference from Goodreturns. Useful for local comparison, not an official benchmark.",
    ),
    SourceConfig(
        "goodreturns-chandigarh-916",
        "India Retail",
        "Goodreturns Chandigarh 22K",
        "Consumer",
        "https://www.goodreturns.in/gold-rates/chandigarh.html",
        "22K",
        916,
        "INR",
        "gram",
        ("22K Gold /g", "22 karat gold"),
        2500,
        23000,
        "Localized consumer gold-rate page",
        "Chandigarh city reference from Goodreturns. Useful for jewellery context, not an official benchmark.",
    ),
    SourceConfig(
        "goodreturns-chandigarh-750",
        "India Retail",
        "Goodreturns Chandigarh 18K",
        "Consumer",
        "https://www.goodreturns.in/gold-rates/chandigarh.html",
        "18K",
        750,
        "INR",
        "gram",
        ("18K Gold /g", "18 karat gold"),
        2000,
        18000,
        "Localized consumer gold-rate page",
        "Chandigarh city reference from Goodreturns. Useful for lower-purity jewellery context.",
    ),
    SourceConfig(
        "groww-999",
        "India Retail",
        "Groww India Gold Rate 24K",
        "Consumer",
        "https://groww.in/gold-rates",
        "24K",
        999,
        "INR",
        "10g",
        ("24K Gold / 10gm",),
        50000,
        250000,
        "Consumer gold-rate reference page",
        "India consumer reference rate. Shown as buyer context, not an official bullion benchmark.",
    ),
    SourceConfig(
        "groww-916",
        "India Retail",
        "Groww India Gold Rate 22K",
        "Consumer",
        "https://groww.in/gold-rates",
        "22K",
        916,
        "INR",
        "10g",
        ("22K Gold / 10gm",),
        40000,
        230000,
        "Consumer gold-rate reference page",
        "India consumer reference rate. Shown as jewellery context, not an official bullion benchmark.",
    ),
]

MARKET_CONTEXT_SOURCES = [
    SourceConfig(
        "mcx-gold-futures",
        "India Market",
        "MCX India Gold Futures",
        "Market",
        "https://www.mcxindia.com/products/bullion/gold",
        "24K",
        995,
        "INR",
        "10g",
        ("Gold", "GOLD"),
        50000,
        250000,
        "Exchange futures page when publicly fetchable",
        "Indian futures market context only; not a buyer retail price.",
    ),
    SourceConfig(
        "moneycontrol-gold-commodity",
        "India Market",
        "Moneycontrol Commodity Gold",
        "Market",
        "https://www.moneycontrol.com/commodity/",
        "24K",
        995,
        "INR",
        "10g",
        ("Gold", "GOLD"),
        50000,
        250000,
        "Commodity market page when publicly fetchable",
        "Commodity/futures context only; not a buyer retail price.",
    ),
    SourceConfig(
        "ndtv-profit-gold-rate",
        "India Market",
        "NDTV Profit Gold Rate",
        "Market",
        "https://www.ndtv.com/gold-rate/gold-price-india",
        "24K",
        999,
        "INR",
        "gram",
        ("24K", "24 Carat", "gold price"),
        3000,
        25000,
        "Financial portal page when publicly fetchable",
        "Broad financial-portal context only; not an official benchmark.",
    ),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def money(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, 2)


def fetch_text(url: str) -> str | None:
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"Could not fetch {url}: {exc}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(" ", strip=True)


def fetch_html(url: str) -> str | None:
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"Could not fetch {url}: {exc}")
        return None
    return response.text


def extract_date(text: str) -> str | None:
    patterns = [
        r"\b(\d{4}-\d{2}-\d{2})\b",
        r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b",
        r"\b(\d{1,2}\s+[A-Za-z]{3,9},?\s+\d{4})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def parse_number(raw: str) -> float | None:
    cleaned = raw.replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def find_price_near_labels(
    text: str,
    labels: tuple[str, ...],
    minimum: float,
    maximum: float,
    window: int = 220,
) -> float | None:
    candidates: list[float] = []
    normalized_text = re.sub(r"\s+", " ", text)

    for label in labels:
        for match in re.finditer(re.escape(label), normalized_text, flags=re.IGNORECASE):
            start = max(match.start() - window, 0)
            end = min(match.end() + window, len(normalized_text))
            snippet = normalized_text[start:end]
            for number_match in re.finditer(r"(?:Rs\.?|INR|AED|USD)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)", snippet):
                value = parse_number(number_match.group(1))
                if value is not None and minimum <= value <= maximum:
                    candidates.append(value)

    if not candidates:
        return None

    # Retail pages can repeat values. The median is more stable than the first
    # hit when navigation or SEO text surrounds the rate table.
    candidates.sort()
    return candidates[len(candidates) // 2]


def find_price_after_label(
    text: str,
    label: str,
    minimum: float,
    maximum: float,
    window: int = 100,
) -> float | None:
    normalized_text = re.sub(r"\s+", " ", text)
    label_pattern = r"\s+".join(re.escape(part) for part in label.split())

    for match in re.finditer(label_pattern, normalized_text, flags=re.IGNORECASE):
        snippet = normalized_text[match.end() : match.end() + window]
        for number_match in re.finditer(r"([0-9][0-9,]*(?:\.[0-9]+)?)", snippet):
            value = parse_number(number_match.group(1))
            if value is not None and minimum <= value <= maximum:
                return value

    return None


def normalize_price(currency: str, unit: str, price: float | None, usd_inr: float | None) -> dict[str, float | None]:
    if price is None:
        return {
            "price_inr_per_gram": None,
            "price_usd_per_gram": None,
            "price_inr_per_10g": None,
            "price_usd_per_oz": None,
        }

    grams = UNIT_GRAMS[unit]
    native_per_gram = price / grams
    inr_per_gram = None
    usd_per_gram = None

    if currency == "INR":
        inr_per_gram = native_per_gram
        usd_per_gram = native_per_gram / usd_inr if usd_inr else None
    elif currency == "USD":
        usd_per_gram = native_per_gram
        inr_per_gram = native_per_gram * usd_inr if usd_inr else None
    elif currency == "AED":
        usd_per_gram = native_per_gram / AED_PER_USD
        inr_per_gram = usd_per_gram * usd_inr if usd_inr else None

    return {
        "price_inr_per_gram": money(inr_per_gram),
        "price_usd_per_gram": money(usd_per_gram),
        "price_inr_per_10g": money(inr_per_gram * 10 if inr_per_gram is not None else None),
        "price_usd_per_oz": money(usd_per_gram * TROY_OUNCE_GRAMS if usd_per_gram is not None else None),
    }


def equivalent_price(price: float, from_fineness: int, to_fineness: int) -> float:
    return price * (to_fineness / from_fineness)


def make_rate(
    rate_id: str,
    market: str,
    source_name: str,
    source_type: str,
    source_url: str,
    purity: str,
    fineness: int,
    currency: str,
    unit: str,
    price: float | None,
    as_of: str | None,
    status: str,
    cadence: str,
    notes: str,
    usd_inr: float | None,
) -> dict[str, Any]:
    return {
        "id": rate_id,
        "market": market,
        "source_name": source_name,
        "source_type": source_type,
        "source_url": source_url,
        "purity": purity,
        "fineness": fineness,
        "currency": currency,
        "unit": unit,
        "price": money(price),
        "as_of": as_of,
        "status": status,
        "cadence": cadence,
        "notes": notes,
        **normalize_price(currency, unit, price, usd_inr),
    }


def unavailable_rate(config: SourceConfig, usd_inr: float | None) -> dict[str, Any]:
    return make_rate(
        config.rate_id,
        config.market,
        config.source_name,
        config.source_type,
        config.source_url,
        config.purity,
        config.fineness,
        config.currency,
        config.unit,
        None,
        None,
        "unavailable",
        config.cadence,
        config.notes,
        usd_inr,
    )


def fetch_fbil_usd_inr() -> dict[str, Any] | None:
    url = "https://www.fbil.org.in/"
    text = fetch_text(url)
    if not text:
        return None

    match = re.search(r"USD\s*/?\s*INR[^0-9]{0,80}([0-9]{2,3}(?:\.[0-9]+)?)", text, flags=re.IGNORECASE)
    if not match:
        return None

    value = parse_number(match.group(1))
    if value is None or not 50 <= value <= 120:
        return None

    return {
        "usd_inr": money(value),
        "source": "FBIL USD/INR reference rate",
        "source_type": "Official",
        "source_url": url,
        "as_of": extract_date(text) or utc_now(),
        "status": "fresh",
        "cadence": "Mumbai business days around 1:00 PM IST",
        "notes": "Official daily reference rate where parseable from public page text.",
    }


def fetch_live_usd_inr_fallback() -> dict[str, Any]:
    sources = [
        (
            "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json",
            lambda data: data["usd"]["inr"],
            "Fawaz Ahmed currency-api",
        ),
        (
            "https://open.er-api.com/v6/latest/USD",
            lambda data: data["rates"]["INR"],
            "open.er-api.com",
        ),
    ]

    for url, getter, name in sources:
        try:
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            value = float(getter(response.json()))
            if 50 <= value <= 120:
                return {
                    "usd_inr": money(value),
                    "source": name,
                    "source_type": "Live fallback",
                    "source_url": url,
                    "as_of": utc_now(),
                    "status": "fresh",
                    "cadence": "Live public no-key FX fallback",
                    "notes": "Used because the official FBIL reference rate was not parseable from public page text.",
                }
        except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
            print(f"Could not fetch FX from {url}: {exc}")

    return {
        "usd_inr": None,
        "source": "Unavailable",
        "source_type": "FX",
        "source_url": None,
        "as_of": None,
        "status": "unavailable",
        "cadence": "Unavailable",
        "notes": "No official or no-key live USD/INR source could be parsed.",
    }


def fetch_fx() -> dict[str, Any]:
    return fetch_fbil_usd_inr() or fetch_live_usd_inr_fallback()


def fetch_global_spot_rates(usd_inr: float | None) -> list[dict[str, Any]]:
    url = "https://api.gold-api.com/price/XAU"
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        price = float(data["price"])
        if not 1000 <= price <= 10000:
            raise ValueError(f"Unexpected XAU/USD price: {price}")
        return [
            make_rate(
                "global-spot-xau",
                "Global Spot",
                "Gold API XAU/USD",
                "Live",
                "https://gold-api.com/",
                "24K",
                999,
                "USD",
                "troy_ounce",
                price,
                data.get("updatedAt") or utc_now(),
                "fresh",
                "Live no-key public XAU/USD spot feed",
                "Live global spot context. Not an official fixing or a retail buyer price.",
                usd_inr,
            )
        ]
    except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
        print(f"Could not fetch global XAU/USD from {url}: {exc}")

    return [
        make_rate(
            "global-spot-xau",
            "Global Spot",
            "Gold API XAU/USD",
            "Live",
            "https://gold-api.com/",
            "24K",
            999,
            "USD",
            "troy_ounce",
            None,
            None,
            "unavailable",
            "Live no-key public XAU/USD spot feed",
            "Live global spot context was not parseable. No estimate was substituted.",
            usd_inr,
        )
    ]


def fetch_ibja_rates(usd_inr: float | None) -> list[dict[str, Any]]:
    url = "https://ibjarates.com/"
    text = fetch_text(url)
    if not text:
        configs = [
            SourceConfig("ibja-999", "India Benchmark", "IBJA", "Official", url, "24K", 999, "INR", "10g", ("999",), 50000, 250000, "Twice daily on business days", "India authoritative bullion benchmark."),
            SourceConfig("ibja-916", "India Benchmark", "IBJA", "Official", url, "22K", 916, "INR", "10g", ("916",), 40000, 230000, "Twice daily on business days", "India authoritative 916 jewellery-purity benchmark."),
        ]
        return [unavailable_rate(config, usd_inr) for config in configs]

    as_of = extract_date(text) or utc_now()

    gram_999 = re.search(r"999\s+Purity\s+([0-9,]+(?:\.[0-9]+)?)\s*\(1\s*Gram\)", text, flags=re.IGNORECASE)
    gram_916 = re.search(r"916\s+Purity\s+([0-9,]+(?:\.[0-9]+)?)\s*\(1\s*Gram\)", text, flags=re.IGNORECASE)
    price_999 = parse_number(gram_999.group(1)) if gram_999 else None
    price_916 = parse_number(gram_916.group(1)) if gram_916 else None
    unit_999 = "gram"
    unit_916 = "gram"

    if price_999 is None:
        price_999 = find_price_near_labels(text, ("999",), 50000, 250000)
        unit_999 = "10g"
    if price_916 is None:
        price_916 = find_price_near_labels(text, ("916",), 40000, 230000)
        unit_916 = "10g"

    return [
        make_rate(
            "ibja-999",
            "India Benchmark",
            "IBJA",
            "Official",
            url,
            "24K",
            999,
            "INR",
            unit_999,
            price_999,
            as_of if price_999 else None,
            "fresh" if price_999 else "unavailable",
            "Twice daily on business days, around 12:05 PM and 5:05 PM IST",
            "IBJA 999 purity rate. Used as the India benchmark.",
            usd_inr,
        ),
        make_rate(
            "ibja-916",
            "India Benchmark",
            "IBJA",
            "Official",
            url,
            "22K",
            916,
            "INR",
            unit_916,
            price_916,
            as_of if price_916 else None,
            "fresh" if price_916 else "unavailable",
            "Twice daily on business days, around 12:05 PM and 5:05 PM IST",
            "IBJA 916 purity rate. Shown as jewellery context, not the primary benchmark.",
            usd_inr,
        ),
    ]


def fetch_dubai_rates(usd_inr: float | None) -> list[dict[str, Any]]:
    official_sources = [
        ("Dubai Gold & Jewellery Group", "Official", "https://www.dubaijewellerygroup.com/"),
        ("Dubai City of Gold", "Official", "https://dubaicityofgold.com/"),
    ]
    mirror_sources = [
        ("GoldRateUAE (DGJG-derived mirror)", "Mirror", "https://goldrateuae.ae/"),
        ("Policybazaar UAE gold-rate page", "Mirror", "https://www.policybazaar.ae/gold-rate-dubai-gdp/"),
    ]

    for source_name, source_type, url in official_sources + mirror_sources:
        text = fetch_text(url)
        if not text:
            continue
        price = find_price_near_labels(text, ("24K", "24 KT", "999"), 350, 800)
        if price:
            note = "Official Dubai public source." if source_type == "Official" else "Mirror page used only when a direct Dubai official source is not parseable."
            return [
                make_rate(
                    "dubai-999",
                    "Dubai",
                    source_name,
                    source_type,
                    url,
                    "24K",
                    999,
                    "AED",
                    "gram",
                    price,
                    extract_date(text) or utc_now(),
                    "fresh",
                    "Live retail benchmark when available",
                    note,
                    usd_inr,
                )
            ]

    return [
        make_rate(
            "dubai-999",
            "Dubai",
            "Dubai Gold & Jewellery Group",
            "Official",
            "https://www.dubaijewellerygroup.com/",
            "24K",
            999,
            "AED",
            "gram",
            None,
            None,
            "unavailable",
            "Live retail benchmark when available",
            "Direct Dubai benchmark and mirrors were not parseable.",
            usd_inr,
        )
    ]


def fetch_configured_retail_rate(config: SourceConfig, usd_inr: float | None) -> dict[str, Any]:
    text = fetch_text(config.source_url)
    if not text:
        return unavailable_rate(config, usd_inr)

    price = find_price_near_labels(text, config.labels, config.minimum, config.maximum)
    return make_rate(
        config.rate_id,
        config.market,
        config.source_name,
        config.source_type,
        config.source_url,
        config.purity,
        config.fineness,
        config.currency,
        config.unit,
        price,
        extract_date(text) or utc_now() if price else None,
        "fresh" if price else "unavailable",
        config.cadence,
        config.notes,
        usd_inr,
    )


def fetch_all_india_bullion_rates(usd_inr: float | None) -> list[dict[str, Any]]:
    text = fetch_text(ALL_INDIA_BULLION_SOURCES[0].source_url)
    if not text:
        return [unavailable_rate(config, usd_inr) for config in ALL_INDIA_BULLION_SOURCES]

    as_of = extract_date(text) or utc_now()
    rates: list[dict[str, Any]] = []
    for config in ALL_INDIA_BULLION_SOURCES:
        price = find_price_after_label(text, config.labels[0], config.minimum, config.maximum)
        rates.append(
            make_rate(
                config.rate_id,
                config.market,
                config.source_name,
                config.source_type,
                config.source_url,
                config.purity,
                config.fineness,
                config.currency,
                config.unit,
                price,
                as_of if price else None,
                "fresh" if price else "unavailable",
                config.cadence,
                config.notes,
                usd_inr,
            )
        )
    return rates


def parse_upstox_prices(html_text: str) -> tuple[float | None, float | None]:
    normalized = html_text.replace('\\"', '"').replace("\\u0022", '"')
    match_24 = re.search(r'"price24k"\s*:\s*\{\s*"today"\s*:\s*([0-9]+(?:\.[0-9]+)?)', normalized)
    match_22 = re.search(r'"price22k"\s*:\s*\{\s*"today"\s*:\s*([0-9]+(?:\.[0-9]+)?)', normalized)
    price_24 = parse_number(match_24.group(1)) if match_24 else None
    price_22 = parse_number(match_22.group(1)) if match_22 else None

    if price_24 is None:
        soup = BeautifulSoup(html_text, "html.parser")
        text = soup.get_text(" ", strip=True)
        price_24 = find_price_near_labels(text, ("24 Carat", "24-karat"), 3000, 25000)

    return price_24, price_22


def fetch_upstox_rates(usd_inr: float | None) -> list[dict[str, Any]]:
    configs = [config for config in CONSUMER_PORTAL_SOURCES if config.rate_id.startswith("upstox-")]
    html_text = fetch_html(configs[0].source_url)
    if not html_text:
        return [unavailable_rate(config, usd_inr) for config in configs]

    price_24, price_22 = parse_upstox_prices(html_text)
    text = BeautifulSoup(html_text, "html.parser").get_text(" ", strip=True)
    as_of = extract_date(text) or utc_now()
    prices = {
        "upstox-999": price_24,
        "upstox-916": price_22,
    }

    rates: list[dict[str, Any]] = []
    for config in configs:
        price = prices[config.rate_id]
        rates.append(
            make_rate(
                config.rate_id,
                config.market,
                config.source_name,
                config.source_type,
                config.source_url,
                config.purity,
                config.fineness,
                config.currency,
                config.unit,
                price,
                as_of if price else None,
                "fresh" if price else "unavailable",
                config.cadence,
                config.notes,
                usd_inr,
            )
        )
    return rates


def fetch_labelled_source_group(configs: list[SourceConfig], usd_inr: float | None) -> list[dict[str, Any]]:
    text = fetch_text(configs[0].source_url)
    if not text:
        return [unavailable_rate(config, usd_inr) for config in configs]

    as_of = extract_date(text) or utc_now()
    rates: list[dict[str, Any]] = []
    for config in configs:
        price = None
        for label in config.labels:
            price = find_price_after_label(text, label, config.minimum, config.maximum)
            if price is not None:
                break
        rates.append(
            make_rate(
                config.rate_id,
                config.market,
                config.source_name,
                config.source_type,
                config.source_url,
                config.purity,
                config.fineness,
                config.currency,
                config.unit,
                price,
                as_of if price else None,
                "fresh" if price else "unavailable",
                config.cadence,
                config.notes,
                usd_inr,
            )
        )
    return rates


def fetch_consumer_portal_rates(usd_inr: float | None) -> list[dict[str, Any]]:
    goodreturns_configs = [
        config for config in CONSUMER_PORTAL_SOURCES if config.rate_id.startswith("goodreturns-")
    ]
    groww_configs = [
        config for config in CONSUMER_PORTAL_SOURCES if config.rate_id.startswith("groww-")
    ]

    return [
        *fetch_upstox_rates(usd_inr),
        *fetch_labelled_source_group(goodreturns_configs, usd_inr),
        *fetch_labelled_source_group(groww_configs, usd_inr),
    ]


def fetch_market_context_rates(usd_inr: float | None) -> list[dict[str, Any]]:
    return [fetch_configured_retail_rate(config, usd_inr) for config in MARKET_CONTEXT_SOURCES]


def fetch_retail_rates(usd_inr: float | None) -> list[dict[str, Any]]:
    return [
        fetch_configured_retail_rate(MMTC_PAMP_SOURCE, usd_inr),
        *[fetch_configured_retail_rate(config, usd_inr) for config in DIGITAL_AND_JEWELLERY_SOURCES],
        *fetch_all_india_bullion_rates(usd_inr),
        *fetch_consumer_portal_rates(usd_inr),
        *fetch_market_context_rates(usd_inr),
    ]


def build_spreads(rates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {rate["id"]: rate for rate in rates}
    bases = [by_id.get("ibja-999"), by_id.get("dubai-999")]
    comparable = [
        rate
        for rate in rates
        if rate.get("purity") == "24K"
        and rate.get("status") != "unavailable"
        and rate.get("price_inr_per_gram") is not None
    ]

    spreads: list[dict[str, Any]] = []
    for base in bases:
        if not base or base.get("price_inr_per_gram") is None:
            continue
        base_value = float(base["price_inr_per_gram"])
        for rate in comparable:
            if rate["id"] == base["id"]:
                continue
            diff = float(rate["price_inr_per_gram"]) - base_value
            spreads.append(
                {
                    "basis_rate_id": base["id"],
                    "compared_rate_id": rate["id"],
                    "basis": f"{base['source_name']} {base['purity']}",
                    "compared_source_name": rate["source_name"],
                    "inr_per_gram_diff": money(diff),
                    "pct_diff": money((diff / base_value) * 100 if base_value else None),
                    "status": "fresh",
                }
            )
    return spreads


def build_payload() -> dict[str, Any]:
    generated_at = utc_now()
    fx = fetch_fx()
    usd_inr = fx.get("usd_inr")
    rates = [
        *fetch_global_spot_rates(usd_inr),
        *fetch_ibja_rates(usd_inr),
        *fetch_dubai_rates(usd_inr),
        *fetch_retail_rates(usd_inr),
    ]

    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "default_city": "Mumbai",
        "fx": fx,
        "rates": rates,
        "spreads": build_spreads(rates),
        "units": {
            "gram": 1,
            "10g": 10,
            "tola": TOLA_GRAMS,
            "troy_ounce": TROY_OUNCE_GRAMS,
        },
        "notes": [
            "India-first display leads with INR per gram.",
            "USD per troy ounce is shown as global context using 31.1034768 grams per troy ounce.",
            "24K/999 is the primary cross-market benchmark.",
            "22K/916 is shown as jewellery context.",
            "Unavailable means no public price could be parsed; no fallback estimates are used.",
        ],
    }


def write_payload(path: str = "data.json") -> None:
    payload = build_payload()
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(f"Wrote {path} with {len(payload['rates'])} rates")


if __name__ == "__main__":
    write_payload()
