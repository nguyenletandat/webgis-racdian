const API_BASE = "";

const map = L.map("map", { zoomControl: true }).setView([10.9, 106.77], 13);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "&copy; OpenStreetMap contributors",
  maxZoom: 19,
}).addTo(map);

const roadsLayer = L.geoJSON(null, { style: { color: "#374151", weight: 1, opacity: 0.6 } });
const ordersLayer = L.geoJSON(null, {
  pointToLayer: (feature, latlng) =>
    L.circleMarker(latlng, {
      radius: 3,
      color: "#facc15",
      weight: 1,
      fillOpacity: 0.7,
    }).bindTooltip(`Khối lượng: ${feature.properties?.KLCTR_up ?? "?"} kg`),
});
const depotLayer = L.geoJSON(null, {
  pointToLayer: (feature, latlng) =>
    L.marker(latlng, {
      icon: L.divIcon({
        className: "depot-icon",
        html: "🏭",
        iconSize: [24, 24],
      }),
    }).bindTooltip("Trạm trung chuyển (Depot)"),
});
const boundaryLayer = L.geoJSON(null, {
  style: { color: "#38bdf8", weight: 2, dashArray: "6 4", fillOpacity: 0.03 },
});
const routesLayer = L.geoJSON(null, {
  style: (feature) => ({ color: feature.properties.color, weight: 4, opacity: 0.9 }),
  onEachFeature: (feature, layer) => {
    const p = feature.properties;
    layer.bindTooltip(
      `Xe ${p.vehicle_id} — ${p.num_orders} điểm — ${p.load_kg}/${p.capacity_kg} kg (${p.utilization_pct}%) — ${p.distance_km} km`
    );
  },
});

routesLayer.addTo(map);
ordersLayer.addTo(map);
boundaryLayer.addTo(map);

async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Lỗi HTTP ${res.status}`);
  }
  return res.json();
}

async function loadMeta() {
  const meta = await fetchJSON(`${API_BASE}/api/meta`);
  document.getElementById("meta-orders").textContent = meta.total_orders.toLocaleString("vi-VN");
  document.getElementById("meta-demand").textContent = `${meta.total_demand_kg.toLocaleString("vi-VN")} kg`;
  document.getElementById("meta-nodes").textContent = meta.road_nodes.toLocaleString("vi-VN");
  document.getElementById("meta-edges").textContent = meta.road_edges.toLocaleString("vi-VN");

  if (meta.ward) {
    document.getElementById("ward-section").hidden = false;
    document.getElementById("ward-name").textContent = `${meta.ward.ten_xa}, ${meta.ward.ten_tinh}`;
    document.getElementById("ward-area").textContent = `${meta.ward.dtich_km2} km²`;
    document.getElementById("ward-population").textContent = meta.ward.dan_so.toLocaleString("vi-VN");
    document.getElementById("ward-density").textContent = `${meta.ward.matdo_km2.toLocaleString("vi-VN")} người/km²`;
    document.getElementById("ward-merged").textContent = `Sáp nhập từ: ${meta.ward.sap_nhap}`;
  }
}

async function loadBoundary() {
  try {
    const geojson = await fetchJSON(`${API_BASE}/api/boundary`);
    boundaryLayer.addData(geojson);
  } catch (err) {
    // Ranh giới hành chính là lớp bổ sung — không chặn phần còn lại của ứng dụng nếu thiếu.
    console.warn("Không tải được ranh giới hành chính:", err.message);
  }
}

async function loadDepot() {
  const geojson = await fetchJSON(`${API_BASE}/api/depots`);
  depotLayer.addData(geojson);
  depotLayer.addTo(map);
  const bounds = depotLayer.getBounds();
  if (bounds.isValid()) map.setView(bounds.getCenter(), 14);
}

async function loadOrders(sampleSize) {
  const geojson = await fetchJSON(`${API_BASE}/api/orders?sample_size=${sampleSize}`);
  ordersLayer.clearLayers();
  ordersLayer.addData(geojson);
}

async function loadRoadNetwork() {
  const geojson = await fetchJSON(`${API_BASE}/api/road-network`);
  roadsLayer.addData(geojson);
}

function setStatus(message, isError = false) {
  const el = document.getElementById("status");
  el.textContent = message;
  el.classList.toggle("error", isError);
}

function renderKPI(kpi) {
  document.getElementById("kpi-section").hidden = false;
  document.getElementById("kpi-vehicles").textContent = `${kpi.vehicles_used}/${kpi.vehicles_available}`;
  document.getElementById("kpi-distance").textContent = kpi.total_distance_km;
  document.getElementById("kpi-utilization").textContent = `${kpi.avg_utilization_pct}%`;
  document.getElementById("kpi-time").textContent = kpi.solve_time_s;
}

function renderRouteTable(features) {
  const tbody = document.getElementById("route-table-body");
  tbody.innerHTML = "";
  const sorted = [...features].sort((a, b) => a.properties.vehicle_id - b.properties.vehicle_id);
  for (const f of sorted) {
    const p = f.properties;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><span style="color:${p.color}">●</span> Xe ${p.vehicle_id}</td>
      <td>${p.num_orders}</td>
      <td>${p.load_kg}</td>
      <td>${p.utilization_pct}%</td>
      <td>${p.distance_km}</td>
    `;
    tbody.appendChild(tr);
  }
}

async function runOptimize(event) {
  event.preventDefault();
  const btn = document.getElementById("optimize-btn");
  btn.disabled = true;
  setStatus("Đang tính toán tuyến tối ưu (Guided Local Search)…");

  const payload = {
    sample_size: Number(document.getElementById("sample_size").value),
    num_vehicles: Number(document.getElementById("num_vehicles").value),
    vehicle_capacity_kg: Number(document.getElementById("vehicle_capacity_kg").value),
    time_limit_s: Number(document.getElementById("time_limit_s").value),
  };

  try {
    const [result] = await Promise.all([
      fetchJSON(`${API_BASE}/api/optimize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),
      loadOrders(payload.sample_size),
    ]);

    routesLayer.clearLayers();
    routesLayer.addData(result);
    const bounds = routesLayer.getBounds();
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [30, 30] });

    renderKPI(result.kpi);
    renderRouteTable(result.features);
    setStatus(`Hoàn tất: ${result.kpi.total_orders_served}/${result.kpi.total_orders_requested} điểm được phục vụ.`);
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    btn.disabled = false;
  }
}

document.getElementById("optimize-form").addEventListener("submit", runOptimize);

document.getElementById("toggle-roads").addEventListener("change", (e) => {
  if (e.target.checked) roadsLayer.addTo(map);
  else map.removeLayer(roadsLayer);
});

document.getElementById("toggle-orders").addEventListener("change", (e) => {
  if (e.target.checked) ordersLayer.addTo(map);
  else map.removeLayer(ordersLayer);
});

document.getElementById("toggle-boundary").addEventListener("change", (e) => {
  if (e.target.checked) boundaryLayer.addTo(map);
  else map.removeLayer(boundaryLayer);
});

(async function init() {
  try {
    await loadMeta();
    await loadDepot();
    await loadOrders(150);
    await loadBoundary();
    loadRoadNetwork().then(() => {
      if (document.getElementById("toggle-roads").checked) roadsLayer.addTo(map);
    });
  } catch (err) {
    setStatus(err.message, true);
  }
})();
