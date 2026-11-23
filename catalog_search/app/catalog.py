"""Алгоритмы каталога.

1. Дерево категорий: рекурсивные CTE (WITH RECURSIVE) и материализованный путь.
2. Фасетная фильтрация: динамический подсчёт товаров для каждого значения фильтра.
3. Полнотекстовый поиск с ранжированием по релевантности (FTS5 + bm25).

SQL написан вручную (text(...)), чтобы его было видно и можно было вставить в отчёт.
"""
import re
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from .db import SessionLocal, engine
from .models import (
    Attribute,
    Brand,
    Category,
    CategoryAttribute,
    Product,
    Sku,
    SkuAttributeValue,
)
from .search_index import has_search_index


class CatalogError(Exception):
    http_status = 400


class NotFound(CatalogError):
    http_status = 404


# =====================================================================
# 1. ДЕРЕВО КАТЕГОРИЙ
# =====================================================================

# Рекурсивный CTE: начинаем с одной категории и на каждом шаге добавляем её детей.
#   Шаг 0: {Электроника}
#   Шаг 1: + {Компьютеры, Смартфоны}          (у кого parent_id = Электроника)
#   Шаг 2: + {Ноутбуки}                         (у кого parent_id = Компьютеры)
#   Шаг 3: + {Игровые ноутбуки}  ... пока новые строки появляются
SUBTREE_CTE = """
WITH RECURSIVE subtree(id, depth) AS (
    SELECT id, 0 FROM categories WHERE id = :category_id      -- стартовая категория
    UNION ALL
    SELECT c.id, s.depth + 1                                  -- её дети, внуки, ...
    FROM categories c
    JOIN subtree s ON c.parent_id = s.id
)
"""


def _check_category(conn, category_id: int) -> None:
    if conn.execute(text("SELECT 1 FROM categories WHERE id = :id"), {"id": category_id}).first() is None:
        raise NotFound(f"Категория {category_id} не найдена")


def subtree_ids(category_id: int) -> list[int]:
    """Сама категория и все её подкатегории на любой глубине."""
    with engine.connect() as conn:
        _check_category(conn, category_id)
        return list(conn.execute(
            text(SUBTREE_CTE + "SELECT id FROM subtree ORDER BY depth, id"),
            {"category_id": category_id},
        ).scalars())


def breadcrumbs(category_id: int, conn=None) -> list[dict]:
    """Путь от корня до категории ("хлебные крошки"): рекурсия ВВЕРХ по parent_id."""
    sql = text("""
        WITH RECURSIVE chain(id, parent_id, name, depth) AS (
            SELECT id, parent_id, name, 0 FROM categories WHERE id = :category_id
            UNION ALL
            SELECT c.id, c.parent_id, c.name, ch.depth + 1
            FROM categories c
            JOIN chain ch ON c.id = ch.parent_id                  -- переходим к родителю
        )
        SELECT id, name FROM chain ORDER BY depth DESC
    """)
    if conn is not None:  # внутри уже открытой транзакции
        _check_category(conn, category_id)
        return [dict(r._mapping) for r in conn.execute(sql, {"category_id": category_id})]
    with engine.connect() as conn:
        return breadcrumbs(category_id, conn)


def category_tree() -> list[dict]:
    """Всё дерево. Для каждой категории считаем товары в ней И во всех подкатегориях.

    Рекурсивный CTE строит пары (предок, потомок) для всех категорий сразу,
    после чего подсчёт товаров - обычный GROUP BY.
    """
    sql = text("""
        WITH RECURSIVE descendants(root_id, id) AS (
            SELECT id, id FROM categories
            UNION ALL
            SELECT d.root_id, c.id
            FROM categories c
            JOIN descendants d ON c.parent_id = d.id
        )
        SELECT c.id, c.parent_id, c.name, c.level, c.path,
               (SELECT COUNT(*) FROM products p WHERE p.category_id = c.id) AS products_own,
               COUNT(p.id) AS products_total
        FROM categories c
        JOIN descendants d ON d.root_id = c.id
        LEFT JOIN products p ON p.category_id = d.id
        GROUP BY c.id
        ORDER BY c.level, c.id
    """)
    with engine.connect() as conn:
        rows = [dict(r._mapping) for r in conn.execute(sql)]

    # Собираем плоский список в дерево (вложенные children)
    by_id = {r["id"]: {**r, "children": []} for r in rows}
    roots = []
    for r in rows:
        node = by_id[r["id"]]
        (by_id[r["parent_id"]]["children"] if r["parent_id"] else roots).append(node)
    return roots


