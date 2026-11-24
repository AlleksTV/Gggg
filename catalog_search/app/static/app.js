// VOLTAZH: витрина каталога. Все данные берутся из того же API, что и в Swagger:
//   GET /categories/tree, GET /categories/{id}/breadcrumbs, GET /search, GET /products/{id}

const LIMIT = 24;
const state = {
  q: "",
  category: null,          // id выбранной категории
  brands: new Set(),
  filters: new Map(),      // код характеристики -> Set выбранных значений
  priceMin: "",
  priceMax: "",
  inStock: false,
  sort: "relevance",
  offset: 0,
};

const $ = (id) => document.getElementById(id);
const money = new Intl.NumberFormat("ru-RU");
let requestNo = 0;         // чтобы старый ответ не перезаписал новый
let bestRelevance = 1;

// ---------- Утилиты ----------

async function api(path, params) {
  const url = params ? `${path}?${params}` : path;
  const res = await fetch(url);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Сервер вернул ошибку");
  return data;
}

function esc(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function plural(n, one, few, many) {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

// ---------- Контурные рисунки товаров (по категории) ----------

const ICONS = {
  pistol: "M12 12 H98 L102 16 V26 H12 Z M64 26 L58 54 H40 L48 26 M48 32 Q46 42 58 40 M20 17 H90",
  shotgun: "M4 20 H112 V28 H70 L66 40 H58 L60 28 H40 L28 48 H14 L22 28 H4 Z M72 28 H98 V35 H72 Z",
  sniper: "M4 26 H100 L114 24 V30 H72 L68 42 H58 L61 30 H42 L32 48 H18 L26 30 H4 Z M46 14 H82 V20 H46 Z M56 20 V26 M72 20 V26",
  knife: "M10 32 H42 V42 H10 Z M42 32 L100 28 Q114 33 100 40 L42 42 Z M16 37 H36",
  rifle: "M4 24 H98 L112 20 V30 H72 L68 42 H58 L61 30 H42 L32 48 H18 L26 30 H4 Z M74 18 H94 V24",
  blade: "M8 50 L22 38 M18 42 L28 34 M25 37 Q70 8 116 6 Q76 20 31 41 Z",
  laptop: "M24 8 H96 V44 H24 Z M10 50 H110 L104 56 H16 Z",
  phone: "M46 2 H74 Q80 2 80 8 V52 Q80 58 74 58 H46 Q40 58 40 52 V8 Q40 2 46 2 Z M55 8 H65",
  shoe: "M10 46 V24 L30 22 L44 34 L76 38 Q104 40 108 50 V54 H10 Z M10 49 H108",
  boot: "M32 4 H58 V34 L92 40 Q108 42 108 52 V56 H32 Z M32 48 H108",
  shirt: "M44 4 L30 8 L12 20 L22 32 L32 26 V56 H88 V26 L98 32 L108 20 L90 8 L76 4 Q60 14 44 4 Z",
  box: "M60 4 L100 18 V44 L60 58 L20 44 V18 Z M20 18 L60 32 L100 18 M60 32 V58",
};
const ICON_BY_CATEGORY = {
  "Пистолеты": "pistol", "Винтовки": "rifle", "Клинки": "blade",
  "Ноутбуки": "laptop", "Игровые ноутбуки": "laptop", "Смартфоны": "phone",
  "Кроссовки": "shoe", "Ботинки": "boot", "Футболки": "shirt",
};
function icon(category, name = "") {
  let kind = ICON_BY_CATEGORY[category] || "box";
  if (/дробовик/i.test(name)) kind = "shotgun";
  else if (/смарт-винтовка|снайпер/i.test(name)) kind = "sniper";
  else if (/нож/i.test(name)) kind = "knife";
  const d = ICONS[kind];
  return `<svg viewBox="0 0 120 60" aria-hidden="true"><path d="${d}"/></svg>`;
}

// ---------- Дерево категорий ----------

let categoryTree = [];

function renderTree() {
  const total = categoryTree.reduce((s, c) => s + c.products_total, 0);
  const node = (c) => `
    <li>
      <button type="button" data-cat="${c.id}" ${state.category === c.id ? 'aria-current="true"' : ""}>
        <span>${esc(c.name)}</span><span class="count">${c.products_total}</span>
      </button>
      ${c.children.length ? `<ul>${c.children.map(node).join("")}</ul>` : ""}
    </li>`;
  $("tree").innerHTML = `
    <li><button type="button" data-cat="" ${state.category === null ? 'aria-current="true"' : ""}>
      <span>Все товары</span><span class="count">${total}</span></button></li>
    ${categoryTree.map(node).join("")}`;
}

$("tree").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-cat]");
  if (!btn) return;
  state.category = btn.dataset.cat ? Number(btn.dataset.cat) : null;
  clearFilters();
  renderTree();
  closeSidePanel();
  run();
});

async function renderCrumbs() {
  const el = $("crumbs");
  if (state.category === null) {
    el.innerHTML = `<li>${state.q ? "Результаты поиска" : "Все товары"}</li>`;
    return;
  }
  const path = await api(`/categories/${state.category}/breadcrumbs`);
  el.innerHTML = path.map((c, i) => i === path.length - 1
    ? `<li aria-current="page">${esc(c.name)}</li>`
    : `<li><button type="button" data-cat="${c.id}">${esc(c.name)}</button></li>`).join("");
}

