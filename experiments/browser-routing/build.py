"""Build checksummed browser-routing assets from a compact modo snapshot."""

from __future__ import annotations

import json
import struct
from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path

import numpy as np
from scipy.sparse import csr_array
from scipy.sparse.csgraph import dijkstra

FORMAT_VERSION = 1
TILE_MAGIC = b"MTILE001"


def digest_bytes(value):
    return sha256(value).hexdigest()


def digest_file(path):
    return digest_bytes(Path(path).read_bytes())


def write_bytes(path, payload):
    path.write_bytes(payload)
    return {
        "url": path.name,
        "bytes": len(payload),
        "sha256": digest_bytes(payload),
    }


def write_json(path, value):
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    return write_bytes(path, payload)


def write_array(directory, filename, value, dtype):
    array = np.asarray(value, dtype=dtype)
    metadata = write_bytes(directory / filename, array.tobytes(order="C"))
    return {
        **metadata,
        "dtype": np.dtype(dtype).str,
        "length": int(array.size),
    }


def decode_vertices(value):
    encoded = json.loads(value.tobytes().decode())
    vertices = []
    for item in encoded:
        if not isinstance(item, list) or len(item) != 2 or not isinstance(item[1], str):
            raise ValueError("invalid compact vertex IDs")
        if item[0] == "string":
            vertices.append(item[1])
        elif item[0] == "integer":
            vertices.append(int(item[1]))
        else:
            raise ValueError("invalid compact vertex ID type")
    if not vertices or len(vertices) != len(set(vertices)):
        raise ValueError("compact vertex IDs must be unique")
    return tuple(vertices)


def load_source(path):
    with np.load(path, allow_pickle=False) as archive:
        if int(archive["format_version"]) != FORMAT_VERSION:
            raise ValueError("unsupported compact snapshot format")
        ids = decode_vertices(archive["vertices"])
        coordinates = np.asarray(archive["coordinates"], dtype=np.float64)
        weights = np.asarray(archive["data"], dtype=np.float64)
        heads_raw = np.asarray(archive["indices"])
        first_out_raw = np.asarray(archive["indptr"])
        directed = bool(archive["directed"])
    size = len(ids)
    if not directed:
        raise ValueError("browser-routing source must be directed")
    if (
        coordinates.shape != (size, 2)
        or np.any(~np.isfinite(coordinates))
        or np.any(np.abs(coordinates[:, 0]) > 90)
        or np.any(np.abs(coordinates[:, 1]) > 180)
    ):
        raise ValueError("invalid coordinates")
    if (
        weights.ndim != 1
        or not len(weights)
        or np.any(~np.isfinite(weights))
        or np.any(weights < 0)
    ):
        raise ValueError("weights must be finite and nonnegative")
    if (
        heads_raw.ndim != 1
        or first_out_raw.ndim != 1
        or not np.issubdtype(heads_raw.dtype, np.integer)
        or not np.issubdtype(first_out_raw.dtype, np.integer)
        or len(heads_raw) != len(weights)
        or len(first_out_raw) != size + 1
        or first_out_raw[0] != 0
        or first_out_raw[-1] != len(weights)
        or np.any(first_out_raw[1:] < first_out_raw[:-1])
        or np.any(heads_raw < 0)
        or np.any(heads_raw >= size)
    ):
        raise ValueError("invalid CSR structure")
    if size >= 2**32 or len(weights) >= 2**32:
        raise ValueError("browser-routing v1 uses uint32 graph indices")
    return {
        "ids": ids,
        "coordinates": coordinates,
        "weights": weights,
        "heads": heads_raw.astype(np.uint32),
        "first_out": first_out_raw.astype(np.uint32),
    }


def vertex_key(vertex, position):
    kind = type(vertex)
    return str(vertex), kind.__module__, kind.__qualname__, position


