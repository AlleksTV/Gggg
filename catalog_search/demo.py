"""Демонстрация всех алгоритмов в консоли.  Запуск: python demo.py"""
from app import catalog
from app.catalog import SearchParams
from app.seed import reset_database


def title(text):
    print("\n" + "=" * 70 + f"\n{text}\n" + "=" * 70)


def print_tree(nodes, indent=0):
    for n in nodes:
        print(f"{'    ' * indent}{n['name']}  (товаров: {n['products_total']}, path={n['path']})")
        print_tree(n["children"], indent + 1)


def print_items(result):
    print(f"Найдено товаров: {result['total']}")
    for i in result["items"]:
        rel = f"  релевантность={i['relevance']}" if i.get("relevance") is not None else ""
        print(f"  - {i['name']}: от {i['min_price']:.0f} ₽{rel}")


def print_facets(facets):
    print("Фасеты (в скобках - сколько товаров будет найдено):")
    print("  Бренд: " + ", ".join(f"{b['value']} ({b['count']})" for b in facets["brands"]))
    print(f"  Цена: от {facets['price']['min']:.0f} до {facets['price']['max']:.0f} ₽")
    for a in facets["attributes"]:
        vals = ", ".join(f"{'[x] ' if v['selected'] else ''}{v['value']} ({v['count']})" for v in a["values"])
        print(f"  {a['name']}: {vals}")


if __name__ == "__main__":
    fts = reset_database()

    title("1. Дерево категорий (рекурсивный CTE)")
    print_tree(catalog.category_tree())

    title("1. Все подкатегории 'Электроники' и путь до 'Игровых ноутбуков'")
    print("ID подкатегорий:", catalog.subtree_ids(1))
    print("Хлебные крошки:", " → ".join(c["name"] for c in catalog.breadcrumbs(4)))

    title("1. Товары категории 'Компьютеры' вместе с подкатегориями")
    cte = catalog.products_in_category(2, method="cte")
    path = catalog.products_in_category(2, method="path")
    own = catalog.products_in_category(2, include_subcategories=False)
    print(f"Через рекурсивный CTE: {len(cte)}, через path LIKE: {len(path)}, "
          f"только в самой категории: {len(own)}")
    for p in cte:
        print(f"  - {p['name']} ({p['category']})")

    title("2. Фасеты: категория 'Ноутбуки', выбран фильтр ОЗУ = 16 ГБ")
    r = catalog.search(SearchParams(category_id=3, filters={"ram": ["16"]}, sort="price_asc"))
    print_items(r)
    print_facets(r["facets"])
    print("\nВажно: у фасета 'ОЗУ' видны и другие значения (8, 32), чтобы их можно было добавить.")

    title("2. Фасеты: ОЗУ = 16 или 32 ГБ И процессор AMD Ryzen 7")
    r = catalog.search(SearchParams(category_id=3, filters={"ram": ["16", "32"], "cpu": ["AMD Ryzen 7"]}))
    print_items(r)
    print_facets(r["facets"])

    title(f"3. Полнотекстовый поиск ({'FTS5 + bm25' if fts else 'LIKE'})")
    for q in ["белые кроссовки", "кроссовок для бега", "игровой ноутбук", "чёрная футболка"]:
        r = catalog.search(SearchParams(q=q))
        print(f"\nЗапрос: «{q}»  ->  FTS-запрос: {r['fts_query']}")
        print_items(r)

    title("3. Поиск + фасеты вместе: «кроссовки», размер 42")
    r = catalog.search(SearchParams(q="кроссовки", filters={"shoe_size": ["42"]}))
    print_items(r)
    print_facets(r["facets"])
