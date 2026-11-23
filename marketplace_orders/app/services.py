"""Бизнес-логика: оформление, оплата, отмена заказа и снятие просроченных резервов.

Главная идея: каждая операция - ОДНА транзакция (`with session.begin()`).
Если на любом шаге ошибка, PostgreSQL откатывает всё целиком:
не бывает ситуации "заказ создан, а товар не зарезервирован" или наоборот.
"""
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import (
    Order,
    OrderItem,
    OrderStatusHistory,
    Reservation,
    Sku,
    Stock,
    StockMovement,
    User,
    Warehouse,
)

RESERVE_TTL_SECONDS = 15 * 60          # сколько минут даётся на оплату
OPTIMISTIC_MAX_ATTEMPTS = 10           # сколько раз повторять при конфликте версий

# Какие переходы статусов разрешены (машина состояний заказа)
ALLOWED_TRANSITIONS = {
    "reserved": {"paid", "cancelled", "expired"},
    "paid": {"assembling", "cancelled"},
    "assembling": {"shipped"},
    "shipped": {"delivered"},
    "delivered": set(),
    "cancelled": set(),
    "expired": set(),
}


# ---------- Ошибки ----------

class ServiceError(Exception):
    http_status = 400


class NotFound(ServiceError):
    http_status = 404


class OutOfStock(ServiceError):
    http_status = 409


class InvalidStatus(ServiceError):
    http_status = 409


class OptimisticLockConflict(ServiceError):
    """Строку остатка успел изменить кто-то другой (version не совпал)."""
    http_status = 409


@dataclass
class CartItem:
    sku_id: int
    quantity: int


# ---------- Вспомогательные функции ----------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _merge_items(items: list[CartItem]) -> list[CartItem]:
    """Склеивает одинаковые SKU и сортирует по sku_id.

    Сортировка важна: все транзакции блокируют строки в ОДНОМ порядке,
    поэтому две транзакции не могут ждать друг друга по кругу (нет deadlock).
    """
    merged: dict[int, int] = {}
    for it in items:
        if it.quantity <= 0:
            raise ServiceError("Количество должно быть больше нуля")
        merged[it.sku_id] = merged.get(it.sku_id, 0) + it.quantity
    if not merged:
        raise ServiceError("Корзина пуста")
    return [CartItem(sku, qty) for sku, qty in sorted(merged.items())]


def _pick_warehouse(stocks: list[Stock], qty: int) -> Stock | None:
    """Выбирает склад, где хватает товара целиком (заказ по SKU не дробим).
    Из подходящих берём тот, где доступно больше всего."""
    suitable = [s for s in stocks if s.quantity - s.reserved >= qty]
    if not suitable:
        return None
    return max(suitable, key=lambda s: (s.quantity - s.reserved, -s.warehouse_id))


def _change_status(session: Session, order: Order, new_status: str, comment: str | None = None):
    if new_status not in ALLOWED_TRANSITIONS[order.status]:
        raise InvalidStatus(f"Нельзя перевести заказ из '{order.status}' в '{new_status}'")
    session.add(OrderStatusHistory(
        order_id=order.id, old_status=order.status, new_status=new_status, comment=comment
    ))
    order.status = new_status


def _create_order_rows(session: Session, user_id: int, picked: list[tuple[CartItem, Stock]],
                       prices: dict[int, Decimal], reserve_seconds: int) -> Order:
    """Создаёт заказ, позиции, резервы и записи журналов (внутри текущей транзакции)."""
    total = sum(prices[item.sku_id] * item.quantity for item, _ in picked)
    order = Order(
        user_id=user_id,
        status="reserved",
        total_amount=total,
        reserve_expires_at=_now() + timedelta(seconds=reserve_seconds),
    )
    session.add(order)
    session.flush()  # получаем order.id

    session.add(OrderStatusHistory(order_id=order.id, old_status=None, new_status="reserved",
                                   comment="Заказ создан, товар зарезервирован"))
    for item, stock in picked:
        session.add_all([
            OrderItem(order_id=order.id, sku_id=item.sku_id, warehouse_id=stock.warehouse_id,
                      quantity=item.quantity, price=prices[item.sku_id]),
            Reservation(order_id=order.id, sku_id=item.sku_id, warehouse_id=stock.warehouse_id,
                        quantity=item.quantity, status="active"),
            StockMovement(order_id=order.id, sku_id=item.sku_id, warehouse_id=stock.warehouse_id,
                          type="reserve", quantity=item.quantity),
        ])
    return order