def canonicalize(values):
    size = len(values["ids"])
    order = np.asarray(
        sorted(range(size), key=lambda index: vertex_key(values["ids"][index], index)),
        dtype=np.uint32,
    )
    old_to_new = np.empty(size, dtype=np.uint32)
    old_to_new[order] = np.arange(size, dtype=np.uint32)
    first_out = np.zeros(size + 1, dtype=np.uint32)
    head_parts, weight_parts = [], []
    for new, old in enumerate(order):
        start, end = values["first_out"][old : old + 2]
        head_parts.append(old_to_new[values["heads"][start:end]])
        weight_parts.append(values["weights"][start:end])
        first_out[new + 1] = first_out[new] + end - start
    return {
        "ids": tuple(values["ids"][old] for old in order),
        "coordinates": values["coordinates"][order],
        "weights": np.concatenate(weight_parts).astype(np.float64),
        "heads": np.concatenate(head_parts).astype(np.uint32),
        "first_out": first_out,
    }


def full_payload(values, directory, source_sha256):
    directory.mkdir(parents=True)
    coordinates_e7 = np.rint(values["coordinates"] * 10_000_000).astype("<i4")
    if not np.array_equal(
        coordinates_e7.astype(np.float64) / 10_000_000, values["coordinates"]
    ):
        raise ValueError("coordinates must be lossless E7 values")
    arrays = {
        "weights": write_array(directory, "weights.f64", values["weights"], "<f8"),
        "heads": write_array(directory, "heads.u32", values["heads"], "<u4"),
        "first_out": write_array(
            directory, "first_out.u32", values["first_out"], "<u4"
        ),
        "coordinates_e7": write_array(
            directory, "coordinates_e7.i32", coordinates_e7, "<i4"
        ),
    }
    manifest = {
        "schema": "modo-browser-csr-v1",
        "source_sha256": source_sha256,
        "directed": True,
        "weight_unit": "seconds",
        "vertex_order": "modo-_vertex_key-v1",
        "vertices": len(values["coordinates"]),
        "arcs": len(values["weights"]),
        "arrays": arrays,
    }
    return manifest, write_json(directory / "manifest.json", manifest)


def tile_payload(values, directory, source_sha256, tile_degrees):
    directory.mkdir(parents=True)
    coordinates = values["coordinates"]
    tile_xy = np.floor((coordinates - coordinates.min(axis=0)) / tile_degrees).astype(
        np.int32
    )
    keys = sorted(set(map(tuple, tile_xy)))
    if len(keys) > np.iinfo(np.uint16).max + 1:
        raise ValueError("browser-routing v1 supports at most 65,536 tiles")
    key_to_index = {key: index for index, key in enumerate(keys)}
    vertex_to_tile = np.array(
        [key_to_index[tuple(key)] for key in tile_xy], dtype=np.uint16
    )
    arrays = {
        "vertex_to_tile": write_array(
            directory, "vertex_to_tile.u16", vertex_to_tile, "<u2"
        ),
    }
    tiles = []
    width = max(3, len(str(len(keys) - 1)))
    for tile_index, key in enumerate(keys):
        vertices = np.flatnonzero(vertex_to_tile == tile_index).astype("<u4")
        first_out = np.zeros(len(vertices) + 1, dtype="<u4")
        head_parts, weight_parts = [], []
        for local, vertex in enumerate(vertices):
            start, end = values["first_out"][vertex : vertex + 2]
            head_parts.append(values["heads"][start:end])
            weight_parts.append(values["weights"][start:end])
            first_out[local + 1] = first_out[local] + end - start
        heads = np.concatenate(head_parts).astype("<u4")
        weights = np.concatenate(weight_parts).astype("<f8")
        header = struct.pack(
            "<8sIII", TILE_MAGIC, FORMAT_VERSION, len(vertices), len(heads)
        )
        prefix = header + vertices.tobytes() + first_out.tobytes() + heads.tobytes()
        payload = prefix + b"\0" * ((-len(prefix)) % 8) + weights.tobytes()
        filename = f"tile-{tile_index:0{width}d}.bin"
        asset = write_bytes(directory / filename, payload)
        tiles.append(
            {
                **asset,
                "index": tile_index,
                "key": list(map(int, key)),
                "vertices": len(vertices),
                "arcs": len(heads),
            }
        )
    manifest = {
        "schema": "modo-browser-tiles-v1",
        "source_sha256": source_sha256,
        "directed": True,
        "weight_unit": "seconds",
        "vertex_order": "modo-_vertex_key-v1",
        "tile_degrees": tile_degrees,
        "vertices": len(coordinates),
        "arcs": len(values["weights"]),
        "arrays": arrays,
        "tiles": tiles,
    }
    return manifest, write_json(directory / "manifest.json", manifest)


