!include "MUI2.nsh"

!define APP_NAME "Jarvis"
!define APP_VERSION "0.1.0"
!define APP_PUBLISHER "Jarvis"
!define APP_EXE "Jarvis.exe"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\Jarvis"
!ifndef DIST_ROOT
!define DIST_ROOT "..\dist"
!endif
!define APP_DIST "${DIST_ROOT}\Jarvis"

Name "${APP_NAME} ${APP_VERSION}"
Caption "${APP_NAME} Setup"
OutFile "${DIST_ROOT}\Jarvis-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\Jarvis"
InstallDirRegKey HKCU "${UNINSTALL_KEY}" "InstallLocation"
RequestExecutionLevel user
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
    SetOutPath "$INSTDIR"
    File /r "${APP_DIST}\*"
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    CreateDirectory "$SMPROGRAMS\Jarvis"
    CreateShortcut "$SMPROGRAMS\Jarvis\Jarvis.lnk" "$INSTDIR\${APP_EXE}"
    CreateShortcut "$SMPROGRAMS\Jarvis\Uninstall Jarvis.lnk" "$INSTDIR\Uninstall.exe"
    CreateShortcut "$DESKTOP\Jarvis.lnk" "$INSTDIR\${APP_EXE}"

    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayName" "${APP_NAME}"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayVersion" "${APP_VERSION}"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "Publisher" "${APP_PUBLISHER}"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\${APP_EXE}"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoModify" 1
    WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
    Delete "$SMPROGRAMS\Jarvis\Jarvis.lnk"
    Delete "$SMPROGRAMS\Jarvis\Uninstall Jarvis.lnk"
    Delete "$DESKTOP\Jarvis.lnk"
    RMDir "$SMPROGRAMS\Jarvis"
    Delete "$APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Jarvis-startup.cmd"
    DeleteRegKey HKCU "${UNINSTALL_KEY}"
    RMDir /r "$INSTDIR"
    MessageBox MB_OK "Jarvis has been removed. Personal data and backups under your user profile were kept."
SectionEnd
