from __future__ import annotations


LABEL_TRANSLATIONS_IT = {
    # Object detector classes
    "book": "libro",
    "smartphone": "telefono",
    "phone": "telefono",
    "cell phone": "telefono",
    "pen": "penna",
    "notebook": "quaderno",
    "paper": "foglio",
    "cup": "tazza",
    "bottle": "bottiglia",
    "keyboard": "tastiera",
    "mouse": "mouse",
    "glasses": "occhiali",
    "keys": "chiavi",
    "wallet": "portafoglio",
    "remote control": "telecomando",
    "charger": "caricatore",
    "cable": "cavo",
    "headphones": "cuffie",
    "bag": "borsa",
    "scissors": "forbici",
    "ruler": "righello",
    "watch": "orologio",
    "laptop": "computer portatile",
    "tablet": "tablet",
    "monitor": "monitor",
    "chair": "sedia",
    "hand": "mano",
    "face": "viso",
    # HaGRID gesture classes
    "grabbing": "presa",
    "grip": "presa stretta",
    "holy": "mani giunte",
    "point": "indice puntato",
    "call": "telefono",
    "three3": "tre",
    "timeout": "time out",
    "x sign": "segno x",
    "xsign": "segno x",
    "hand heart": "cuore con le mani",
    "hand heart2": "cuore con le mani",
    "little finger": "mignolo",
    "middle finger": "dito medio",
    "take picture": "scatta foto",
    "dislike": "non mi piace",
    "fist": "pugno",
    "four": "quattro",
    "like": "mi piace",
    "mute": "muto",
    "ok": "ok",
    "one": "uno",
    "palm": "palmo",
    "peace": "pace",
    "peace inverted": "pace invertito",
    "rock": "rock",
    "stop": "stop",
    "stop inverted": "stop invertito",
    "three": "tre",
    "three2": "tre",
    "two up": "due",
    "two up inverted": "due invertito",
    "three gun": "pistola con tre dita",
    "thumb index": "pollice e indice",
    "thumb index2": "pollice e indice",
    "no gesture": "nessun gesto",
    # Landmark fallback labels
    "hand visible": "mano visibile",
    "move hand right": "mano verso destra",
    "move hand left": "mano verso sinistra",
    "move hand up": "mano verso l'alto",
    "move hand down": "mano verso il basso",
    "push away": "allontana la mano",
    "bring hand close": "avvicina la mano",
}


def translate_label_it(label: str) -> str:
    normalized = _normalize_label(label)
    return LABEL_TRANSLATIONS_IT.get(normalized, label.strip())


def _normalize_label(label: str) -> str:
    return " ".join(label.strip().replace("_", " ").lower().split())
