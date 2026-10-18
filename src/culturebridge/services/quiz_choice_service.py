"""Balanced random positions, persisted with each quiz rather than a fixed rotation."""

from random import SystemRandom


def answer_positions(count):
    rng = SystemRandom()
    positions = list(range(4)) * (count // 4) + rng.sample(range(4), count % 4)
    rng.shuffle(positions)
    return positions


def arranged_choices(choices, correct, position):
    other = [choice for index, choice in enumerate(choices) if index != correct]
    SystemRandom().shuffle(other)
    other.insert(position, choices[correct])
    return other
