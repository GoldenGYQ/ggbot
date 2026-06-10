"""Tests for example pet-sprite rendering utilities."""

from __future__ import annotations

import pytest

from example.tui_frontend.pets import PetBones, list_species, render_sprite


@pytest.mark.unit
def test_list_species_non_empty() -> None:
    """list_species should include common animals like 'duck'."""
    names = list_species()
    assert 'duck' in names
    assert len(names) >= 5


@pytest.mark.unit
def test_render_sprite_replaces_eye_placeholder() -> None:
    """Rendered sprite should contain the chosen eye character."""
    bones = PetBones(species='duck', eye='@')
    lines = render_sprite(bones)
    assert any('@' in line for line in lines)

