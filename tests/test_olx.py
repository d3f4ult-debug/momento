"""
Unit and integration tests for OLX.uz marketplace client and intent routing.
Verifies:
1. OLX client helper functions (format_uzs_price, build_olx_search_url, parse_olx_offer).
2. OLX API search with live parsing, fallback generation, and error handling.
3. Natural language intent detection (detect_olx_search_intent) with price extraction (UZS).
4. Local execution (execute_olx_search_locally).
5. GET /api/olx/search endpoint.
6. Main chat routing bypassing cloud Google Workspace fallback.
"""

from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from main import (
    app,
    detect_olx_search_intent,
    execute_olx_search_locally,
)
from services.olx_client import (
    format_uzs_price,
    build_olx_search_url,
    build_olx_item_url,
    slugify,
    parse_olx_offer,
    generate_fallback_listings,
    search_olx_listings,
    resolve_olx_city_id,
    resolve_olx_category_path,
    OLX_BASE_URL,
)

client = TestClient(app)


# ==============================================================================
# 1. OLX Client Helper Functions
# ==============================================================================

def test_resolve_olx_city_id():
    """Verify city name resolution to OLX city_id."""
    assert resolve_olx_city_id(None) is None
    assert resolve_olx_city_id(1) == 1
    assert resolve_olx_city_id("1") == 1
    assert resolve_olx_city_id("Tashkent") == 1
    assert resolve_olx_city_id("Toshkent, Mirzo Ulug'bek") == 1
    assert resolve_olx_city_id("Ташкент") == 1
    assert resolve_olx_city_id("Samarqand") == 2
    assert resolve_olx_city_id("Самарканд") == 2
    assert resolve_olx_city_id("Buxoro") == 3
    assert resolve_olx_city_id("UnknownCity123") is None


def test_format_uzs_price():
    """Verify Uzbek currency formatting for integers, floats, None, and fallbacks."""
    assert format_uzs_price(None) == "Договорная (Negotiable)"
    assert format_uzs_price("") == "Договорная (Negotiable)"
    assert format_uzs_price(12500000) == "12 500 000 so'm"
    assert format_uzs_price("12500000") == "12 500 000 so'm"
    assert format_uzs_price("12 500 000") == "12 500 000 so'm"
    assert format_uzs_price(1500.5, "USD") == "1 500.50 USD"
    assert format_uzs_price(300000, "SOM") == "300 000 so'm"


def test_resolve_olx_category_path():
    """Verify mapping of query keywords into targeted OLX category paths."""
    assert resolve_olx_category_path("iPhone 15") == "elektronika/telefony/mobilnye-telefony"
    assert resolve_olx_category_path("samsung galaxy s24") == "elektronika/telefony/mobilnye-telefony"
    assert resolve_olx_category_path("MacBook Air M2") == "elektronika/kompyutery-i-servera/noutbuki"
    assert resolve_olx_category_path("PlayStation 5") == "elektronika/igry-i-igrovye-pristavki/pristavki"
    assert resolve_olx_category_path("Sony Headphones") == "elektronika/aksessuary-i-komplektuyuschie"
    assert resolve_olx_category_path("Chevrolet Cobalt") == "transport/legkovye-avtomobili"
    assert resolve_olx_category_path("apartment in Tashkent") == "nedvizhimost/kvartiry"
    assert resolve_olx_category_path("antique desk") is None


def test_build_olx_search_url():
    """Verify URL generation with scoped category, query, price filters, and city_id parameters."""
    # Query matching phones category
    url1 = build_olx_search_url("iphone 15")
    assert url1 == f"{OLX_BASE_URL}/elektronika/telefony/mobilnye-telefony/q-iphone%2015/"

    # Query with price_max and laptop category
    url2 = build_olx_search_url("macbook", price_max=12000000)
    assert url2.startswith(f"{OLX_BASE_URL}/elektronika/kompyutery-i-servera/noutbuki/q-macbook/")
    assert "search%5Bfilter_float_price%3Ato%5D=12000000" in url2

    # Query with price_min and price_max and transport category
    url3 = build_olx_search_url("cobalt", price_min=100000000, price_max=150000000)
    assert url3.startswith(f"{OLX_BASE_URL}/transport/legkovye-avtomobili/q-cobalt/")
    assert "search%5Bfilter_float_price%3Afrom%5D=100000000" in url3
    assert "search%5Bfilter_float_price%3Ato%5D=150000000" in url3

    # Query with city_id and location and real estate category
    url4 = build_olx_search_url("apartments", city_id=1)
    assert url4.startswith(f"{OLX_BASE_URL}/nedvizhimost/kvartiry/q-apartments/")
    assert "search%5Bcity_id%5D=1" in url4

    url5 = build_olx_search_url("cobalt", location="Samarqand")
    assert "search%5Bcity_id%5D=2" in url5

    # Generic query without category match defaults to list
    url_generic = build_olx_search_url("vintage guitar")
    assert url_generic == f"{OLX_BASE_URL}/list/q-vintage%20guitar/"


