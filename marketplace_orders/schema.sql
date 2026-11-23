-- Схема БД (PostgreSQL). Сгенерирована из app/models.py, приложение создаёт таблицы само.


\restrict jtQpOqlIumn9WbFazkdxkGWXXcoq6oDVRD6fGlWEq8H4pCGERia6BiyhKLPLy7X

-- Name: order_items; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.order_items (
    id integer NOT NULL,
    order_id integer NOT NULL,
    sku_id integer NOT NULL,
    warehouse_id integer NOT NULL,
    quantity integer NOT NULL,
    price numeric(12,2) NOT NULL,
    CONSTRAINT ck_item_quantity CHECK ((quantity > 0))
);

-- Name: order_items_id_seq; Type: SEQUENCE; Schema: public; Owner: -

CREATE SEQUENCE public.order_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

-- Name: order_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -

ALTER SEQUENCE public.order_items_id_seq OWNED BY public.order_items.id;

-- Name: order_status_history; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.order_status_history (
    id integer NOT NULL,
    order_id integer NOT NULL,
    old_status character varying(20),
    new_status character varying(20) NOT NULL,
    comment character varying(255),
    changed_at timestamp with time zone DEFAULT now() NOT NULL
);

-- Name: order_status_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -

CREATE SEQUENCE public.order_status_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

-- Name: order_status_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -

ALTER SEQUENCE public.order_status_history_id_seq OWNED BY public.order_status_history.id;

-- Name: orders; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.orders (
    id integer NOT NULL,
    user_id integer NOT NULL,
    status character varying(20) NOT NULL,
    total_amount numeric(12,2) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    reserve_expires_at timestamp with time zone,
    paid_at timestamp with time zone,
    CONSTRAINT ck_order_status CHECK (((status)::text = ANY ((ARRAY['reserved'::character varying, 'paid'::character varying, 'assembling'::character varying, 'shipped'::character varying, 'delivered'::character varying, 'cancelled'::character varying, 'expired'::character varying])::text[])))
);

-- Name: orders_id_seq; Type: SEQUENCE; Schema: public; Owner: -

CREATE SEQUENCE public.orders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

-- Name: orders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -

ALTER SEQUENCE public.orders_id_seq OWNED BY public.orders.id;

-- Name: reservations; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.reservations (
    id integer NOT NULL,
    order_id integer NOT NULL,
    warehouse_id integer NOT NULL,
    sku_id integer NOT NULL,
    quantity integer NOT NULL,
    status character varying(10) NOT NULL,
    CONSTRAINT ck_reservation_quantity CHECK ((quantity > 0)),
    CONSTRAINT ck_reservation_status CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'consumed'::character varying, 'released'::character varying])::text[])))
);

-- Name: reservations_id_seq; Type: SEQUENCE; Schema: public; Owner: -

CREATE SEQUENCE public.reservations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

-- Name: reservations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -

ALTER SEQUENCE public.reservations_id_seq OWNED BY public.reservations.id;

-- Name: skus; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.skus (
    id integer NOT NULL,
    article character varying(50) NOT NULL,
    name character varying(255) NOT NULL,
    price numeric(12,2) NOT NULL
);

-- Name: skus_id_seq; Type: SEQUENCE; Schema: public; Owner: -

CREATE SEQUENCE public.skus_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

-- Name: skus_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -

ALTER SEQUENCE public.skus_id_seq OWNED BY public.skus.id;

-- Name: stock_movements; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.stock_movements (
    id integer NOT NULL,
    warehouse_id integer NOT NULL,
    sku_id integer NOT NULL,
    order_id integer,
    type character varying(10) NOT NULL,
    quantity integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_movement_type CHECK (((type)::text = ANY ((ARRAY['income'::character varying, 'reserve'::character varying, 'unreserve'::character varying, 'outcome'::character varying])::text[])))
);

-- Name: stock_movements_id_seq; Type: SEQUENCE; Schema: public; Owner: -

CREATE SEQUENCE public.stock_movements_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

-- Name: stock_movements_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -

ALTER SEQUENCE public.stock_movements_id_seq OWNED BY public.stock_movements.id;

-- Name: stocks; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.stocks (
    warehouse_id integer NOT NULL,
    sku_id integer NOT NULL,
    quantity integer NOT NULL,
    reserved integer NOT NULL,
    version integer NOT NULL,
    CONSTRAINT ck_stock_quantity CHECK ((quantity >= 0)),
    CONSTRAINT ck_stock_reserved CHECK ((reserved >= 0)),
    CONSTRAINT ck_stock_reserved_le_quantity CHECK ((reserved <= quantity))
);

-- Name: users; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.users (
    id integer NOT NULL,
    full_name character varying(150) NOT NULL
);

-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;

-- Name: warehouses; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.warehouses (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    type character varying(3) NOT NULL,
    CONSTRAINT ck_warehouse_type CHECK (((type)::text = ANY ((ARRAY['FBO'::character varying, 'FBS'::character varying])::text[])))
);

-- Name: warehouses_id_seq; Type: SEQUENCE; Schema: public; Owner: -

CREATE SEQUENCE public.warehouses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

-- Name: warehouses_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -

ALTER SEQUENCE public.warehouses_id_seq OWNED BY public.warehouses.id;

