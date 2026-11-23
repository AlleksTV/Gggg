"""REST API (FastAPI). Swagger открывается по адресу http://127.0.0.1:8000/docs"""
import asyncio
import os
from contextlib import asynccontextmanager
from enum import Enum

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from . import services
from .db import SessionLocal
from .models import Order, Stock, StockMovement
from .seed import reset_database
from .services import CartItem, ServiceError

CLEANER_INTERVAL_SECONDS = int(os.getenv("CLEANER_INTERVAL_SECONDS", "10"))


async def reservation_cleaner():
    """Фоновая задача: раз в N секунд снимает просроченные резервы."""
    while True:
        try:
            expired = await run_in_threadpool(services.expire_overdue_reservations)
            if expired:
                print(f"[cleaner] Сняты резервы с заказов: {expired}")
        except Exception as exc:  # фоновая задача не должна падать навсегда
            print(f"[cleaner] Ошибка: {exc}")
        await asyncio.sleep(CLEANER_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(reservation_cleaner())
    yield
    task.cancel()


app = FastAPI(
    title="Маркетплейс: заказы и складские остатки",
    description="Тема 2. ACID-транзакции, пессимистическая и оптимистическая блокировки, "
                "автоматическое снятие неоплаченного резерва.",
    lifespan=lifespan,
)


# ---------- Схемы запросов ----------

class LockMode(str, Enum):
    pessimistic = "pessimistic"
    optimistic = "optimistic"
    unsafe = "unsafe"


class CartItemIn(BaseModel):
    sku_id: int = Field(examples=[1])
    quantity: int = Field(gt=0, examples=[2])


class CreateOrderIn(BaseModel):
    user_id: int = Field(examples=[1])
    items: list[CartItemIn]
    lock_mode: LockMode = LockMode.pessimistic
    reserve_seconds: int = Field(default=services.RESERVE_TTL_SECONDS, gt=0,
                                 description="Сколько секунд даётся на оплату")


class StatusIn(BaseModel):
    status: str = Field(examples=["assembling"])


class IncomeIn(BaseModel):
    warehouse_id: int = Field(examples=[1])
    sku_id: int = Field(examples=[3])
    quantity: int = Field(gt=0, examples=[5])


async def call(fn, *args):
    """Запускает функцию сервиса в отдельном потоке и превращает ошибки в HTTP-ответы."""
    try:
        return await run_in_threadpool(fn, *args)
    except ServiceError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc))


# ---------- Заказы ----------

CREATE_FUNCS = {
    LockMode.pessimistic: services.create_order_pessimistic,
    LockMode.optimistic: services.create_order_optimistic,
    LockMode.unsafe: services.create_order_unsafe,
}


@app.post("/orders", tags=["Заказы"], summary="Оформить заказ (резерв товара)")
async def create_order(body: CreateOrderIn):
    items = [CartItem(i.sku_id, i.quantity) for i in body.items]
    order_id = await call(CREATE_FUNCS[body.lock_mode], body.user_id, items, body.reserve_seconds)
    return await get_order(order_id)


@app.get("/orders/{order_id}", tags=["Заказы"], summary="Заказ с позициями и историей статусов")
async def get_order(order_id: int):
    def load():
        with SessionLocal() as session:
            order = session.scalars(
                select(Order).where(Order.id == order_id).options(
                    selectinload(Order.items), selectinload(Order.history),
                    selectinload(Order.reservations))
            ).one_or_none()
            if order is None:
                raise services.NotFound(f"Заказ {order_id} не найден")
            return {
                "id": order.id,
                "user_id": order.user_id,
                "status": order.status,
                "total_amount": str(order.total_amount),
                "created_at": order.created_at,
                "reserve_expires_at": order.reserve_expires_at,
                "paid_at": order.paid_at,
                "items": [{"sku_id": i.sku_id, "warehouse_id": i.warehouse_id,
                           "quantity": i.quantity, "price": str(i.price)} for i in order.items],
                "reservations": [{"sku_id": r.sku_id, "warehouse_id": r.warehouse_id,
                                  "quantity": r.quantity, "status": r.status}
                                 for r in order.reservations],
                "history": [{"from": h.old_status, "to": h.new_status, "comment": h.comment,
                             "at": h.changed_at} for h in order.history],
            }
    return await call(load)


@app.post("/orders/{order_id}/pay", tags=["Заказы"], summary="Оплатить (списать товар со склада)")
async def pay(order_id: int):
    await call(services.pay_order, order_id)
    return await get_order(order_id)


@app.post("/orders/{order_id}/cancel", tags=["Заказы"], summary="Отменить заказ")
async def cancel(order_id: int):
    await call(services.cancel_order, order_id)
    return await get_order(order_id)


@app.post("/orders/{order_id}/status", tags=["Заказы"],
          summary="Статус доставки: assembling → shipped → delivered")
async def set_status(order_id: int, body: StatusIn):
    await call(services.set_delivery_status, order_id, body.status)
    return await get_order(order_id)


# ---------- Склад ----------

@app.get("/stocks", tags=["Склад"], summary="Остатки по складам")
async def list_stocks(sku_id: int | None = None):
    def load():
        with SessionLocal() as session:
            q = select(Stock).order_by(Stock.sku_id, Stock.warehouse_id)
            if sku_id is not None:
                q = q.where(Stock.sku_id == sku_id)
            return [{"sku_id": s.sku_id, "warehouse_id": s.warehouse_id, "quantity": s.quantity,
                     "reserved": s.reserved, "available": s.quantity - s.reserved,
                     "version": s.version} for s in session.scalars(q)]
    return await call(load)


@app.get("/stocks/movements", tags=["Склад"], summary="Журнал движения товаров")
async def list_movements(sku_id: int | None = None, limit: int = 50):
    def load():
        with SessionLocal() as session:
            q = select(StockMovement).order_by(StockMovement.id.desc()).limit(limit)
            if sku_id is not None:
                q = q.where(StockMovement.sku_id == sku_id)
            return [{"id": m.id, "type": m.type, "sku_id": m.sku_id,
                     "warehouse_id": m.warehouse_id, "quantity": m.quantity,
                     "order_id": m.order_id, "at": m.created_at} for m in session.scalars(q)]
    return await call(load)


@app.post("/stocks/income", tags=["Склад"], summary="Приход товара на склад")
async def income(body: IncomeIn):
    await call(services.add_income, body.warehouse_id, body.sku_id, body.quantity)
    return await list_stocks(body.sku_id)


# ---------- Служебное ----------

@app.post("/admin/expire-reservations", tags=["Служебное"],
          summary="Снять просроченные резервы прямо сейчас (не дожидаясь фоновой задачи)")
async def expire_now():
    return {"expired_orders": await call(services.expire_overdue_reservations)}


@app.post("/admin/reset", tags=["Служебное"], summary="Пересоздать БД с демо-данными")
async def reset():
    await call(reset_database)
    return {"ok": True}
