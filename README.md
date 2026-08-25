# Multi Origin Distance Optimizer

`modo` optimizes WGS84 geodesic distances for lists of equally weighted
coordinates.

```python
from modo import geographic_median, minimax_center

median = geographic_median([(41.8781, -87.6298), (29.7604, -95.3698)])
center = minimax_center([(41.8781, -87.6298), (29.7604, -95.3698)])
```

`geographic_median` minimizes the sum of distances. `minimax_center` returns
only the `(latitude, longitude)` center that minimizes the greatest distance,
or equivalently the center of the smallest enclosing geodesic circle.
Coordinates use `(latitude, longitude)` order. Both return a single input as a
float tuple and return the WGS84 geodesic midpoint for two inputs. Empty,
malformed, and out-of-range inputs raise `ValueError`.

The functions target ordinary regional datasets. `minimax_center` uses
deterministic, order-independent starting points. Global inputs are supported
on a best-effort basis, but antipodal and other pathological configurations may
not have a unique answer. In particular, `minimax_center` uses numerical
optimization and can converge to a non-global solution for such inputs.

## Development

```text
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[test]"
.venv\Scripts\python -m pytest
```

