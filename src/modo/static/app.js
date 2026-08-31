const PALETTE = [
  "#176B87",
  "#C84457",
  "#6C4AB6",
  "#2D7D46",
  "#B85A0C",
  "#A63D8F",
  "#007C78",
  "#6E5C41",
];
const state = {
  rows: [],
  nextColor: 0,
  nextRowId: 0,
  request: null,
  layers: [],
  photonBbox: null,
  maxOrigins: 32,
};
const view = {
  addOrigin: document.querySelector("#add-origin"),
  origins: document.querySelector("#origins"),
  panel: document.querySelector(".panel"),
  result: document.querySelector("#result"),
  bestTime: document.querySelector("#best-time"),
  status: document.querySelector("#status"),
};
const map = L.map("map", {
  zoomControl: false,
  attributionControl: false,
  preferCanvas: true,
}).setView(
  [41.8781, -87.6298],
  10,
);
map.createPane("routePane").style.zIndex = 410;
map.createPane("regionPane").style.zIndex = 420;
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution:
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19,
}).addTo(map);
L.control.zoom({ position: "topright" }).addTo(map);
L.control.attribution({ position: "topright" }).addTo(map);
const canvas = L.canvas({ padding: 0.5, pane: "regionPane" });
new ResizeObserver(() => map.invalidateSize()).observe(document.querySelector("#map"));

function nextColor() {
  const index = state.nextColor++;
  if (index < PALETTE.length) return PALETTE[index];
  return `hsl(${(198 + index * 137.508) % 360} 58% 30%)`;
}

function setStatus(message) {
  view.status.textContent = message;
}

function duration(seconds) {
  const rounded = Math.max(0, Math.round(seconds));
  if (rounded < 60) return `${rounded} sec`;
  const minutes = rounded / 60;
  return `${Number(minutes.toFixed(minutes < 10 ? 1 : 0))} min`;
}

function parseCoordinate(value) {
  const match = value.match(
    /^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*,\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*$/,
  );
  if (!match) return null;
  const coordinate = [Number(match[1]), Number(match[2])];
  if (
    !coordinate.every(Number.isFinite) ||
    Math.abs(coordinate[0]) > 90 ||
    Math.abs(coordinate[1]) > 180
  ) {
    return null;
  }
  return coordinate;
}

function formatCoordinate(coordinate) {
  return `${coordinate[0].toFixed(5)}, ${coordinate[1].toFixed(5)}`;
}

function looksLikeCoordinateInput(value) {
  return /^[+\-\d.,\s]+$/.test(value);
}

function featureLabel(feature) {
  const value = feature?.properties || {};
  return [value.name, value.street, value.city || value.district, value.state]
    .filter((part, index, parts) => part && parts.indexOf(part) === index)
    .join(", ");
}

function originIcon(row) {
  const index = state.rows.indexOf(row);
  return L.divIcon({
    className: "",
    html: `<span class="origin-pin" style="background:${row.color}">${index + 1}</span>`,
    iconSize: [32, 32],
    iconAnchor: [16, 16],
  });
}

function updateMarker(row) {
  if (!row.coordinate) return;
  if (row.marker) {
    row.marker.setLatLng(row.coordinate).setIcon(originIcon(row));
  } else {
    row.marker = L.marker(row.coordinate, {
      icon: originIcon(row),
      keyboard: false,
      title: row.input.value,
    }).addTo(map);
  }
}

function clearResult() {
  state.request?.abort();
  state.request = null;
  state.layers.splice(0).forEach((layer) => layer.remove());
  view.result.hidden = true;
  state.rows.forEach((row) => {
    row.time.textContent = "";
  });
}

function fitConfirmedOrigins() {
  const coordinates = state.rows.filter((row) => row.coordinate).map((row) => row.coordinate);
  if (!coordinates.length) return;
  map.stop();
  map.fitBounds(coordinates, fitOptions(12));
}

function fitOptions(maxZoom) {
  const mobile = window.matchMedia("(max-width: 640px)").matches;
  return {
    animate: false,
    maxZoom,
    paddingTopLeft: mobile ? [32, 32] : [view.panel.offsetWidth + 48, 48],
    paddingBottomRight: mobile ? [32, view.panel.offsetHeight + 48] : [48, 48],
  };
}

function confirmOrigin(row, label, coordinate) {
  clearTimeout(row.timer);
  row.timer = null;
  row.controller?.abort();
  row.controller = null;
  row.coordinate = coordinate.map(Number);
  row.snappedCoordinate = null;
  row.input.value = label;
  row.input.title = `Confirmed at ${formatCoordinate(row.coordinate)}`;
  clearSuggestions(row);
  updateMarker(row);
  fitConfirmedOrigins();
  calculate();
}

function addSuggestion(row, label, coordinate) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.id = `origin-option-${row.id}-${row.suggestions.children.length}`;
  button.setAttribute("role", "option");
  button.tabIndex = -1;
  button.setAttribute("aria-selected", "false");
  button.onclick = () => confirmOrigin(row, label, coordinate);
  button.onmouseenter = () => {
    const options = [...row.suggestions.querySelectorAll('[role="option"]')];
    setActiveSuggestion(row, options.indexOf(button));
  };
  const item = document.createElement("li");
  item.setAttribute("role", "none");
  item.append(button);
  row.suggestions.append(item);
  row.input.setAttribute("aria-expanded", "true");
}

