"""Automated MMIP policy discovery pipeline."""

from discovery.models import Candidate

__all__ = ["Candidate", "DiscoveryPipeline"]


def __getattr__(name: str):
    if name == "DiscoveryPipeline":
        from discovery.pipeline import DiscoveryPipeline

        return DiscoveryPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