def _load_prices_and_check_user(session: Session, user_id: int, items: list[CartItem]) -> dict[int, Decimal]:
    if session.get(User, user_id) is None:
        raise NotFound(f"Пользователь {user_id} не найден")
    sku_ids = [i.sku_id for i in items]
    prices = dict(session.execute(select(Sku.id, Sku.price).where(Sku.id.in_(sku_ids))).all())
    missing = set(sku_ids) - set(prices)
    if missing:
        raise NotFound(f"SKU не найдены: {sorted(missing)}")
    return prices


# ---------- 1. Оформление заказа: ПЕССИМИСТИЧЕСКАЯ блокировка ----------

def create_order_pessimistic(user_id: int, items: list[CartItem],
                             reserve_seconds: int = RESERVE_TTL_SECONDS) -> int:
    """SELECT ... FOR UPDATE: блокируем строки остатков ДО проверки.

    Второй покупатель, который пришёл за тем же товаром, просто ждёт на SELECT,
    пока первая транзакция не закончится. Потом он видит уже обновлённый остаток.
    """
    items = _merge_items(items)
    with SessionLocal() as session, session.begin():
        prices = _load_prices_and_check_user(session, user_id, items)
        picked = []
        for item in items:
            stocks = session.scalars(
                select(Stock)
                .where(Stock.sku_id == item.sku_id)
                .order_by(Stock.warehouse_id)
                .with_for_update()                      # <-- SELECT ... FOR UPDATE
            ).all()
            stock = _pick_warehouse(stocks, item.quantity)
            if stock is None:
                raise OutOfStock(f"Недостаточно товара SKU {item.sku_id}")
            stock.reserved += item.quantity
            stock.version += 1
            picked.append((item, stock))
        order = _create_order_rows(session, user_id, picked, prices, reserve_seconds)
        return order.id


# ---------- 2. Оформление заказа: ОПТИМИСТИЧЕСКАЯ блокировка ----------

def _try_create_order_optimistic(user_id: int, items: list[CartItem], reserve_seconds: int) -> int:
    with SessionLocal() as session, session.begin():
        prices = _load_prices_and_check_user(session, user_id, items)
        picked = []
        for item in items:
            # Читаем БЕЗ блокировки и запоминаем version
            stocks = session.scalars(
                select(Stock).where(Stock.sku_id == item.sku_id).order_by(Stock.warehouse_id)
            ).all()
            stock = _pick_warehouse(stocks, item.quantity)
            if stock is None:
                raise OutOfStock(f"Недостаточно товара SKU {item.sku_id}")

            # Обновляем, только если version не изменилась с момента чтения
            result = session.execute(
                update(Stock)
                .where(Stock.warehouse_id == stock.warehouse_id,
                       Stock.sku_id == stock.sku_id,
                       Stock.version == stock.version)           # <-- проверка версии
                .values(reserved=Stock.reserved + item.quantity,
                        version=Stock.version + 1)
                .execution_options(synchronize_session=False)
            )
            if result.rowcount == 0:
                # Кто-то успел изменить строку раньше нас -> откатываем всю транзакцию
                raise OptimisticLockConflict("Остаток изменился, повторите попытку")
            picked.append((item, stock))
        order = _create_order_rows(session, user_id, picked, prices, reserve_seconds)
        return order.id


