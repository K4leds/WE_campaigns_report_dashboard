# tests/test_verification.py
import pytest
import pandas as pd
import numpy as np
from dashboard.verification import create_audit_trail, validate_metric, get_audit_tooltip


class TestAuditTrail:
    def test_creates_audit_entry(self):
        entry = create_audit_trail(
            metric_name="AOV",
            formula="Revenue ÷ Unique Conversions",
            inputs={"Revenue": 45000.0, "Unique Conversions": 320.0},
            result=140.625
        )
        assert entry["metric_name"] == "AOV"
        assert entry["formula"] == "Revenue ÷ Unique Conversions"
        assert entry["inputs"]["Revenue"] == 45000.0
        assert entry["result"] == 140.625
        assert "timestamp" in entry
