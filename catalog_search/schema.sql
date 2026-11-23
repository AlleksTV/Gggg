-- Схема БД (SQLite). Сгенерирована из приложения: таблицы, индексы, FTS5 и триггеры.

CREATE TABLE categories (
	id INTEGER NOT NULL, 
	parent_id INTEGER, 
	name VARCHAR(100) NOT NULL, 
	path VARCHAR(255) NOT NULL, 
	level INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(parent_id) REFERENCES categories (id)
);

CREATE TABLE brands (
	id INTEGER NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE TABLE attributes (
	id INTEGER NOT NULL, 
	code VARCHAR(50) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	data_type VARCHAR(10) NOT NULL, 
	unit VARCHAR(20), 
	is_filterable BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_attr_type CHECK (data_type IN ('text', 'number')), 
	UNIQUE (code)
);

CREATE TABLE products (
	id INTEGER NOT NULL, 
	category_id INTEGER NOT NULL, 
	brand_id INTEGER, 
	name VARCHAR(255) NOT NULL, 
	description TEXT NOT NULL, 
	extra JSON NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(category_id) REFERENCES categories (id), 
	FOREIGN KEY(brand_id) REFERENCES brands (id)
);

CREATE TABLE category_attributes (
	category_id INTEGER NOT NULL, 
	attribute_id INTEGER NOT NULL, 
	PRIMARY KEY (category_id, attribute_id), 
	FOREIGN KEY(category_id) REFERENCES categories (id), 
	FOREIGN KEY(attribute_id) REFERENCES attributes (id)
);

CREATE TABLE skus (
	id INTEGER NOT NULL, 
	product_id INTEGER NOT NULL, 
	article VARCHAR(50) NOT NULL, 
	price NUMERIC(12, 2) NOT NULL, 
	stock INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_sku_price CHECK (price >= 0), 
	CONSTRAINT ck_sku_stock CHECK (stock >= 0), 
	FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE, 
	UNIQUE (article)
);

CREATE TABLE sku_attribute_values (
	sku_id INTEGER NOT NULL, 
	attribute_id INTEGER NOT NULL, 
	value_text VARCHAR(100) NOT NULL, 
	value_num NUMERIC, 
	PRIMARY KEY (sku_id, attribute_id), 
	FOREIGN KEY(sku_id) REFERENCES skus (id) ON DELETE CASCADE, 
	FOREIGN KEY(attribute_id) REFERENCES attributes (id)
);

CREATE VIRTUAL TABLE product_fts USING fts5(
        name, description, brand, category, attrs,
        tokenize = 'unicode61 remove_diacritics 2'
    );

CREATE INDEX ix_categories_path ON categories (path);

CREATE INDEX ix_categories_parent_id ON categories (parent_id);

CREATE INDEX ix_products_category_id ON products (category_id);

CREATE INDEX ix_products_brand_id ON products (brand_id);

CREATE INDEX ix_skus_product_id ON skus (product_id);

CREATE INDEX ix_skus_price ON skus (price);

CREATE INDEX ix_value_attr_text ON sku_attribute_values (attribute_id, value_text);

CREATE INDEX ix_value_attr_num ON sku_attribute_values (attribute_id, value_num);

CREATE TRIGGER products_fts_insert AFTER INSERT ON products BEGIN
        
        DELETE FROM product_fts WHERE rowid = new.id;
        INSERT INTO product_fts(rowid, name, description, brand, category, attrs)
        SELECT p.id, replace(replace(p.name, 'ё', 'е'), 'Ё', 'Е'), replace(replace(p.description, 'ё', 'е'), 'Ё', 'Е'), replace(replace(b.name, 'ё', 'е'), 'Ё', 'Е'), replace(replace(c.name, 'ё', 'е'), 'Ё', 'Е'),
               replace(replace((SELECT group_concat(DISTINCT v.value_text)
                FROM skus s JOIN sku_attribute_values v ON v.sku_id = s.id
                WHERE s.product_id = p.id), 'ё', 'е'), 'Ё', 'Е')
        FROM products p
        JOIN categories c ON c.id = p.category_id
        LEFT JOIN brands b ON b.id = p.brand_id
        WHERE p.id = new.id;
    
    END;

CREATE TRIGGER products_fts_update AFTER UPDATE ON products BEGIN
        DELETE FROM product_fts WHERE rowid = old.id;
        
        DELETE FROM product_fts WHERE rowid = new.id;
        INSERT INTO product_fts(rowid, name, description, brand, category, attrs)
        SELECT p.id, replace(replace(p.name, 'ё', 'е'), 'Ё', 'Е'), replace(replace(p.description, 'ё', 'е'), 'Ё', 'Е'), replace(replace(b.name, 'ё', 'е'), 'Ё', 'Е'), replace(replace(c.name, 'ё', 'е'), 'Ё', 'Е'),
               replace(replace((SELECT group_concat(DISTINCT v.value_text)
                FROM skus s JOIN sku_attribute_values v ON v.sku_id = s.id
                WHERE s.product_id = p.id), 'ё', 'е'), 'Ё', 'Е')
        FROM products p
        JOIN categories c ON c.id = p.category_id
        LEFT JOIN brands b ON b.id = p.brand_id
        WHERE p.id = new.id;
    
    END;

CREATE TRIGGER products_fts_delete AFTER DELETE ON products BEGIN
        DELETE FROM product_fts WHERE rowid = old.id;
    END;

CREATE TRIGGER values_fts_insert AFTER INSERT ON sku_attribute_values BEGIN
        
        DELETE FROM product_fts WHERE rowid = (SELECT product_id FROM skus WHERE id = new.sku_id);
        INSERT INTO product_fts(rowid, name, description, brand, category, attrs)
        SELECT p.id, replace(replace(p.name, 'ё', 'е'), 'Ё', 'Е'), replace(replace(p.description, 'ё', 'е'), 'Ё', 'Е'), replace(replace(b.name, 'ё', 'е'), 'Ё', 'Е'), replace(replace(c.name, 'ё', 'е'), 'Ё', 'Е'),
               replace(replace((SELECT group_concat(DISTINCT v.value_text)
                FROM skus s JOIN sku_attribute_values v ON v.sku_id = s.id
                WHERE s.product_id = p.id), 'ё', 'е'), 'Ё', 'Е')
        FROM products p
        JOIN categories c ON c.id = p.category_id
        LEFT JOIN brands b ON b.id = p.brand_id
        WHERE p.id = (SELECT product_id FROM skus WHERE id = new.sku_id);
    
    END;

CREATE TRIGGER values_fts_update AFTER UPDATE ON sku_attribute_values BEGIN
        
        DELETE FROM product_fts WHERE rowid = (SELECT product_id FROM skus WHERE id = old.sku_id);
        INSERT INTO product_fts(rowid, name, description, brand, category, attrs)
        SELECT p.id, replace(replace(p.name, 'ё', 'е'), 'Ё', 'Е'), replace(replace(p.description, 'ё', 'е'), 'Ё', 'Е'), replace(replace(b.name, 'ё', 'е'), 'Ё', 'Е'), replace(replace(c.name, 'ё', 'е'), 'Ё', 'Е'),
               replace(replace((SELECT group_concat(DISTINCT v.value_text)
                FROM skus s JOIN sku_attribute_values v ON v.sku_id = s.id
                WHERE s.product_id = p.id), 'ё', 'е'), 'Ё', 'Е')
        FROM products p
        JOIN categories c ON c.id = p.category_id
        LEFT JOIN brands b ON b.id = p.brand_id
        WHERE p.id = (SELECT product_id FROM skus WHERE id = old.sku_id);
    
        
        DELETE FROM product_fts WHERE rowid = (SELECT product_id FROM skus WHERE id = new.sku_id);
        INSERT INTO product_fts(rowid, name, description, brand, category, attrs)
        SELECT p.id, replace(replace(p.name, 'ё', 'е'), 'Ё', 'Е'), replace(replace(p.description, 'ё', 'е'), 'Ё', 'Е'), replace(replace(b.name, 'ё', 'е'), 'Ё', 'Е'), replace(replace(c.name, 'ё', 'е'), 'Ё', 'Е'),
               replace(replace((SELECT group_concat(DISTINCT v.value_text)
                FROM skus s JOIN sku_attribute_values v ON v.sku_id = s.id
                WHERE s.product_id = p.id), 'ё', 'е'), 'Ё', 'Е')
        FROM products p
        JOIN categories c ON c.id = p.category_id
        LEFT JOIN brands b ON b.id = p.brand_id
        WHERE p.id = (SELECT product_id FROM skus WHERE id = new.sku_id);
    
    END;

CREATE TRIGGER values_fts_delete AFTER DELETE ON sku_attribute_values BEGIN
        
        DELETE FROM product_fts WHERE rowid = (SELECT product_id FROM skus WHERE id = old.sku_id);
        INSERT INTO product_fts(rowid, name, description, brand, category, attrs)
        SELECT p.id, replace(replace(p.name, 'ё', 'е'), 'Ё', 'Е'), replace(replace(p.description, 'ё', 'е'), 'Ё', 'Е'), replace(replace(b.name, 'ё', 'е'), 'Ё', 'Е'), replace(replace(c.name, 'ё', 'е'), 'Ё', 'Е'),
               replace(replace((SELECT group_concat(DISTINCT v.value_text)
                FROM skus s JOIN sku_attribute_values v ON v.sku_id = s.id
                WHERE s.product_id = p.id), 'ё', 'е'), 'Ё', 'Е')
        FROM products p
        JOIN categories c ON c.id = p.category_id
        LEFT JOIN brands b ON b.id = p.brand_id
        WHERE p.id = (SELECT product_id FROM skus WHERE id = old.sku_id);
    
    END;

