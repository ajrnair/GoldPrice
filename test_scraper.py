from scraper import (
    AED_PER_USD,
    TROY_OUNCE_GRAMS,
    equivalent_price,
    find_price_after_label,
    make_rate,
    normalize_price,
    parse_upstox_prices,
)


def test_normalizes_inr_per_10g_to_common_units():
    result = normalize_price("INR", "10g", 100000, 80)

    assert result["price_inr_per_gram"] == 10000
    assert result["price_usd_per_gram"] == 125
    assert result["price_inr_per_10g"] == 100000
    assert result["price_usd_per_oz"] == round(125 * TROY_OUNCE_GRAMS, 2)


def test_normalizes_aed_per_gram_through_usd_peg():
    result = normalize_price("AED", "gram", AED_PER_USD * 100, 83)

    assert result["price_usd_per_gram"] == 100
    assert result["price_inr_per_gram"] == 8300


def test_normalizes_usd_troy_ounce_to_india_first_units():
    result = normalize_price("USD", "troy_ounce", 3100, 83)

    assert result["price_usd_per_gram"] == round(3100 / TROY_OUNCE_GRAMS, 2)
    assert result["price_inr_per_gram"] == round((3100 / TROY_OUNCE_GRAMS) * 83, 2)
    assert result["price_usd_per_oz"] == 3100


def test_equivalent_price_uses_fineness_ratio():
    assert round(equivalent_price(10000, 999, 916), 2) == 9169.17
    assert round(equivalent_price(10000, 999, 750), 2) == 7507.51


def test_find_price_after_label_ignores_non_price_numbers():
    text = "24K Gold / 10gm 18 May '26 ₹ 158450.00 -3,528.00"

    assert find_price_after_label(text, "24K Gold / 10gm", 50000, 250000) == 158450


def test_parse_upstox_prices_from_embedded_payload():
    html = '\\"price24k\\":{\\"today\\":15708},\\"price22k\\":{\\"today\\":14400}'

    assert parse_upstox_prices(html) == (15708, 14400)


def test_unavailable_rate_keeps_price_fields_empty():
    rate = make_rate(
        "source-999",
        "India Retail",
        "Example",
        "Digital",
        "https://example.com",
        "24K",
        999,
        "INR",
        "gram",
        None,
        None,
        "unavailable",
        "Live",
        "No public quote parsed.",
        83,
    )

    assert rate["status"] == "unavailable"
    assert rate["price"] is None
    assert rate["price_inr_per_gram"] is None
    assert rate["price_usd_per_gram"] is None
