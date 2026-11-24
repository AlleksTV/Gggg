"""REST API (FastAPI). Swagger открывается по адресу http://127.0.0.1:8000/docs"""
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from . import catalog
from .db import SessionLocal, engine
from .seed import reset_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    # При первом запуске база пустая - создаём её с демо-данными
    if not inspect(engine).has_table("products"):
        reset_database()
    yield


app = FastAPI(
    title="Маркетплейс: каталог и умный поиск",
    description="Тема 1. Дерево категорий (рекурсивные CTE), SPU/SKU, характеристики "
                "(EAV + JSON), фасетная фильтрация, полнотекстовый поиск с ранжированием. "
                "СУБД: SQLite.",
    lifespan=lifespan,
)


STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def storefront():
    """Неоновая витрина магазина (HTML-страница поверх этого же API)."""
    return FileResponse(STATIC_DIR / "index.html")


async def call(fn, *args, **kwargs):
    try:
        return await run_in_threadpool(fn, *args, **kwargs)
    except catalog.CatalogError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc))
    except IntegrityError as exc:  # например, артикул SKU уже занят
        raise HTTPException(status_code=409, detail=f"Нарушено ограничение БД: {exc.orig}")


# ---------- Категории ----------

@app.get("/categories/tree", tags=["Категории"],
         summary="Всё дерево категорий с количеством товаров (рекурсивный CTE)")
async def tree():
    return await call(catalog.category_tree)


@app.get("/categories/{category_id}/breadcrumbs", tags=["Категории"],
         summary="Путь от корня до категории (рекурсия вверх)")
async def breadcrumbs(category_id: int):
    return await call(catalog.breadcrumbs, category_id)


@app.get("/categories/{category_id}/subcategories", tags=["Категории"],
         summary="ID категории и всех её подкатегорий (рекурсия вниз)")
async def subcategories(category_id: int):
    return await call(catalog.subtree_ids, category_id)


@app.get("/categories/{category_id}/products", tags=["Категории"],
         summary="Товары категории и её подкатегорий")
async def category_products(
    category_id: int,
    include_subcategories: bool = True,
    method: Annotated[str, Query(description="cte - рекурсивный CTE, path - материализованный путь")] = "cte",
):
    return await call(catalog.products_in_category, category_id, include_subcategories, method)


# ---------- Поиск ----------

@app.get("/search", tags=["Поиск"], summary="Поиск + фасетные фильтры")
async def search(
    q: Annotated[str | None, Query(description="Строка поиска, например: белые кроссовки")] = None,
    category_id: Annotated[int | None, Query(description="Искать в категории и всех подкатегориях")] = None,
    brand: Annotated[list[str], Query(description="Бренды (можно несколько)")] = [],
    price_min: float | None = None,
    price_max: float | None = None,
    f: Annotated[list[str], Query(description="Фильтры вида код:значение, например ram:16, color:белый. "
                                              "Можно несколько")] = [],
    in_stock: bool = False,
    sort: Annotated[str, Query(description="relevance, price_asc, price_desc, name")] = "relevance",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    filters: dict[str, list[str]] = {}
    for item in f:
        code, sep, value = item.partition(":")
        if not sep or not code or not value:
            raise HTTPException(400, f"Фильтр '{item}' должен быть в виде код:значение")
        filters.setdefault(code.strip(), []).append(value.strip())
    params = catalog.SearchParams(q=q, category_id=category_id, brands=brand, price_min=price_min,
                                  price_max=price_max, filters=filters, in_stock=in_stock,
                                  sort=sort, limit=limit, offset=offset)
    return await call(catalog.search, params)


# ---------- Товары ----------

@app.get("/products/{product_id}", tags=["Товары"], summary="Карточка товара: SPU + все SKU")
async def product(product_id: int):
    return await call(catalog.get_product, product_id)


class SkuIn(BaseModel):
    article: str = Field(examples=["SNK-NB-574-42"])
    price: float = Field(ge=0, examples=[9990])
    stock: int = Field(default=0, ge=0, examples=[5])
    attributes: dict[str, str | float] = Field(
        default_factory=dict, examples=[{"shoe_size": 42, "color": "серый", "material": "замша"}])


class ProductIn(BaseModel):
    category_id: int = Field(examples=[8])
    name: str = Field(examples=["Кроссовки New Balance 574"])
    brand: str | None = Field(default=None, examples=["New Balance"])
    description: str = Field(default="", examples=["Повседневные кроссовки из замши."])
    extra: dict = Field(default_factory=dict, examples=[{"Сезон": "демисезон"}])
    skus: list[SkuIn]


@app.post("/products", tags=["Товары"],
          summary="Добавить товар (проверяется, что характеристики есть у категории)")
async def create(body: ProductIn):
    def do():
        with SessionLocal() as session, session.begin():
            prod = catalog.create_product(
                session, category_id=body.category_id, name=body.name, brand=body.brand,
                description=body.description, extra=body.extra,
                skus=[s.model_dump() for s in body.skus])
            return prod.id
    product_id = await call(do)
    return await call(catalog.get_product, product_id)


# ---------- Служебное ----------

@app.post("/admin/reset", tags=["Служебное"], summary="Пересоздать БД с демо-данными")
async def reset():
    fts = await call(reset_database)
    return {"ok": True, "search_engine": "fts5" if fts else "like"}
