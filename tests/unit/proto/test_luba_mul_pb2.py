"""Wire layout of the ``luba_mul.proto`` additions from app 2.3.20.30: the voice volume."""

from __future__ import annotations

import betterproto2

from pymammotion.proto import MulAudioCfg, MulSetAudio


def test_set_audio_sends_volume_as_oneof_field_4() -> None:
    audio = MulSetAudio(au_volume=60)

    assert bytes(audio) == b"\x20\x3c"  # (4 << 3) = 32 -> 0x20.
    assert betterproto2.which_one_of(audio, "AudioCfg_u")[0] == "au_volume"


def test_audio_cfg_reads_volume_from_field_4() -> None:
    assert MulAudioCfg().parse(b"\x20\x3c").au_volume == 60
