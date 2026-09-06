# Time-dependent traffic experiment

This offline experiment tests three semantics before any provider or production
engine is selected:

- each piecewise-linear edge profile is FIFO, so leaving an edge later cannot
  produce an earlier arrival;
- every origin shares one departure time and the minimax result can change with
  that time; and
- constant profiles exactly reproduce modo's current static minimax result and
  fixed 60-second region on the synthetic graph.

The candidate search interleaves one FIFO shortest-path frontier per origin.
The first vertex reached by every frontier establishes the exact minimax
radius. It then settles only labels through that radius plus 60 seconds, which
is enough to return the complete region. A reference implementation still
calculates full distance fields as a test oracle. A graph with a long remote
tail proves the bounded search returns the same result without visiting that
irrelevant tail.

Run it from the modo repository root:

```sh
uv run --locked python -m pytest experiments/time_dependent_traffic
uv run --locked python experiments/time_dependent_traffic/experiment.py
```

The four-vertex graph is deliberately tiny and deterministic. Its changing
profile represents synthetic congestion, not live or historical traffic. The
experiment validates model behavior only. It is not a production architecture,
provider integration, or performance benchmark. Exact searches can still touch
most of a graph when the origins or qualifying region are broad; production
road hierarchies and partitioning remain separate performance work.
