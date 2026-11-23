"""Таблицы каталога.

Дерево категорий:  categories (Adjacency List: parent_id + Materialized Path: path)
Товары:            products (SPU - общая карточка), skus (конкретный вариант: размер / цвет)
Характеристики:    гибридный подход
                   - EAV (attributes + sku_attribute_values) - то, по чему фильтруют
                   - JSON (products.extra) - описательные свойства, по которым не фильтруют
Поиск:             product_fts - полнотекстовый индекс FTS5 (создаётся в search_index.py)
"""
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Category(Base):
    """Категория. parent_id ссылается на эту же таблицу -> дерево любой глубины.

    path  - "материализованный путь" от корня, например "1/2/3/".
            Позволяет найти все подкатегории одним запросом: path LIKE '1/2/%'.
    level - глубина (0 - корневая категория).
    """

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    path: Mapped[str] = mapped_column(String(255), index=True)
    level: Mapped[int] = mapped_column(Integer, default=0)


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


class Product(Base):
    """SPU - общая карточка товара (например, "Кроссовки Nike Air Max 90")."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    extra: Mapped[dict] = mapped_column(JSON, default=dict)  # JSON-часть гибридного подхода

    skus: Mapped[list["Sku"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    brand: Mapped[Brand | None] = relationship()
    category: Mapped[Category] = relationship()


class Sku(Base):
    """SKU - конкретный вариант товара (размер 42, белый), со своей ценой и остатком."""

    __tablename__ = "skus"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_sku_price"),
        CheckConstraint("stock >= 0", name="ck_sku_stock"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    article: Mapped[str] = mapped_column(String(50), unique=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), index=True)
    stock: Mapped[int] = mapped_column(Integer, default=0)

    product: Mapped[Product] = relationship(back_populates="skus")
    values: Mapped[list["SkuAttributeValue"]] = relationship(cascade="all, delete-orphan")


class Attribute(Base):
    """EAV: Attribute - справочник характеристик ("ОЗУ", "Размер", "Цвет")."""

    __tablename__ = "attributes"
    __table_args__ = (CheckConstraint("data_type IN ('text', 'number')", name="ck_attr_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)   # для URL: ram, color
    name: Mapped[str] = mapped_column(String(100))                # для людей: "ОЗУ"
    data_type: Mapped[str] = mapped_column(String(10))
    unit: Mapped[str | None] = mapped_column(String(20))
    is_filterable: Mapped[bool] = mapped_column(Boolean, default=True)


class CategoryAttribute(Base):
    """Какие характеристики есть у категории (M:N). Наследуются подкатегориями."""

    __tablename__ = "category_attributes"

    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), primary_key=True)
    attribute_id: Mapped[int] = mapped_column(ForeignKey("attributes.id"), primary_key=True)


class SkuAttributeValue(Base):
    """EAV: Value - значение характеристики у конкретного SKU.

    value_text - значение строкой (всегда заполнено, по нему строятся фильтры);
    value_num  - то же значение числом (для чисел: сортировка 8 < 16 < 32, диапазоны).
    """

    __tablename__ = "sku_attribute_values"
    __table_args__ = (
        Index("ix_value_attr_text", "attribute_id", "value_text"),
        Index("ix_value_attr_num", "attribute_id", "value_num"),
    )

    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id", ondelete="CASCADE"), primary_key=True)
    attribute_id: Mapped[int] = mapped_column(ForeignKey("attributes.id"), primary_key=True)
    value_text: Mapped[str] = mapped_column(String(100))
    value_num: Mapped[float | None] = mapped_column(Numeric(asdecimal=False))

    attribute: Mapped[Attribute] = relationship()
