"""GNN architecture implementations for trojan classification."""

from backend.trojan_classifier.architectures.gat import GATClassifier
from backend.trojan_classifier.architectures.gcn import GCNClassifier
from backend.trojan_classifier.architectures.gin import GINClassifier

__all__ = ["GCNClassifier", "GATClassifier", "GINClassifier"]
