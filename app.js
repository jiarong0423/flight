const routeSelect = document.querySelector("#routeSelect");
const monthInput = document.querySelector("#monthInput");
const updatedAt = document.querySelector("#updatedAt");
const monthTitle = document.querySelector("#monthTitle");
const calendarGrid = document.querySelector("#calendarGrid");
const prevMonth = document.querySelector("#prevMonth");
const nextMonth = document.querySelector("#nextMonth");
const detailToggle = document.querySelector("#detailToggle");
const detailTitle = document.querySelector("#detailTitle");
const detailCount = document.querySelector("#detailCount");
const detailBody = document.querySelector("#detailBody");
const detailRows = document.querySelector("#detailRows");
const languageSelect = document.querySelector("#languageSelect");

let scheduleData = null;
let changesData = null;
let tablesData = null;
let selectedDate = null;
let currentLang = localStorage.getItem("flight_lang") || "zh";

const translations = {
  zh: {
    appTitle: "航班價格月曆",
    eyebrow: "固定班表 + 變動提示",
    language: "語言",
    updatedAt: "最後更新",
    route: "航線",
    month: "月份",
    rows: "筆",
    flights: "班",
    fixed: "固定",
    changed: "變動",
    view: "查看",
    noSchedule: "此日期沒有固定班表",
    direct: "直飛",
    stops: "轉機",
    checked: "托運",
    carryOn: "手提",
    noPrice: "未抓到價格",
    changedFields: {
      price: "票價",
      transfer_count: "轉機",
      baggage_checked_weight_kg: "托運重量",
      baggage_checked_pieces: "托運件數",
      baggage_carry_on_weight_kg: "手提重量",
    },
  },
  en: {
    appTitle: "Flight Fare Calendar",
    eyebrow: "Fixed schedule + change overlay",
    language: "Language",
    updatedAt: "Updated",
    route: "Route",
    month: "Month",
    rows: "rows",
    flights: "flights",
    fixed: "Fixed",
    changed: "Changed",
    view: "View",
    noSchedule: "No fixed schedule for this date",
    direct: "Direct",
    stops: "stop(s)",
    checked: "Checked",
    carryOn: "Carry-on",
    noPrice: "No fare",
    changedFields: {
      price: "Fare",
      transfer_count: "Transfer",
      baggage_checked_weight_kg: "Checked weight",
      baggage_checked_pieces: "Checked pieces",
      baggage_carry_on_weight_kg: "Carry-on weight",
    },
  },
  ja: {
    appTitle: "航空券カレンダー",
    eyebrow: "固定ダイヤ + 変更表示",
    language: "言語",
    updatedAt: "更新",
    route: "路線",
    month: "月",
    rows: "件",
    flights: "便",
    fixed: "固定",
    changed: "変更",
    view: "表示",
    noSchedule: "この日の固定ダイヤはありません",
    direct: "直行",
    stops: "乗継",
    checked: "受託",
    carryOn: "機内",
    noPrice: "価格なし",
    changedFields: {
      price: "価格",
      transfer_count: "乗継",
      baggage_checked_weight_kg: "受託重量",
      baggage_checked_pieces: "受託個数",
      baggage_carry_on_weight_kg: "機内重量",
    },
  },
  ko: {
    appTitle: "항공권 달력",
    eyebrow: "고정 스케줄 + 변경 표시",
    language: "언어",
    updatedAt: "업데이트",
    route: "노선",
    month: "월",
    rows: "건",
    flights: "편",
    fixed: "고정",
    changed: "변경",
    view: "보기",
    noSchedule: "해당 날짜의 고정 스케줄이 없습니다",
    direct: "직항",
    stops: "환승",
    checked: "위탁",
    carryOn: "기내",
    noPrice: "요금 없음",
    changedFields: {
      price: "요금",
      transfer_count: "환승",
      baggage_checked_weight_kg: "위탁 무게",
      baggage_checked_pieces: "위탁 개수",
      baggage_carry_on_weight_kg: "기내 무게",
    },
  },
};

