"""測試共用設定：Qt 一律用 offscreen，確保無顯示器也確定性。"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
