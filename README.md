# Pomodoro Mini

Bongo Cat 風格的常駐桌面迷你懸浮番茄鐘（PySide6 + `uv`）。

## 功能特色

- **極簡懸浮膠囊（244x84）**：無邊框圓角、底部動態進度條、滑鼠左鍵自由拖曳、滑鼠懸停才顯示操作鈕（播放/暫停、快進、設定、離開）。
- **專注 / 遊戲雙模式**：膠囊正上方切換標籤，保留各自週期與剩餘時間；遊戲模式時間到自動歸零待命。
- **獨立設定分頁**：專注與遊戲各自設定時長、桌面通知、內建 4 款合成音軌（Chime / Beep / Wood / Bell）與音量試聽；共用透明度與置頂設定。
- **每日專注與娛樂總結**：關閉視窗時顯示今日專注次數、專注總時長與娛樂總時長，跨日自動歸零。

## 啟動與安裝（Linux）

```bash
# 直接啟動
./launch-pomodoro.sh

# 註冊進系統應用程式清單（$HOME/.local/share/applications/）
./install-desktop.sh
```

> 若在 Wayland 桌面需要完整支援「記住上次關閉位置」、「置頂」與「工作列邊界限制」，建議安裝 `libxcb-cursor0`（`launch-pomodoro.sh` 會自動偵測並切換 `QT_QPA_PLATFORM=xcb`）。

## 測試

```bash
uv run --with pytest pytest -v
```