def typed_id(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise TypeError("case origin IDs must be strings or integers")
    return type(value), value


def load_cases(path, values):
    document = json.loads(Path(path).read_text())
    if document.get("schema") != "modo-browser-cases-v1":
        raise ValueError("unsupported browser-routing case schema")
    cases = document.get("cases")
    if not isinstance(cases, dict) or not cases:
        raise ValueError("cases must be a nonempty object")
    indices = {typed_id(value): index for index, value in enumerate(values["ids"])}
    output = {}
    for name, case in cases.items():
        origins = case.get("origin_ids") if isinstance(case, dict) else None
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(origins, list)
            or len(origins) < 2
        ):
            raise ValueError("each case needs a name and at least two origin_ids")
        try:
            output[name] = np.asarray(
                [indices[typed_id(value)] for value in origins], dtype=np.uint32
            )
        except KeyError as error:
            raise ValueError(f"case {name!r} contains an unknown origin ID") from error
    return output


def result(matrix, ids, origins):
    distances = np.atleast_2d(dijkstra(matrix, directed=True, indices=origins))
    reachable = np.all(np.isfinite(distances), axis=0)
    vertices = np.flatnonzero(reachable)
    if not len(vertices):
        raise ValueError("case origins have no mutually reachable vertex")
    scores = np.max(distances[:, reachable], axis=0)
    objective = float(scores.min())
    best = int(vertices[scores == objective].min())
    region = vertices[scores <= objective + 60].astype("<u4")
    return {
        "origins": list(map(int, origins)),
        "objective_seconds": objective,
        "best_vertex": best,
        "best_source_id": ids[best],
        "region_vertices": len(region),
        "region_sha256_u32_le": digest_bytes(region.tobytes()),
    }


def baselines(values, cases):
    size = len(values["coordinates"])
    matrix = csr_array(
        (values["weights"], values["heads"], values["first_out"]),
        shape=(size, size),
    )
    return {
        name: result(matrix, values["ids"], origins) for name, origins in cases.items()
    }


def build(source, cases, output, tile_degrees=0.05):
    source, cases, output = Path(source), Path(cases), Path(output)
    if not np.isfinite(tile_degrees) or tile_degrees <= 0:
        raise ValueError("tile degrees must be positive and finite")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("output directory must be an empty directory")
    output.mkdir(parents=True, exist_ok=True)
    source_sha256 = digest_file(source)
    values = canonicalize(load_source(source))
    if digest_file(source) != source_sha256:
        raise RuntimeError("source snapshot changed while it was being read")
    expected = baselines(values, load_cases(cases, values))
    full, full_asset = full_payload(values, output / "full", source_sha256)
    tiled, tile_asset = tile_payload(
        values, output / "tiles", source_sha256, tile_degrees
    )
    baseline_asset = write_json(output / "baselines.json", expected)
    summary = {
        "schema": "modo-browser-build-v1",
        "source_sha256": source_sha256,
        "full_payload_bytes": sum(item["bytes"] for item in full["arrays"].values()),
        "tile_payload_bytes": sum(item["bytes"] for item in tiled["arrays"].values())
        + sum(item["bytes"] for item in tiled["tiles"]),
        "tiles": len(tiled["tiles"]),
        "cases": list(expected),
        "baselines": baseline_asset,
        "manifests": {
            "full": {**full_asset, "url": "full/manifest.json"},
            "tiles": {**tile_asset, "url": "tiles/manifest.json"},
        },
    }
    write_json(output / "build-summary.json", summary)
    return summary


def main():
    parser = ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--tile-degrees", type=float, default=0.05)
    args = parser.parse_args()
    print(
        json.dumps(
            build(args.source, args.cases, args.output, args.tile_degrees), indent=2
        )
    )


if __name__ == "__main__":
    main()
