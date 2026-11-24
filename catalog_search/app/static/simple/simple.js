// Простая версия витрины. Использует то же API, что и Swagger:
//   GET /categories/tree               - дерево категорий (рекурсивный CTE)
//   GET /categories/{id}/breadcrumbs   - путь до категории
//   GET /search                        - поиск, фильтры, фасеты
//   GET /products/{id}                 - карточка товара (SPU + SKU)

const state = {
  q: "",
  category: null,
  brands: [],
  filters: {},          // { "ram": ["16", "32"], "color": ["белый"] }
  priceMin: "",
  priceMax: "",
  inStock: false,
  sort: "relevance",
};

const $ = (id) => document.getElementById(id);

async function api(url) {
  const res = await fetch(url);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail);
  return data;
}

function esc(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}

const rub = (n) => n.toLocaleString("ru-RU");

// ---------- Категории ----------

async function loadTree() {
  const tree = await api("/categories/tree");
  const item = (c) => `
    <li>
      <a href="#" data-cat="${c.id}" class="${state.category === c.id ? "active" : ""}">${esc(c.name)}</a>
      <span class="count">(${c.products_total})</span>
      ${c.children.length ? `<ul>${c.children.map(item).join("")}</ul>` : ""}
    </li>`;
  $("tree").innerHTML =
    `<li><a href="#" data-cat="" class="${state.category === null ? "active" : ""}">Все товары</a></li>` +
    tree.map(item).join("");
}

$("tree").addEventListener("click", (e) => {
  const link = e.target.closest("a");
  if (!link) return;
  e.preventDefault();
  state.category = link.dataset.cat ? Number(link.dataset.cat) : null;
  resetFilters();
  loadTree();
  search();
});

async function showCrumbs() {
  if (state.category === null) {
    $("crumbs").textContent = "Все товары";
    return;
  }
  const path = await api(`/categories/${state.category}/breadcrumbs`);
  $("crumbs").textContent = path.map((c) => c.name).join(" → ");
}

// ---------- Поиск ----------

async function search() {
  const p = new URLSearchParams();
  if (state.q) p.set("q", state.q);
  if (state.category !== null) p.set("category_id", state.category);
  state.brands.forEach((b) => p.append("brand", b));
  for (const [code, values] of Object.entries(state.filters)) {
    values.forEach((v) => p.append("f", `${code}:${v}`));
  }
  if (state.priceMin) p.set("price_min", state.priceMin);
  if (state.priceMax) p.set("price_max", state.priceMax);
  if (state.inStock) p.set("in_stock", "true");
  p.set("sort", state.sort);
  p.set("limit", 100);

  let data;
  try {
    data = await api("/search?" + p);
  } catch (err) {
    $("summary").textContent = "Ошибка: " + err.message;
    return;
  }

  $("summary").textContent = `Найдено товаров: ${data.total}` +
    (data.fts_query ? ` (запрос к FTS5: ${data.fts_query})` : "");

  $("results").innerHTML = data.items.map((i) => `
    <tr>
      <td>
        <a href="#" data-id="${i.id}">${esc(i.name)}</a>
        ${i.snippet ? `<br><small>${esc(i.snippet).replace(/\[(.*?)\]/g, "<mark>$1</mark>")}</small>` : ""}
      </td>
      <td>${esc(i.brand)}</td>
      <td>${esc(i.category)}</td>
      <td class="num">${i.min_price === i.max_price ? rub(i.min_price) : `${rub(i.min_price)} – ${rub(i.max_price)}`}</td>
      <td class="num">${i.matched_skus}</td>
      <td class="num">${i.relevance ?? "—"}</td>
    </tr>`).join("") ||
    `<tr><td colspan="6">Ничего не найдено. Измените запрос или сбросьте фильтры.</td></tr>`;

  showFacets(data.facets);
  showCrumbs();
}

// ---------- Фасеты ----------

