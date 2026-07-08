from __future__ import annotations

from speech_announcer import _parse_wpctl_default_sink, _parse_wpctl_sinks, _split_keywords


def test_parse_wpctl_sinks_extracts_sink_ids_and_names() -> None:
    status = """
Audio
 ├─ Sinks:
 │  *   48. Built-in Audio Analog Stereo        [vol: 0.40]
 │      91. Andrea Glasses                      [vol: 0.70]
 │      92. GP107GL HDMI                        [vol: 0.40]
 │
 ├─ Sink endpoints:
"""

    assert _parse_wpctl_sinks(status) == [
        ("48", "Built-in Audio Analog Stereo"),
        ("91", "Andrea Glasses"),
        ("92", "GP107GL HDMI"),
    ]
    assert _parse_wpctl_default_sink(status) == "48"


def test_split_keywords_normalizes_and_drops_empty_values() -> None:
    assert _split_keywords(" Aria, glasses, ,Andrea ") == ["aria", "glasses", "andrea"]
