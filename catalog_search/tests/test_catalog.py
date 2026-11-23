import pytest
from fastapi.testclient import TestClient

from app import catalog
from app.catalog import SearchParams
from app.db import SessionLocal
from app.main import app


def names(result):
    return [i["name"] for i in result["items"]]


def facet(result, code):
    return {v["value"]: v["count"] for a in result["facets"]["attributes"]
            if a["code"] == code for v in a["values"]}


# ---------- 1. Дерево категорий ----------

def test_subtree_recursive_cte():
    assert sorted(catalog.subtree_ids(1)) == [1, 2, 3, 4, 5]     # Электроника и всё внутри
    assert catalog.subtree_ids(4) == [4]                          # лист дерева


def test_breadcrumbs():
    assert [c["name"] for c in catalog.breadcrumbs(4)] == \
        ["Электроника", "Компьютеры", "Ноутбуки", "Игровые ноутбуки"]


def test_tree_counts_products_in_subcategories():
    tree = catalog.category_tree()
    electronics = next(n for n in tree if n["name"] == "Электроника")
    assert electronics["products_total"] == 9
    assert electronics["products_own"] == 0


def test_cte_and_materialized_path_give_same_result():
    for cat in range(1, 12):
        cte = catalog.products_in_category(cat, method="cte")
        path = catalog.products_in_category(cat, method="path")
        assert [p["id"] for p in cte] == [p["id"] for p in path]
    assert len(catalog.products_in_category(2)) == 6
    assert catalog.products_in_category(2, include_subcategories=False) == []


def test_unknown_category():
    with pytest.raises(catalog.NotFound):
        catalog.subtree_ids(999)


# ---------- 2. Фасеты ----------

def test_facets_exclude_own_filter():
    r = catalog.search(SearchParams(category_id=3, filters={"ram": ["16"]}))
    assert r["total"] == 6
    # Фильтр по ОЗУ выбран, но в фасете ОЗУ видны все варианты
    assert facet(r, "ram") == {"8": 3, "16": 6, "32": 2}


def test_facets_or_inside_and_between():
    r = catalog.search(SearchParams(category_id=3, filters={"ram": ["16", "32"], "cpu": ["AMD Ryzen 7"]}))
    assert sorted(names(r)) == ["Игровой ноутбук Lenovo Legion 5 Pro", "Ноутбук Lenovo IdeaPad Slim 5"]


def test_filters_apply_to_same_sku():
    """Nike Air Max есть в размере 43 и есть в чёрном цвете, но чёрного 43-го нет."""
    r = catalog.search(SearchParams(category_id=8, filters={"shoe_size": ["43"], "color": ["чёрный"]}))
    assert r["total"] == 0


def test_selected_value_with_zero_count_stays_visible():
    r = catalog.search(SearchParams(category_id=8, filters={"shoe_size": ["43"], "color": ["чёрный"]}))
    colors = {v["value"]: v for a in r["facets"]["attributes"] if a["code"] == "color" for v in a["values"]}
    assert colors["чёрный"]["selected"] is True


def test_numeric_facet_sorted_as_numbers():
    r = catalog.search(SearchParams(category_id=3))
    assert list(facet(r, "ram")) == ["8", "16", "32"]   # а не "16", "32", "8"


def test_brand_and_price_facets():
    r = catalog.search(SearchParams(category_id=5, brands=["Apple"]))
    assert names(r) == ["Смартфон Apple iPhone 15"]
    brands = {b["value"]: b["count"] for b in r["facets"]["brands"]}
    assert brands == {"Apple": 1, "Samsung": 1, "Xiaomi": 1}
    assert r["facets"]["price"] == {"min": 79990.0, "max": 89990.0}


def test_price_range_and_in_stock():
    r = catalog.search(SearchParams(category_id=5, price_max=30000))
    assert names(r) == ["Смартфон Xiaomi Redmi Note 13"]
    r = catalog.search(SearchParams(category_id=5, filters={"color": ["фиолетовый"]}, in_stock=True))
    assert r["total"] == 0  # фиолетового Samsung нет в наличии


def test_unknown_filter():
    with pytest.raises(catalog.CatalogError):
        catalog.search(SearchParams(filters={"wings": ["2"]}))


# ---------- 3. Полнотекстовый поиск ----------

