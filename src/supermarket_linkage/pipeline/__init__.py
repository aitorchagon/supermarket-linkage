"""Linkage pipeline stages and orchestrator."""

from supermarket_linkage.pipeline.base_stage import BaseStage

__all__ = [
    "BaseStage",
    "BlockingStage",
    "DistanceStage",
    "Embedder",
    "HeuristicStage",
    "LinkageOrchestrator",
    "SemanticStage",
    "cosine_similarity",
    "heuristic_pass",
    "products_to_candidates",
    "select_winner",
]


def __getattr__(name: str):
    if name == "BlockingStage":
        from supermarket_linkage.pipeline.blocking_stage import BlockingStage

        return BlockingStage
    if name == "DistanceStage":
        from supermarket_linkage.pipeline.distance_stage import DistanceStage

        return DistanceStage
    if name == "HeuristicStage":
        from supermarket_linkage.pipeline.heuristic_stage import HeuristicStage

        return HeuristicStage
    if name == "heuristic_pass":
        from supermarket_linkage.pipeline.heuristic_stage import heuristic_pass

        return heuristic_pass
    if name in {"LinkageOrchestrator", "products_to_candidates", "select_winner"}:
        from supermarket_linkage.pipeline import linkage_orchestrator as _lo

        return getattr(_lo, name)
    if name in {"Embedder", "SemanticStage", "cosine_similarity"}:
        from supermarket_linkage.pipeline import semantic_stage as _ss

        return getattr(_ss, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