def create_order_optimistic(user_id: int, items: list[CartItem],
                            reserve_seconds: int = RESERVE_TTL_SECONDS) -> int:
    """Оптимистическая блокировка: ничего не блокируем, а при конфликте повторяем.

    Подходит, когда конфликты редкие. При конфликте вся транзакция откатывается
    и выполняется заново с уже свежими данными.
    """
    items = _merge_items(items)
    for attempt in range(1, OPTIMISTIC_MAX_ATTEMPTS + 1):
        try:
            return _try_create_order_optimistic(user_id, items, reserve_seconds)
        except OptimisticLockConflict:
            if attempt == OPTIMISTIC_MAX_ATTEMPTS:
                raise
            time.sleep(random.uniform(0.005, 0.03) * attempt)  # небольшая пауза перед повтором
    raise OptimisticLockConflict("Не удалось оформить заказ")


# ---------- 3. НЕПРАВИЛЬНЫЙ вариант (только для демонстрации гонки) ----------

def create_order_unsafe(user_id: int, items: list[CartItem],
                        reserve_seconds: int = RESERVE_TTL_SECONDS) -> int:
    """Без блокировок: прочитали остаток, проверили в Python, записали новое значение.

    Если два покупателя прочитали остаток одновременно, оба увидят "есть 1 шт."
    и оба оформят заказ -> товар продан дважды (Race Condition).
    НЕ ИСПОЛЬЗОВАТЬ в реальном коде, функция нужна, чтобы показать проблему.
    """
    items = _merge_items(items)
    with SessionLocal() as session, session.begin():
        prices = _load_prices_and_check_user(session, user_id, items)
        picked = []
        for item in items:
            stocks = session.scalars(select(Stock).where(Stock.sku_id == item.sku_id)).all()
            stock = _pick_warehouse(stocks, item.quantity)
            if stock is None:
                raise OutOfStock(f"Недостаточно товара SKU {item.sku_id}")
            new_reserved = stock.reserved + item.quantity
            time.sleep(0.05)  # "задумались" - окно, в которое влезает второй покупатель
            session.execute(
                update(Stock)
                .where(Stock.warehouse_id == stock.warehouse_id, Stock.sku_id == stock.sku_id)
                .values(reserved=new_reserved)
                .execution_options(synchronize_session=False)
            )
            picked.append((item, stock))
        order = _create_order_rows(session, user_id, picked, prices, reserve_seconds)
        return order.id


# ---------- Снятие резерва (общая часть для отмены и таймаута) ----------

def _release_reservations(session: Session, order: Order):
    active = [r for r in order.reservations if r.status == "active"]
    for r in sorted(active, key=lambda r: (r.sku_id, r.warehouse_id)):
        stock = session.scalars(
            select(Stock)
            .where(Stock.warehouse_id == r.warehouse_id, Stock.sku_id == r.sku_id)
            .with_for_update()
        ).one()
        stock.reserved -= r.quantity
        stock.version += 1
        r.status = "released"
        session.add(StockMovement(order_id=order.id, sku_id=r.sku_id, warehouse_id=r.warehouse_id,
                                  type="unreserve", quantity=r.quantity))


def _lock_order(session: Session, order_id: int) -> Order:
    order = session.scalars(
        select(Order).where(Order.id == order_id).with_for_update()
    ).one_or_none()
    if order is None:
        raise NotFound(f"Заказ {order_id} не найден")
    return order


# ---------- 4. Оплата ----------

def pay_order(order_id: int) -> None:
    """Оплата: резерв превращается в реальное списание со склада."""
    expired = False
    with SessionLocal() as session, session.begin():
        order = _lock_order(session, order_id)
        if order.status == "reserved" and order.reserve_expires_at <= _now():
            # Опоздали с оплатой: снимаем резерв (это сохранится), а потом сообщаем об ошибке
            _release_reservations(session, order)
            _change_status(session, order, "expired", "Срок оплаты истёк")
            expired = True
        else:
            _consume_reservations(session, order)
    if expired:
        raise InvalidStatus("Срок оплаты заказа истёк, резерв снят")


