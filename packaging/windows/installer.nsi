Unicode true
!include "MUI2.nsh"
!include "x64.nsh"
Name "${APPNAME}"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\${INSTALLFOLDER}"
RequestExecutionLevel user
SetCompressor /SOLID lzma
VIProductVersion "2.0.0.64"
VIAddVersionKey "ProductName" "${APPNAME}"
VIAddVersionKey "FileDescription" "${APPNAME} Setup"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "MIT License - ${APPNAME} contributors"
!if "${APPNAME}" == "NextUp"
!define MUI_ICON "${SOURCE}/studio/static/nextup.ico"
!define MUI_UNICON "${SOURCE}/studio/static/nextup.ico"
!endif
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_TEXT "${APPNAME} is installed with its own runtime. You do not need Python. Open ${APPNAME} from your desktop or Start menu."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${SOURCE}/LICENSE"
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"
Var AppMutex
Var WebViewVersion

Function CheckWebView
  SetRegView 32
  ReadRegStr $WebViewVersion HKLM "SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  ${If} $WebViewVersion == ""
  ${OrIf} $WebViewVersion == "0.0.0.0"
    ReadRegStr $WebViewVersion HKCU "SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  ${EndIf}
FunctionEnd

!macro AppGuard
  System::Call 'kernel32::CreateMutexW(p 0, i 0, w "Local\${MUTEX}") p .r0 ?e'
  Pop $1
  StrCpy $AppMutex $0
  ${If} $0 == 0
    MessageBox MB_OK|MB_ICONSTOP "Could not check whether ${APPNAME} is running. Setup cannot continue." /SD IDOK
    SetErrorLevel 2
    Abort
  ${EndIf}
  ${If} $1 == 183
    MessageBox MB_OK|MB_ICONEXCLAMATION "Close ${APPNAME} using Tools > Exit, then run setup or uninstall again." /SD IDOK
    SetErrorLevel 2
    Abort
  ${EndIf}
!macroend
Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_OK|MB_ICONSTOP "${APPNAME} requires 64-bit Windows." /SD IDOK
    SetErrorLevel 2
    Abort
  ${EndIf}
  SetShellVarContext current
  !insertmacro AppGuard
FunctionEnd
Function un.onInit
  SetShellVarContext current
  !insertmacro AppGuard
