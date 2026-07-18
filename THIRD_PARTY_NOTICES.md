# Third-party notices

NovelForge is distributed under the MIT License. A binary distribution also
contains third-party components governed by their own licenses.

| Component | License | License text |
| --- | --- | --- |
| PySide6, Shiboken6, and Qt 6 | LGPL-3.0-only | `licenses/LGPL-3.0-only.txt` and `licenses/GPL-3.0-only.txt` |
| qasync | BSD-2-Clause | `licenses/qasync-BSD-2-Clause.txt` |
| Pydantic | MIT | `licenses/pydantic-MIT.txt` |
| PyYAML | MIT | `licenses/PyYAML-MIT.txt` |
| keyring | MIT | `licenses/keyring-MIT.txt` |
| HTTPX | BSD-3-Clause | `licenses/httpx-BSD-3-Clause.txt` |
| OpenAI Python library | Apache-2.0 | `licenses/openai-Apache-2.0.txt` |
| Python-Markdown | BSD-3-Clause | `licenses/Markdown-BSD-3-Clause.txt` |
| Python | PSF-2.0 | `licenses/Python-PSF-2.0.txt` |
| PyInstaller bootloader | GPL-2.0-or-later with bootloader exception | `licenses/PyInstaller-GPL-2.0-or-later-with-bootloader-exception.txt` |

PySide6 and Qt are used under LGPL version 3. Recipients may replace the Qt
libraries in a binary distribution and may reverse engineer the application
for debugging modifications to those libraries, as permitted by the LGPL.
NovelForge does not modify PySide6, Shiboken6, or Qt.

Qt contains additional third-party components. The notices applicable to the
Qt modules included in a release are published in the Qt documentation:
https://doc.qt.io/qt-6/licenses-used-in-qt.html

Before publishing a binary, ship this file, the project `LICENSE`, and the
entire `licenses` directory beside the executable. Recheck the notice list
whenever dependencies or bundled Qt modules change.
