!include "MUI2.nsh"

Name "Jarvis"
OutFile "..\dist\Jarvis-Setup.exe"
InstallDir "$PROGRAMFILES64\Jarvis"
RequestExecutionLevel admin

Page license
Page directory
Page instfiles

!insertmacro MUI_LANGUAGE "English"

Section "Install"
    SetOutPath "$INSTDIR"
    File "..\dist\Jarvis.exe"
    CreateDirectory "$SMPROGRAMS\Jarvis"
    CreateShortcut "$SMPROGRAMS\Jarvis\Jarvis.lnk" "$INSTDIR\Jarvis.exe"
    CreateShortcut "$DESKTOP\Jarvis.lnk" "$INSTDIR\Jarvis.exe"
SectionEnd
