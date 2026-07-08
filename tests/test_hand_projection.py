from __future__ import annotations

from processing.hand_projection import project_hand_to_camera


def test_hand_projection_can_mirror_user_view() -> None:
    landmarks = [(0.0, 0.0, 0.5), (1.0, 1.0, 0.5)]

    normal = project_hand_to_camera(landmarks, 100, 100, mirror_x=False)
    mirrored = project_hand_to_camera(landmarks, 100, 100, mirror_x=True)

    assert normal[0][0] == 0
    assert normal[1][0] == 100
    assert mirrored[0][0] == 100
    assert mirrored[1][0] == 0


def test_hand_projection_keeps_fingers_up_by_default() -> None:
    landmarks = [(0.0, 0.0, 0.5), (0.0, 1.0, 0.5)]

    projected = project_hand_to_camera(landmarks, 100, 100)

    assert projected[0][1] == 0
    assert projected[1][1] == 100
