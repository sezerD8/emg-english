from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ui.common import make_app_icon  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)


def main() -> int:
    from PIL import Image

    app = QApplication(sys.argv)  # noqa: F841
    pm = make_app_icon(256).pixmap(256, 256)
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pm.save(buf, "PNG")
    out = ROOT / "assets" / "emg.ico"
    out.parent.mkdir(exist_ok=True)
    Image.open(BytesIO(bytes(buf.data()))).save(out, sizes=[(s, s) for s in SIZES])
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
