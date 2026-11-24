"""Создание таблиц и демо-каталога.  Запуск: python -m app.seed"""
from .catalog import add_category, create_product
from .db import Base, SessionLocal, engine
from .models import Attribute, CategoryAttribute
from .search_index import create_search_index

ATTRIBUTES = [
    # code,        name,            type,     unit
    ("ram",        "ОЗУ",           "number", "ГБ"),
    ("cpu",        "Процессор",     "text",   None),
    ("screen",     "Диагональ",     "number", "\""),
    ("storage",    "Накопитель",    "number", "ГБ"),
    ("color",      "Цвет",          "text",   None),
    ("shoe_size",  "Размер обуви",  "number", None),
    ("cloth_size", "Размер одежды", "text",   None),
    ("material",   "Материал",      "text",   None),
    ("damage",     "Урон",          "number", None),
    ("magazine",   "Магазин",       "number", "патр."),
    ("tech",       "Технология",    "text",   None),
    ("finish",     "Отделка",       "text",   None),
]

# Дерево категорий: (ключ, название, ключ родителя, характеристики категории)
CATEGORIES = [
    ("electronics", "Электроника",      None,          []),
    ("computers",   "Компьютеры",       "electronics", ["ram", "cpu", "screen", "storage"]),
    ("laptops",     "Ноутбуки",         "computers",   []),   # характеристики наследуются
    ("gaming",      "Игровые ноутбуки", "laptops",     []),
    ("phones",      "Смартфоны",        "electronics", ["ram", "storage", "screen", "color"]),
    ("fashion",     "Одежда и обувь",   None,          ["color", "material"]),
    ("shoes",       "Обувь",            "fashion",     ["shoe_size"]),
    ("sneakers",    "Кроссовки",        "shoes",       []),
    ("boots",       "Ботинки",          "shoes",       []),
    ("clothes",     "Одежда",           "fashion",     ["cloth_size"]),
    ("tshirts",     "Футболки",         "clothes",     []),
    # Вымышленное оружие для киберпанк-витрины
    ("arsenal",     "Арсенал",          None,          ["damage", "tech", "finish"]),
    ("pistols",     "Пистолеты",        "arsenal",     ["magazine"]),
    ("rifles",      "Винтовки",         "arsenal",     ["magazine"]),
    ("blades",      "Клинки",           "arsenal",     []),
]


def _gun(damage, magazine, tech, finish):
    return {"damage": damage, "magazine": magazine, "tech": tech, "finish": finish}


def _laptop(ram, cpu, screen, storage):
    return {"ram": ram, "cpu": cpu, "screen": screen, "storage": storage}