function clearSuggestions(row) {
  row.suggestions.replaceChildren();
  row.activeIndex = -1;
  row.input.setAttribute("aria-expanded", "false");
  row.input.removeAttribute("aria-activedescendant");
}

function setActiveSuggestion(row, index) {
  const options = [...row.suggestions.querySelectorAll('[role="option"]')];
  if (!options.length) return;
  row.activeIndex = (index + options.length) % options.length;
  options.forEach((option, optionIndex) => {
    option.setAttribute("aria-selected", String(optionIndex === row.activeIndex));
  });
  row.input.setAttribute("aria-activedescendant", options[row.activeIndex].id);
}

async function suggest(row) {
  const query = row.input.value.trim();
  row.controller?.abort();
  clearSuggestions(row);
  const coordinate = parseCoordinate(query);
  if (coordinate) {
    addSuggestion(row, `Use ${formatCoordinate(coordinate)}`, coordinate);
    return;
  }
  if (query.length < 3 || looksLikeCoordinateInput(query)) return;
  const controller = new AbortController();
  row.controller = controller;
  try {
    const scope = state.photonBbox ? `&bbox=${state.photonBbox}` : "&countrycode=US";
    const response = await fetch(
      `https://photon.komoot.io/api/?limit=5${scope}&q=${encodeURIComponent(query)}`,
      { signal: controller.signal, referrerPolicy: "no-referrer" },
    );
    if (!response.ok) throw new Error();
    const result = await response.json();
    if (
      row.controller !== controller ||
      row.input.value.trim() !== query ||
      !state.rows.includes(row)
    ) {
      return;
    }
    result.features.forEach((feature) => {
      const geometry = feature?.geometry?.coordinates;
      if (!Array.isArray(geometry) || geometry.length < 2) return;
      const point = [Number(geometry[1]), Number(geometry[0])];
      if (
        !point.every(Number.isFinite) ||
        Math.abs(point[0]) > 90 ||
        Math.abs(point[1]) > 180
      ) {
        return;
      }
      addSuggestion(row, featureLabel(feature) || formatCoordinate(point), point);
    });
  } catch (error) {
    if (error.name !== "AbortError") {
      setStatus("Address suggestions are unavailable. Enter latitude, longitude instead.");
    }
  }
}

function renumber() {
  state.rows.forEach((row, index) => {
    row.input.placeholder = `Origin ${index + 1}`;
    row.input.setAttribute("aria-label", `Origin ${index + 1}`);
    row.remove.setAttribute("aria-label", `Remove origin ${index + 1}`);
    row.remove.disabled = state.rows.length <= 2;
    if (row.marker) row.marker.setIcon(originIcon(row));
  });
  view.addOrigin.disabled = state.rows.length >= state.maxOrigins;
}

function addOrigin() {
  if (state.rows.length >= state.maxOrigins) return;
  const row = {
    id: state.nextRowId++,
    color: nextColor(),
    coordinate: null,
    snappedCoordinate: null,
    marker: null,
    controller: null,
    timer: null,
    input: null,
    remove: null,
    suggestions: null,
    time: null,
    activeIndex: -1,
  };
  const element = document.createElement("div");
  element.className = "origin";
  element.style.setProperty("--origin", row.color);
  const inputWrap = document.createElement("div");
  inputWrap.className = "origin-input-wrap";
  row.input = document.createElement("input");
  row.input.autocomplete = "off";
  row.input.spellcheck = false;
  row.input.setAttribute("role", "combobox");
  row.input.setAttribute("aria-autocomplete", "list");
  row.input.setAttribute("aria-haspopup", "listbox");
  row.input.setAttribute("aria-expanded", "false");
  row.time = document.createElement("span");
  row.time.className = "origin-time";
  row.time.id = `origin-time-${row.id}`;
  row.input.setAttribute("aria-describedby", row.time.id);
  row.suggestions = document.createElement("ul");
  row.suggestions.className = "suggestions";
  row.suggestions.id = `origin-suggestions-${row.id}`;
  row.suggestions.setAttribute("role", "listbox");
  row.input.setAttribute("aria-controls", row.suggestions.id);
  row.remove = document.createElement("button");
  row.remove.type = "button";
  row.remove.className = "remove";
  row.remove.textContent = "×";
  row.remove.onclick = () => {
    row.controller?.abort();
    clearTimeout(row.timer);
    row.marker?.remove();
    state.rows.splice(state.rows.indexOf(row), 1);
    element.remove();
    renumber();
    calculate();
  };
  row.input.oninput = () => {
    row.coordinate = null;
    row.snappedCoordinate = null;
    row.input.removeAttribute("title");
    row.controller?.abort();
    row.controller = null;
    clearSuggestions(row);
    row.marker?.remove();
    row.marker = null;
    clearTimeout(row.timer);
    clearResult();
    row.timer = setTimeout(() => suggest(row), 300);
    calculate();
  };
  row.input.onkeydown = (event) => {
    const options = [...row.suggestions.querySelectorAll('[role="option"]')];
    if (event.key === "ArrowDown" && options.length) {
      event.preventDefault();
      setActiveSuggestion(row, row.activeIndex + 1);
      return;
    }
    if (event.key === "ArrowUp" && options.length) {
      event.preventDefault();
      setActiveSuggestion(row, row.activeIndex < 0 ? options.length - 1 : row.activeIndex - 1);
      return;
    }
    if (event.key === "Escape") {
      clearSuggestions(row);
      return;
    }
    if (event.key !== "Enter") return;
    const coordinate = parseCoordinate(row.input.value);
    const selected = options[row.activeIndex] || options[0];
    if (coordinate) {
      event.preventDefault();
      confirmOrigin(row, formatCoordinate(coordinate), coordinate);
    } else if (selected) {
      event.preventDefault();
      selected.click();
    }
  };
  row.input.onblur = () => {
    setTimeout(() => {
      if (!row.suggestions.contains(document.activeElement)) {
        clearSuggestions(row);
      }
    }, 150);
  };
  inputWrap.append(row.input, row.time, row.suggestions);
  element.append(inputWrap, row.remove);
  view.origins.append(element);
  state.rows.push(row);
  renumber();
}

