"""Ensure transport-layer models stay separated from runtime models."""

from __future__ import annotations

import pytest

import ggbot.models.runtime_models as runtime_models


@pytest.mark.unit
def test_runtime_models_no_transport_event_model() -> None:
    """Transport envelope should live only in transport_protocol, not in runtime_models."""
    # Guardrail: transport envelope lives in transport_protocol only.
    assert not hasattr(runtime_models, "TransportEvent")

