"""
Verify the trending DB query layer correctly isolates products by country.

The user reported KSA showing the same products as UAE. The audit confirmed
the routing code passes country to the DB query — these tests prove the DB
query path is actually country-isolated when given a fake DB.

The test mocks the SQLAlchemy `db.query(...).filter(...).order_by(...).all()`
chain to verify which `country` value the filter receives, and that
list_active_trending_for_country returns ONLY rows whose country matches.
"""
from __future__ import annotations

from typing import Any, List
from unittest.mock import MagicMock

from services.trending_products_service import bot_query


def _row(*, pid: int, country: str, name: str, is_trending: bool = True) -> Any:
    """Build a fake TrendingProduct row that matches the column attrs the
    bot_query code reads."""
    r = MagicMock()
    r.id = pid
    r.country = country
    r.product_name = name
    r.price = 100
    r.currency = "AED" if country == "UAE" else "SAR" if country == "KSA" else "PKR"
    r.category = "general"
    r.description = ""
    r.image_keys = []
    r.image_url_legacy = None
    r.is_trending = is_trending
    r.is_active = True
    return r


# Country-keyed product universe — each country has DISTINCT products.
PRODUCTS_BY_COUNTRY = {
    "UAE": [
        _row(pid=1, country="UAE", name="UAE Trending A"),
        _row(pid=2, country="UAE", name="UAE Trending B"),
    ],
    "KSA": [
        _row(pid=3, country="KSA", name="KSA Trending A"),
        _row(pid=4, country="KSA", name="KSA Trending B"),
    ],
    "PK": [
        _row(pid=5, country="PK", name="PK Trending A"),
    ],
}


def _build_fake_db(products_by_country: dict) -> MagicMock:
    """Build a fake SQLAlchemy session whose `.query().filter().order_by().all()`
    chain returns only the rows whose country matches what was passed to the
    `.filter()` call.

    This is a structural test: we don't simulate SQL, we capture the country
    arg by reading the filter clauses.
    """
    db = MagicMock()

    # The filter call gets BinaryExpression objects. We can't easily introspect
    # them, so we use a different strategy: have `.filter()` return a Query-like
    # whose .order_by().all() returns our fixture for whichever country the
    # caller most recently asked about. We do this by tracking calls and
    # peeking at the .filter clauses' right-hand side.
    state = {"country": None, "is_trending": None}

    def _filter(*clauses):
        # SQLAlchemy BinaryExpression — inspect the clause's string form which
        # always includes the column name. e.g.
        #   "trending_products.country = :country_1"
        #   "trending_products.is_trending IS true"
        # The boolean `IS true/false` operator doesn't surface a BindParameter,
        # so we parse the string directly.
        for c in clauses:
            s = str(c).lower()
            r = getattr(c, "right", None)
            v = getattr(r, "value", None) if r is not None else None
            if "country" in s and isinstance(v, str) and v.upper() in {"UAE", "KSA", "PK"}:
                state["country"] = v.upper()
            elif "is_trending" in s:
                if " is true" in s:
                    state["is_trending"] = True
                elif " is false" in s:
                    state["is_trending"] = False
        q2 = MagicMock()
        q2.filter = _filter

        def _order_by(*_a, **_kw):
            q3 = MagicMock()
            country = state["country"]
            wanted_trending = state["is_trending"]
            rows = products_by_country.get(country, [])
            if wanted_trending is not None:
                rows = [r for r in rows if bool(r.is_trending) == wanted_trending]
            q3.all = lambda: rows
            q3.count = lambda: len(rows)
            return q3

        q2.order_by = _order_by
        q2.count = lambda: len(products_by_country.get(state["country"], []))
        return q2

    q1 = MagicMock()
    q1.filter = _filter
    db.query = lambda *_a, **_kw: q1
    return db


class TestCountryIsolation:
    def test_uae_returns_only_uae_products(self) -> None:
        db = _build_fake_db(PRODUCTS_BY_COUNTRY)
        out = bot_query.list_active_trending_for_country(db, tenant_id=1, country="UAE")
        names = [p["product_name"] for p in out]
        assert all(n.startswith("UAE") for n in names), names
        assert len(out) == 2

    def test_ksa_returns_only_ksa_products(self) -> None:
        db = _build_fake_db(PRODUCTS_BY_COUNTRY)
        out = bot_query.list_active_trending_for_country(db, tenant_id=1, country="KSA")
        names = [p["product_name"] for p in out]
        assert all(n.startswith("KSA") for n in names), names
        # CRITICAL: must NOT contain any UAE products. This is exactly the bug
        # the user reported — KSA returning UAE rows.
        assert not any("UAE" in n for n in names), (
            "KSA query leaked UAE products — country isolation broken"
        )
        assert len(out) == 2

    def test_pk_returns_only_pk_products(self) -> None:
        db = _build_fake_db(PRODUCTS_BY_COUNTRY)
        out = bot_query.list_active_trending_for_country(db, tenant_id=1, country="PK")
        names = [p["product_name"] for p in out]
        assert all(n.startswith("PK") for n in names), names
        assert len(out) == 1

    def test_country_codes_normalized_to_upper(self) -> None:
        """Lowercase country codes must still hit the right partition."""
        db = _build_fake_db(PRODUCTS_BY_COUNTRY)
        out = bot_query.list_active_trending_for_country(db, tenant_id=1, country="ksa")
        names = [p["product_name"] for p in out]
        assert all(n.startswith("KSA") for n in names)


class TestNonTrendingPath:
    def test_non_trending_uses_is_trending_false(self) -> None:
        # Set up a country with both trending AND non-trending rows.
        mixed = {
            "UAE": [
                _row(pid=1, country="UAE", name="UAE Trending Hero", is_trending=True),
                _row(pid=2, country="UAE", name="UAE Quiet Item", is_trending=False),
            ],
        }
        db = _build_fake_db(mixed)
        trending = bot_query.list_active_trending_for_country(db, tenant_id=1, country="UAE")
        assert [p["product_name"] for p in trending] == ["UAE Trending Hero"]
        non_trending = bot_query.list_active_non_trending_for_country(
            db, tenant_id=1, country="UAE"
        )
        assert [p["product_name"] for p in non_trending] == ["UAE Quiet Item"]
