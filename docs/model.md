# Mathematical model

MODO optimizes driving time on a road graph.

## Road graph

$$
G=(V,E)
$$

$V$ is the set of road vertices and $E$ is the set of road edges. Each edge has
a permitted direction and a nonnegative travel-time cost in seconds. This
represents one-way roads and different travel times in opposite directions.

For origins $o_1,\ldots,o_n$, define

$$
d_G(o_i,v)
$$

as the shortest driving time from origin $o_i$ to vertex $v$. MODO evaluates
the mutually reachable vertices

$$
R=\{v\in V\mid d_G(o_i,v)<\infty\text{ for every }i\}.
$$

## Total-time mode

The total and average travel times to vertex $v$ are

$$
T(v)=\sum_{i=1}^{n}d_G(o_i,v),
\qquad
A(v)=\frac{T(v)}{n}.
$$

They select the same optimum:

$$
v_T^*=\arg\min_{v\in R}T(v),
\qquad
T^*=T(v_T^*).
$$

For a tolerance of $\Delta$ seconds per traveler, the near-optimal region is

$$
S_{T,\Delta}
=\{v\in R\mid A(v)\le A^*+\Delta\}
=\{v\in R\mid T(v)\le T^*+n\Delta\}.
$$

A 60-second tolerance means the average trip is within one minute of the best
average, allowing $60n$ seconds of additional group total time.

## Maximum-time mode

The longest individual trip to vertex $v$ is

$$
M(v)=\max_{1\le i\le n}d_G(o_i,v).
$$

The optimum and near-optimal region are

$$
v_M^*=\arg\min_{v\in R}M(v),
\qquad
M^*=M(v_M^*),
$$

$$
S_{M,\Delta}=\{v\in R\mid M(v)\le M^*+\Delta\}.
$$

A 60-second tolerance keeps the longest trip within one minute of the best
possible longest trip.

Define origin $i$'s road-network isochrone as

$$
B_i(r)=\{v\in V\mid d_G(o_i,v)\le r\}.
$$

The maximum-time optimum and region can then be written as

$$
M^*=\min\{r\mid\bigcap_i B_i(r)\ne\varnothing\},
\qquad
S_{M,\Delta}=\bigcap_i B_i(M^*+\Delta).
$$

## Region

The near-optimal region is MODO's mathematical result. It may be a cluster, a
road corridor, several disconnected components, or a single vertex. MODO also
selects one exact optimum as a representative when a single coordinate is
useful, but that point is not the only meaningful result.

Geographic centers and pairwise midpoints can be useful search seeds or visual
references. They are not safe boundaries for a road optimum or its region.

## Static and time-dependent costs

The current implementation uses constant edge costs:

$$
w_e=\text{constant}.
$$

It runs one shortest-path search per origin and exactly evaluates every vertex
in $R$ under the supplied graph and weights.

Future traffic-aware routing changes the edge cost to

$$
w_e(t)=\text{time to traverse edge }e\text{ when entered at time }t
$$

and makes routes, objectives, and regions time-specific:

$$
d_G(o_i,v;t_0),
$$

$$
T(v,t_0)=\sum_{i=1}^{n}d_G(o_i,v;t_0),
\qquad
M(v,t_0)=\max_{1\le i\le n}d_G(o_i,v;t_0),
$$

$$
S_\Delta(t_0)=\{v\mid f(v,t_0)\le f^*(t_0)+\Delta\}.
$$

Here $t_0$ is a requested departure time and $f$ is the selected objective.
For a required arrival time $T$, let $L_i(v,T)$ be origin $i$'s latest feasible
departure time. Its trip duration is

$$
D_i(v,T)=T-L_i(v,T).
$$

A time-dependent model should satisfy the FIFO property

$$
t_2\ge t_1\Rightarrow t_2+w_e(t_2)\ge t_1+w_e(t_1),
$$

so entering an edge later cannot produce an earlier exit. Time-dependent costs,
depart-at, and arrive-by are not implemented yet.
