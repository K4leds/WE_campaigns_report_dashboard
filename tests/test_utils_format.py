"""Tests for the format_metric utility function."""

import sys
from pathlib import Path

# Ensure project root is on sys.path so utils can be imported
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

import pytest
import numpy as np
from utils import format_metric


class TestFormatMetric:
    def test_formats_thousands(self):
        """Values >= 1K use K suffix."""
        assert format_metric(1500) == "1.5K"

    def test_formats_millions(self):
        """Values >= 1M use M suffix."""
        assert format_metric(2500000) == "2.5M"

    def test_formats_small_numbers(self):
        """Values < 1K show full number with commas."""
        assert format_metric(999) == "999"

    def test_formats_with_unit(self):
        """Unit label appended when provided."""
        result = format_metric(45000, "SAR")
        assert result == "45.0K SAR"

    def test_handles_nan(self):
        """NaN returns N/A."""
        assert format_metric(float("nan")) == "N/A"

    def test_handles_none(self):
        """None returns N/A."""
        assert format_metric(None) == "N/A"
