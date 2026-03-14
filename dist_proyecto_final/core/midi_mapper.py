# core/midi_mapper.py
from __future__ import annotations

from dataclasses import dataclass

from .text_analysis import TextEvent


@dataclass(slots=True)
class MidiMessage:
    note: int
    velocity: int
    duration_ms: int
    channel: int
    program: int


class MidiMapper:
    PROSE_SCALE = [0, 2, 4, 5, 7, 9, 11]
    VERSE_SCALE = [0, 3, 5, 7, 10]

    def to_midi(self, event: TextEvent) -> MidiMessage:
        base_note = event.note_hint
        scale = self.VERSE_SCALE if event.work_type == "verse" else self.PROSE_SCALE
        step = scale[event.midi_value % len(scale)]
        octave = (event.midi_value // len(scale)) % 3
        category_shift = {"verb": 5, "noun": 0, "adj": 2, "adv": 7, "func": -2}.get(event.category, 0)
        note = max(24, min(108, base_note + step + octave * 12 + category_shift))
        velocity = int(45 + min(72, event.lexical_density * 50 + event.cadence_strength * 3 + (event.metric % 18)))
        duration_ms = int(event.duration_ms + event.pause_after_ms)
        channel = 1 if event.work_type == "verse" else 0
        program = 48 if event.work_type == "verse" else 0
        return MidiMessage(note=note, velocity=max(1, min(127, velocity)), duration_ms=duration_ms, channel=channel, program=program)