const weekdays = {
  zh: ["日", "一", "二", "三", "四", "五", "六"],
  en: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
  ja: ["日", "月", "火", "水", "木", "金", "土"],
  ko: ["일", "월", "화", "수", "목", "금", "토"],
};

function t(key) {
  return translations[currentLang][key] || translations.zh[key] || key;
}

function pad(value) {
  return String(value).padStart(2, "0");
}

function isoDate(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function parseDate(value) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function monthKey(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}`;
}

function addMonths(value, delta) {
  const date = parseDate(`${value}-01`);
  date.setMonth(date.getMonth() + delta);
  return monthKey(date);
}

function text(value) {
  return String(value ?? "").trim();
}

function escapeHtml(value) {
  return text(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function money(value, currency = "TWD") {
  if (value === "" || value === null || value === undefined) return t("noPrice");
  const locale = { zh: "zh-TW", en: "en-US", ja: "ja-JP", ko: "ko-KR" }[currentLang] || "zh-TW";
  return new Intl.NumberFormat(locale, { style: "currency", currency, maximumFractionDigits: 0 }).format(Number(value));
}

async function loadJson(path) {
  const response = await fetch(`${path}?ts=${Date.now()}`);
  if (!response.ok) throw new Error(`讀取 ${path} 失敗`);
  return response.json();
}

async function loadData() {
  [scheduleData, changesData, tablesData] = await Promise.all([
    loadJson("./data/schedule.json"),
    loadJson("./data/changes.json"),
    loadJson("./data/tables.json"),
  ]);
}

function tableMap(name, key) {
  return new Map((tablesData?.tables?.[name] || []).map((item) => [item[key], item]));
}

function airport(code) {
  return tableMap("airports", "airport_id").get(code) || { airport_id: code };
}

function airline(code) {
  return tableMap("airlines", "airline_id").get(code) || { airline_id: code };
}

function airportName(code) {
  const item = airport(code);
  if (currentLang === "zh") return item.airport_name_zh || item.airport_name_en || code;
  return item.airport_name_en || item.airport_name_zh || code;
}

function airlineName(code) {
  const item = airline(code);
  if (currentLang === "zh") return item.airline_name_zh || item.airline_name_en || code;
  return item.airline_name_en || item.airline_name_zh || code;
}

function countryBadge(code) {
  const item = airport(code);
  return `<span class="country-badge">${escapeHtml(item.country || code)}</span>`;
}

function routeLabel(route) {
  const [origin, destination] = route.split("-");
  return `${airportName(origin)} ${origin} → ${airportName(destination)} ${destination}`;
}

function airlineIcon(code) {
  const item = airline(code);
  const label = escapeHtml(code || "?");
  if (!item.icon_url) return `<span class="airline-fallback">${label}</span>`;
  return `<img class="airline-logo" src="${escapeHtml(item.icon_url)}" alt="${escapeHtml(airlineName(code))}" loading="lazy" onerror="this.hidden=true;this.nextElementSibling.hidden=false"><span class="airline-fallback" hidden>${label}</span>`;
}

function routeOptions() {
  return tablesData?.tables?.routes?.map((item) => item.route) || [...new Set(scheduleData.items.map((item) => item.route))];
}

function setRouteOptions() {
  const selected = routeSelect.value;
  routeSelect.innerHTML = "";
  for (const route of routeOptions()) {
    const option = document.createElement("option");
    option.value = route;
    option.textContent = routeLabel(route);
    routeSelect.append(option);
  }
  if (selected && [...routeSelect.options].some((option) => option.value === selected)) {
    routeSelect.value = selected;
  }
}

function applyI18n() {
  document.documentElement.lang = { zh: "zh-Hant", en: "en", ja: "ja", ko: "ko" }[currentLang];
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
  document.querySelector("#weekdayRow").innerHTML = weekdays[currentLang].map((day) => `<span>${day}</span>`).join("");
  prevMonth.setAttribute("aria-label", currentLang === "en" ? "Previous month" : "上一月");
  nextMonth.setAttribute("aria-label", currentLang === "en" ? "Next month" : "下一月");
}

function changedLabel(fields) {
  const labels = translations[currentLang].changedFields;
  return text(fields)
    .split(",")
    .filter(Boolean)
    .map((field) => labels[field] || field)
    .join(" / ");
}

function transferAirportNames(value) {
  return text(value)
    .split(",")
    .filter(Boolean)
    .map((code) => airportName(code))
    .join(" / ");
}

function transferText(row, change) {
  const count = Number(change?.transfer_count ?? row.transfer_count ?? 0);
  const airports = transferAirportNames(change?.transfer_airports || row.transfer_airports);
  if (count === 0) return t("direct");
  return airports ? `${count} ${t("stops")} ${airports}` : `${count} ${t("stops")}`;
}

function scheduleForDate(route, date) {
  return scheduleData.items.filter((item) => item.route === route && item.flight_date === date);
}

function changesForDate(route, date) {
  return changesData.items.filter((item) => item.route === route && item.flight_date === date);
}

function changeByFlight(route, date) {
  const map = new Map();
  for (const change of changesForDate(route, date)) {
    map.set(change.flight_number, change);
  }
  return map;
}

function calendarCells(month) {
  const first = parseDate(`${month}-01`);
  const startOffset = first.getDay();
  const last = new Date(first.getFullYear(), first.getMonth() + 1, 0);
  const cells = [];
  for (let i = 0; i < startOffset; i += 1) cells.push(null);
  for (let day = 1; day <= last.getDate(); day += 1) {
    cells.push(new Date(first.getFullYear(), first.getMonth(), day));
  }
  return cells;
}

function renderCalendar() {
  const route = routeSelect.value;
  const month = monthInput.value;
  const locale = { zh: "zh-TW", en: "en-US", ja: "ja-JP", ko: "ko-KR" }[currentLang] || "zh-TW";
  const monthDate = parseDate(`${month}-01`);
  monthTitle.textContent = new Intl.DateTimeFormat(locale, { year: "numeric", month: "long" }).format(monthDate);
  updatedAt.textContent = new Date(changesData.generated_at || scheduleData.generated_at).toLocaleString(locale);
  calendarGrid.innerHTML = "";

  for (const cellDate of calendarCells(month)) {
    const cell = document.createElement("button");
    cell.type = "button";
    cell.className = "day-cell";
    if (!cellDate) {
      cell.classList.add("empty");
      calendarGrid.append(cell);
      continue;
    }
    const date = isoDate(cellDate);
    const schedule = scheduleForDate(route, date);
    const changes = changesForDate(route, date);
    if (changes.length > 0) cell.classList.add("has-change");
    if (selectedDate === date) cell.classList.add("selected");
    const prices = changes.map((item) => Number(item.price || 0)).filter(Boolean);
    const lowest = prices.length ? Math.min(...prices) : null;
    cell.innerHTML = `
      <span class="date-number">${cellDate.getDate()}</span>
      <span class="day-meta">${schedule.length} ${t("flights")}</span>
      ${lowest ? `<span class="price-pill">${money(lowest)}</span>` : ""}
      ${changes.length ? `<span class="change-bubble">${changes.length}</span>` : ""}
    `;
    cell.addEventListener("click", () => {
      selectedDate = date;
      renderCalendar();
      renderDetails();
    });
    calendarGrid.append(cell);
  }
}

function flightCard(row, change) {
  const origin = row.origin || change?.origin || "";
  const destination = row.destination || change?.destination || "";
  const airlineId = row.airline_id || change?.airline_id || "";
  const checked = text(change?.baggage_checked_weight_kg);
  const pieces = text(change?.baggage_checked_pieces);
  const carry = text(change?.baggage_carry_on_weight_kg);
  const bookingUrl = text(change?.booking_url);
  const changedText = changedLabel(change?.changed_fields);
  return `
    <article class="flight-card ${change ? "changed" : ""}">
      <div class="flight-time">
        <strong>${escapeHtml(row.departure_time || change?.departure_time || "-")}</strong>
        <span>${countryBadge(origin)} ${escapeHtml(airportName(origin))}</span>
        <span class="route-arrow">→</span>
        <span>${countryBadge(destination)} ${escapeHtml(airportName(destination))}</span>
      </div>
      <div class="flight-main">
        <div>
          <strong>${escapeHtml(row.flight_number || change?.flight_number || "-")}</strong>
          <span class="airline-name">${airlineIcon(airlineId)} ${escapeHtml(airlineName(airlineId))}</span>
        </div>
      </div>
      <div class="flight-price">
        <strong>${change ? money(change.price, change.currency) : t("noPrice")}</strong>
        <span class="status-chip ${change ? "hot" : ""}">${change ? t("changed") : t("fixed")}</span>
      </div>
      <div class="flight-facts">
        <span class="fact-chip">${escapeHtml(transferText(row, change))}</span>
        ${checked ? `<span class="fact-chip">${t("checked")} ${escapeHtml(checked)} kg${pieces ? ` / ${escapeHtml(pieces)}件` : ""}</span>` : ""}
        ${carry ? `<span class="fact-chip">${t("carryOn")} ${escapeHtml(carry)} kg</span>` : ""}
        ${changedText ? `<span class="fact-chip hot">${escapeHtml(changedText)}</span>` : ""}
      </div>
      <div class="flight-action">
        ${bookingUrl ? `<a class="action-link" href="${escapeHtml(bookingUrl)}" target="_blank" rel="noopener">${t("view")}</a>` : ""}
      </div>
    </article>
  `;
}

function renderDetails() {
  const route = routeSelect.value;
  const date = selectedDate || isoDate(parseDate(`${monthInput.value}-01`));
  const schedule = scheduleForDate(route, date);
  const changes = changeByFlight(route, date);
  const orphanChanges = changesForDate(route, date).filter((change) => !schedule.some((row) => row.flight_number === change.flight_number));
  const rows = [...schedule, ...orphanChanges];
  detailTitle.textContent = `${date} ${routeLabel(route)}`;
  detailCount.textContent = `${rows.length} ${t("rows")}`;
  detailRows.innerHTML = rows
    .map((row) => flightCard(row, changes.get(row.flight_number) || (row.change_id ? row : null)))
    .join("");

  if (rows.length === 0) {
    detailRows.innerHTML = `<div class="empty-row">${t("noSchedule")}</div>`;
  }
}

function render() {
  if (!selectedDate || !selectedDate.startsWith(monthInput.value)) {
    selectedDate = isoDate(parseDate(`${monthInput.value}-01`));
  }
  renderCalendar();
  renderDetails();
}

async function init() {
  await loadData();
  languageSelect.value = currentLang;
  applyI18n();
  setRouteOptions();
  monthInput.value = monthKey(new Date());
  selectedDate = isoDate(new Date());
  render();
}

routeSelect.addEventListener("change", render);
monthInput.addEventListener("change", render);
languageSelect.addEventListener("change", () => {
  currentLang = languageSelect.value;
  localStorage.setItem("flight_lang", currentLang);
  applyI18n();
  setRouteOptions();
  render();
});
prevMonth.addEventListener("click", () => {
  monthInput.value = addMonths(monthInput.value, -1);
  selectedDate = isoDate(parseDate(`${monthInput.value}-01`));
  render();
});
nextMonth.addEventListener("click", () => {
  monthInput.value = addMonths(monthInput.value, 1);
  selectedDate = isoDate(parseDate(`${monthInput.value}-01`));
  render();
});
detailToggle.addEventListener("click", () => {
  detailBody.classList.toggle("collapsed");
});

init().catch((error) => {
  updatedAt.textContent = error.message;
});
