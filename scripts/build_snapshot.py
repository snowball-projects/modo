"""Compile an OSMnx-style GraphML file into modo's compact format."""

from argparse import ArgumentParser

import networkx as nx

from modo import CompactRoadGraph

parser = ArgumentParser()
parser.add_argument("source")
parser.add_argument("destination")
args = parser.parse_args()

CompactRoadGraph.from_networkx(nx.read_graphml(args.source)).save(args.destination)