@pytest.mark.parametrize("query, expected", [
    ("белые кроссовки", {"Кроссовки Nike Air Max 90", "Кроссовки adidas Ultraboost Light"}),
    ("кроссовок для бега", {"Беговые кроссовки ASICS Gel-Kayano 30", "Кроссовки adidas Ultraboost Light"}),
    ("SAMSUNG", {"Смартфон Samsung Galaxy S24"}),
    ("черная футболка", {"Футболка хлопковая базовая", "Футболка спортивная Nike Dri-FIT"}),
])
def test_fulltext_search(query, expected):
    assert set(names(catalog.search(SearchParams(q=query)))) == expected


def test_ranking_title_match_beats_description_match():
    r = catalog.search(SearchParams(q="бег"))
    # "Беговые" в названии -> выше, чем товары, где "бег" только в описании
    assert names(r)[0] == "Беговые кроссовки ASICS Gel-Kayano 30"
    rel = [i["relevance"] for i in r["items"]]
    assert rel == sorted(rel, reverse=True)


def test_search_inside_category_with_facets():
    r = catalog.search(SearchParams(q="кроссовки", filters={"shoe_size": ["42"]}))
    assert r["total"] == 3
    assert facet(r, "shoe_size")["42"] == 3


def test_index_updates_automatically_via_triggers():
    with SessionLocal() as session, session.begin():
        catalog.create_product(session, category_id=8, name="Кроссовки New Balance 574",
                               brand="New Balance", description="Замшевые кроссовки",
                               skus=[{"article": "NB-1", "price": 9990, "stock": 1,
                                      "attributes": {"shoe_size": 42, "color": "серый"}}])
    assert names(catalog.search(SearchParams(q="замша"))) == ["Кроссовки New Balance 574"]
    assert names(catalog.search(SearchParams(q="серые"))) == ["Кроссовки New Balance 574"]


def test_like_fallback_without_fts5(monkeypatch):
    monkeypatch.setattr(catalog, "has_search_index", lambda conn: False)
    r = catalog.search(SearchParams(q="Белые кроссовки"))
    assert r["search_engine"] == "like"
    assert r["total"] >= 1
    assert all("Кроссовки" in n for n in names(r))


# ---------- Товары (EAV + JSON) ----------

def test_attribute_must_belong_to_category():
    with SessionLocal() as session, session.begin():
        with pytest.raises(catalog.CatalogError):
            catalog.create_product(session, category_id=8, name="Странные кроссовки", brand=None,
                                   skus=[{"article": "X-1", "price": 1, "attributes": {"ram": 16}}])


def test_inherited_attributes_and_number_validation():
    with SessionLocal() as session, session.begin():
        # "color" задан у "Одежды и обуви", а товар кладём в "Кроссовки" - наследуется
        catalog.create_product(session, category_id=8, name="Кеды", brand=None,
                               skus=[{"article": "K-1", "price": 1, "attributes": {"color": "красный"}}])
        with pytest.raises(catalog.CatalogError):
            catalog.create_product(session, category_id=8, name="Кеды 2", brand=None,
                                   skus=[{"article": "K-2", "price": 1,
                                          "attributes": {"shoe_size": "большой"}}])


def test_product_card():
    p = catalog.get_product(1)
    assert p["extra"]["Гарантия"] == "1 год"
    assert p["skus"][0]["attributes"]["ОЗУ"] == "8 ГБ"
    assert [c["name"] for c in p["category_path"]][-1] == "Ноутбуки"


# ---------- API ----------

def test_api():
    with TestClient(app) as client:
        assert client.get("/categories/tree").status_code == 200
        r = client.get("/search", params=[("q", "ноутбук"), ("f", "ram:16"), ("f", "ram:32"),
                                          ("brand", "Lenovo"), ("sort", "price_asc")])
        assert r.status_code == 200, r.text
        prices = [i["min_price"] for i in r.json()["items"]]
        assert prices == sorted(prices) and len(prices) == 2
        assert client.get("/search", params={"f": "ram16"}).status_code == 400
        assert client.get("/categories/999/products").status_code == 404
        body = {"category_id": 8, "name": "Кроссовки New Balance 574", "brand": "New Balance",
                "skus": [{"article": "NB-574", "price": 9990, "attributes": {"shoe_size": 42}}]}
        assert client.post("/products", json=body).status_code == 200
        assert client.post("/products", json=body).status_code == 409   # артикул уже занят
