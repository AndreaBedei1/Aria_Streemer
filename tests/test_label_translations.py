from __future__ import annotations

from label_translations import translate_label_it


def test_object_labels_are_translated_to_italian() -> None:
    assert translate_label_it("book") == "libro"
    assert translate_label_it("remote control") == "telecomando"
    assert translate_label_it("laptop") == "computer portatile"


def test_hagrid_labels_are_translated_to_italian() -> None:
    assert translate_label_it("Palm") == "palmo"
    assert translate_label_it("take_picture") == "scatta foto"
    assert translate_label_it("X sign") == "segno x"


def test_unknown_label_falls_back_to_original_text() -> None:
    assert translate_label_it("custom object") == "custom object"