PRODUCTS = [
    # ---------- Ноутбуки ----------
    ("laptops", "Ноутбук Lenovo IdeaPad Slim 5", "Lenovo",
     "Лёгкий ноутбук для учёбы и работы, металлический корпус, до 12 часов автономной работы.",
     {"Гарантия": "1 год", "Вес": "1.5 кг"},
     [(54990, 7, _laptop(8, "AMD Ryzen 5", 15.6, 512)),
      (64990, 4, _laptop(16, "AMD Ryzen 5", 15.6, 512)),
      (74990, 0, _laptop(16, "AMD Ryzen 7", 15.6, 1024))]),
    ("laptops", "Ноутбук ASUS Vivobook 15", "ASUS",
     "Недорогой ноутбук для дома и учёбы с большим экраном.",
     {"Гарантия": "1 год", "Вес": "1.7 кг"},
     [(42990, 12, _laptop(8, "Intel Core i3", 15.6, 256)),
      (51990, 6, _laptop(16, "Intel Core i5", 15.6, 512))]),
    ("laptops", "Ноутбук Apple MacBook Air 13 M2", "Apple",
     "Тонкий и тихий ноутбук без вентилятора, яркий дисплей Liquid Retina.",
     {"Гарантия": "1 год", "Вес": "1.24 кг"},
     [(99990, 3, _laptop(8, "Apple M2", 13.6, 256)),
      (129990, 2, _laptop(16, "Apple M2", 13.6, 512))]),
    ("laptops", "Ноутбук HUAWEI MateBook D 16", "HUAWEI",
     "Ноутбук с экраном 16 дюймов для работы с документами и учёбы.",
     {"Гарантия": "2 года", "Вес": "1.7 кг"},
     [(58990, 5, _laptop(16, "Intel Core i5", 16, 512))]),
    # ---------- Игровые ноутбуки ----------
    ("gaming", "Игровой ноутбук ASUS ROG Strix G16", "ASUS",
     "Мощный игровой ноутбук с видеокартой RTX 4060 и экраном 165 Гц.",
     {"Гарантия": "2 года", "Видеокарта": "RTX 4060"},
     [(139990, 4, _laptop(16, "Intel Core i7", 16, 1024)),
      (164990, 2, _laptop(32, "Intel Core i9", 16, 1024))]),
    ("gaming", "Игровой ноутбук Lenovo Legion 5 Pro", "Lenovo",
     "Игровой ноутбук для современных игр, продуманное охлаждение.",
     {"Гарантия": "2 года", "Видеокарта": "RTX 4070"},
     [(154990, 3, _laptop(16, "AMD Ryzen 7", 16, 1024)),
      (179990, 1, _laptop(32, "AMD Ryzen 9", 16, 2048))]),
    # ---------- Смартфоны ----------
    ("phones", "Смартфон Apple iPhone 15", "Apple",
     "Смартфон с камерой 48 Мп и разъёмом USB-C.",
     {"Гарантия": "1 год", "Защита": "IP68"},
     [(79990, 10, {"ram": 6, "storage": 128, "screen": 6.1, "color": "чёрный"}),
      (79990, 8, {"ram": 6, "storage": 128, "screen": 6.1, "color": "синий"}),
      (89990, 5, {"ram": 6, "storage": 256, "screen": 6.1, "color": "чёрный"})]),
    ("phones", "Смартфон Samsung Galaxy S24", "Samsung",
     "Компактный флагманский смартфон с ярким экраном и хорошей камерой.",
     {"Гарантия": "1 год", "Защита": "IP68"},
     [(74990, 9, {"ram": 8, "storage": 256, "screen": 6.2, "color": "чёрный"}),
      (74990, 0, {"ram": 8, "storage": 256, "screen": 6.2, "color": "фиолетовый"})]),
    ("phones", "Смартфон Xiaomi Redmi Note 13", "Xiaomi",
     "Недорогой смартфон с большим экраном и ёмким аккумулятором.",
     {"Гарантия": "1 год"},
     [(19990, 25, {"ram": 6, "storage": 128, "screen": 6.67, "color": "чёрный"}),
      (23990, 15, {"ram": 8, "storage": 256, "screen": 6.67, "color": "синий"})]),
    # ---------- Кроссовки ----------
    ("sneakers", "Кроссовки Nike Air Max 90", "Nike",
     "Классические кроссовки с видимой воздушной подушкой.",
     {"Сезон": "лето"},
     [(12990, 4, {"shoe_size": 41, "color": "белый", "material": "кожа"}),
      (12990, 6, {"shoe_size": 42, "color": "белый", "material": "кожа"}),
      (12990, 0, {"shoe_size": 43, "color": "белый", "material": "кожа"}),
      (12990, 3, {"shoe_size": 42, "color": "чёрный", "material": "кожа"})]),
    ("sneakers", "Беговые кроссовки ASICS Gel-Kayano 30", "ASICS",
     "Беговые кроссовки с поддержкой стопы для длинных дистанций.",
     {"Сезон": "лето", "Назначение": "бег"},
     [(15990, 5, {"shoe_size": 42, "color": "синий", "material": "текстиль"}),
      (15990, 2, {"shoe_size": 44, "color": "синий", "material": "текстиль"})]),
    ("sneakers", "Кроссовки adidas Ultraboost Light", "adidas",
     "Лёгкие беговые кроссовки с амортизирующей подошвой Boost.",
     {"Сезон": "лето", "Назначение": "бег"},
     [(17990, 3, {"shoe_size": 41, "color": "белый", "material": "текстиль"}),
      (17990, 4, {"shoe_size": 42, "color": "чёрный", "material": "текстиль"})]),
    # ---------- Ботинки ----------
    ("boots", "Ботинки зимние Timberland 6-Inch", "Timberland",
     "Тёплые водонепроницаемые ботинки из нубука для зимы.",
     {"Сезон": "зима"},
     [(21990, 3, {"shoe_size": 42, "color": "жёлтый", "material": "нубук"}),
      (21990, 2, {"shoe_size": 43, "color": "жёлтый", "material": "нубук"})]),
    # ---------- Футболки ----------
    ("tshirts", "Футболка хлопковая базовая", "Befree",
     "Однотонная футболка из 100% хлопка на каждый день.",
     {"Состав": "хлопок 100%"},
     [(799, 30, {"cloth_size": "S", "color": "белый", "material": "хлопок"}),
      (799, 40, {"cloth_size": "M", "color": "белый", "material": "хлопок"}),
      (799, 25, {"cloth_size": "M", "color": "чёрный", "material": "хлопок"}),
      (799, 0, {"cloth_size": "L", "color": "чёрный", "material": "хлопок"})]),
    ("tshirts", "Футболка спортивная Nike Dri-FIT", "Nike",
     "Спортивная футболка для бега и тренировок, быстро сохнет.",
     {"Состав": "полиэстер 100%"},
     [(2990, 10, {"cloth_size": "M", "color": "чёрный", "material": "полиэстер"}),
      (2990, 7, {"cloth_size": "L", "color": "синий", "material": "полиэстер"})]),
    # ---------- Арсенал (вымышленные модели) ----------
    ("pistols", "Пистолет Kestrel P-12 «Оса»", "Kestrel Arms",
     "Компактный кинетический пистолет с титановой рамкой. Не боится дождя и пыли.",
     {"Гарантия": "3 года", "Вес": "0.7 кг"},
     [(8900, 5, _gun(34, 12, "кинетика", "графит")),
      (9400, 2, _gun(34, 12, "кинетика", "хром"))]),
    ("pistols", "Смарт-пистолет Ostrog SP-3 «Гончая»", "Ostrog Dynamics",
     "Пули с самонаведением. Связь с имплантом через нейропорт, цель захватывается взглядом.",
     {"Гарантия": "2 года", "Совместимость": "нейропорт 4-го поколения"},
     [(21900, 3, _gun(28, 15, "смарт", "графит")),
      (23900, 0, _gun(28, 15, "смарт", "неоновый розовый"))]),
    ("pistols", "Импульсный револьвер Mirai R-6 «Гром»", "Mirai Kinetics",
     "Магнитный разгон пули. При полном заряде пробивает лёгкие укрытия.",
     {"Гарантия": "2 года", "Время заряда": "0.8 с"},
     [(18500, 4, _gun(61, 6, "импульс", "воронёная сталь"))]),
    ("rifles", "Импульсная винтовка Kestrel AR-9 «Гелиос»", "Kestrel Arms",
     "Штурмовая винтовка с магнитными рельсами и охлаждаемым стволом для длинных очередей.",
     {"Гарантия": "3 года", "Вес": "3.4 кг"},
     [(54900, 2, _gun(48, 30, "импульс", "графит")),
      (57900, 1, _gun(48, 30, "импульс", "песочный"))]),
    ("rifles", "Смарт-винтовка Ostrog SR-1 «Сокол»", "Ostrog Dynamics",
     "Снайперская винтовка с умными пулями, которые огибают препятствия по траектории.",
     {"Гарантия": "2 года", "Дальность": "1200 м"},
     [(89900, 1, _gun(120, 5, "смарт", "графит"))]),
    ("rifles", "Дробовик Mirai SG-4 «Таран»", "Mirai Kinetics",
     "Помповый дробовик для ближнего боя с усиленной отдачей и широким разлётом.",
     {"Гарантия": "2 года", "Вес": "3.9 кг"},
     [(31900, 6, _gun(95, 8, "кинетика", "воронёная сталь"))]),
    ("blades", "Термокатана Vantablade «Тень»", "Vantablade",
     "Лезвие нагревается до 900 °C за две секунды. Рукоять с защитой от перегрева.",
     {"Гарантия": "5 лет", "Длина клинка": "72 см"},
     [(44900, 2, {"damage": 80, "tech": "термо", "finish": "чёрный хром"}),
      (47900, 1, {"damage": 80, "tech": "термо", "finish": "неоновый голубой"})]),
    ("blades", "Тактический нож Kestrel K-1", "Kestrel Arms",
     "Нож из углеродной стали с керамическим покрытием. Помещается в скрытое крепление на предплечье.",
     {"Гарантия": "пожизненная"},
     [(4900, 15, {"damage": 22, "tech": "кинетика", "finish": "графит"})]),
]


