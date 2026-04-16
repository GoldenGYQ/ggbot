from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Species = Literal[
    'duck',
    'goose',
    'blob',
    'cat',
    'dragon',
    'octopus',
    'owl',
    'penguin',
    'turtle',
    'snail',
    'ghost',
    'axolotl',
    'capybara',
    'cactus',
    'robot',
    'rabbit',
    'mushroom',
    'chonk',
    'jlu',
]


Hat = Literal['none', 'crown', 'tophat', 'propeller', 'halo', 'wizard', 'beanie', 'tinyduck']


@dataclass(frozen=True)
class PetBones:
    species: Species
    eye: str = 'o'
    hat: Hat = 'none'


# Each sprite is 5 lines tall, 12 wide (after {E}→1char substitution).
# Multiple frames per species for idle fidget animation.
# Line 0 is the hat slot — must be blank in frames 0-1; frame 2 may use it.
BODIES: dict[Species, list[list[str]]] = {
    'duck': [
        [
            '            ',
            '    __      ',
            '  <({E} )___  ',
            '   (  ._>   ',
            '    `--´    ',
        ],
        [
            '            ',
            '    __      ',
            '  <({E} )___  ',
            '   (  ._>   ',
            '    `--´~   ',
        ],
        [
            '            ',
            '    __      ',
            '  <({E} )___  ',
            '   (  .__>  ',
            '    `--´    ',
        ],
    ],
    'jlu': [
         []
    ],
    'goose': [
        [
            '            ',
            '     ({E}>    ',
            '     ||     ',
            '   _(__)_   ',
            '    ^^^^    ',
        ],
        [
            '            ',
            '    ({E}>     ',
            '     ||     ',
            '   _(__)_   ',
            '    ^^^^    ',
        ],
        [
            '            ',
            '     ({E}>>   ',
            '     ||     ',
            '   _(__)_   ',
            '    ^^^^    ',
        ],
    ],
    'blob': [
        [
            '            ',
            '   .----.   ',
            '  ( {E}  {E} )  ',
            '  (      )  ',
            '   `----´   ',
        ],
        [
            '            ',
            '  .------.  ',
            ' (  {E}  {E}  ) ',
            ' (        ) ',
            '  `------´  ',
        ],
        [
            '            ',
            '    .--.    ',
            '   ({E}  {E})   ',
            '   (    )   ',
            '    `--´    ',
        ],
    ],
    'cat': [
        [
            '            ',
            '   /\\_/\\    ',
            '  ( {E}   {E})  ',
            '  (  ω  )   ',
            '  (")_(")   ',
        ],
        [
            '            ',
            '   /\\_/\\    ',
            '  ( {E}   {E})  ',
            '  (  ω  )   ',
            '  (")_(")~  ',
        ],
        [
            '            ',
            '   /\\-/\\    ',
            '  ( {E}   {E})  ',
            '  (  ω  )   ',
            '  (")_(")   ',
        ],
    ],
    'dragon': [
        [
            '            ',
            '  /^\\  /^\\  ',
            ' <  {E}  {E}  > ',
            ' (   ~~   ) ',
            '  `-vvvv-´  ',
        ],
        [
            '            ',
            '  /^\\  /^\\  ',
            ' <  {E}  {E}  > ',
            ' (        ) ',
            '  `-vvvv-´  ',
        ],
        [
            '   ~    ~   ',
            '  /^\\  /^\\  ',
            ' <  {E}  {E}  > ',
            ' (   ~~   ) ',
            '  `-vvvv-´  ',
        ],
    ],
    'octopus': [
        [
            '            ',
            '   .----.   ',
            '  ( {E}  {E} )  ',
            '  (______)  ',
            '  /\\/\\/\\/\\  ',
        ],
        [
            '            ',
            '   .----.   ',
            '  ( {E}  {E} )  ',
            '  (______)  ',
            '  \\/\\/\\/\\/  ',
        ],
        [
            '     o      ',
            '   .----.   ',
            '  ( {E}  {E} )  ',
            '  (______)  ',
            '  /\\/\\/\\/\\  ',
        ],
    ],
    'owl': [
        [
            '            ',
            '   /\\  /\\   ',
            '  (({E})({E}))  ',
            '  (  ><  )  ',
            '   `----´   ',
        ],
        [
            '            ',
            '   /\\  /\\   ',
            '  (({E})({E}))  ',
            '  (  ><  )  ',
            '   .----.   ',
        ],
        [
            '            ',
            '   /\\  /\\   ',
            '  (({E})(-))  ',
            '  (  ><  )  ',
            '   `----´   ',
        ],
    ],
    'penguin': [
        [
            '            ',
            '  .---.     ',
            '  ({E}>{E})     ',
            ' /(   )\\    ',
            '  `---´     ',
        ],
        [
            '            ',
            '  .---.     ',
            '  ({E}>{E})     ',
            ' |(   )|    ',
            '  `---´     ',
        ],
        [
            '  .---.     ',
            '  ({E}>{E})     ',
            ' /(   )\\    ',
            '  `---´     ',
            '   ~ ~      ',
        ],
    ],
    'turtle': [
        [
            '            ',
            '   _,--._   ',
            '  ( {E}  {E} )  ',
            ' /[______]\\ ',
            '  ``    ``  ',
        ],
        [
            '            ',
            '   _,--._   ',
            '  ( {E}  {E} )  ',
            ' /[______]\\ ',
            '   ``  ``   ',
        ],
        [
            '            ',
            '   _,--._   ',
            '  ( {E}  {E} )  ',
            ' /[======]\\ ',
            '  ``    ``  ',
        ],
    ],
    'snail': [
        [
            '            ',
            ' {E}    .--.  ',
            '  \\  ( @ )  ',
            '   \\_`--´   ',
            '  ~~~~~~~   ',
        ],
        [
            '            ',
            '  {E}   .--.  ',
            '  |  ( @ )  ',
            '   \\_`--´   ',
            '  ~~~~~~~   ',
        ],
        [
            '            ',
            ' {E}    .--.  ',
            '  \\  ( @  ) ',
            '   \\_`--´   ',
            '   ~~~~~~   ',
        ],
    ],
    'ghost': [
        [
            '            ',
            '   .----.   ',
            '  / {E}  {E} \\  ',
            '  |      |  ',
            '  ~`~``~`~  ',
        ],
        [
            '            ',
            '   .----.   ',
            '  / {E}  {E} \\  ',
            '  |      |  ',
            '  `~`~~`~`  ',
        ],
        [
            '    ~  ~    ',
            '   .----.   ',
            '  / {E}  {E} \\  ',
            '  |      |  ',
            '  ~~`~~`~~  ',
        ],
    ],
    'axolotl': [
        [
            '            ',
            '}~(______)~{',
            '}~({E} .. {E})~{',
            '  ( .--. )  ',
            '  (_/  \\_)  ',
        ],
        [
            '            ',
            '~}(______){~',
            '~}({E} .. {E}){~',
            '  ( .--. )  ',
            '  (_/  \\_)  ',
        ],
        [
            '            ',
            '}~(______)~{',
            '}~({E} .. {E})~{',
            '  (  --  )  ',
            '  ~_/  \\_~  ',
        ],
    ],
    'capybara': [
        [
            '            ',
            '  n______n  ',
            ' ( {E}    {E} ) ',
            ' (   oo   ) ',
            '  `------´  ',
        ],
        [
            '            ',
            '  n______n  ',
            ' ( {E}    {E} ) ',
            ' (   Oo   ) ',
            '  `------´  ',
        ],
        [
            '    ~  ~    ',
            '  u______n  ',
            ' ( {E}    {E} ) ',
            ' (   oo   ) ',
            '  `------´  ',
        ],
    ],
    'cactus': [
        [
            '            ',
            ' n  ____  n ',
            ' | |{E}  {E}| | ',
            ' |_|    |_| ',
            '   |    |   ',
        ],
        [
            '            ',
            '    ____    ',
            ' n |{E}  {E}| n ',
            ' |_|    |_| ',
            '   |    |   ',
        ],
        [
            ' n        n ',
            ' |  ____  | ',
            ' | |{E}  {E}| | ',
            ' |_|    |_| ',
            '   |    |   ',
        ],
    ],
    'robot': [
        [
            '            ',
            '   .[||].   ',
            '  [ {E}  {E} ]  ',
            '  [ ==== ]  ',
            '  `------´  ',
        ],
        [
            '            ',
            '   .[||].   ',
            '  [ {E}  {E} ]  ',
            '  [ -==- ]  ',
            '  `------´  ',
        ],
        [
            '     *      ',
            '   .[||].   ',
            '  [ {E}  {E} ]  ',
            '  [ ==== ]  ',
            '  `------´  ',
        ],
    ],
    'rabbit': [
        [
            '            ',
            '   (\\__/)   ',
            '  ( {E}  {E} )  ',
            ' =(  ..  )= ',
            '  (")__(")  ',
        ],
        [
            '            ',
            '   (|__/)   ',
            '  ( {E}  {E} )  ',
            ' =(  ..  )= ',
            '  (")__(")  ',
        ],
        [
            '            ',
            '   (\\__/)   ',
            '  ( {E}  {E} )  ',
            ' =( .  . )= ',
            '  (")__(")  ',
        ],
    ],
    'mushroom': [
        [
            '            ',
            ' .-o-OO-o-. ',
            '(__________)',
            '   |{E}  {E}|   ',
            '   |____|   ',
        ],
        [
            '            ',
            ' .-O-oo-O-. ',
            '(__________)',
            '   |{E}  {E}|   ',
            '   |____|   ',
        ],
        [
            '   . o  .   ',
            ' .-o-OO-o-. ',
            '(__________)',
            '   |{E}  {E}|   ',
            '   |____|   ',
        ],
    ],
    'chonk': [
        [
            '            ',
            '  /\\    /\\  ',
            ' ( {E}    {E} ) ',
            ' (   ..   ) ',
            '  `------´  ',
        ],
        [
            '            ',
            '  /\\    /|  ',
            ' ( {E}    {E} ) ',
            ' (   ..   ) ',
            '  `------´  ',
        ],
        [
            '            ',
            '  /\\    /\\  ',
            ' ( {E}    {E} ) ',
            ' (   ..   ) ',
            '  `------´~ ',
        ],
    ],
}


HAT_LINES: dict[Hat, str] = {
    'none': '',
    'crown': '   \\^^^/    ',
    'tophat': '   [___]    ',
    'propeller': '    -+-     ',
    'halo': '   (   )    ',
    'wizard': '    /^\\     ',
    'beanie': '   (___)    ',
    'tinyduck': '    ,>      ',
}


def list_species() -> list[str]:
    return sorted(BODIES.keys())


def sprite_frame_count(species: Species) -> int:
    return len(BODIES[species])


def render_sprite(bones: PetBones, frame: int = 0) -> list[str]:
    frames = BODIES[bones.species]
    body = [line.replace('{E}', bones.eye) for line in frames[frame % len(frames)]]
    lines = list(body)

    # Only replace with hat if line 0 is empty (some fidget frames use it for smoke etc)
    if bones.hat != 'none' and not lines[0].strip():
        lines[0] = HAT_LINES[bones.hat]

    # Drop blank hat slot — wastes a row when no hat & frame isn't using it.
    # Only safe when ALL frames have blank line 0; otherwise heights oscillate.
    if not lines[0].strip() and all(not f[0].strip() for f in frames):
        lines.pop(0)

    return lines