$("crumbs").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-cat]");
  if (!btn) return;
  state.category = Number(btn.dataset.cat);
  clearFilters();
  renderTree();
  run();
});

// ---------- Поиск ----------

function buildParams() {
  const p = new URLSearchParams();
  if (state.q) p.set("q", state.q);
  if (state.category !== null) p.set("category_id", state.category);
  state.brands.forEach((b) => p.append("brand", b));
  state.filters.forEach((values, code) => values.forEach((v) => p.append("f", `${code}:${v}`)));
  if (state.priceMin !== "") p.set("price_min", state.priceMin);
  if (state.priceMax !== "") p.set("price_max", state.priceMax);
  if (state.inStock) p.set("in_stock", "true");
  p.set("sort", state.sort);
  p.set("limit", LIMIT);
  p.set("offset", state.offset);
  return p;
}

async function run(append = false) {
  if (!append) state.offset = 0;
  const myNo = ++requestNo;
  let data;
  try {
    data = await api("/search", buildParams());
  } catch (err) {
    if (myNo !== requestNo) return;
    $("grid").innerHTML = "";
    showEmpty(`Поиск не выполнен: ${err.message}. Проверьте, что сервер запущен, и обновите страницу.`);
    return;
  }
  if (myNo !== requestNo) return;

  if (!append) bestRelevance = Math.max(...data.items.map((i) => i.relevance || 0), 0.0001);
  const cards = data.items.map(card).join("");
  $("grid").innerHTML = append ? $("grid").innerHTML + cards : cards;

  const shown = state.offset + data.items.length;
  $("more").hidden = shown >= data.total;
  $("readout").textContent = `${data.total} ${plural(data.total, "позиция", "позиции", "позиций")}`;

  if (data.total === 0) {
    showEmpty(hasFilters()
      ? "С такими фильтрами ничего нет. Уберите часть фильтров или нажмите «Сбросить»."
      : "Ничего не нашлось. Попробуйте другое слово или выберите категорию слева.");
  } else {
    $("empty").hidden = true;
  }
  if (!append) {
    renderFacets(data.facets);
    renderCrumbs();
  }
}

function showEmpty(text) {
  $("empty").textContent = text;
  $("empty").hidden = false;
  $("more").hidden = true;
}

function card(item) {
  const price = item.min_price === item.max_price
    ? `${money.format(item.min_price)} ₽`
    : `от ${money.format(item.min_price)} ₽`;
  // Подсказку показываем, только если совпадение нашлось не в названии, а, например, в описании
  const norm = (t) => t.replace(/[\[\]]/g, "").replace(/ё/g, "е").toLowerCase();
  const fromName = item.snippet && norm(item.name).includes(norm(item.snippet).replace(/…/g, "").trim());
  const snippet = state.q && item.snippet && !fromName
    ? `<p class="card-snippet">${esc(item.snippet).replace(/\[(.*?)\]/g, "<mark>$1</mark>")}</p>`
    : "";
  const match = item.relevance
    ? `<div class="match" title="Совпадение с запросом"><span style="width:${Math.round(item.relevance / bestRelevance * 100)}%"></span></div>`
    : "";
  const n = item.matched_skus;
  return `
    <button type="button" class="card" data-id="${item.id}" aria-label="${esc(item.name)}, ${price}">
      <div class="card-inner">
        <div class="card-art">${icon(item.category, item.name)}</div>
        <div class="card-body">
          <span class="card-brand">${esc(item.brand || item.category)}</span>
          <h3 class="card-name">${esc(item.name)}</h3>
          ${snippet}
        </div>
        ${match}
        <div class="card-foot">
          <span class="price">${price}</span>
          <span class="variants">${n} ${plural(n, "вариант", "варианта", "вариантов")}</span>
        </div>
      </div>
    </button>`;
}

$("more").addEventListener("click", () => {
  state.offset += LIMIT;
  run(true);
});

// ---------- Фильтры (фасеты) ----------

function hasFilters() {
  return state.brands.size > 0 || state.filters.size > 0 || state.inStock ||
    state.priceMin !== "" || state.priceMax !== "";
}

function clearFilters() {
  state.brands.clear();
  state.filters.clear();
  state.priceMin = state.priceMax = "";
  state.inStock = false;
  $("price-min").value = $("price-max").value = "";
  $("in-stock").checked = false;
}

function option(kind, code, v) {
  return `
    <label class="facet-opt ${v.count === 0 ? "zero" : ""}">
      <input type="checkbox" data-kind="${kind}" data-code="${esc(code)}" value="${esc(v.value)}"
             ${v.selected ? "checked" : ""} ${v.count === 0 && !v.selected ? "disabled" : ""}>
      <span class="val">${esc(v.value)}</span>
      <span class="count">${v.count}</span>
    </label>`;
}