PRODUCT_LIST_SELECT = """
SELECT p.id, p.name, b.name AS brand, c.name AS category,
       MIN(s.price) AS min_price, MAX(s.price) AS max_price, COUNT(s.id) AS skus
FROM products p
JOIN categories c ON c.id = p.category_id
LEFT JOIN brands b ON b.id = p.brand_id
LEFT JOIN skus s ON s.product_id = p.id
"""


def products_in_category(category_id: int, include_subcategories: bool = True,
                         method: str = "cte") -> list[dict]:
    """Товары категории. Два способа обхода дерева, результат одинаковый:

    method="cte"  - рекурсивный CTE по parent_id (Adjacency List);
    method="path" - по материализованному пути: path LIKE '1/2/%'.
    """
    with engine.connect() as conn:
        _check_category(conn, category_id)
        params = {"category_id": category_id}
        if not include_subcategories:
            sql = PRODUCT_LIST_SELECT + "WHERE p.category_id = :category_id"
        elif method == "cte":
            sql = (SUBTREE_CTE + PRODUCT_LIST_SELECT +
                   "WHERE p.category_id IN (SELECT id FROM subtree)")
        elif method == "path":
            params["prefix"] = conn.execute(
                text("SELECT path FROM categories WHERE id = :category_id"), params
            ).scalar_one()
            sql = PRODUCT_LIST_SELECT + "WHERE c.path LIKE :prefix || '%'"
        else:
            raise CatalogError("method должен быть 'cte' или 'path'")
        sql += " GROUP BY p.id ORDER BY p.id"
        return [_money(dict(r._mapping)) for r in conn.execute(text(sql), params)]


def add_category(session, name: str, parent_id: int | None = None) -> Category:
    """Новая категория: path и level вычисляются из родителя."""
    parent = None
    if parent_id is not None:
        parent = session.get(Category, parent_id)
        if parent is None:
            raise NotFound(f"Родительская категория {parent_id} не найдена")
    cat = Category(name=name, parent_id=parent_id, path="", level=parent.level + 1 if parent else 0)
    session.add(cat)
    session.flush()  # нужен id, чтобы собрать path
    cat.path = f"{parent.path if parent else ''}{cat.id}/"
    return cat


# =====================================================================
# 2-3. ПОИСК + ФАСЕТНАЯ ФИЛЬТРАЦИЯ
# =====================================================================

SORTS = ("relevance", "price_asc", "price_desc", "name")


@dataclass
class SearchParams:
    q: str | None = None                       # строка поиска
    category_id: int | None = None             # искать в категории и её подкатегориях
    brands: list[str] = field(default_factory=list)
    price_min: float | None = None
    price_max: float | None = None
    filters: dict[str, list[str]] = field(default_factory=dict)  # {"ram": ["16", "32"]}
    in_stock: bool = False
    sort: str = "relevance"
    limit: int = 20
    offset: int = 0


def simple_stem(word: str) -> str:
    """Упрощённый стемминг: отрезаем окончание, дальше ищем по префиксу.

    FTS5 не знает русской морфологии, и "кроссовки" != "кроссовок".
    Если отрезать 2 последние буквы у слов от 5 букв и искать "кроссов*",
    то находятся все формы: кроссовки, кроссовок, кроссовками.
    """
    if word.isdigit() or len(word) < 4:
        return word
    if len(word) == 4:  # "бега" -> "бег", "игры" -> "игр"
        return word[:-1] if word[-1] in "аеёиоуыэюяy" else word
    return word[:-2]


# Служебные слова не несут смысла для поиска: "ноутбук для учёбы" == "ноутбук учёбы"
STOP_WORDS = {"и", "в", "во", "на", "с", "со", "для", "по", "из", "от", "до", "к", "о", "а", "или"}


def query_terms(q: str | None) -> list[str]:
    words = re.findall(r"\w+", (q or "").lower().replace("ё", "е"))
    return [simple_stem(w) for w in words if w not in STOP_WORDS]


def make_fts_query(q: str | None) -> str | None:
    """'Белые кроссовки' -> '"бел"* "кроссов"*'  (все слова должны встретиться)."""
    terms = query_terms(q)
    return " ".join(f'"{t}"*' for t in terms) or None


