; ==============================================================================
; Momento Universal AI Agent Workspace - NSIS Installer Script
; ==============================================================================
; Target: Windows (x64 / x86)
; Execution Level: User (No UAC elevation required, installs to %LOCALAPPDATA%)
; ==============================================================================

!include "MUI2.nsh"
!include "FileFunc.nsh"

; General Configuration
Name "Momento"
Caption "Momento Universal AI Agent Workspace Setup"
OutFile "dist\Momento-Setup-NSIS.exe"
InstallDir "$LOCALAPPDATA\Programs\Momento"
InstallDirRegKey HKCU "Software\Momento" "Install_Dir"
RequestExecutionLevel user

; Version Information
VIProductVersion "1.1.0.0"
VIAddVersionKey "ProductName" "Momento Universal AI Agent Workspace"
VIAddVersionKey "CompanyName" "Momento AI"
VIAddVersionKey "LegalCopyright" "© 2026 Momento AI"
VIAddVersionKey "FileDescription" "Momento Installer"
VIAddVersionKey "FileVersion" "1.1.0.0"
VIAddVersionKey "ProductVersion" "1.1.0.0"

; UI Configuration
!define MUI_ABORTWARNING
!define MUI_COMPONENTSPAGE_NODESC

; Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\Momento.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Launch Momento now"
!insertmacro MUI_PAGE_FINISH

; Uninstaller Pages
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; Languages
!insertmacro MUI_LANGUAGE "English"

; ------------------------------------------------------------------------------
; Installer Section
; ------------------------------------------------------------------------------
Section "Momento Core (required)" SecCore
    SectionIn RO

    SetOutPath "$INSTDIR"

    ; Copy all files from the built dist\Momento directory
    File /r "dist\Momento\*.*"

    ; Store installation folder in registry
    WriteRegStr HKCU "Software\Momento" "Install_Dir" "$INSTDIR"

    ; Create Windows Add/Remove Programs entry
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Momento" "DisplayName" "Momento Universal AI Agent Workspace"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Momento" "DisplayVersion" "1.1.0"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Momento" "Publisher" "Momento AI"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Momento" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Momento" "DisplayIcon" "$INSTDIR\Momento.exe,0"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Momento" "UninstallString" '"$INSTDIR\uninstall.exe"'
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Momento" "NoModify" 1
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Momento" "NoRepair" 1

    ; Create uninstaller
    WriteUninstaller "$INSTDIR\uninstall.exe"

    ; Create Shortcuts
    CreateDirectory "$SMPROGRAMS\Momento"
    CreateShortcut "$SMPROGRAMS\Momento\Momento.lnk" "$INSTDIR\Momento.exe" "" "$INSTDIR\Momento.exe" 0
    CreateShortcut "$SMPROGRAMS\Momento\Uninstall Momento.lnk" "$INSTDIR\uninstall.exe" "" "$INSTDIR\uninstall.exe" 0
    CreateShortcut "$DESKTOP\Momento.lnk" "$INSTDIR\Momento.exe" "" "$INSTDIR\Momento.exe" 0

SectionEnd

; ------------------------------------------------------------------------------
; Uninstaller Section
; ------------------------------------------------------------------------------
Section "Uninstall"

    ; Remove shortcuts
    Delete "$DESKTOP\Momento.lnk"
    Delete "$SMPROGRAMS\Momento\Momento.lnk"
    Delete "$SMPROGRAMS\Momento\Uninstall Momento.lnk"
    RMDir "$SMPROGRAMS\Momento"

    ; Remove registry keys
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Momento"
    DeleteRegKey HKCU "Software\Momento"

    ; Remove application files and directories
    RMDir /r "$INSTDIR\_internal"
    Delete "$INSTDIR\Momento.exe"
    Delete "$INSTDIR\uninstall.exe"
    Delete "$INSTDIR\uninstall.bat"
    RMDir /r "$INSTDIR"

SectionEnd
