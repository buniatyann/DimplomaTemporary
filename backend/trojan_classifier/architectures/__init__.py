"""GNN architecture implementations for trojan classification."""

from trojan_detector.backend.trojan_classifier.architectures.gat import GATClassifier
from trojan_detector.backend.trojan_classifier.architectures.gcn import GCNClassifier
from trojan_detector.backend.trojan_classifier.architectures.gin import GINClassifier

__all__ = ["GCNClassifier", "GATClassifier", "GINClassifier"]
