!include "MUI2.nsh"

!define APP_NAME "Jarvis"
!define APP_VERSION "0.1.0"
!define APP_PUBLISHER "Jarvis"
!define APP_EXE "Jarvis.exe"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\Jarvis"

Name "${APP_NAME} ${APP_VERSION}"
Caption "${APP_NAME} Setup"
OutFile "..\dist\Jarvis-Setup.exe"
InstallDir "$PROGRAMFILES64\Jarvis"
InstallDirRegKey HKLM "${UNINSTALL_KEY}" "InstallLocation"
RequestExecutionLevel admin
Unicode True
SetCompressor /SOLID lzma
SetCompressorDictSize 32

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "Install Jarvis" SEC_MAIN
    SectionIn RO
    SetOutPath "$INSTDIR"
    File "..\dist\Jarvis.exe"
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    CreateDirectory "$SMPROGRAMS\Jarvis"
    CreateShortcut "$SMPROGRAMS\Jarvis\Jarvis.lnk" "$INSTDIR\${APP_EXE}"
    CreateShortcut "$SMPROGRAMS\Jarvis\Uninstall Jarvis.lnk" "$INSTDIR\Uninstall.exe"

    WriteRegStr HKLM "${UNINSTALL_KEY}" "DisplayName" "${APP_NAME}"
    WriteRegStr HKLM "${UNINSTALL_KEY}" "DisplayVersion" "${APP_VERSION}"
    WriteRegStr HKLM "${UNINSTALL_KEY}" "Publisher" "${APP_PUBLISHER}"
    WriteRegStr HKLM "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "${UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\${APP_EXE}"
    WriteRegStr HKLM "${UNINSTALL_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegDWORD HKLM "${UNINSTALL_KEY}" "NoModify" 1
    WriteRegDWORD HKLM "${UNINSTALL_KEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
    Delete "$SMPROGRAMS\Jarvis\Jarvis.lnk"
    Delete "$SMPROGRAMS\Jarvis\Uninstall Jarvis.lnk"
    RMDir "$SMPROGRAMS\Jarvis"
    Delete "$APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Jarvis-startup.cmd"
    DeleteRegKey HKLM "${UNINSTALL_KEY}"
    RMDir /r "$INSTDIR"
    MessageBox MB_OK "Jarvis has been removed. Personal data and backups under your user profile were kept."
SectionEnd
