"""Expression evolution engine — data structures.

``MutationResult``, ``CrossoverResult``, ``EvolutionResult`` dataclasses
originally defined at the top of ``evolution.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MutationResult:
    """Result of a single mutation operation."""
    expression: str
    strategy: str
    parent_expression: str = ""
    parent_score: float = 0.0
    generation: int = 0
    mutation_id: str = ""

    def to_dict(self) -> dict:
        return {
            "expression": self.expression,
            "strategy": self.strategy,
            "parent_expression": self.parent_expression,
            "parent_score": self.parent_score,
            "generation": self.generation,
            "mutation_id": self.mutation_id,
        }

@dataclass
class CrossoverResult:
    """Result of crossover between two parent expressions."""
    expression: str
    parent_a: str = ""
    parent_b: str = ""
    crossover_point: int = 0
    generation: int = 0

    def to_dict(self) -> dict:
        return {
            "expression": self.expression,
            "parent_a": self.parent_a,
            "parent_b": self.parent_b,
            "crossover_point": self.crossover_point,
            "generation": self.generation,
        }

@dataclass
class EvolutionResult:
    """Complete evolution cycle result."""
    generation: int
    population: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    best_expression: str = ""
    best_score: float = 0.0
    strategy_used: str = "EXPLORE"
    mutations: list[MutationResult] = field(default_factory=list)
    crossovers: list[CrossoverResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "generation": self.generation,
            "population_size": len(self.population),
            "best_expression": self.best_expression,
            "best_score": self.best_score,
            "strategy_used": self.strategy_used,
            "mutations": [m.to_dict() for m in self.mutations],
            "crossovers": [c.to_dict() for c in self.crossovers],
        }
