@echo off
echo Installing PyInstaller...
pip install pyinstaller

echo.
echo Building VoiceKey...
pyinstaller --onedir --windowed --name VoiceKey voicekey.py

echo.
echo Done! VoiceKey.exe is in dist\VoiceKey\
pause
