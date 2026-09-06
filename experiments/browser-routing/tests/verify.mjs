import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

globalThis.self = {
  crossOriginIsolated: false,
  location: { href: pathToFileURL(resolve("index.html")).href },
};
globalThis.fetch = async (input) => {
  const url = input instanceof URL ? input : new URL(input);
  if (url.protocol !== "file:") return new Response(null, { status: 400 });
  try {
    return new Response(await readFile(fileURLToPath(url)), { status: 200 });
  } catch {
    return new Response(null, { status: 404 });
  }
};

const summaryPath = resolve(process.argv[2]);
const summaryUrl = pathToFileURL(summaryPath);
const summary = JSON.parse(await readFile(summaryPath, "utf8"));
const base = pathToFileURL(`${dirname(summaryPath)}/`);
const baselines = JSON.parse(await readFile(
  fileURLToPath(new URL(summary.baselines.url, base)), "utf8"));
const expected = baselines[summary.cases[0]];
const { runMessage } = await import("../site/worker.js");

async function run(mode) {
  const metadata = summary.manifests[mode === "full" ? "full" : "tiles"];
  return runMessage({
    id: mode,
    mode,
    manifestUrl: new URL(metadata.url, base).href,
    manifestSha256: metadata.sha256,
    origins: expected.origins,
  });
}

function exact(actual) {
  return actual.objective_seconds === expected.objective_seconds
    && actual.best_vertex === expected.best_vertex
    && actual.region_vertices === expected.region_vertices
    && actual.region_sha256_u32_le === expected.region_sha256_u32_le;
}

const full = await run("full");
const tiled = await run("tiled");
assert(full.ok && full.worker && exact(full.result), "full Worker result differs from SciPy");
assert(tiled.ok && tiled.worker && exact(tiled.result), "tiled Worker result differs from SciPy");
assert(tiled.result.exact_boundary_certificate, "tiled result lacks exactness certificate");

const unpinned = await runMessage({
  id: "unpinned",
  mode: "full",
  manifestUrl: new URL(summary.manifests.full.url, base).href,
  origins: expected.origins,
});
assert(!unpinned.ok && unpinned.error.includes("pin is required"), "missing pin was accepted");

const fullManifestPath = fileURLToPath(new URL(summary.manifests.full.url, base));
const fullManifest = JSON.parse(await readFile(fullManifestPath, "utf8"));
const weightsPath = resolve(dirname(fullManifestPath), fullManifest.arrays.weights.url);
const originalWeights = await readFile(weightsPath);
const changedWeights = Buffer.from(originalWeights);
changedWeights[0] ^= 1;
try {
  await writeFile(weightsPath, changedWeights);
  const corrupted = await run("full");
  assert(!corrupted.ok && corrupted.error.includes("checksum mismatch"),
    "corrupted array was accepted");
} finally {
  await writeFile(weightsPath, originalWeights);
}

console.log(JSON.stringify({
  passed: true,
  objective_seconds: full.result.objective_seconds,
  best_vertex: full.result.best_vertex,
  tiles_loaded: tiled.result.tiles_loaded,
}));
