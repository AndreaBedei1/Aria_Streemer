from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from config import parse_args
from widgets.main_window import MainWindow


def setup_logging(debug_streams: bool) -> None:
    level = logging.DEBUG if debug_streams else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def main() -> int:
    config = parse_args()
    setup_logging(config.debug_streams)
    app = QApplication(sys.argv)
    window = MainWindow(config)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