def test_build_olx_item_url():
    """Verify construction of direct individual listing URLs matching OLX format."""
    # 1. Custom title with placeholder ID (e.g. ID4fQg4)
    url1 = build_olx_item_url("PlayStation 5", "ID4fQg4")
    assert url1 == f"{OLX_BASE_URL}/d/obyavlenie/playstation-5-ID4fQg4.html"

    # 2. Integer ID without ID prefix
    url2 = build_olx_item_url("iPhone 15 Pro Max", 45000001)
    assert url2 == f"{OLX_BASE_URL}/d/obyavlenie/iphone-15-pro-max-ID45000001.html"

    # 3. Cyrillic title transliteration into clean slug
    url3 = build_olx_item_url("Новый в коробке", "4fQg2")
    assert url3 == f"{OLX_BASE_URL}/d/obyavlenie/novyy-v-korobke-ID4fQg2.html"

    # 4. Auto-generated hash ID when item_id is omitted
    url4 = build_olx_item_url("Samsung S24 Ultra")
    assert url4.startswith(f"{OLX_BASE_URL}/d/obyavlenie/samsung-s24-ultra-ID")
    assert url4.endswith(".html")


def test_parse_olx_offer():
    """Verify parsing of OLX API offer payload into normalized dictionary."""
    sample_offer = {
        "id": 98765432,
        "title": "iPhone 15 Pro Max 256GB Blue",
        "url": "/d/obyavlenie/iphone-15-pro-max-98765432.html",
        "created_time": "2026-09-25T10:00:00+05:00",
        "params": [
            {
                "key": "price",
                "value": {
                    "value": 14200000,
                    "currency": "UZS",
                    "label": "14 200 000 so'm"
                }
            }
        ],
        "location": {
            "city": {"name": "Ташкент"},
            "district": {"name": "Мирзо-Улугбекский район"}
        },
        "photos": [
            {"link": "https://img.olx.uz/photos/1.jpg"}
        ]
    }
    parsed = parse_olx_offer(sample_offer)
    assert parsed["id"] == 98765432
    assert parsed["title"] == "iPhone 15 Pro Max 256GB Blue"
    assert parsed["price"] == 14200000
    assert parsed["formatted_price"] == "14 200 000 so'm"
    assert "Ташкент" in parsed["location"]
    assert "Мирзо-Улугбекский" in parsed["location"]
    # Authentic offer retains direct item URL
    assert parsed["url"] == f"{OLX_BASE_URL}/d/obyavlenie/iphone-15-pro-max-98765432.html"
    assert parsed["photo_url"] == "https://img.olx.uz/photos/1.jpg"

    # Offer with missing url but verified ID constructs direct item URL
    offer_no_url = {"id": 1234567, "title": "Minimal item"}
    parsed_no_url = parse_olx_offer(offer_no_url)
    assert parsed_no_url["url"] == f"{OLX_BASE_URL}/d/obyavlenie/1234567.html"

    # Unverified offer or missing ID constructs targeted search catalog URL under exact category path with exact bounds
    offer_unverified = {"title": "Samsung Galaxy S24", "unverified": True}
    parsed_unverified = parse_olx_offer(offer_unverified)
    assert parsed_unverified["url"].startswith(f"{OLX_BASE_URL}/elektronika/telefony/mobilnye-telefony/q-Samsung%20Galaxy%20S24/")
    assert "/d/obyavlenie/" not in parsed_unverified["url"]


def test_generate_fallback_listings():
    """Verify fallback listing generation constructs targeted search catalog URLs under exact category path with bounds."""
    items = generate_fallback_listings("PlayStation 5", price_min=4000000, price_max=7000000, limit=4)
    assert len(items) == 4
    for it in items:
        assert "Playstation 5" in it["title"]
        assert 4000000 <= it["price"] <= 7000000
        assert "so'm" in it["formatted_price"]
        # Scoped category search URL under exact gaming console path
        assert it["url"].startswith(f"{OLX_BASE_URL}/elektronika/igry-i-igrovye-pristavki/pristavki/q-PlayStation%205/")
        # Strict price bounds included
        assert "search%5Bfilter_float_price%3A" in it["url"]
        # Location parameter included
        assert "search%5Bcity_id%5D=" in it["url"]
        # Eliminates unverified ad paths
        assert "/d/obyavlenie/" not in it["url"]


