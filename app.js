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

let scheduleData = null;
let changesData = null;
let selectedDate = null;

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
  return new Intl.NumberFormat("zh-TW", { style: "currency", currency, maximumFractionDigits: 0 }).format(Number(value));
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
    option.textContent = route;
    routeSelect.append(option);
  }
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
  monthTitle.textContent = `${monthDate.getFullYear()} 年 ${monthDate.getMonth() + 1} 月`;
  updatedAt.textContent = new Date(changesData.generated_at || scheduleData.generated_at).toLocaleString("zh-TW");
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
      <span class="day-meta">${schedule.length} 班</span>
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
  detailCount.textContent = `${rows.length} 筆`;
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
      <td><strong>${text(row.flight_number)}</strong><br><small>${text(row.airline_name_zh || row.airline_name || row.airline_id)}</small></td>
      <td>${change ? money(change.price, change.currency) : money(row.baseline_price, row.baseline_currency)}</td>
      <td>${text(change?.transfer_count ?? row.transfer_count) || "0"}</td>
      <td>${checked ? `${checked} kg` : "-"}</td>
      <td>${carry ? `${carry} kg` : "-"}</td>
      <td>${change ? `<span class="badge">${text(change.changed_fields)}</span>` : `<span class="badge quiet">固定</span>`}</td>
      <td>${bookingUrl ? `<a href="${bookingUrl}" target="_blank" rel="noopener">查看</a>` : "-"}</td>
    `;
    detailRows.append(tr);
  }
  if (rows.length === 0) {
    detailRows.innerHTML = `<tr><td class="empty-row" colspan="8">此日期沒有固定班表</td></tr>`;
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
  setRouteOptions();
  monthInput.value = monthKey(new Date());
  selectedDate = isoDate(new Date());
  render();
}

routeSelect.addEventListener("change", render);
monthInput.addEventListener("change", render);
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
