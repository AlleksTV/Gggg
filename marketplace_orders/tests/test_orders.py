import threading
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import services
from app.db import SessionLocal
from app.main import app
from app.models import Order, OrderStatusHistory, Reservation, Stock, StockMovement
from app.seed import set_stock
from app.services import CartItem


def stock(sku_id, warehouse_id):
    with SessionLocal() as s:
        st = s.get(Stock, (warehouse_id, sku_id))
        return st.quantity, st.reserved


def order(order_id):
    with SessionLocal() as s:
        return s.get(Order, order_id)


def count(model):
    with SessionLocal() as s:
        return s.scalar(select(func.count()).select_from(model))


# ---------- Оформление заказа ----------

@pytest.mark.parametrize("create", [services.create_order_pessimistic,
                                    services.create_order_optimistic])
def test_create_order_reserves_stock(create):
    order_id = create(1, [CartItem(2, 2)])
    assert stock(2, 1) == (3, 2)                 # ноутбуков 3, из них 2 в резерве
    o = order(order_id)
    assert o.status == "reserved"
    assert str(o.total_amount) == "149980.00"


def test_same_sku_twice_in_cart_is_merged():
    services.create_order_pessimistic(1, [CartItem(2, 1), CartItem(2, 1)])
    assert stock(2, 1) == (3, 2)


def test_order_is_atomic_when_one_item_missing():
    """Первая позиция есть, второй не хватает -> не должно измениться НИЧЕГО."""
    with pytest.raises(services.OutOfStock):
        services.create_order_pessimistic(1, [CartItem(1, 1), CartItem(2, 100)])
    assert stock(1, 1) == (10, 0)
    assert stock(1, 2) == (5, 0)
    assert count(Order) == 0
    assert count(Reservation) == 0


def test_warehouse_with_enough_stock_is_chosen_and_order_not_split():
    services.create_order_pessimistic(1, [CartItem(1, 7)])   # хватает только в Подольске (10)
    assert stock(1, 1) == (10, 7)
    assert stock(1, 2) == (5, 0)
    # 4 + 5 = 9 >= 9, но ни на одном складе целиком нет -> отказ, заказ не дробим
    with pytest.raises(services.OutOfStock):
        services.create_order_pessimistic(1, [CartItem(1, 9)])


def test_unknown_sku_and_user():
    with pytest.raises(services.NotFound):
        services.create_order_pessimistic(1, [CartItem(999, 1)])
    with pytest.raises(services.NotFound):
        services.create_order_pessimistic(999, [CartItem(1, 1)])


# ---------- Гонка за последний товар ----------

def race(create_fn, buyers=10):
    set_stock(3, 2, quantity=1)
    barrier = threading.Barrier(buyers)
    ok, fail = [], []

    def buyer(i):
        barrier.wait()
        try:
            ok.append(create_fn((i % 3) + 1, [CartItem(3, 1)]))
        except services.OutOfStock:
            fail.append(i)

    threads = [threading.Thread(target=buyer, args=(i,)) for i in range(buyers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return ok, fail


@pytest.mark.parametrize("create", [services.create_order_pessimistic,
                                    services.create_order_optimistic])
def test_race_only_one_buyer_gets_last_item(create):
    ok, fail = race(create)
    assert len(ok) == 1
    assert len(fail) == 9
    assert stock(3, 2) == (1, 1)


def test_race_without_locks_oversells():
    """Доказываем, что проблема реальна: без блокировок товар продаётся несколько раз."""
    ok, _ = race(services.create_order_unsafe, buyers=5)
    assert len(ok) > 1


# ---------- Оплата, отмена, таймаут ----------

def test_pay_writes_off_stock():
    order_id = services.create_order_pessimistic(1, [CartItem(2, 2)])
    services.pay_order(order_id)
    assert stock(2, 1) == (1, 0)
    assert order(order_id).status == "paid"
    with SessionLocal() as s:
        types = s.scalars(select(StockMovement.type).where(StockMovement.order_id == order_id)).all()
    assert sorted(types) == ["outcome", "reserve"]


def test_cannot_pay_twice():
    order_id = services.create_order_pessimistic(1, [CartItem(2, 1)])
    services.pay_order(order_id)
    with pytest.raises(services.InvalidStatus):
        services.pay_order(order_id)
    assert stock(2, 1) == (2, 0)


def test_cancel_releases_reserve():
    order_id = services.create_order_pessimistic(1, [CartItem(2, 3)])
    services.cancel_order(order_id)
    assert stock(2, 1) == (3, 0)
    assert order(order_id).status == "cancelled"


def test_cancel_paid_order_returns_goods():
    order_id = services.create_order_pessimistic(1, [CartItem(2, 1)])
    services.pay_order(order_id)
    services.cancel_order(order_id)
    assert stock(2, 1) == (3, 0)


def test_unpaid_reserve_expires_by_timeout():
    order_id = services.create_order_pessimistic(1, [CartItem(3, 1)], reserve_seconds=1)
    assert services.expire_overdue_reservations() == []      # ещё рано
    time.sleep(1.2)
    assert services.expire_overdue_reservations() == [order_id]
    assert stock(3, 2) == (1, 0)                              # товар снова доступен
    assert order(order_id).status == "expired"
    # теперь футболку может купить другой человек
    services.create_order_pessimistic(2, [CartItem(3, 1)])


def test_paying_expired_order_fails_and_releases_reserve():
    order_id = services.create_order_pessimistic(1, [CartItem(3, 1)], reserve_seconds=1)
    time.sleep(1.2)
    with pytest.raises(services.InvalidStatus):
        services.pay_order(order_id)
    assert order(order_id).status == "expired"
    assert stock(3, 2) == (1, 0)


def test_status_machine_and_history():
    order_id = services.create_order_pessimistic(1, [CartItem(1, 1)])
    with pytest.raises(services.InvalidStatus):
        services.set_delivery_status(order_id, "shipped")      # нельзя отправить без оплаты
    services.pay_order(order_id)
    for st in ("assembling", "shipped", "delivered"):
        services.set_delivery_status(order_id, st)
    with SessionLocal() as s:
        steps = s.scalars(select(OrderStatusHistory.new_status)
                          .where(OrderStatusHistory.order_id == order_id)
                          .order_by(OrderStatusHistory.id)).all()
    assert steps == ["reserved", "paid", "assembling", "shipped", "delivered"]


def test_income():
    services.add_income(1, 3, 5)
    assert stock(3, 1) == (5, 0)


# ---------- API ----------

def test_api_flow():
    with TestClient(app) as client:
        assert client.get("/openapi.json").status_code == 200
        r = client.post("/orders", json={"user_id": 1, "items": [{"sku_id": 3, "quantity": 1}],
                                         "lock_mode": "optimistic"})
        assert r.status_code == 200, r.text
        order_id = r.json()["id"]
        r = client.post("/orders", json={"user_id": 2, "items": [{"sku_id": 3, "quantity": 1}]})
        assert r.status_code == 409
        r = client.post(f"/orders/{order_id}/pay")
        assert r.json()["status"] == "paid"
        assert client.get("/stocks", params={"sku_id": 3}).json()[0]["quantity"] == 0
        assert client.get("/orders/999").status_code == 404