function renderFacets(f) {
  const brands = f.brands.length
    ? `<fieldset class="facet"><legend>Бренд</legend>
         ${f.brands.map((b) => option("brand", "", b)).join("")}</fieldset>`
    : "";
  const attrs = f.attributes.map((a) => `
    <fieldset class="facet"><legend>${esc(a.name)}${a.unit ? `, ${esc(a.unit)}` : ""}</legend>
      ${a.values.map((v) => option("attr", a.code, v)).join("")}
    </fieldset>`).join("");
  $("facets").innerHTML = brands + attrs;

  $("price-min").placeholder = f.price.min != null ? `от ${money.format(f.price.min)}` : "от";
  $("price-max").placeholder = f.price.max != null ? `до ${money.format(f.price.max)}` : "до";
  $("reset-filters").hidden = !hasFilters();
}

$("facets").addEventListener("change", (e) => {
  const box = e.target;
  if (box.dataset.kind === "brand") {
    box.checked ? state.brands.add(box.value) : state.brands.delete(box.value);
  } else {
    const set = state.filters.get(box.dataset.code) || new Set();
    box.checked ? set.add(box.value) : set.delete(box.value);
    set.size ? state.filters.set(box.dataset.code, set) : state.filters.delete(box.dataset.code);
  }
  run();
});

const priceChanged = debounce(() => {
  state.priceMin = $("price-min").value;
  state.priceMax = $("price-max").value;
  run();
}, 400);
$("price-min").addEventListener("input", priceChanged);
$("price-max").addEventListener("input", priceChanged);

$("in-stock").addEventListener("change", (e) => { state.inStock = e.target.checked; run(); });
$("reset-filters").addEventListener("click", () => { clearFilters(); run(); });

// ---------- Строка поиска и сортировка ----------

const typed = debounce(() => { state.q = $("q").value.trim(); run(); }, 250);
$("q").addEventListener("input", typed);
$("search-form").addEventListener("submit", (e) => {
  e.preventDefault();
  state.q = $("q").value.trim();
  run();
});
$("sort").addEventListener("change", (e) => { state.sort = e.target.value; run(); });

// ---------- Карточка товара ----------

let lastFocus = null;

$("grid").addEventListener("click", (e) => {
  const c = e.target.closest(".card");
  if (c) openProduct(Number(c.dataset.id));
});

async function openProduct(id) {
  lastFocus = document.activeElement;
  let p;
  try {
    p = await api(`/products/${id}`);
  } catch (err) {
    showEmpty(`Карточка не открылась: ${err.message}`);
    return;
  }
  const category = p.category_path[p.category_path.length - 1]?.name;
  const variants = p.skus.map((s) => {
    const attrs = Object.entries(s.attributes).map(([k, v]) => `${esc(k)}: ${esc(v)}`).join(", ");
    return `
      <div class="variant ${s.stock > 0 ? "" : "out"}">
        <span class="attrs">${attrs || "Базовая комплектация"}</span>
        <span class="v-price">${money.format(s.price)} ₽</span>
        <span class="stock">${s.stock > 0 ? `В наличии: ${s.stock} шт.` : "Нет в наличии"}</span>
        <span class="article">Артикул ${esc(s.article)}</span>
      </div>`;
  }).join("");
  const specs = Object.entries(p.extra || {});
  $("drawer-body").innerHTML = `
    <p class="d-path">${p.category_path.map((c) => esc(c.name)).join(" / ")}</p>
    <h2 class="d-title" id="drawer-title">${esc(p.name)}</h2>
    <p class="d-brand">${esc(p.brand || "")}</p>
    <div class="card-art d-art">${icon(category, p.name)}</div>
    <p class="d-desc">${esc(p.description)}</p>
    <h3 class="d-section">Варианты</h3>
    <div class="variants-list">${variants}</div>
    ${specs.length ? `
      <h3 class="d-section">Подробнее</h3>
      <table class="specs">${specs.map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`).join("")}</table>` : ""}`;
  $("drawer").hidden = false;
  $("backdrop").hidden = false;
  $("drawer-close").focus();
}

function closeProduct() {
  $("drawer").hidden = true;
  $("backdrop").hidden = true;
  if (lastFocus) lastFocus.focus();
}
$("drawer-close").addEventListener("click", closeProduct);
$("backdrop").addEventListener("click", closeProduct);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("drawer").hidden) closeProduct();
});

// ---------- Панель фильтров на телефоне ----------

function closeSidePanel() {
  $("side").classList.remove("open");
  $("filters-toggle").setAttribute("aria-expanded", "false");
}
$("filters-toggle").addEventListener("click", () => {
  const open = $("side").classList.toggle("open");
  $("filters-toggle").setAttribute("aria-expanded", String(open));
});

// ---------- Старт: открываем «Арсенал», если он есть ----------

(async function init() {
  try {
    categoryTree = await api("/categories/tree");
  } catch (err) {
    showEmpty(`Каталог не загрузился: ${err.message}. Запустите сервер и обновите страницу.`);
    return;
  }
  const arsenal = categoryTree.find((c) => c.name === "Арсенал");
  state.category = arsenal ? arsenal.id : null;
  renderTree();
  run();
})();
