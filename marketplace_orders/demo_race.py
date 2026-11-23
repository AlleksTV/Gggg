"""Демонстрация гонки: 5 покупателей одновременно покупают ПОСЛЕДНЮЮ футболку.

Запуск:  python demo_race.py

Для каждого способа видно, сколько заказов успело оформиться.
Правильный ответ: ровно 1 заказ, остальные получают "Недостаточно товара".
"""
import threading

from app import services
from app.db import SessionLocal
from app.models import Stock
from app.seed import reset_database, set_stock
from app.services import CartItem

BUYERS = 5
SKU_ID, WAREHOUSE_ID = 3, 2  # футболка, остаток ровно 1 шт.


def run(mode_name: str, create_fn) -> None:
    set_stock(SKU_ID, WAREHOUSE_ID, quantity=1)

    barrier = threading.Barrier(BUYERS)   # все потоки стартуют одновременно
    results: list[str] = [""] * BUYERS

    def buyer(i: int):
        barrier.wait()
        try:
            order_id = create_fn(user_id=(i % 3) + 1, items=[CartItem(SKU_ID, 1)])
            results[i] = f"заказ №{order_id} оформлен"
        except services.ServiceError as exc:
            results[i] = f"отказ: {exc}"

    threads = [threading.Thread(target=buyer, args=(i,)) for i in range(BUYERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with SessionLocal() as s:
        stock = s.get(Stock, (WAREHOUSE_ID, SKU_ID))
        success = sum(r.startswith("заказ") for r in results)

    print(f"\n=== {mode_name} ===")
    for i, r in enumerate(results, 1):
        print(f"  Покупатель {i}: {r}")
    print(f"  На складе: quantity={stock.quantity}, reserved={stock.reserved}")
    verdict = "OK" if success == 1 else f"ОШИБКА: продано {success} шт. при остатке 1"
    print(f"  Итог: оформлено заказов: {success} -> {verdict}")


if __name__ == "__main__":
    reset_database()
    run("Без блокировок (unsafe)", services.create_order_unsafe)
    run("Пессимистическая блокировка (SELECT ... FOR UPDATE)", services.create_order_pessimistic)
    run("Оптимистическая блокировка (поле version)", services.create_order_optimistic)