function checkbox(kind, code, v) {
  return `
    <label class="${v.count === 0 ? "zero" : ""}">
      <input type="checkbox" data-kind="${kind}" data-code="${code}" value="${esc(v.value)}"
             ${v.selected ? "checked" : ""}>
      ${esc(v.value)} <span class="count">(${v.count})</span>
    </label>`;
}

function showFacets(f) {
  let html = "";
  if (f.brands.length) {
    html += `<fieldset><legend>Бренд</legend>${f.brands.map((b) => checkbox("brand", "", b)).join("")}</fieldset>`;
  }
  for (const a of f.attributes) {
    html += `<fieldset><legend>${esc(a.name)}${a.unit ? ", " + esc(a.unit) : ""}</legend>
      ${a.values.map((v) => checkbox("attr", a.code, v)).join("")}</fieldset>`;
  }
  $("facets").innerHTML = html;
  $("price-min").placeholder = f.price.min != null ? "от " + rub(f.price.min) : "от";
  $("price-max").placeholder = f.price.max != null ? "до " + rub(f.price.max) : "до";
}

$("facets").addEventListener("change", (e) => {
  const box = e.target;
  if (box.dataset.kind === "brand") {
    state.brands = box.checked
      ? [...state.brands, box.value]
      : state.brands.filter((b) => b !== box.value);
  } else {
    const code = box.dataset.code;
    const values = state.filters[code] || [];
    state.filters[code] = box.checked ? [...values, box.value] : values.filter((v) => v !== box.value);
    if (state.filters[code].length === 0) delete state.filters[code];
  }
  search();
});

function resetFilters() {
  state.brands = [];
  state.filters = {};
  state.priceMin = state.priceMax = "";
  state.inStock = false;
  $("price-min").value = $("price-max").value = "";
  $("in-stock").checked = false;
}

$("reset").addEventListener("click", () => { resetFilters(); search(); });
$("in-stock").addEventListener("change", (e) => { state.inStock = e.target.checked; search(); });
$("price-apply").addEventListener("click", () => {
  state.priceMin = $("price-min").value;
  state.priceMax = $("price-max").value;
  search();
});

// ---------- Строка поиска ----------

$("search-form").addEventListener("submit", (e) => {
  e.preventDefault();
  state.q = $("q").value.trim();
  search();
});
$("sort").addEventListener("change", (e) => { state.sort = e.target.value; search(); });

// ---------- Карточка товара ----------

$("results").addEventListener("click", async (e) => {
  const link = e.target.closest("a[data-id]");
  if (!link) return;
  e.preventDefault();
  const p = await api(`/products/${link.dataset.id}`);

  const rows = p.skus.map((s) => `
    <tr>
      <td>${esc(s.article)}</td>
      <td>${Object.entries(s.attributes).map(([k, v]) => `${esc(k)}: ${esc(v)}`).join("<br>")}</td>
      <td class="num">${rub(s.price)}</td>
      <td class="num">${s.stock}</td>
    </tr>`).join("");
  const extra = Object.entries(p.extra || {})
    .map(([k, v]) => `<li>${esc(k)}: ${esc(v)}</li>`).join("");

  const box = $("product");
  box.innerHTML = `
    <h2>${esc(p.name)}</h2>
    <p>${p.category_path.map((c) => esc(c.name)).join(" → ")}<br>Бренд: ${esc(p.brand)}</p>
    <p>${esc(p.description)}</p>
    <h3>Варианты (SKU)</h3>
    <table>
      <thead><tr><th>Артикул</th><th>Характеристики (EAV)</th><th>Цена, ₽</th><th>Остаток</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    ${extra ? `<h3>Дополнительно (JSON)</h3><ul>${extra}</ul>` : ""}
    <p><button type="button" id="close-product">Закрыть</button></p>`;
  box.hidden = false;
  box.scrollIntoView({ behavior: "smooth" });
  $("close-product").addEventListener("click", () => { box.hidden = true; });
});

// ---------- Старт ----------

loadTree();
search();