def create_schema() -> bool:
    """Пересоздаёт все таблицы и полнотекстовый индекс. Возвращает True, если есть FTS5."""
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS product_fts")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        return create_search_index(conn)


def reset_database() -> bool:
    fts = create_schema()
    with SessionLocal() as session, session.begin():
        attrs = {}
        for code, name, dtype, unit in ATTRIBUTES:
            attrs[code] = Attribute(code=code, name=name, data_type=dtype, unit=unit, is_filterable=True)
            session.add(attrs[code])
        session.flush()

        cats = {}
        for key, name, parent, codes in CATEGORIES:
            cats[key] = add_category(session, name, cats[parent].id if parent else None)
            for code in codes:
                session.add(CategoryAttribute(category_id=cats[key].id, attribute_id=attrs[code].id))
        session.flush()

        for n, (cat, name, brand, descr, extra, skus) in enumerate(PRODUCTS, 1):
            create_product(
                session, category_id=cats[cat].id, name=name, brand=brand,
                description=descr, extra=extra,
                skus=[{"article": f"P{n:03d}-{i}", "price": price, "stock": stock, "attributes": a}
                      for i, (price, stock, a) in enumerate(skus, 1)],
            )
    return fts


if __name__ == "__main__":
    has_fts = reset_database()
    print("База пересоздана и заполнена демо-данными.")
    print("Полнотекстовый поиск:", "FTS5" if has_fts else "FTS5 недоступен, используется LIKE")