class _Query:
    """Собирает WHERE для поиска по SKU.

    Условия на SKU-уровне: если выбраны "размер 42" и "цвет белый",
    то подходит товар, у которого есть SKU, где ОДНОВРЕМЕННО размер 42 и белый цвет.
    Значения одной характеристики объединяются через ИЛИ (16 ГБ или 32 ГБ),
    разные характеристики - через И (ОЗУ 16 ГБ и диагональ 15.6).
    """

    FROM = """
        FROM skus s
        JOIN products p ON p.id = s.product_id
        JOIN categories c ON c.id = p.category_id
        LEFT JOIN brands b ON b.id = p.brand_id
    """

    def __init__(self, p: SearchParams, use_fts: bool):
        self.p = p
        self.use_fts = use_fts
        self.terms = query_terms(p.q)
        self.fts = make_fts_query(p.q) if use_fts else None
        self.prefix = SUBTREE_CTE if p.category_id is not None else ""

    def where(self, skip_attr: str | None = None, skip_brand=False, skip_price=False):
        p, conds, params = self.p, ["1 = 1"], {}
        if p.category_id is not None:
            conds.append("p.category_id IN (SELECT id FROM subtree)")
            params["category_id"] = p.category_id
        if self.terms:
            if self.use_fts:
                conds.append("p.id IN (SELECT rowid FROM product_fts WHERE product_fts MATCH :fts)")
                params["fts"] = self.fts
            else:  # запасной вариант без FTS5
                for i, t in enumerate(self.terms):
                    conds.append(f"""(py_lower(p.name) LIKE :t{i} OR py_lower(p.description) LIKE :t{i}
                        OR py_lower(b.name) LIKE :t{i} OR py_lower(c.name) LIKE :t{i}
                        OR EXISTS (SELECT 1 FROM skus s2
                                   JOIN sku_attribute_values v2 ON v2.sku_id = s2.id
                                   WHERE s2.product_id = p.id AND py_lower(v2.value_text) LIKE :t{i}))""")
                    params[f"t{i}"] = f"%{t}%"
        if p.brands and not skip_brand:
            names = [f":brand{i}" for i in range(len(p.brands))]
            conds.append(f"b.name IN ({', '.join(names)})")
            params.update({f"brand{i}": b for i, b in enumerate(p.brands)})
        if not skip_price:
            if p.price_min is not None:
                conds.append("s.price >= :price_min")
                params["price_min"] = p.price_min
            if p.price_max is not None:
                conds.append("s.price <= :price_max")
                params["price_max"] = p.price_max
        if p.in_stock:
            conds.append("s.stock > 0")
        for i, (code, values) in enumerate(sorted(p.filters.items())):
            if code == skip_attr or not values:
                continue
            names = [f":f{i}v{j}" for j in range(len(values))]
            conds.append(f"""EXISTS (
                SELECT 1 FROM sku_attribute_values v
                JOIN attributes a ON a.id = v.attribute_id
                WHERE v.sku_id = s.id AND a.code = :f{i}code
                  AND v.value_text IN ({', '.join(names)}))""")
            params[f"f{i}code"] = code
            params.update({f"f{i}v{j}": v for j, v in enumerate(values)})
        return " AND ".join(conds), params

    def relevance_sql(self) -> tuple[str, str, str]:
        """Возвращает (WITH-часть, JOIN, выражение оценки). Чем МЕНЬШЕ score, тем выше товар."""
        if not self.terms:
            return self.prefix, "", "0"
        if self.use_fts:
            # bm25 - стандартная формула ранжирования поисковиков. Веса колонок:
            # название (10), описание (1), бренд (5), категория (3), характеристики (2).
            # MATERIALIZED - чтобы SQLite посчитал bm25 прямо внутри поиска по индексу
            # (вне его bm25 вызывать нельзя).
            ranked = """ranked AS MATERIALIZED (
                SELECT rowid AS pid,
                       bm25(product_fts, 10.0, 1.0, 5.0, 3.0, 2.0) AS score,
                       snippet(product_fts, -1, '[', ']', '…', 10) AS snippet
                FROM product_fts WHERE product_fts MATCH :fts
            )"""
            with_sql = (self.prefix + ", " + ranked) if self.prefix else ("WITH " + ranked)
            return with_sql, "JOIN ranked f ON f.pid = p.id", "f.score"
        parts = []
        for i in range(len(self.terms)):
            parts.append(f"(CASE WHEN py_lower(p.name) LIKE :t{i} THEN 10 ELSE 0 END"
                         f" + CASE WHEN py_lower(b.name) LIKE :t{i} THEN 5 ELSE 0 END"
                         f" + CASE WHEN py_lower(c.name) LIKE :t{i} THEN 3 ELSE 0 END"
                         f" + CASE WHEN py_lower(p.description) LIKE :t{i} THEN 1 ELSE 0 END)")
        return self.prefix, "", "-(" + " + ".join(parts) + ")"


