"""Создание таблиц и тестовых данных."""
from decimal import Decimal

from sqlalchemy import text

from .db import Base, SessionLocal, engine
from .models import Sku, Stock, StockMovement, User, Warehouse


def reset_database() -> None:
    """Удаляет и заново создаёт все таблицы, заполняет демо-данными."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    with SessionLocal() as session, session.begin():
        session.add_all([
            User(id=1, full_name="Иван Покупатель"),
            User(id=2, full_name="Мария Покупатель"),
            User(id=3, full_name="Пётр Покупатель"),
        ])
        session.add_all([
            Warehouse(id=1, name="Склад маркетплейса, Подольск", type="FBO"),
            Warehouse(id=2, name="Склад продавца, Казань", type="FBS"),
        ])
        session.add_all([
            Sku(id=1, article="SNK-42-WHT", name="Кроссовки белые, размер 42", price=Decimal("5990.00")),
            Sku(id=2, article="NB-16-512", name="Ноутбук 16 ГБ / 512 ГБ", price=Decimal("74990.00")),
            Sku(id=3, article="LAST-ONE", name="Лимитированная футболка (последняя!)", price=Decimal("1990.00")),
        ])
        session.flush()
        stocks = [
            (1, 1, 10), (2, 1, 5),   # кроссовки: 10 шт. в Подольске, 5 шт. в Казани
            (1, 2, 3),               # ноутбук: 3 шт. в Подольске
            (2, 3, 1),               # футболка: ровно 1 шт. - для демонстрации гонки
        ]
        for wh, sku, qty in stocks:
            session.add(Stock(warehouse_id=wh, sku_id=sku, quantity=qty, reserved=0, version=1))
            session.add(StockMovement(warehouse_id=wh, sku_id=sku, type="income", quantity=qty))

        # Явно заданные id выше не двигают счётчики SERIAL - подвинем вручную
        for table in ("users", "warehouses", "skus"):
            session.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT MAX(id) FROM {table}))"
            ))


def set_stock(sku_id: int, warehouse_id: int, quantity: int) -> None:
    """Для демонстраций: выставить остаток напрямую."""
    with SessionLocal() as session, session.begin():
        stock = session.get(Stock, (warehouse_id, sku_id))
        stock.quantity, stock.reserved = quantity, 0


if __name__ == "__main__":
    reset_database()
    print("База пересоздана и заполнена демо-данными")
