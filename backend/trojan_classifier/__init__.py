"""Trojan classifier module using Graph Neural Networks."""

from trojan_detector.backend.trojan_classifier.classifier import TrojanClassifier
from trojan_detector.backend.trojan_classifier.models import ClassificationResult, TrojanVerdict

__all__ = ["TrojanClassifier", "ClassificationResult", "TrojanVerdict"]
