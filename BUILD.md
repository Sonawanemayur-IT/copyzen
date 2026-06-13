# Building CopyZen from Source

## Prerequisites
- Python 3.7+ (with `pip`)
- Windows (the build is currently Windows‑only)
- PyInstaller (`pip install pyinstaller`)

## Steps
1. Clone this repository.
2. Download the Android Platform Tools from [Google](https://developer.android.com/studio/releases/platform-tools) and copy `adb.exe`, `AdbWinApi.dll`, `AdbWinUsbApi.dll` into the folder.
3. Place your custom font (`Bellfast-gx9zY.otf`) and icon (`copyzen.ico`) in the same folder.
4. Run the build command:
   ```bash
   pyinstaller --onefile --noconsole --name copyzen --icon copyzen.ico --add-data "adb.exe;." --add-data "AdbWinApi.dll;." --add-data "AdbWinUsbApi.dll;." --add-data "Bellfast-gx9zY.otf;." --add-data "copyzen.ico;." --hidden-import tkinter copyzen.py