async function responseBody(response) {
  try {
    return await response.json();
  } catch {
    return { error: `Request failed with status ${response.status}.` };
  }
}

function drawResult(result, activeRows) {
  activeRows.forEach((row, index) => {
    row.snappedCoordinate = result.snapped_origins[index];
    row.input.title = `Confirmed at ${formatCoordinate(row.coordinate)}. Route begins at ${formatCoordinate(row.snappedCoordinate)}.`;
    row.time.textContent = duration(result.travel_times_seconds[index]);
    updateMarker(row);
    if (
      row.coordinate[0] !== row.snappedCoordinate[0] ||
      row.coordinate[1] !== row.snappedCoordinate[1]
    ) {
      const connector = L.polyline([row.coordinate, row.snappedCoordinate], {
        pane: "routePane",
        color: row.color,
        weight: 3,
        opacity: 0.65,
        dashArray: "2 7",
        lineCap: "round",
        interactive: false,
      }).addTo(map);
      state.layers.push(connector);
    }
  });
  result.routes.forEach((coordinates, index) => {
    const route = L.polyline(coordinates, {
      pane: "routePane",
      color: activeRows[index].color,
      weight: 5,
      opacity: 0.72,
      lineCap: "round",
      lineJoin: "round",
      interactive: false,
    }).addTo(map);
    state.layers.push(route);
  });
  const region = L.layerGroup(
    result.region.map((point) =>
      L.circleMarker(point.coordinate, {
        pane: "regionPane",
        renderer: canvas,
        radius: 7,
        stroke: false,
        fillColor: "#00A98F",
        fillOpacity: 0.27,
        interactive: false,
      }),
    ),
  ).addTo(map);
  state.layers.push(region);
  const bounds = L.latLngBounds([
    ...result.origins,
    ...result.snapped_origins,
    ...result.region.map((point) => point.coordinate),
    ...result.routes.flat(),
  ]);
  view.bestTime.textContent = duration(result.objective_seconds);
  view.result.hidden = false;
  if (bounds.isValid()) {
    map.stop();
    map.fitBounds(bounds.pad(0.12), fitOptions(14));
  }
  setStatus("One-minute region ready.");
}

async function calculate() {
  clearResult();
  const activeRows = state.rows.filter((row) => row.coordinate);
  if (activeRows.length < 2) {
    setStatus("Confirm at least two origins.");
    return;
  }
  const controller = new AbortController();
  state.request = controller;
  setStatus("Calculating the one-minute region…");
  try {
    const response = await fetch("/api/evaluations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ origins: activeRows.map((row) => row.coordinate) }),
      signal: controller.signal,
    });
    const result = await responseBody(response);
    if (!response.ok) throw new Error(result.error);
    if (state.request !== controller) return;
    drawResult(result, activeRows);
  } catch (error) {
    if (error.name !== "AbortError" && state.request === controller) {
      setStatus(error.message || "modo could not calculate these origins.");
    }
  } finally {
    if (state.request === controller) state.request = null;
  }
}

async function configure() {
  try {
    const response = await fetch("/api/config");
    const config = await responseBody(response);
    if (!response.ok) throw new Error(config.error);
    state.maxOrigins = config.max_origins;
    const [south, west, north, east] = config.core_bounds;
    state.photonBbox = [west, south, east, north].join(",");
    if (!state.rows.some((row) => row.coordinate)) {
      map.stop();
      map.fitBounds(
        [
          [south, west],
          [north, east],
        ],
        fitOptions(12),
      );
    }
    renumber();
  } catch {
    setStatus("Road coverage is unavailable. Enter latitude, longitude to retry.");
  }
}

view.addOrigin.onclick = addOrigin;
addOrigin();
addOrigin();
configure();
