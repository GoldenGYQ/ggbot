from ggbot.ui.pets import PetBones, list_species, render_sprite


def test_list_species_non_empty() -> None:
    names = list_species()
    assert 'duck' in names
    assert len(names) >= 5


def test_render_sprite_replaces_eye_placeholder() -> None:
    bones = PetBones(species='duck', eye='@')
    lines = render_sprite(bones)
    assert any('@' in line for line in lines)