def _money(row: dict) -> dict:
    for k in ("min_price", "max_price"):
        if row.get(k) is not None:
            row[k] = float(row[k])
    return row


def search(p: SearchParams) -> dict:
    if p.sort not in SORTS:
        raise CatalogError(f"sort должен быть одним из: {', '.join(SORTS)}")
    if p.sort == "relevance" and not query_terms(p.q):
        p.sort = "name"  # без строки поиска сортировать по релевантности нечего

    with engine.connect() as conn:
        if p.category_id is not None:
            _check_category(conn, p.category_id)
        known = set(conn.execute(text("SELECT code FROM attributes")).scalars())
        unknown = set(p.filters) - known
        if unknown:
            raise CatalogError(f"Неизвестные характеристики: {sorted(unknown)}")

        qb = _Query(p, use_fts=has_search_index(conn))
        where, params = qb.where()

        # ---- Количество найденных товаров ----
        total = conn.execute(
            text(f"{qb.prefix} SELECT COUNT(DISTINCT p.id) {qb.FROM} WHERE {where}"), params
        ).scalar_one()

        # ---- Сами товары (страница) ----
        with_sql, rel_join, rel_expr = qb.relevance_sql()
        order = {
            "relevance": "score ASC, p.id",
            "price_asc": "min_price ASC, p.id",
            "price_desc": "min_price DESC, p.id",
            "name": "p.name, p.id",
        }[p.sort]
        snippet_col = ", f.snippet AS snippet" if rel_join else ""
        items_sql = f"""{with_sql}
            SELECT p.id, p.name, b.name AS brand, c.name AS category,
                   MIN(s.price) AS min_price, MAX(s.price) AS max_price,
                   COUNT(s.id) AS matched_skus, {rel_expr} AS score {snippet_col}
            {qb.FROM} {rel_join}
            WHERE {where}
            GROUP BY p.id
            ORDER BY {order}
            LIMIT :limit OFFSET :offset
        """
        rows = conn.execute(text(items_sql), {**params, "limit": p.limit, "offset": p.offset})
        items = []
        for r in rows:
            item = _money(dict(r._mapping))
            item["relevance"] = round(-float(item.pop("score")), 4) if qb.terms else None
            items.append(item)

        facets = _facets(conn, qb, known)

    return {"total": total, "items": items, "facets": facets,
            "fts_query": qb.fts, "search_engine": "fts5" if qb.use_fts else "like"}


def _facets(conn, qb: _Query, known_codes: set[str]) -> dict:
    """Фасеты - сколько товаров найдётся, если дополнительно выбрать это значение.

    Главное правило: при подсчёте фасета характеристики X фильтр по самой X
    НЕ применяется (а все остальные - применяются). Иначе, выбрав "16 ГБ",
    пользователь перестал бы видеть вариант "32 ГБ" и не смог бы выбрать оба.
    """
    p = qb.p

    # Бренды
    where, params = qb.where(skip_brand=True)
    brand_rows = conn.execute(text(f"""{qb.prefix}
        SELECT b.name AS value, COUNT(DISTINCT p.id) AS count
        {qb.FROM} WHERE {where} AND b.name IS NOT NULL
        GROUP BY b.name ORDER BY count DESC, b.name"""), params)
    brands = [{**dict(r._mapping), "selected": r.value in p.brands} for r in brand_rows]

    # Диапазон цен
    where, params = qb.where(skip_price=True)
    pr = conn.execute(text(f"""{qb.prefix}
        SELECT MIN(s.price) AS min, MAX(s.price) AS max {qb.FROM} WHERE {where}"""), params).one()
    price = {"min": float(pr.min) if pr.min is not None else None,
             "max": float(pr.max) if pr.max is not None else None}

    # Какие характеристики вообще есть у найденных товаров (без учёта фильтров по характеристикам)
    no_attr_filters = _Query(SearchParams(**{**p.__dict__, "filters": {}}), qb.use_fts)
    where, params = no_attr_filters.where()
    codes = list(conn.execute(text(f"""{qb.prefix}
        SELECT DISTINCT a.code
        {qb.FROM}
        JOIN sku_attribute_values v ON v.sku_id = s.id
        JOIN attributes a ON a.id = v.attribute_id
        WHERE {where} AND a.is_filterable = 1
        ORDER BY a.id"""), params).scalars())
    codes += [c for c in p.filters if c in known_codes and c not in codes]

    # Для каждой характеристики - отдельный подсчёт без её собственного фильтра
    attributes = []
    for code in codes:
        where, params = qb.where(skip_attr=code)
        rows = conn.execute(text(f"""{qb.prefix}
            SELECT v.value_text AS value,
                   MIN(v.value_num) AS num, COUNT(DISTINCT p.id) AS count
            {qb.FROM}
            JOIN sku_attribute_values v ON v.sku_id = s.id
            JOIN attributes a ON a.id = v.attribute_id
            WHERE {where} AND a.code = :facet_code
            GROUP BY v.value_text
            ORDER BY num, v.value_text"""), {**params, "facet_code": code}).all()
        selected = p.filters.get(code, [])
        values = [{"value": r.value, "count": r.count, "selected": r.value in selected}
                  for r in rows]
        # Выбранное значение показываем всегда (даже с нулём), чтобы его можно было снять
        shown = {v["value"] for v in values}
        values += [{"value": v, "count": 0, "selected": True} for v in selected if v not in shown]
        if not values:
            continue
        attr = conn.execute(text("SELECT name, unit FROM attributes WHERE code = :c"),
                            {"c": code}).one()
        attributes.append({"code": code, "name": attr.name, "unit": attr.unit, "values": values})
    return {"brands": brands, "price": price, "attributes": attributes}