def _consume_reservations(session: Session, order: Order):
    """Списывает зарезервированный товар со склада и переводит заказ в paid."""
    if order.status != "reserved":
        raise InvalidStatus(f"Заказ в статусе '{order.status}', оплатить нельзя")

    for r in sorted(order.reservations, key=lambda r: (r.sku_id, r.warehouse_id)):
        if r.status != "active":
            continue
        stock = session.scalars(
            select(Stock)
            .where(Stock.warehouse_id == r.warehouse_id, Stock.sku_id == r.sku_id)
            .with_for_update()
        ).one()
        stock.quantity -= r.quantity
        stock.reserved -= r.quantity
        stock.version += 1
        r.status = "consumed"
        session.add(StockMovement(order_id=order.id, sku_id=r.sku_id,
                                  warehouse_id=r.warehouse_id, type="outcome",
                                  quantity=r.quantity))
    order.paid_at = _now()
    _change_status(session, order, "paid", "Оплата получена")


# ---------- 5. Отмена ----------

def cancel_order(order_id: int) -> None:
    with SessionLocal() as session, session.begin():
        order = _lock_order(session, order_id)
        if order.status == "paid":
            # Товар уже списан: возвращаем его на склад как приход
            for r in order.reservations:
                if r.status == "consumed":
                    stock = session.scalars(
                        select(Stock)
                        .where(Stock.warehouse_id == r.warehouse_id, Stock.sku_id == r.sku_id)
                        .with_for_update()
                    ).one()
                    stock.quantity += r.quantity
                    stock.version += 1
                    session.add(StockMovement(order_id=order.id, sku_id=r.sku_id,
                                              warehouse_id=r.warehouse_id, type="income",
                                              quantity=r.quantity))
        else:
            _release_reservations(session, order)
        _change_status(session, order, "cancelled", "Отменён покупателем")


# ---------- 6. Смена статуса доставки ----------

def set_delivery_status(order_id: int, new_status: str) -> None:
    if new_status not in ("assembling", "shipped", "delivered"):
        raise ServiceError("Здесь можно ставить только assembling, shipped или delivered")
    with SessionLocal() as session, session.begin():
        order = _lock_order(session, order_id)
        _change_status(session, order, new_status)


# ---------- 7. Автоматическое снятие неоплаченного резерва по таймауту ----------

def expire_overdue_reservations(batch_size: int = 100) -> list[int]:
    """Находит заказы, у которых истёк срок оплаты, и снимает их резервы.

    FOR UPDATE SKIP LOCKED: если заказ сейчас оплачивается (строка заблокирована),
    мы его пропускаем, а не ждём. Так можно запускать несколько копий фоновой задачи
    одновременно, и они не будут мешать друг другу и покупателям.
    """
    with SessionLocal() as session, session.begin():
        orders = session.scalars(
            select(Order)
            .where(Order.status == "reserved", Order.reserve_expires_at <= _now())
            .order_by(Order.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        ).all()
        for order in orders:
            _release_reservations(session, order)
            _change_status(session, order, "expired", "Не оплачен вовремя, резерв снят")
        return [o.id for o in orders]


# ---------- 8. Приход товара на склад ----------

def add_income(warehouse_id: int, sku_id: int, quantity: int) -> None:
    if quantity <= 0:
        raise ServiceError("Количество должно быть больше нуля")
    with SessionLocal() as session, session.begin():
        if session.get(Warehouse, warehouse_id) is None:
            raise NotFound(f"Склад {warehouse_id} не найден")
        if session.get(Sku, sku_id) is None:
            raise NotFound(f"SKU {sku_id} не найден")
        stock = session.scalars(
            select(Stock)
            .where(Stock.warehouse_id == warehouse_id, Stock.sku_id == sku_id)
            .with_for_update()
        ).one_or_none()
        if stock is None:
            stock = Stock(warehouse_id=warehouse_id, sku_id=sku_id, quantity=0, reserved=0, version=1)
            session.add(stock)
        stock.quantity += quantity
        stock.version += 1
        session.add(StockMovement(warehouse_id=warehouse_id, sku_id=sku_id,
                                  type="income", quantity=quantity))
