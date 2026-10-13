/* NextUp's native Windows launcher. MIT License. No system Python or shell. */
#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#ifndef APP_NAME
#define APP_NAME L"NextUp"
#endif
#ifndef APP_MUTEX
#define APP_MUTEX L"Local\\NextUpApp"
#endif
#include <windows.h>
#include <wchar.h>

int WINAPI wWinMain(HINSTANCE a, HINSTANCE b, PWSTR args, int show) {
    wchar_t root[32768], exe[32768], cmd[32768];
    DWORD n = GetModuleFileNameW(NULL, root, 32768);
    if (!n || n >= 32768) return 1;
    wchar_t *slash = wcsrchr(root, L'\\');
    if (!slash) return 1;
    *slash = 0;
    HANDLE mutex = CreateMutexW(NULL, TRUE, APP_MUTEX);
    if (!mutex || GetLastError() == ERROR_ALREADY_EXISTS) {
        HWND window = FindWindowW(NULL, APP_NAME);
        if (window) { ShowWindow(window, SW_RESTORE); SetForegroundWindow(window); }
        else MessageBoxW(NULL, L"The app is already starting, stopping, or its installer is running. Please wait a moment.", APP_NAME, MB_OK | MB_ICONINFORMATION);
        if (mutex) CloseHandle(mutex);
        return 1;
    }
    SetEnvironmentVariableW(L"NEXTUP_HOME", root);
    SetEnvironmentVariableW(L"NEXTUP_APP_NAME", APP_NAME);
    SetEnvironmentVariableW(L"NEXTUP_USERDATA", NULL);
    SetEnvironmentVariableW(L"NEXTUP_BUNDLED", L"1");
    if (swprintf(exe, 32768, L"%ls\\runtime\\pythonw.exe", root) < 0 ||
        swprintf(cmd, 32768, L"\"%ls\" \"%ls\\bootstrap.py\"%ls", exe, root,
            wcscmp(args, L"--rollback") == 0 ? L" --rollback" : L"") < 0) return 1;
    STARTUPINFOW si = {0}; si.cb = sizeof(si);
    PROCESS_INFORMATION pi = {0};
    if (!CreateProcessW(exe, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, root, &si, &pi)) {
        MessageBoxW(NULL, L"The app could not start its bundled runtime. Run the EXE installer again to repair it.", APP_NAME, MB_OK | MB_ICONERROR);
        CloseHandle(mutex); return 1;
    }
    CloseHandle(pi.hThread);
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 1; GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hProcess); CloseHandle(mutex);
    return (int)code;
}
