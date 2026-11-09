"""Synthesize original reusable instrumental music using the standard library."""
from array import array
import math
import os
from pathlib import Path
import sys
import tempfile
import wave


_RATE = 24000
_TAU = 2 * math.pi
_MAJOR = ((60, 64, 67, 71), (57, 60, 64, 67), (53, 57, 60, 64), (55, 60, 62, 67))
_MINOR = ((57, 60, 64, 67), (53, 57, 60, 64), (50, 53, 57, 60), (52, 55, 59, 62))
_PROFILES = {
    'soft': {'bpm': 120, 'chords': _MAJOR, 'pad': .020, 'bass': .055, 'voice': 'piano', 'decay': .65, 'level': .11},
    'upbeat': {'bpm': 124, 'chords': _MAJOR, 'pad': .014, 'bass': .07, 'voice': 'pluck', 'decay': .28, 'level': .12},
    'ambient': {'bpm': 60, 'chords': _MAJOR, 'pad': .038, 'bass': .025, 'voice': 'bell', 'decay': 1.6, 'level': .045},
    'cinematic': {'bpm': 72, 'chords': _MINOR, 'pad': .050, 'bass': .11, 'voice': 'piano', 'decay': .95, 'level': .055},
    'acoustic': {'bpm': 104, 'chords': _MAJOR, 'pad': .008, 'bass': .05, 'voice': 'pluck', 'decay': .43, 'level': .17},
    'playful': {'bpm': 138, 'chords': _MAJOR, 'pad': .009, 'bass': .04, 'voice': 'bell', 'decay': .22, 'level': .17},
}
_PARTIALS = {
    'piano': ((1, 1), (2, .20), (3, .05)),
    'pluck': ((1, 1), (2, .32), (3, .16), (4, .07)),
    'bell': ((1, 1), (2.76, .25), (5.4, .08)),
}


def _frequency(note):
    return 440 * 2 ** ((note - 69) / 12)


def _note(samples, frames, start, note, level, pan, voice, decay, echo):
    first = round(start * _RATE)
    if first >= frames:
        return
    count = min(round(min(4.8, decay * 6) * _RATE), frames - first)
    harmonics = [(_TAU * _frequency(note) * ratio / _RATE, amplitude) for ratio, amplitude in _PARTIALS[voice]]
    delay = round(.24 * _RATE)
    for index in range(count):
        elapsed = index / _RATE
        envelope = min(1, elapsed / .008) * math.exp(-elapsed / decay)
        envelope *= min(1, (count - index) / (_RATE * .02))
        value = level * envelope * sum(math.sin(angular * index) * amplitude for angular, amplitude in harmonics)
        at = first + index
        samples[at * 2] += value * (1 - pan)
        samples[at * 2 + 1] += value * (1 + pan)
        if echo and at + delay < frames:
            samples[(at + delay) * 2] += value * echo * (1 + pan)
            samples[(at + delay) * 2 + 1] += value * echo * (1 - pan)


def _drum(samples, frames, start, kind, level, seed):
    first = round(start * _RATE)
    count = min(round({'kick': .24, 'snare': .15, 'hat': .045}[kind] * _RATE), frames - first)
    state, previous = seed + 1, 0.0
    for index in range(max(0, count)):
        elapsed = index / _RATE
        if kind == 'kick':
            # A falling sine frequency gives a soft electronic bass drum.
            phase = _TAU * (45 * elapsed + 45 * .045 * (1 - math.exp(-elapsed / .045)))
            tone = math.sin(phase) * math.exp(-elapsed / .065)
        else:
            state = (1664525 * state + 1013904223) & 0xffffffff
            noise = state / 2147483648 - 1
            high = (noise - previous) / 2
            previous = noise
            tone = high * math.exp(-elapsed / (.036 if kind == 'snare' else .009))
            if kind == 'snare':
                tone += .25 * math.sin(_TAU * 180 * elapsed) * math.exp(-elapsed / .025)
        value = tone * level * min(1, elapsed / .001)
        at = (first + index) * 2
        samples[at] += value
        samples[at + 1] += value


