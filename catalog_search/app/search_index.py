"""Полнотекстовый индекс на SQLite FTS5.

FTS5 - встроенный в SQLite модуль полнотекстового поиска. Он разбивает текст на слова
и строит "обратный индекс": слово -> список товаров, где оно встречается.
Поэтому поиск не перебирает все строки, как LIKE '%...%', а сразу находит нужные.

Индекс обновляется ТРИГГЕРАМИ: при добавлении / изменении / удалении товара
SQLite сам обновит product_fts, приложению об этом думать не нужно.
"""
from sqlalchemy import text
from sqlalchemy.engine import Connection

def _yo(expr: str) -> str:
    """Заменяем ё на е: FTS5 не считает их одной буквой, а люди пишут по-разному."""
    return f"replace(replace({expr}, 'ё', 'е'), 'Ё', 'Е')"


def _reindex(product_id_expr: str) -> str:
    """SQL, который заново собирает строку индекса для одного товара.

    В индекс попадают: название, описание, бренд, категория и значения характеристик
    всех SKU (цвет, материал, процессор...), чтобы находился запрос "белые кроссовки".
    """
    return f"""
        DELETE FROM product_fts WHERE rowid = {product_id_expr};
        INSERT INTO product_fts(rowid, name, description, brand, category, attrs)
        SELECT p.id, {_yo("p.name")}, {_yo("p.description")}, {_yo("b.name")}, {_yo("c.name")},
               {_yo("""(SELECT group_concat(DISTINCT v.value_text)
                FROM skus s JOIN sku_attribute_values v ON v.sku_id = s.id
                WHERE s.product_id = p.id)""")}
        FROM products p
        JOIN categories c ON c.id = p.category_id
        LEFT JOIN brands b ON b.id = p.brand_id
        WHERE p.id = {product_id_expr};
    """


FTS_DDL = [
    # unicode61: регистр букв не важен (и для кириллицы тоже)
    """
    CREATE VIRTUAL TABLE product_fts USING fts5(
        name, description, brand, category, attrs,
        tokenize = 'unicode61 remove_diacritics 2'
    )
    """,
    f"""
    CREATE TRIGGER products_fts_insert AFTER INSERT ON products BEGIN
        {_reindex("new.id")}
    END
    """,
    f"""
    CREATE TRIGGER products_fts_update AFTER UPDATE ON products BEGIN
        DELETE FROM product_fts WHERE rowid = old.id;
        {_reindex("new.id")}
    END
    """,
    """
    CREATE TRIGGER products_fts_delete AFTER DELETE ON products BEGIN
        DELETE FROM product_fts WHERE rowid = old.id;
    END
    """,
    # Изменились характеристики SKU -> переиндексировать его товар
    f"""
    CREATE TRIGGER values_fts_insert AFTER INSERT ON sku_attribute_values BEGIN
        {_reindex("(SELECT product_id FROM skus WHERE id = new.sku_id)")}
    END
    """,
    f"""
    CREATE TRIGGER values_fts_update AFTER UPDATE ON sku_attribute_values BEGIN
        {_reindex("(SELECT product_id FROM skus WHERE id = old.sku_id)")}
        {_reindex("(SELECT product_id FROM skus WHERE id = new.sku_id)")}
    END
    """,
    f"""
    CREATE TRIGGER values_fts_delete AFTER DELETE ON sku_attribute_values BEGIN
        {_reindex("(SELECT product_id FROM skus WHERE id = old.sku_id)")}
    END
    """,
]


def fts5_available(conn: Connection) -> bool:
    """В некоторых сборках SQLite нет FTS5 - тогда будет запасной поиск через LIKE."""
    try:
        conn.execute(text("CREATE VIRTUAL TABLE temp._fts_probe USING fts5(x)"))
        conn.execute(text("DROP TABLE temp._fts_probe"))
        return True
    except Exception:
        return False


def create_search_index(conn: Connection) -> bool:
    if not fts5_available(conn):
        return False
    for ddl in FTS_DDL:
        conn.execute(text(ddl))
    return True


def has_search_index(conn: Connection) -> bool:
    return conn.execute(
        text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'product_fts'")
    ).first() is not None
