const routeSelect = document.querySelector("#routeSelect");
const fromDate = document.querySelector("#fromDate");
const rangeSelect = document.querySelector("#rangeSelect");
const updatedAt = document.querySelector("#updatedAt");
const recordCount = document.querySelector("#recordCount");
const lowestPrice = document.querySelector("#lowestPrice");
const averagePrice = document.querySelector("#averagePrice");
const sourceName = document.querySelector("#sourceName");
const calendarTitle = document.querySelector("#calendarTitle");
const calendarGrid = document.querySelector("#calendarGrid");

let flightData = null;

function isoDate(date) {
  return date.toISOString().slice(0, 10);
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function parseLocalDate(value) {
  return new Date(`${value}T00:00:00`);
}

function money(value, currency) {
  return new Intl.NumberFormat("zh-TW", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

async function loadData() {
  const response = await fetch(`./data/flights.json?ts=${Date.now()}`);
  if (!response.ok) {
    throw new Error("讀取 data/flights.json 失敗");
  }
  flightData = await response.json();
}

function setRouteOptions() {
  routeSelect.innerHTML = "";
  for (const route of flightData.routes) {
    const option = document.createElement("option");
    option.value = route;
    option.textContent = route;
    routeSelect.append(option);
  }
}

function dateCells(start, end, items) {
  const map = new Map(items.map((item) => [item.travel_date, item]));
  const cells = [];
  for (let index = 0; index < start.getDay(); index += 1) {
    cells.push({ empty: true });
  }
  for (let cursor = new Date(start); cursor <= end; cursor = addDays(cursor, 1)) {
    cells.push({ date: new Date(cursor), item: map.get(isoDate(cursor)) });
  }
  return cells;
}

function render() {
  const route = routeSelect.value;
  const start = parseLocalDate(fromDate.value);
  const days = Number(rangeSelect.value);
  const end = addDays(start, days - 1);
  const items = flightData.items.filter((item) => {
    const travelDate = parseLocalDate(item.travel_date);
    return item.route === route && travelDate >= start && travelDate <= end;
  });

  updatedAt.textContent = new Date(flightData.generated_at).toLocaleString("zh-TW");
  recordCount.textContent = items.length;
  sourceName.textContent = flightData.source;
  calendarTitle.textContent = `${route} 價格日曆`;

  const prices = items.map((item) => item.price);
  if (prices.length > 0) {
    const lowest = Math.min(...prices);
    const average = Math.round(prices.reduce((sum, value) => sum + value, 0) / prices.length);
    lowestPrice.textContent = money(lowest, flightData.currency);
    averagePrice.textContent = money(average, flightData.currency);
  } else {
    lowestPrice.textContent = "-";
    averagePrice.textContent = "-";
  }

  calendarGrid.innerHTML = "";
  for (const cell of dateCells(start, end, items)) {
    const day = document.createElement("div");
    day.className = cell.empty ? "day empty" : "day";
    if (!cell.empty) {
      const dateNumber = document.createElement("span");
      dateNumber.className = "date-number";
      dateNumber.textContent = cell.date.getDate();
      day.append(dateNumber);

      if (cell.item) {
        const price = document.createElement("div");
        price.className = "price";
        price.textContent = money(cell.item.price, cell.item.currency);
        const badge = document.createElement("span");
        badge.className = cell.item.price > 12000 ? "badge high" : "badge";
        badge.textContent = cell.item.price > 12000 ? "偏高" : "可觀察";
        day.append(price, badge);
      } else {
        const missing = document.createElement("div");
        missing.className = "missing";
        missing.textContent = "無資料";
        day.append(missing);
      }
    }
    calendarGrid.append(day);
  }
}

async function init() {
  fromDate.value = isoDate(new Date());
  await loadData();
  setRouteOptions();
  render();
}

routeSelect.addEventListener("change", render);
fromDate.addEventListener("change", render);
rangeSelect.addEventListener("change", render);

init().catch((error) => {
  updatedAt.textContent = error.message;
});
