"""Entry point for the NovelForge desktop application."""

from __future__ import annotations

import asyncio
import gc
import sys

import qasync
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def main() -> None:
    QCoreApplication.setOrganizationName("NovelForge")
    QCoreApplication.setApplicationName("NovelForge")

    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = MainWindow()
    window.show()

    with loop:
        loop.run_forever()

    # Force GC after the event loop stops but before full interpreter
    # shutdown, to reduce httpcore async-generator cleanup warnings.
    gc.collect()


if __name__ == "__main__":
    main()
