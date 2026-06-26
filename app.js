const airportSelect = document.querySelector("#airportSelect");
const directionSelect = document.querySelector("#directionSelect");
const searchInput = document.querySelector("#searchInput");
const updatedAt = document.querySelector("#updatedAt");
const recordCount = document.querySelector("#recordCount");
const delayCount = document.querySelector("#delayCount");
const doneCount = document.querySelector("#doneCount");
const sourceName = document.querySelector("#sourceName");
const boardTitle = document.querySelector("#boardTitle");
const routeHeader = document.querySelector("#routeHeader");
const flightRows = document.querySelector("#flightRows");

let flightData = null;

const airportNames = {
  TPE: "桃園",
  TSA: "松山",
  KHH: "高雄",
  RMQ: "臺中",
  HUN: "花蓮",
  TTT: "臺東",
  MZG: "馬公",
  KNH: "金門",
  LZN: "南竿",
};

function text(value) {
  return String(value || "").trim();
}

function statusClass(remark) {
  const value = text(remark);
  if (/延|取消|異常|關閉|Delay|Cancel/i.test(value)) return "badge warn";
  if (/已飛|抵達|到達|Departed|Arrived/i.test(value)) return "badge done";
  return "badge";
}

async function loadData() {
  const response = await fetch(`./data/flights.json?ts=${Date.now()}`);
  if (!response.ok) {
    throw new Error("讀取 data/flights.json 失敗");
  }
  flightData = await response.json();
}

function setAirportOptions() {
  airportSelect.innerHTML = "";
  for (const airport of flightData.airports) {
    const option = document.createElement("option");
    option.value = airport;
    option.textContent = `${airport} ${airportNames[airport] || ""}`.trim();
    airportSelect.append(option);
  }
}

function currentItems() {
  const airport = airportSelect.value;
  const direction = directionSelect.value;
  const query = searchInput.value.trim().toLowerCase();
  return flightData.items
    .filter((item) => item.airport === airport && item.direction === direction)
    .filter((item) => {
      if (!query) return true;
      return [
        item.flight_number,
        item.airline_id,
        item.airline_name,
        item.departure_airport,
        item.departure_airport_name,
        item.arrival_airport,
        item.arrival_airport_name,
        item.remark,
      ]
        .join(" ")
        .toLowerCase()
        .includes(query);
    });
}

function render() {
  const airport = airportSelect.value;
  const direction = directionSelect.value;
  const items = currentItems();
  const isDeparture = direction === "departure";

  updatedAt.textContent = new Date(flightData.generated_at).toLocaleString("zh-TW");
  recordCount.textContent = items.length;
  delayCount.textContent = items.filter((item) => /延|取消|異常|Delay|Cancel/i.test(text(item.remark))).length;
  doneCount.textContent = items.filter((item) => /已飛|抵達|到達|Departed|Arrived/i.test(text(item.remark))).length;
  sourceName.textContent = flightData.source;
  boardTitle.textContent = `${airport} ${airportNames[airport] || ""} ${isDeparture ? "出發" : "抵達"}`;
  routeHeader.textContent = isDeparture ? "目的地" : "出發地";

  flightRows.innerHTML = "";
  for (const item of items) {
    const row = document.createElement("tr");
    const routeCode = isDeparture ? item.arrival_airport : item.departure_airport;
    const routeName = isDeparture ? item.arrival_airport_name : item.departure_airport_name;
    const actual = item.actual_time || item.estimated_time || "-";
    const terminalGate = [item.terminal && `T${item.terminal}`, item.gate].filter(Boolean).join(" / ") || "-";
    row.innerHTML = `
      <td>${text(item.scheduled_time) || "-"}</td>
      <td>${text(actual)}</td>
      <td><strong>${text(item.flight_number) || "-"}</strong></td>
      <td>${text(item.airline_name) || text(item.airline_id) || "-"}</td>
      <td>${text(routeCode)} ${text(routeName)}</td>
      <td>${terminalGate}</td>
      <td><span class="${statusClass(item.remark)}">${text(item.remark) || "查詢中"}</span></td>
    `;
    flightRows.append(row);
  }

  if (items.length === 0) {
    const empty = document.createElement("tr");
    empty.innerHTML = `<td colspan="7" class="empty-row">目前沒有符合條件的航班</td>`;
    flightRows.append(empty);
  }
}

async function init() {
  await loadData();
  setAirportOptions();
  render();
}

airportSelect.addEventListener("change", render);
directionSelect.addEventListener("change", render);
searchInput.addEventListener("input", render);

init().catch((error) => {
  updatedAt.textContent = error.message;
});