FunctionEnd
Section "${APPNAME}"
  ReadRegDWORD $0 HKLM "SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full" "Release"
  ${If} $0 < 394802
    MessageBox MB_OK|MB_ICONSTOP "${APPNAME} needs Microsoft .NET Framework 4.6.2 or newer. Install Windows updates or .NET Framework 4.8 from Microsoft, then run setup again." /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
  ; Microsoft's shared Evergreen runtime is installed only when it is missing.
  Call CheckWebView
  ${If} $WebViewVersion == ""
  ${OrIf} $WebViewVersion == "0.0.0.0"
    DetailPrint "Installing Microsoft WebView2 for the desktop window (internet required)..."
    InitPluginsDir
    SetOutPath "$PLUGINSDIR"
    File "${PAYLOAD}/MicrosoftEdgeWebview2Setup.exe"
    ExecWait '"$PLUGINSDIR\MicrosoftEdgeWebview2Setup.exe" /silent /install' $0
    Call CheckWebView
    ${If} $WebViewVersion == ""
    ${OrIf} $WebViewVersion == "0.0.0.0"
      MessageBox MB_OK|MB_ICONSTOP "Microsoft WebView2 could not be installed. Connect to the internet and run setup again, or install the WebView2 Evergreen Runtime from Microsoft. No Python installation is needed." /SD IDOK
      SetErrorLevel 1
      Abort
    ${EndIf}
  ${EndIf}
  SetOutPath "$INSTDIR"
  File "${PAYLOAD}/${APPNAME}.exe"
  File "${SOURCE}/bootstrap.py"
  File "${SOURCE}/packaging/windows/install_support.py"
  SetOutPath "$INSTDIR\runtime"
  File /r "${PAYLOAD}/runtime/*"
  ; Save a result even if Windows cannot start Python to create its own log.
  FileOpen $1 "$INSTDIR\install-check.txt" w
  FileWrite $1 "Starting bundled runtime check.$\r$\n"
  FileClose $1
  nsExec::ExecToStack /TIMEOUT=15000 '"$INSTDIR\runtime\python.exe" "$INSTDIR\install_support.py" --check'
  Pop $0
  Pop $2
  DetailPrint "Runtime check returned: $0"
  DetailPrint "$2"
  FileOpen $1 "$INSTDIR\install-check.txt" a
  FileWrite $1 "Result: $0$\r$\n$2$\r$\n"
  FileClose $1
  ${If} $0 == 10
    MessageBox MB_OK|MB_ICONSTOP "Another NextUp process holds the application lock. Close it before installing." /SD IDOK
    SetErrorLevel 2
    Abort
  ${ElseIf} $0 != 0
    MessageBox MB_OK|MB_ICONSTOP "The bundled runtime check failed (result $0). This does not mean the bot is running. See $INSTDIR\install-check.txt and any Windows error popup. Your settings were retained." /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
  SetOutPath "$INSTDIR\versions\${VERSION}"
  File /r "${PAYLOAD}/app/*"
  SetOutPath "$INSTDIR"
  ; Activation performs one preflight, including repairs, and writes .ready.
  Delete "$INSTDIR\versions\${VERSION}\.ready"
  nsExec::ExecToLog '"$INSTDIR\runtime\python.exe" "$INSTDIR\install_support.py" "${VERSION}"'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_OK|MB_ICONSTOP "Setup could not activate ${APPNAME}. The component check failed. See Show details or $INSTDIR\install-diagnostics.txt for the exact error. Existing settings were retained." /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\${APPNAME}"
  CreateShortcut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\${APPNAME}.exe"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\${APPNAME}.exe"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\Roll back last update.lnk" "$INSTDIR\${APPNAME}.exe" "--rollback"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${REGKEY}" "DisplayName" "${APPNAME}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${REGKEY}" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${REGKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${REGKEY}" "DisplayIcon" "$INSTDIR\${APPNAME}.exe"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${REGKEY}" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${REGKEY}" "NoRepair" 1
SectionEnd
Section "Uninstall"
  ; Save a result even if Windows cannot start Python to create its own log.
  FileOpen $1 "$INSTDIR\install-check.txt" w
  FileWrite $1 "Starting bundled runtime check.$\r$\n"
  FileClose $1
  nsExec::ExecToStack /TIMEOUT=15000 '"$INSTDIR\runtime\python.exe" "$INSTDIR\install_support.py" --check'
  Pop $0
  Pop $2
  DetailPrint "Runtime check returned: $0"
  DetailPrint "$2"
  FileOpen $1 "$INSTDIR\install-check.txt" a
  FileWrite $1 "Result: $0$\r$\n$2$\r$\n"
  FileClose $1
  ${If} $0 == 10
    MessageBox MB_OK|MB_ICONSTOP "Another NextUp process holds the application lock. Close it before uninstalling." /SD IDOK
    SetErrorLevel 2
    Abort
  ${ElseIf} $0 != 0
    MessageBox MB_OK|MB_ICONSTOP "The bundled runtime check failed (result $0). This does not mean the bot is running. See $INSTDIR\install-check.txt and any Windows error popup. Your settings were retained." /SD IDOK
    SetErrorLevel 1
    Abort
  ${EndIf}
  Delete "$DESKTOP\${APPNAME}.lnk"
  RMDir /r "$SMPROGRAMS\${APPNAME}"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${REGKEY}"
  RMDir /r "$INSTDIR\versions"
  RMDir /r "$INSTDIR\runtime"
  RMDir /r "$INSTDIR\staging-download"
  Delete "$INSTDIR\${APPNAME}.exe"
  Delete "$INSTDIR\bootstrap.py"
  Delete "$INSTDIR\install_support.py"
  Delete "$INSTDIR\current.json"
  Delete "$INSTDIR\previous.json"
  Delete "$INSTDIR\pending.json"
  Delete "$INSTDIR\Uninstall.exe"
  ; Userdata (settings, linked account tokens and history) is intentionally kept.
  MessageBox MB_OK "${APPNAME} was removed. Your settings, account connections and history remain in $INSTDIR\userdata. Delete that folder yourself if you want to remove them." /SD IDOK
SectionEnd
