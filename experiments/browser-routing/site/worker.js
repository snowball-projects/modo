import { evaluateFull, evaluateTiled } from "./engine.js";

export async function runMessage(data) {
  const { id, mode, manifestUrl, manifestSha256, origins } = data;
  try {
    if (mode !== "full" && mode !== "tiled") throw new Error("unknown routing mode");
    const result = mode === "full"
      ? await evaluateFull(manifestUrl, manifestSha256, origins)
      : await evaluateTiled(manifestUrl, manifestSha256, origins);
    return {
      id,
      ok: true,
      worker: true,
      cross_origin_isolated: self.crossOriginIsolated === true,
      result,
    };
  } catch (error) {
    return { id, ok: false, error: error instanceof Error ? error.stack : String(error) };
  }
}

if (typeof self !== "undefined" && "postMessage" in self) {
  self.onmessage = async (event) => self.postMessage(await runMessage(event.data));
}
