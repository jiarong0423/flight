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
    time: "時間",
    origin: "出發地",
    destination: "目的地",
    flight: "航班",
    price: "價格",
    transfer: "轉機",
    checkedBaggage: "托運",
    carryOn: "手提",
    status: "狀態",
    link: "連結",
    rows: "筆",
    flights: "班",
    fixed: "固定",
    view: "查看",
    noSchedule: "此日期沒有固定班表",
    direct: "直飛",
    stops: "轉機",
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
    time: "Time",
    origin: "Origin",
    destination: "Destination",
    flight: "Flight",
    price: "Price",
    transfer: "Transfer",
    checkedBaggage: "Checked",
    carryOn: "Carry-on",
    status: "Status",
    link: "Link",
    rows: "rows",
    flights: "flights",
    fixed: "Fixed",
    view: "View",
    noSchedule: "No fixed schedule for this date",
    direct: "Direct",
    stops: "stop(s)",
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
    time: "時刻",
    origin: "出発地",
    destination: "目的地",
    flight: "便名",
    price: "価格",
    transfer: "乗継",
    checkedBaggage: "受託",
    carryOn: "機内",
    status: "状態",
    link: "リンク",
    rows: "件",
    flights: "便",
    fixed: "固定",
    view: "表示",
    noSchedule: "この日の固定ダイヤはありません",
    direct: "直行",
    stops: "乗継",
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
    time: "시간",
    origin: "출발지",
    destination: "도착지",
    flight: "항공편",
    price: "가격",
    transfer: "환승",
    checkedBaggage: "위탁",
    carryOn: "기내",
    status: "상태",
    link: "링크",
    rows: "건",
    flights: "편",
    fixed: "고정",
    view: "보기",
    noSchedule: "해당 날짜의 고정 스케줄이 없습니다",
    direct: "직항",
    stops: "환승",
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

function isoDate(date) {
  return date.toISOString().slice(0, 10);
}

function parseDate(value) {
  return new Date(`${value}T00:00:00`);
}

function monthKey(date) {
  return date.toISOString().slice(0, 7);
}

function addMonths(value, delta) {
  const date = parseDate(`${value}-01`);
  date.setMonth(date.getMonth() + delta);
  return monthKey(date);
}

function money(value, currency = "TWD") {
  if (value === "" || value === null || value === undefined) return "-";
  const locale = { zh: "zh-TW", en: "en-US", ja: "ja-JP", ko: "ko-KR" }[currentLang] || "zh-TW";
  return new Intl.NumberFormat(locale, { style: "currency", currency, maximumFractionDigits: 0 }).format(Number(value));
}

function text(value) {
  return String(value || "").trim();
}

async function loadJson(path) {
  const response = await fetch(`${path}?ts=${Date.now()}`);
  if (!response.ok) throw new Error(`讀取 ${path} 失敗`);
  return response.json();
}

async function loadData() {
  [scheduleData, changesData] = await Promise.all([
    loadJson("./data/schedule.json"),
    loadJson("./data/changes.json"),
  ]);
}

function routeOptions() {
  return scheduleData.routes || [...new Set(scheduleData.items.map((item) => item.route))];
}

function setRouteOptions() {
  routeSelect.innerHTML = "";
  for (const route of routeOptions()) {
    const option = document.createElement("option");
    option.value = route;
    const sample = scheduleData.items.find((item) => item.route === route);
    option.textContent = sample
      ? `${sample.origin_flag || ""}${sample.origin} ${sample.destination_flag || ""}${sample.destination}`
      : route;
    routeSelect.append(option);
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

function transferText(row, change) {
  const count = Number(change?.transfer_count ?? row.transfer_count ?? 0);
  const airports = text(change?.transfer_airports_zh || row.transfer_airports_zh);
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
  const monthDate = parseDate(`${month}-01`);
  monthTitle.textContent = new Intl.DateTimeFormat(
    { zh: "zh-TW", en: "en-US", ja: "ja-JP", ko: "ko-KR" }[currentLang],
    { year: "numeric", month: "long" },
  ).format(monthDate);
  updatedAt.textContent = new Date(changesData.generated_at || scheduleData.generated_at).toLocaleString(
    { zh: "zh-TW", en: "en-US", ja: "ja-JP", ko: "ko-KR" }[currentLang],
  );
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

function renderDetails() {
  const route = routeSelect.value;
  const date = selectedDate || isoDate(parseDate(`${monthInput.value}-01`));
  const schedule = scheduleForDate(route, date);
  const changes = changeByFlight(route, date);
  const orphanChanges = changesForDate(route, date).filter((change) => !schedule.some((row) => row.flight_number === change.flight_number));
  const rows = [...schedule, ...orphanChanges];
  detailTitle.textContent = `${date} ${route}`;
  detailCount.textContent = `${rows.length} ${t("rows")}`;
  detailRows.innerHTML = "";

  for (const row of rows) {
    const change = changes.get(row.flight_number) || (row.change_id ? row : null);
    const tr = document.createElement("tr");
    if (change) tr.classList.add("changed-row");
    const bookingUrl = text(change?.booking_url);
    const checked = text(change?.baggage_checked_weight_kg || row.baseline_checked_baggage_kg);
    const carry = text(change?.baggage_carry_on_weight_kg || row.baseline_carry_on_kg);
    tr.innerHTML = `
      <td>${text(row.departure_time) || "-"}</td>
      <td>${text(row.origin_flag || change?.origin_flag)} ${text(row.origin_name_zh || change?.origin_name_zh || row.origin || change?.origin)}</td>
      <td>${text(row.destination_flag || change?.destination_flag)} ${text(row.destination_name_zh || change?.destination_name_zh || row.destination || change?.destination)}</td>
      <td><strong>${text(row.flight_number)}</strong><br><small>${text(row.airline_name_zh || row.airline_name || row.airline_id)}</small></td>
      <td>${change ? money(change.price, change.currency) : money(row.baseline_price, row.baseline_currency)}</td>
      <td>${transferText(row, change)}</td>
      <td>${checked ? `${checked} kg` : "-"}</td>
      <td>${carry ? `${carry} kg` : "-"}</td>
      <td>${change ? `<span class="badge">${changedLabel(change.changed_fields)}</span>` : `<span class="badge quiet">${t("fixed")}</span>`}</td>
      <td>${bookingUrl ? `<a href="${bookingUrl}" target="_blank" rel="noopener">${t("view")}</a>` : "-"}</td>
    `;
    detailRows.append(tr);
  }
  if (rows.length === 0) {
    detailRows.innerHTML = `<tr><td class="empty-row" colspan="10">${t("noSchedule")}</td></tr>`;
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
  render();
});
nextMonth.addEventListener("click", () => {
  monthInput.value = addMonths(monthInput.value, 1);
  render();
});
detailToggle.addEventListener("click", () => {
  detailBody.classList.toggle("collapsed");
});

init().catch((error) => {
  updatedAt.textContent = error.message;
});