def compose(path, preset='soft', duration=32):
    """Write 24 kHz stereo PCM16; all notes and percussion are synthesized here.

    ``compose(path)`` retains the existing 32 second default. Short durations are
    useful for previews and tests; the 120 second bound limits offline memory use.
    """
    if not isinstance(preset, str) or preset not in _PROFILES:
        raise ValueError('Unsupported music preset')
    if type(duration) not in (int, float) or not math.isfinite(duration) or not .1 <= duration <= 120:
        raise ValueError('Music duration must be a finite number between 0.1 and 120 seconds')
    profile = _PROFILES[preset]
    frames = round(_RATE * duration)
    samples = array('f', [0]) * (frames * 2)
    beat = 60 / profile['bpm']
    measure = beat * 8
    # Sustained chord and bass voices make beds remain useful under narration.
    for bar in range(math.ceil(duration / measure)):
        chord = profile['chords'][bar % len(profile['chords'])]
        angulars = [_TAU * _frequency(note) / _RATE for note in chord]
        bass_angular = _TAU * _frequency(chord[0] - (24 if preset == 'cinematic' else 12)) / _RATE
        first, last = round(bar * measure * _RATE), min(frames, round((bar + 1) * measure * _RATE))
        for index in range(first, last):
            local = index / _RATE - bar * measure
            attack = .65 if preset in ('ambient', 'cinematic') else .12
            envelope = min(1, local / attack) * min(1, (measure - local) / .24)
            pad = sum(math.sin(angular * index) + .12 * math.sin(angular * 1.002 * index) for angular in angulars) * profile['pad']
            bass = profile['bass'] * math.sin(bass_angular * index) * (.35 + .65 * math.exp(-local / 1.8))
            samples[index * 2] = samples[index * 2 + 1] = (pad + bass) * envelope
    notes = []
    if preset == 'ambient':
        for pulse in range(math.ceil(duration / (beat * 2))):
            chord = profile['chords'][(pulse // 4) % 4]
            notes.append((pulse * beat * 2 + .12, chord[(pulse + 2) % 4] + 12, .045, (pulse % 3 - 1) * .35))
    elif preset == 'cinematic':
        for pulse in range(math.ceil(duration / beat)):
            chord = profile['chords'][(pulse // 8) % 4]
            notes.append((pulse * beat, chord[pulse % 4], .055 + (pulse % 4 == 0) * .035, (pulse % 2 * 2 - 1) * .15))
            if pulse % 4 == 0:
                _drum(samples, frames, pulse * beat, 'kick', .13, pulse)
    else:
        subdivision = .5
        for pulse in range(math.ceil(duration / (beat * subdivision))):
            chord = profile['chords'][(pulse // 16) % 4]
            note = chord[pulse % 4] + (24 if preset == 'playful' and pulse % 4 == 2 else 12)
            if preset == 'acoustic' and pulse % 4 == 0:
                note -= 12
            notes.append((pulse * beat * subdivision, note, profile['level'], (pulse % 3 - 1) * .3))
        if preset == 'soft':
            melody = (72, 76, 74, 71, 69, 72, 76, 74, 72, 69, 67, 64, 67, 72, 74, 71)
            for pulse in range(math.ceil(duration / (beat * 4))):
                notes.append((pulse * beat * 4 + .1, melody[pulse % len(melody)], .13, 0))
        if preset in ('upbeat', 'playful', 'acoustic'):
            for pulse in range(math.ceil(duration / beat)):
                if preset != 'acoustic':
                    _drum(samples, frames, pulse * beat, 'kick' if pulse % 2 == 0 else 'snare', .17 if preset == 'upbeat' else .065, pulse)
                _drum(samples, frames, pulse * beat + beat * .5, 'hat', .03 if preset == 'acoustic' else .045, pulse + 2000)
    for start, note, level, pan in notes:
        _note(samples, frames, start, note, level, pan, profile['voice'], profile['decay'], .14 if preset == 'soft' else .05 if preset == 'ambient' else 0)
    fade_in, fade_out = min(.35, duration / 5), min(.65, duration / 4)
    for index in range(frames):
        edge = min(1, (index / _RATE) / fade_in, ((frames - 1 - index) / _RATE) / fade_out)
        samples[index * 2] *= edge
        samples[index * 2 + 1] *= edge
    peak = max(abs(value) for value in samples) or 1
    output = array('h', (round(value / peak * .72 * 32767) for value in samples))
    if sys.byteorder != 'little':
        output.byteswap()
    destination = Path(path)
    # Atomic replacement keeps an existing preview intact if synthesis/write fails.
    descriptor, pending = tempfile.mkstemp(prefix=destination.name + '.', suffix='.pending', dir=destination.parent)
    os.close(descriptor)
    try:
        with wave.open(pending, 'wb') as track:
            track.setnchannels(2)
            track.setsampwidth(2)
            track.setframerate(_RATE)
            track.writeframes(output.tobytes())
        os.replace(pending, destination)
    finally:
        if os.path.exists(pending):
            os.unlink(pending)


if __name__ == '__main__':
    compose(Path(__file__).with_name('builtin_music.wav'))
