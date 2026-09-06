"""Create a tiny directed compact graph and external browser-routing cases."""

import json
from argparse import ArgumentParser
from pathlib import Path

import numpy as np


def build(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    vertices = ("f", "b", "d", "a", "e", "c")
    coordinates_by_id = {
        "a": (41.00, -88.00),
        "b": (41.00, -87.98),
        "c": (41.00, -87.94),
        "d": (41.04, -87.94),
        "e": (41.06, -87.94),
        "f": (41.06, -87.88),
    }
    edges = (
        ("a", "b", 10),
        ("b", "a", 12),
        ("b", "c", 10),
        ("c", "b", 12),
        ("c", "d", 10),
        ("d", "c", 12),
        ("d", "e", 10),
        ("e", "d", 12),
        ("e", "f", 10),
        ("f", "e", 12),
    )
    indices = {vertex: index for index, vertex in enumerate(vertices)}
    rows = [[] for _vertex in vertices]
    for start, end, weight in edges:
        rows[indices[start]].append((indices[end], weight))
    heads, weights, first_out = [], [], [0]
    for row in rows:
        for head, weight in sorted(row):
            heads.append(head)
            weights.append(weight)
        first_out.append(len(heads))
    encoded = np.frombuffer(
        json.dumps(
            [["string", vertex] for vertex in vertices], separators=(",", ":")
        ).encode(),
        dtype=np.uint8,
    )
    source = directory / "synthetic.npz"
    with source.open("wb") as output:
        np.savez_compressed(
            output,
            format_version=np.array(1, dtype=np.uint8),
            vertices=encoded,
            coordinates=np.asarray(
                [coordinates_by_id[vertex] for vertex in vertices], dtype=np.float64
            ),
            data=np.asarray(weights, dtype=np.float64),
            indices=np.asarray(heads, dtype=np.int32),
            indptr=np.asarray(first_out, dtype=np.int32),
            directed=np.array(True, dtype=np.bool_),
        )
    cases = directory / "cases.json"
    cases.write_text(
        json.dumps(
            {
                "schema": "modo-browser-cases-v1",
                "cases": {
                    "ends": {"origin_ids": ["a", "f"]},
                    "inside": {"origin_ids": ["b", "e"]},
                },
            },
            indent=2,
        )
        + "\n"
    )
    return source, cases


def main():
    parser = ArgumentParser()
    parser.add_argument("--directory", required=True)
    args = parser.parse_args()
    build(args.directory)


if __name__ == "__main__":
    main()
