const TYPES = {
  "<f8": Float64Array,
  "<u4": Uint32Array,
  "<i4": Int32Array,
  "<u2": Uint16Array,
};
const SHA256 = /^[0-9a-f]{64}$/;

function now() { return performance.now(); }

function hex(bytes) {
  return [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
}

async function hash(buffer) {
  return hex(new Uint8Array(await crypto.subtle.digest("SHA-256", buffer)));
}

function integer(value, name, minimum = 0) {
  if (!Number.isSafeInteger(value) || value < minimum) throw new Error(`invalid ${name}`);
  return value;
}

function assetMetadata(value, dtype, length, name) {
  const Type = TYPES[dtype];
  if (!value || value.dtype !== dtype || value.length !== length
      || value.bytes !== length * Type.BYTES_PER_ELEMENT
      || typeof value.url !== "string" || !value.url || !SHA256.test(value.sha256)) {
    throw new Error(`invalid ${name} metadata`);
  }
}

async function fetchBuffer(url) {
  const response = await fetch(url, { cache: "no-store", mode: "cors" });
  if (!response.ok) throw new Error(`fetch failed (${response.status}): ${url}`);
  return response.arrayBuffer();
}

async function verifiedBuffer(url, metadata) {
  const buffer = await fetchBuffer(url);
  if (buffer.byteLength !== metadata.bytes) throw new Error(`wrong byte length: ${url}`);
  if (await hash(buffer) !== metadata.sha256) throw new Error(`checksum mismatch: ${url}`);
  return buffer;
}

async function arrayAsset(base, metadata) {
  const Type = TYPES[metadata.dtype];
  const buffer = await verifiedBuffer(new URL(metadata.url, base), metadata);
  const value = new Type(buffer);
  if (value.length !== metadata.length) throw new Error(`wrong array length: ${metadata.url}`);
  return value;
}

async function manifest(url, expectedSchema, expectedSha256) {
  if (!SHA256.test(expectedSha256 || "")) throw new Error("manifest SHA-256 pin is required");
  const buffer = await fetchBuffer(url);
  if (await hash(buffer) !== expectedSha256) throw new Error("manifest checksum mismatch");
  let value;
  try {
    value = JSON.parse(new TextDecoder().decode(buffer));
  } catch (error) {
    throw new Error("invalid graph manifest JSON", { cause: error });
  }
  if (value.schema !== expectedSchema || !value.directed || value.weight_unit !== "seconds"
      || value.vertex_order !== "modo-_vertex_key-v1" || !SHA256.test(value.source_sha256 || "")) {
    throw new Error("unsupported graph manifest");
  }
  integer(value.vertices, "vertex count", 1);
  integer(value.arcs, "arc count", 1);
  return value;
}

function validateOrigins(origins, vertices) {
  if (!Array.isArray(origins) || origins.length < 2) throw new Error("at least two origins are required");
  for (const origin of origins) {
    if (!Number.isInteger(origin) || origin < 0 || origin >= vertices) {
      throw new Error("invalid origin vertex");
    }
  }
}

function validateCsr(weights, heads, firstOut, rows, headLimit, arcs) {
  if (firstOut.length !== rows + 1 || firstOut[0] !== 0 || firstOut[rows] !== arcs) {
    throw new Error("invalid CSR offsets");
  }
  for (let index = 0; index < arcs; index++) {
    if (heads[index] >= headLimit
        || !Number.isFinite(weights[index]) || weights[index] < 0) {
      throw new Error("invalid CSR arc");
    }
  }
  for (let index = 1; index < firstOut.length; index++) {
    if (firstOut[index] < firstOut[index - 1]) throw new Error("invalid CSR row order");
  }
}

class Heap {
  constructor() { this.nodes = []; this.costs = []; }
  push(node, cost) {
    let index = this.nodes.length;
    this.nodes.push(node); this.costs.push(cost);
    while (index) {
      const parent = (index - 1) >> 1;
      if (this.costs[parent] <= cost) break;
      this.nodes[index] = this.nodes[parent];
      this.costs[index] = this.costs[parent];
      index = parent;
    }
    this.nodes[index] = node; this.costs[index] = cost;
  }
  pop() {
    if (!this.nodes.length) return null;
    const node = this.nodes[0], cost = this.costs[0];
    const lastNode = this.nodes.pop(), lastCost = this.costs.pop();
    if (this.nodes.length) {
      let index = 0;
      while (true) {
        let child = index * 2 + 1;
        if (child >= this.nodes.length) break;
        if (child + 1 < this.nodes.length && this.costs[child + 1] < this.costs[child]) child++;
        if (this.costs[child] >= lastCost) break;
        this.nodes[index] = this.nodes[child];
        this.costs[index] = this.costs[child];
        index = child;
      }
      this.nodes[index] = lastNode; this.costs[index] = lastCost;
    }
    return [node, cost];
  }
}

function fullDijkstra(weights, heads, firstOut, origin) {
  const distance = new Float64Array(firstOut.length - 1); distance.fill(Infinity);
  const settled = new Uint8Array(distance.length);
  const queue = new Heap();
  distance[origin] = 0; queue.push(origin, 0);
  while (queue.nodes.length) {
    const [vertex, cost] = queue.pop();
    if (settled[vertex] || cost !== distance[vertex]) continue;
    settled[vertex] = 1;
    for (let edge = firstOut[vertex]; edge < firstOut[vertex + 1]; edge++) {
      const target = heads[edge], proposal = cost + weights[edge];
      if (proposal < distance[target]) { distance[target] = proposal; queue.push(target, proposal); }
    }
  }
  return distance;
}

async function summarize(maximum, reachable, tolerance = 60) {
  let objective = Infinity, bestVertex = -1;
  for (let vertex = 0; vertex < maximum.length; vertex++) {
    if (!reachable[vertex]) continue;
    const score = maximum[vertex];
    if (score < objective) { objective = score; bestVertex = vertex; }
  }
  if (!Number.isFinite(objective)) return null;
  const region = [];
  for (let vertex = 0; vertex < maximum.length; vertex++) {
    if (reachable[vertex] && maximum[vertex] <= objective + tolerance) region.push(vertex);
  }
  const values = Uint32Array.from(region);
  return {
    objective_seconds: objective,
    best_vertex: bestVertex,
    region_vertices: values.length,
    region_sha256_u32_le: await hash(values.buffer),
  };
}

export async function evaluateFull(manifestUrl, manifestSha256, origins) {
  const loadStart = now();
  const metadata = await manifest(manifestUrl, "modo-browser-csr-v1", manifestSha256);
  validateOrigins(origins, metadata.vertices);
  const arrays = metadata.arrays;
  if (!arrays || Object.keys(arrays).sort().join(",") !== "coordinates_e7,first_out,heads,weights") {
    throw new Error("invalid full array catalog");
  }
  assetMetadata(arrays.weights, "<f8", metadata.arcs, "weights");
  assetMetadata(arrays.heads, "<u4", metadata.arcs, "heads");
  assetMetadata(arrays.first_out, "<u4", metadata.vertices + 1, "first_out");
  assetMetadata(arrays.coordinates_e7, "<i4", metadata.vertices * 2, "coordinates_e7");
  const base = new URL(manifestUrl, self.location.href);
  const entries = await Promise.all(Object.entries(arrays).map(
    async ([name, item]) => [name, await arrayAsset(base, item)]
  ));
  const loaded = Object.fromEntries(entries);
  validateCsr(
    loaded.weights, loaded.heads, loaded.first_out,
    metadata.vertices, metadata.vertices, metadata.arcs,
  );
  for (let vertex = 0; vertex < metadata.vertices; vertex++) {
    const latitude = loaded.coordinates_e7[vertex * 2] / 10_000_000;
    const longitude = loaded.coordinates_e7[vertex * 2 + 1] / 10_000_000;
    if (Math.abs(latitude) > 90 || Math.abs(longitude) > 180) {
      throw new Error("invalid graph coordinate");
    }
  }
  const loadMs = now() - loadStart;
  const computeStart = now();
  const maximum = new Float64Array(metadata.vertices);
  const reachable = new Uint8Array(metadata.vertices); reachable.fill(1);
  for (const origin of origins) {
    const distance = fullDijkstra(
      loaded.weights, loaded.heads, loaded.first_out, origin);
    for (let vertex = 0; vertex < metadata.vertices; vertex++) {
      if (!Number.isFinite(distance[vertex])) reachable[vertex] = 0;
      else if (distance[vertex] > maximum[vertex]) maximum[vertex] = distance[vertex];
    }
  }
  const result = await summarize(maximum, reachable);
  if (!result) throw new Error("origins have no common reachable vertex");
  return {
    mode: "full",
    exact_over: metadata.source_sha256,
    loaded_bytes: Object.values(arrays).reduce((sum, item) => sum + item.bytes, 0),
    load_ms: loadMs,
    compute_ms: now() - computeStart,
    ...result,
  };
}

function parseTile(buffer, expected, globalVertices) {
  const view = new DataView(buffer);
  const magic = new TextDecoder().decode(new Uint8Array(buffer, 0, 8));
  const version = view.getUint32(8, true);
  const vertices = view.getUint32(12, true), arcs = view.getUint32(16, true);
  if (magic !== "MTILE001" || version !== 1
      || vertices !== expected.vertices || arcs !== expected.arcs) {
    throw new Error(`invalid tile ${expected.index}`);
  }
  const vertexOffset = 20;
  const firstOutOffset = vertexOffset + vertices * 4;
  const headOffset = firstOutOffset + (vertices + 1) * 4;
  const weightOffset = (headOffset + arcs * 4 + 7) & ~7;
  if (weightOffset + arcs * 8 !== buffer.byteLength) {
    throw new Error(`invalid tile size ${expected.index}`);
  }
  const tile = {
    index: expected.index,
    vertices: new Uint32Array(buffer, vertexOffset, vertices),
    firstOut: new Uint32Array(buffer, firstOutOffset, vertices + 1),
    heads: new Uint32Array(buffer, headOffset, arcs),
    weights: new Float64Array(buffer, weightOffset, arcs),
    bytes: buffer.byteLength,
  };
  validateCsr(
    tile.weights, tile.heads, tile.firstOut, vertices, globalVertices, arcs,
  );
  for (const vertex of tile.vertices) {
    if (vertex >= globalVertices) throw new Error(`invalid tile vertex ${expected.index}`);
  }
  return tile;
}

function validateTileManifest(metadata) {
  const arrays = metadata.arrays;
  if (!arrays || Object.keys(arrays).join(",") !== "vertex_to_tile") {
    throw new Error("invalid tile array catalog");
  }
  assetMetadata(arrays.vertex_to_tile, "<u2", metadata.vertices, "vertex_to_tile");
  if (!Number.isFinite(metadata.tile_degrees) || metadata.tile_degrees <= 0
      || !Array.isArray(metadata.tiles) || !metadata.tiles.length
      || metadata.tiles.length > 65_536) {
    throw new Error("invalid tile catalog");
  }
  let vertices = 0, arcs = 0;
  metadata.tiles.forEach((tile, index) => {
    integer(tile.vertices, `tile ${index} vertex count`, 1);
    integer(tile.arcs, `tile ${index} arc count`);
    if (tile.index !== index || typeof tile.url !== "string" || !tile.url
        || !Number.isSafeInteger(tile.bytes) || tile.bytes < 24
        || !SHA256.test(tile.sha256 || "")) {
      throw new Error(`invalid tile metadata ${index}`);
    }
    vertices += tile.vertices; arcs += tile.arcs;
  });
  if (vertices !== metadata.vertices || arcs !== metadata.arcs) {
    throw new Error("tile catalog dimensions do not match graph");
  }
}

function localGraph(loaded, globalVertices) {
  const tiles = [...loaded.values()].sort((a, b) => a.index - b.index);
  const count = tiles.reduce((sum, tile) => sum + tile.vertices.length, 0);
  const globals = new Uint32Array(count);
  const tileIndex = new Uint16Array(count), tileRow = new Uint32Array(count);
  const globalToLocal = new Int32Array(globalVertices); globalToLocal.fill(-1);
  let local = 0;
  for (const tile of tiles) {
    for (let row = 0; row < tile.vertices.length; row++, local++) {
      const global = tile.vertices[row];
      if (globalToLocal[global] >= 0) throw new Error("vertex appears in multiple tiles");
      globals[local] = global; tileIndex[local] = tile.index;
      tileRow[local] = row; globalToLocal[global] = local;
    }
  }
  return { globals, tileIndex, tileRow, globalToLocal, loaded };
}

function localDijkstra(graph, originGlobal, limit = Infinity) {
  const origin = graph.globalToLocal[originGlobal];
  if (origin < 0) throw new Error("origin tile is not loaded");
  const distance = new Float64Array(graph.globals.length); distance.fill(Infinity);
  const settled = new Uint8Array(distance.length), boundaryTargets = new Set();
  const queue = new Heap(); distance[origin] = 0; queue.push(origin, 0);
  while (queue.nodes.length) {
    const [vertex, cost] = queue.pop();
    if (cost > limit) break;
    if (settled[vertex] || cost !== distance[vertex]) continue;
    settled[vertex] = 1;
    const tile = graph.loaded.get(graph.tileIndex[vertex]), row = graph.tileRow[vertex];
    for (let edge = tile.firstOut[row]; edge < tile.firstOut[row + 1]; edge++) {
      const proposal = cost + tile.weights[edge];
      if (proposal > limit) continue;
      const targetGlobal = tile.heads[edge], target = graph.globalToLocal[targetGlobal];
      if (target < 0) { boundaryTargets.add(targetGlobal); continue; }
      if (proposal < distance[target]) { distance[target] = proposal; queue.push(target, proposal); }
    }
  }
  return { distance, boundaryTargets };
}

async function localSummary(graph, origins) {
  const maximum = new Float64Array(graph.globals.length);
  const reachable = new Uint8Array(graph.globals.length); reachable.fill(1);
  const boundaryTargets = new Set();
  for (const origin of origins) {
    const result = localDijkstra(graph, origin);
    for (const target of result.boundaryTargets) boundaryTargets.add(target);
    for (let local = 0; local < graph.globals.length; local++) {
      const value = result.distance[local];
      if (!Number.isFinite(value)) reachable[local] = 0;
      else if (value > maximum[local]) maximum[local] = value;
    }
  }
  let objective = Infinity, bestGlobal = -1;
  for (let local = 0; local < graph.globals.length; local++) {
    if (!reachable[local]) continue;
    const global = graph.globals[local], score = maximum[local];
    if (score < objective || (score === objective && global < bestGlobal)) {
      objective = score; bestGlobal = global;
    }
  }
  if (!Number.isFinite(objective)) return { summary: null, boundaryTargets };
  const region = [];
  for (let local = 0; local < graph.globals.length; local++) {
    if (reachable[local] && maximum[local] <= objective + 60) {
      region.push(graph.globals[local]);
    }
  }
  region.sort((a, b) => a - b);
  const values = Uint32Array.from(region);
  return {
    summary: {
      objective_seconds: objective,
      best_vertex: bestGlobal,
      region_vertices: values.length,
      region_sha256_u32_le: await hash(values.buffer),
    },
    boundaryTargets,
  };
}

export async function evaluateTiled(manifestUrl, manifestSha256, origins) {
  const loadStart = now();
  const metadata = await manifest(
    manifestUrl, "modo-browser-tiles-v1", manifestSha256);
  validateOrigins(origins, metadata.vertices);
  validateTileManifest(metadata);
  const base = new URL(manifestUrl, self.location.href);
  const vertexToTile = await arrayAsset(base, metadata.arrays.vertex_to_tile);
  for (const tile of vertexToTile) {
    if (tile >= metadata.tiles.length) throw new Error("invalid vertex-to-tile index");
  }
  const loaded = new Map();
  let loadedBytes = metadata.arrays.vertex_to_tile.bytes;
  async function loadTiles(indices) {
    const missing = [...new Set(indices)].filter((index) => !loaded.has(index));
    await Promise.all(missing.map(async (index) => {
      const item = metadata.tiles[index];
      if (!item) throw new Error(`unknown tile ${index}`);
      const buffer = await verifiedBuffer(new URL(item.url, base), item);
      const tile = parseTile(buffer, item, metadata.vertices);
      for (const vertex of tile.vertices) {
        if (vertexToTile[vertex] !== index) throw new Error(`wrong tile for vertex ${vertex}`);
      }
      loaded.set(index, tile); loadedBytes += item.bytes;
    }));
    return missing.length;
  }
  await loadTiles(origins.map((origin) => vertexToTile[origin]));
  const initialLoadMs = now() - loadStart;
  const computeStart = now();
  let rounds = 0, result = null;
  while (rounds++ <= metadata.tiles.length) {
    const graph = localGraph(loaded, metadata.vertices);
    const provisional = await localSummary(graph, origins);
    if (!provisional.summary) {
      const targets = [...provisional.boundaryTargets];
      if (!targets.length) throw new Error("origins have no common reachable vertex");
      await loadTiles(targets.map((target) => vertexToTile[target]));
      continue;
    }
    const limit = provisional.summary.objective_seconds + 60;
    const boundaryTargets = new Set();
    for (const origin of origins) {
      const bounded = localDijkstra(graph, origin, limit);
      for (const target of bounded.boundaryTargets) boundaryTargets.add(target);
    }
    const added = await loadTiles(
      [...boundaryTargets].map((target) => vertexToTile[target]));
    if (!added) { result = provisional.summary; break; }
  }
  if (!result) throw new Error("tile expansion did not converge");
  return {
    mode: "adaptive-tiles",
    exact_over: metadata.source_sha256,
    exact_boundary_certificate: true,
    tiles_loaded: loaded.size,
    tile_rounds: rounds,
    loaded_bytes: loadedBytes,
    initial_load_ms: initialLoadMs,
    total_ms: now() - loadStart,
    compute_ms: now() - computeStart,
    ...result,
  };
}