# ==============================================================================
# 2. Asynchronous OLX Client Search
# ==============================================================================

@pytest.mark.anyio
async def test_search_olx_listings_empty_query():
    """Search with empty string should return early with success=False."""
    res = await search_olx_listings("   ")
    assert res["success"] is False
    assert res["count"] == 0


@pytest.mark.anyio
async def test_search_olx_listings_live_mocked_success():
    """Search with successful 200 JSON API response."""
    mock_payload = {
        "data": [
            {
                "id": 111,
                "title": "Chevrolet Cobalt 2023",
                "url": "/d/obyavlenie/cobalt-111.html",
                "params": [{"key": "price", "value": {"value": 135000000, "currency": "UZS"}}],
                "location": {"city": {"name": "Tashkent"}},
                "photos": []
            }
        ],
        "total_count": 1
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp

    res = await search_olx_listings("Cobalt", limit=5, client=mock_client)
    assert res["success"] is True
    assert res["live"] is True
    assert res["count"] == 1
    assert res["listings"][0]["title"] == "Chevrolet Cobalt 2023"
    assert res["listings"][0]["price"] == 135000000


@pytest.mark.anyio
async def test_search_olx_listings_waf_fallback():
    """When upstream returns 403 (CloudFront WAF), gracefully fallback without error."""
    mock_resp = MagicMock()
    mock_resp.status_code = 403

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp

    res = await search_olx_listings("iPhone 13", price_max=8000000, limit=4, client=mock_client)
    assert res["success"] is True
    assert res["live"] is False
    assert res["count"] == 4
    assert len(res["listings"]) == 4
    assert "iPhone 13" in res["listings"][0]["title"] or "Iphone 13" in res["listings"][0]["title"]


# ==============================================================================
# 3. Intent Detection (detect_olx_search_intent)
# ==============================================================================

def test_detect_olx_search_intent_basic():
    """Verify natural language patterns for basic search."""
    # Pattern A: Search OLX for [item]
    res1 = detect_olx_search_intent("Search OLX for iPhone 15 Pro")
    assert res1 is not None
    assert res1["action"] == "olx_search"
    assert res1["query"].lower() == "iphone 15 pro"
    assert res1["price_min"] is None
    assert res1["price_max"] is None

    # Pattern B: [item] on OLX
    res2 = detect_olx_search_intent("Find macbook m2 on OLX")
    assert res2 is not None
    assert "macbook m2" in res2["query"].lower()

    # Pattern C: OLX search [item] with city location filter
    res3 = detect_olx_search_intent("olx search apartment in Tashkent")
    assert res3 is not None
    assert "apartment" in res3["query"].lower()
    assert res3["city_id"] == 1
    assert res3["location"] == "Tashkent"


def test_detect_olx_search_intent_price_max():
    """Verify maximum price constraint extraction in Uzbek sums."""
    res = detect_olx_search_intent("Search OLX for iPhone 14 under 9 000 000 so'm")
    assert res is not None
    assert "iphone 14" in res["query"].lower()
    assert res["price_max"] == 9000000
    assert res["price_min"] is None


def test_detect_olx_search_intent_price_range():
    """Verify range extraction (between X and Y UZS)."""
    res = detect_olx_search_intent("Look up cobalt on OLX between 100000000 and 150000000 uzs")
    assert res is not None
    assert "cobalt" in res["query"].lower()
    assert res["price_min"] == 100000000
    assert res["price_max"] == 150000000


def test_detect_olx_search_intent_price_min():
    """Verify minimum price constraint extraction (above / over)."""
    res = detect_olx_search_intent("find gaming pc on olx above 5000000 som")
    assert res is not None
    assert "gaming pc" in res["query"].lower()
    assert res["price_min"] == 5000000
    assert res["price_max"] == 0 or res["price_max"] is None


def test_detect_olx_search_intent_non_matching():
    """Verify non-OLX queries return None."""
    assert detect_olx_search_intent("What is the weather today in Tashkent?") is None
    assert detect_olx_search_intent("Summarize my document") is None
    assert detect_olx_search_intent("List files in Google Drive") is None


# ==============================================================================
# 4. Local Execution (execute_olx_search_locally)
# ==============================================================================

@pytest.mark.anyio
async def test_execute_olx_search_locally():
    """Verify markdown intelligence card creation with integrations.olx and individual item links."""
    olx_intent = {
        "action": "olx_search",
        "query": "Smart Watch",
        "price_min": 500000,
        "price_max": 1500000,
        "city_id": 1,
        "location": "Tashkent"
    }
    result = await execute_olx_search_locally("search olx for smart watch in Tashkent", olx_intent)
    assert result["status"] == "success"
    assert "🛍️ OLX.uz Marketplace Search: Smart Watch" in result["result"]
    assert "Price Range" in result["result"]
    assert "Location" in result["result"]
    assert "integrations" in result
    assert result["integrations"]["olx"] is not None
    assert result["integrations"]["olx"]["query"] == "Smart Watch"
    # Ensure scoped category search URL with bounds is present and unverified ad paths eliminated
    assert "/elektronika/aksessuary-i-komplektuyuschie/q-Smart%20Watch/" in result["result"]
    assert "search%5Bfilter_float_price%3A" in result["result"]
    assert "search%5Bcity_id%5D=1" in result["result"]
    assert "/d/obyavlenie/" not in result["result"]
    # Ensure redundant bottom global search button is removed from markdown
    assert "Open Full Search on OLX.uz" not in result["result"]


# ==============================================================================
# 5. REST Endpoint & Safe External Opening Tests
# ==============================================================================

def test_api_olx_search_endpoint():
    """Verify GET /api/olx/search endpoint returns structured JSON with precision filters."""
    response = client.get("/api/olx/search", params={"query": "Sony Headphones", "city_id": 1, "limit": 3})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["query"] == "Sony Headphones"
    assert "listings" in data
    assert len(data["listings"]) <= 5
    assert "search%5Bcity_id%5D=1" in data["search_url"]
    # Verify fallback listings have scoped search catalog URLs under exact category path with exact bounds
    for item in data["listings"]:
        assert "/elektronika/aksessuary-i-komplektuyuschie/q-Sony%20Headphones/" in item["url"]
        assert "search%5Bfilter_float_price%3A" in item["url"]
        assert "search%5Bcity_id%5D=1" in item["url"]
        assert "/d/obyavlenie/" not in item["url"]


@patch("webbrowser.open")
def test_open_external_url_endpoint(mock_wb_open):
    """Verify POST /api/open-external-url safely handles external URLs."""
    # 1. Empty URL
    res_empty = client.post("/api/open-external-url", data={"url": ""})
    assert res_empty.status_code == 400

    # 2. Invalid Scheme
    res_invalid = client.post("/api/open-external-url", data={"url": "javascript:alert(1)"})
    assert res_invalid.status_code == 400

    # 3. Valid OLX URL
    valid_url = "https://www.olx.uz/d/obyavlenie/iphone-15-45000001.html"
    res_valid = client.post("/api/open-external-url", data={"url": valid_url})
    assert res_valid.status_code == 200
    assert res_valid.json()["success"] is True
    assert mock_wb_open.called
    assert mock_wb_open.call_args[0][0] == valid_url


def test_desktop_api_open_external_url():
    """Verify DesktopApi class in desktop.py safely opens external URLs."""
    from desktop import DesktopApi

    api = DesktopApi()
    with patch("webbrowser.open") as mock_wb:
        # Invalid scheme
        assert api.open_external_url("ftp://example.com") is False
        assert not mock_wb.called

        # Valid HTTPS link
        target = "https://www.olx.uz/d/obyavlenie/sample-123.html"
        assert api.open_external_url(target) is True
        assert mock_wb.called
        assert mock_wb.call_args[0][0] == target


@patch("main.list_google_drive_files")
@patch("main.execute_gemini_transformation")
def test_chat_olx_intent_bypasses_google_and_gemini(mock_gemini, mock_gdrive):
    """
    Verify that an OLX search query in /api/chat is intercepted by Priority #1
    and never calls Google Workspace or Gemini transformations.
    """
    response = client.post(
        "/api/chat",
        data={"prompt": "Find Chevrolet Gentra on OLX under 140000000 so'm"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "OLX.uz Marketplace Search" in data["result"]
    assert data["integrations"]["olx"] is not None
    assert "Gentra" in data["integrations"]["olx"]["query"] or "gentra" in data["integrations"]["olx"]["query"].lower()

    # Crucial assertion: Google Workspace and cloud Gemini are bypassed
    assert not mock_gdrive.called
    assert not mock_gemini.called
