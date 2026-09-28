"""Offline graph identity fixture. Assessments never confer merge authority."""

from dataclasses import dataclass
from asyncio import CancelledError
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

    def merge_if_current(self, left: Entity, right: Entity, expected_revision: int, audit=None):
        """Recheck revision and run any pre-merge audit before mutation, under one lock."""
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
            if audit is not None:
                try:
                    audit(receipt)
                except (Exception, CancelledError):
                    return None
            self.merges.append(receipt)
            self.revision += 1
            return receipt


def reconcile(classifier, graph, left, right, approval, expected_revision, *, audit=None):
    """Only an approved, current, exact `same` assessment may reach the adapter."""
    try:
        hypothesis = classifier.classify(left, right)
    except (Exception, CancelledError):
        return None
    if type(hypothesis) is not str or hypothesis != "same" or approval is not True:
        return None
    return graph.merge_if_current(left, right, expected_revision, audit=audit)