# =====================================================================
# Карточка товара и добавление товара (EAV + JSON)
# =====================================================================

def get_product(product_id: int) -> dict:
    with SessionLocal() as session:
        prod = session.scalars(
            select(Product).where(Product.id == product_id).options(
                selectinload(Product.skus).selectinload(Sku.values)
                .selectinload(SkuAttributeValue.attribute),
                selectinload(Product.brand))
        ).one_or_none()
        if prod is None:
            raise NotFound(f"Товар {product_id} не найден")
        return {
            "id": prod.id,
            "name": prod.name,
            "brand": prod.brand.name if prod.brand else None,
            "category_path": breadcrumbs(prod.category_id, session.connection()),
            "description": prod.description,
            "extra": prod.extra,
            "skus": [{
                "id": s.id, "article": s.article, "price": float(s.price), "stock": s.stock,
                "attributes": {v.attribute.name: v.value_text + (f" {v.attribute.unit}" if v.attribute.unit else "")
                               for v in sorted(s.values, key=lambda v: v.attribute_id)},
            } for s in prod.skus],
        }


def allowed_attributes(session, category_id: int) -> dict[str, Attribute]:
    """Характеристики категории + всех её предков (наследование вниз по дереву)."""
    ids = [c["id"] for c in breadcrumbs(category_id, session.connection())]
    rows = session.scalars(
        select(Attribute).join(CategoryAttribute, CategoryAttribute.attribute_id == Attribute.id)
        .where(CategoryAttribute.category_id.in_(ids))
    ).all()
    return {a.code: a for a in rows}


def _normalize(attr: Attribute, value) -> tuple[str, float | None]:
    if attr.data_type == "number":
        try:
            num = float(str(value).replace(",", "."))
        except ValueError:
            raise CatalogError(f"'{attr.name}' должно быть числом, получено: {value!r}")
        return (str(int(num)) if num.is_integer() else str(num)), num
    return str(value).strip(), None


def create_product(session, *, category_id: int, name: str, brand: str | None,
                   description: str = "", extra: dict | None = None,
                   skus: list[dict]) -> Product:
    """skus = [{"article": "...", "price": 100, "stock": 5, "attributes": {"ram": 16}}]"""
    if session.get(Category, category_id) is None:
        raise NotFound(f"Категория {category_id} не найдена")
    if not skus:
        raise CatalogError("У товара должен быть хотя бы один SKU")
    allowed = allowed_attributes(session, category_id)

    brand_obj = None
    if brand:
        brand_obj = session.scalars(select(Brand).where(Brand.name == brand)).one_or_none()
        if brand_obj is None:
            brand_obj = Brand(name=brand)
            session.add(brand_obj)
            session.flush()

    prod = Product(category_id=category_id, brand_id=brand_obj.id if brand_obj else None,
                   name=name, description=description, extra=extra or {})
    for s in skus:
        sku = Sku(article=s["article"], price=s["price"], stock=s.get("stock", 0))
        for code, value in s.get("attributes", {}).items():
            attr = allowed.get(code)
            if attr is None:
                raise CatalogError(f"У категории нет характеристики '{code}'. "
                                   f"Доступны: {sorted(allowed)}")
            vt, vn = _normalize(attr, value)
            sku.values.append(SkuAttributeValue(attribute_id=attr.id, value_text=vt, value_num=vn))
        prod.skus.append(sku)
    session.add(prod)
    session.flush()
    return prod
