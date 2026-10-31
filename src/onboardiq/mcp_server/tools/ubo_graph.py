"""UBO (Ultimate Beneficial Ownership) Graph Analysis Tool.

Per docs/03_ARCHITECTURE.md Section 8 and docs/06_IMPLEMENTATION_PLAN.md T15:
- Uses NetworkX directed graph to trace ownership chains.
- Calculates cumulative percentage of ownership to identify owners >= 10%.
- Detects opaque, broken, offshore trust, or nominee structures.
"""

from __future__ import annotations

from typing import Any

import networkx as nx
from pydantic import BaseModel, Field

OPAQUE_KEYWORDS = {
    "trust",
    "shadow",
    "panama",
    "bvi",
    "bearer",
    "nominee",
    "offshore",
    "anonymous",
    "shell",
    "cayman",
}


class ResolvedUBO(BaseModel):
    owner_name: str
    ownership_pct: float = Field(ge=0, le=100)
    path: list[str]
    is_individual: bool = True
    is_opaque: bool = False


class UBOResult(BaseModel):
    entity: str
    ubos: list[ResolvedUBO]
    is_opaque: bool = False
    opaque_reasons: list[str] = Field(default_factory=list)
    total_resolved_pct: float = 0.0


def resolve_ubo_graph(
    ownership_chart: dict[str, Any] | None,
    threshold_pct: float = 10.0,
) -> UBOResult:
    """Analyze corporate ownership structure using a NetworkX directed graph."""
    if not ownership_chart:
        return UBOResult(
            entity="unknown",
            ubos=[],
            is_opaque=False,
            opaque_reasons=["No ownership chart provided"],
            total_resolved_pct=0.0,
        )

    entity_name = ownership_chart.get("entity", "Company")
    graph = nx.DiGraph()

    # Two possible input structures:
    # 1. Direct 'owners' list with declared paths and percentages (standard case format)
    # 2. Graph format with 'nodes' and 'edges'
    owners_list = ownership_chart.get("owners", [])
    edges_list = ownership_chart.get("edges", [])

    if owners_list:
        # Build graph from declared owner paths
        for entry in owners_list:
            owner_name = entry.get("name", "")
            pct = float(entry.get("pct", 0.0))
            path = entry.get("path", [entity_name, owner_name])

            # Add edges along the path
            for i in range(len(path) - 1):
                u, v = path[i], path[i + 1]
                weight = pct if i == len(path) - 2 else 100.0
                graph.add_edge(u, v, weight=weight)

    elif edges_list:
        for edge in edges_list:
            u = edge.get("source")
            v = edge.get("target")
            w = float(edge.get("weight", 100.0))
            if u and v:
                graph.add_edge(u, v, weight=w)

    resolved_ubos: list[ResolvedUBO] = []
    opaque_reasons: list[str] = []
    is_structure_opaque = False

    # Traverse graph from entity_name to all leaf nodes (nodes with out_degree == 0)
    if entity_name in graph:
        leaves = [n for n in graph.nodes if graph.out_degree(n) == 0 and n != entity_name]
    else:
        leaves = []

    for leaf in leaves:
        # Find simple paths from root to this leaf
        try:
            paths = list(nx.all_simple_paths(graph, source=entity_name, target=leaf))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            paths = []

        total_leaf_pct = 0.0
        best_path: list[str] = [entity_name, leaf]

        for p in paths:
            best_path = p
            # Calculate cumulative pct along path
            mult = 1.0
            for i in range(len(p) - 1):
                edge_weight = graph[p[i]][p[i + 1]].get("weight", 100.0)
                mult *= edge_weight / 100.0
            total_leaf_pct += mult * 100.0

        leaf_lower = leaf.lower()
        node_opaque = any(kw in leaf_lower for kw in OPAQUE_KEYWORDS)
        path_opaque = any(
            any(kw in node.lower() for kw in OPAQUE_KEYWORDS) for node in best_path
        )

        if node_opaque or path_opaque:
            is_structure_opaque = True
            opaque_reasons.append(
                f"Opaque offshore entity or nominee structure identified: '{leaf}' along path {best_path}"
            )

        if total_leaf_pct >= threshold_pct:
            resolved_ubos.append(
                ResolvedUBO(
                    owner_name=leaf,
                    ownership_pct=round(total_leaf_pct, 2),
                    path=best_path,
                    is_individual=not node_opaque,
                    is_opaque=node_opaque or path_opaque,
                )
            )

    # Sort descending by ownership percentage
    resolved_ubos.sort(key=lambda u: u.ownership_pct, reverse=True)
    total_pct = sum(u.ownership_pct for u in resolved_ubos)

    return UBOResult(
        entity=entity_name,
        ubos=resolved_ubos,
        is_opaque=is_structure_opaque,
        opaque_reasons=opaque_reasons,
        total_resolved_pct=round(total_pct, 2),
    )

