"""Таблицы базы данных (SQLAlchemy ORM).

Справочники:      users, warehouses, skus
Остатки:          stocks (склад x SKU, с полем version для оптимистической блокировки)
Транзакционные:   orders, order_items, reservations
Журналы событий:  stock_movements (движение товара), order_status_history (смена статусов)
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


# ---------- Справочники ----------

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(150))


class Warehouse(Base):
    __tablename__ = "warehouses"
    __table_args__ = (CheckConstraint("type IN ('FBO', 'FBS')", name="ck_warehouse_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(3))


class Sku(Base):
    __tablename__ = "skus"

    id: Mapped[int] = mapped_column(primary_key=True)
    article: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))


# ---------- Остатки ----------

class Stock(Base):
    """Остаток одного SKU на одном складе.

    quantity - сколько штук физически лежит на складе;
    reserved - сколько из них уже зарезервировано под неоплаченные заказы;
    доступно к продаже = quantity - reserved.
    version  - номер версии строки, растёт при каждом изменении
               (нужен для оптимистической блокировки).
    """

    __tablename__ = "stocks"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_stock_quantity"),
        CheckConstraint("reserved >= 0", name="ck_stock_reserved"),
        CheckConstraint("reserved <= quantity", name="ck_stock_reserved_le_quantity"),
    )

    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), primary_key=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id"), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    reserved: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)


# ---------- Заказы ----------

ORDER_STATUSES = ("reserved", "paid", "assembling", "shipped", "delivered", "cancelled", "expired")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(f"status IN {ORDER_STATUSES}", name="ck_order_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), index=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reserve_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list["OrderItem"]] = relationship(back_populates="order")
    reservations: Mapped[list["Reservation"]] = relationship(back_populates="order")
    history: Mapped[list["OrderStatusHistory"]] = relationship(
        back_populates="order", order_by="OrderStatusHistory.id"
    )


class OrderItem(Base):
    """Позиция заказа: что и по какой цене купили (цена фиксируется на момент заказа)."""

    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_item_quantity"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id"))
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    order: Mapped[Order] = relationship(back_populates="items")


class Reservation(Base):
    """Резерв товара на складе под заказ.

    active   - товар отложен и ждёт оплаты;
    consumed - заказ оплачен, товар списан со склада;
    released - резерв снят (отмена или истёк срок оплаты), товар снова доступен.
    """

    __tablename__ = "reservations"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'consumed', 'released')", name="ck_reservation_status"),
        CheckConstraint("quantity > 0", name="ck_reservation_quantity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"))
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10), default="active")

    order: Mapped[Order] = relationship(back_populates="reservations")


# ---------- Журналы событий ("Event Sourcing на минималках") ----------

class StockMovement(Base):
    """Каждое изменение остатка записывается отдельной строкой.

    income    - приход товара на склад      (quantity +)
    reserve   - резерв под заказ            (reserved +)
    unreserve - снятие резерва              (reserved -)
    outcome   - списание после оплаты       (quantity -, reserved -)
    """

    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint(
            "type IN ('income', 'reserve', 'unreserve', 'outcome')", name="ck_movement_type"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"))
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id"))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    type: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    old_status: Mapped[str | None] = mapped_column(String(20))
    new_status: Mapped[str] = mapped_column(String(20))
    comment: Mapped[str | None] = mapped_column(String(255))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    order: Mapped[Order] = relationship(back_populates="history")
