const output = document.querySelector("#output");
const status = document.querySelector("#status");
const parameters = new URLSearchParams(location.search);
const summaryUrl = new URL(
  parameters.get("summary") || "generated/build-summary.json", location.href);
const caseName = parameters.get("case");

function workerRun(mode, manifestUrl, manifestSha256, origins) {
  return new Promise((resolve, reject) => {
    const worker = new Worker("worker.js", { type: "module" });
    const timer = setTimeout(() => {
      worker.terminate(); reject(new Error("worker timeout"));
    }, 120000);
    worker.onmessage = ({ data }) => {
      clearTimeout(timer); worker.terminate();
      if (data.ok) resolve(data); else reject(new Error(data.error));
    };
    worker.onerror = (event) => {
      clearTimeout(timer); worker.terminate(); reject(new Error(event.message));
    };
    worker.postMessage({
      id: crypto.randomUUID(), mode, manifestUrl, manifestSha256, origins,
    });
  });
}

async function sha256(response) {
  const buffer = await response.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  const value = [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return { buffer, value };
}

async function verifiedJson(url, metadata) {
  const response = await fetch(url, { cache: "no-store", mode: "cors" });
  if (!response.ok) throw new Error(`fetch failed (${response.status}): ${url}`);
  const result = await sha256(response);
  if (result.buffer.byteLength !== metadata.bytes || result.value !== metadata.sha256) {
    throw new Error(`checksum mismatch: ${url}`);
  }
  return JSON.parse(new TextDecoder().decode(result.buffer));
}

function comparison(actual, expected) {
  return {
    objective: Math.abs(actual.objective_seconds - expected.objective_seconds) <= 1e-9,
    best_vertex: actual.best_vertex === expected.best_vertex,
    region_count: actual.region_vertices === expected.region_vertices,
    region_hash: actual.region_sha256_u32_le === expected.region_sha256_u32_le,
  };
}

async function run() {
  status.textContent = "Running full and adaptive-tile workers...";
  const summary = await fetch(summaryUrl, { cache: "no-store" })
    .then((response) => response.json());
  if (summary.schema !== "modo-browser-build-v1") throw new Error("invalid build summary");
  const base = new URL(".", summaryUrl);
  const baselines = await verifiedJson(
    new URL(summary.baselines.url, base), summary.baselines);
  const selected = caseName || summary.cases[0];
  const expected = baselines[selected];
  if (!expected) throw new Error(`unknown case: ${selected}`);
  const fullMetadata = summary.manifests.full;
  const tileMetadata = summary.manifests.tiles;
  const fullUrl = parameters.get("full")
    || new URL(fullMetadata.url, base).href;
  const tileUrl = parameters.get("tiles")
    || new URL(tileMetadata.url, base).href;
  const fullSha256 = parameters.get("full_sha256") || fullMetadata.sha256;
  const tileSha256 = parameters.get("tiles_sha256") || tileMetadata.sha256;
  const full = await workerRun("full", fullUrl, fullSha256, expected.origins);
  const tiled = await workerRun("tiled", tileUrl, tileSha256, expected.origins);
  const result = {
    browser: navigator.userAgent,
    page_origin: location.origin,
    case: selected,
    expected,
    full: { ...full, comparison: comparison(full.result, expected) },
    tiled: { ...tiled, comparison: comparison(tiled.result, expected) },
  };
  const passed = Object.values(result.full.comparison).every(Boolean)
    && Object.values(result.tiled.comparison).every(Boolean)
    && tiled.result.exact_boundary_certificate;
  document.body.dataset.passed = String(passed);
  status.textContent = passed ? "PASS" : "FAIL";
  output.textContent = JSON.stringify(result, null, 2);
}

function fail(error) {
  document.body.dataset.passed = "false";
  status.textContent = "ERROR";
  output.textContent = error.stack || String(error);
}

document.querySelector("#run").addEventListener("click", () => run().catch(fail));
run().catch(fail);