-- Name: order_items id; Type: DEFAULT; Schema: public; Owner: -

ALTER TABLE ONLY public.order_items ALTER COLUMN id SET DEFAULT nextval('public.order_items_id_seq'::regclass);

-- Name: order_status_history id; Type: DEFAULT; Schema: public; Owner: -

ALTER TABLE ONLY public.order_status_history ALTER COLUMN id SET DEFAULT nextval('public.order_status_history_id_seq'::regclass);

-- Name: orders id; Type: DEFAULT; Schema: public; Owner: -

ALTER TABLE ONLY public.orders ALTER COLUMN id SET DEFAULT nextval('public.orders_id_seq'::regclass);

-- Name: reservations id; Type: DEFAULT; Schema: public; Owner: -

ALTER TABLE ONLY public.reservations ALTER COLUMN id SET DEFAULT nextval('public.reservations_id_seq'::regclass);

-- Name: skus id; Type: DEFAULT; Schema: public; Owner: -

ALTER TABLE ONLY public.skus ALTER COLUMN id SET DEFAULT nextval('public.skus_id_seq'::regclass);

-- Name: stock_movements id; Type: DEFAULT; Schema: public; Owner: -

ALTER TABLE ONLY public.stock_movements ALTER COLUMN id SET DEFAULT nextval('public.stock_movements_id_seq'::regclass);

-- Name: users id; Type: DEFAULT; Schema: public; Owner: -

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);

-- Name: warehouses id; Type: DEFAULT; Schema: public; Owner: -

ALTER TABLE ONLY public.warehouses ALTER COLUMN id SET DEFAULT nextval('public.warehouses_id_seq'::regclass);

-- Name: order_items order_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_pkey PRIMARY KEY (id);

-- Name: order_status_history order_status_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.order_status_history
    ADD CONSTRAINT order_status_history_pkey PRIMARY KEY (id);

-- Name: orders orders_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (id);

-- Name: reservations reservations_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.reservations
    ADD CONSTRAINT reservations_pkey PRIMARY KEY (id);

-- Name: skus skus_article_key; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.skus
    ADD CONSTRAINT skus_article_key UNIQUE (article);

-- Name: skus skus_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.skus
    ADD CONSTRAINT skus_pkey PRIMARY KEY (id);

-- Name: stock_movements stock_movements_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.stock_movements
    ADD CONSTRAINT stock_movements_pkey PRIMARY KEY (id);

-- Name: stocks stocks_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.stocks
    ADD CONSTRAINT stocks_pkey PRIMARY KEY (warehouse_id, sku_id);

-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);

-- Name: warehouses warehouses_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.warehouses
    ADD CONSTRAINT warehouses_pkey PRIMARY KEY (id);

-- Name: ix_order_status_history_order_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_order_status_history_order_id ON public.order_status_history USING btree (order_id);

-- Name: ix_orders_reserve_expires_at; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_orders_reserve_expires_at ON public.orders USING btree (reserve_expires_at);

-- Name: ix_orders_status; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_orders_status ON public.orders USING btree (status);

-- Name: ix_reservations_order_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_reservations_order_id ON public.reservations USING btree (order_id);

-- Name: order_items order_items_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id);

-- Name: order_items order_items_sku_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_sku_id_fkey FOREIGN KEY (sku_id) REFERENCES public.skus(id);

-- Name: order_items order_items_warehouse_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_warehouse_id_fkey FOREIGN KEY (warehouse_id) REFERENCES public.warehouses(id);

-- Name: order_status_history order_status_history_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.order_status_history
    ADD CONSTRAINT order_status_history_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id);

-- Name: orders orders_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);

-- Name: reservations reservations_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.reservations
    ADD CONSTRAINT reservations_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id);

-- Name: reservations reservations_sku_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.reservations
    ADD CONSTRAINT reservations_sku_id_fkey FOREIGN KEY (sku_id) REFERENCES public.skus(id);

-- Name: reservations reservations_warehouse_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.reservations
    ADD CONSTRAINT reservations_warehouse_id_fkey FOREIGN KEY (warehouse_id) REFERENCES public.warehouses(id);

-- Name: stock_movements stock_movements_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.stock_movements
    ADD CONSTRAINT stock_movements_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id);

-- Name: stock_movements stock_movements_sku_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.stock_movements
    ADD CONSTRAINT stock_movements_sku_id_fkey FOREIGN KEY (sku_id) REFERENCES public.skus(id);

-- Name: stock_movements stock_movements_warehouse_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.stock_movements
    ADD CONSTRAINT stock_movements_warehouse_id_fkey FOREIGN KEY (warehouse_id) REFERENCES public.warehouses(id);

-- Name: stocks stocks_sku_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.stocks
    ADD CONSTRAINT stocks_sku_id_fkey FOREIGN KEY (sku_id) REFERENCES public.skus(id);

-- Name: stocks stocks_warehouse_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.stocks
    ADD CONSTRAINT stocks_warehouse_id_fkey FOREIGN KEY (warehouse_id) REFERENCES public.warehouses(id);

\unrestrict jtQpOqlIumn9WbFazkdxkGWXXcoq6oDVRD6fGlWEq8H4pCGERia6BiyhKLPLy7X

