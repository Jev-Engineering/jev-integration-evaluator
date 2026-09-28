"""Offline graph identity fixture. Assessments never confer merge authority."""

from dataclasses import dataclass
from threading import RLock


@dataclass(frozen=True)
class Entity:
    key: str
    name: str
    jurisdiction: str
    registry_id: str | None
    provenance: str


class InMemoryGraph:
    """Minimal atomic merge adapter, not a database or production transaction."""

    def __init__(self, left: Entity, right: Entity, revision: int = 0):
        if left.key == right.key:
            raise ValueError("candidate keys must differ")
        self._lock = RLock()
        self.entities = {left.key: left, right.key: right}
        self.revision = revision
        self.merges: list[dict] = []

    def merge_if_current(self, left: Entity, right: Entity, expected_revision: int):
        """Recheck revision and record both sources under one lock."""
        with self._lock:
            if self.revision != expected_revision:
                return None
            if (self.entities.get(left.key) != left or
                    self.entities.get(right.key) != right):
                return None
            receipt = {
                "left_key": left.key,
                "right_key": right.key,
                "sources": [left.provenance, right.provenance],
                "revision_before": self.revision,
                "revision_after": self.revision + 1,
            }
            self.merges.append(receipt)
            self.revision += 1
            return receipt


def reconcile(classifier, graph, left, right, approval, expected_revision):
    """Only an approved, current, exact `same` assessment may reach the adapter."""
    hypothesis = classifier.classify(left, right)
    if hypothesis != "same" or approval is not True:
        return None
    return graph.merge_if_current(left, right, expected_revision)
