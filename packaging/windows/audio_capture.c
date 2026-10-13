/* NextUp application loopback helper. MIT; Windows public WASAPI/COM APIs.
 * --list: visible application process identities (no window titles/paths).
 * --capture PID CREATION_TIME: 48 kHz stereo signed 16-bit PCM on stdout.
 * Audio is streamed to NextUp in memory, never written to a recording file.
 */
#define COBJMACROS
#define INITGUID
#define _WIN32_WINNT 0x0A00
#include <winsock2.h>
#include <windows.h>
#include <iphlpapi.h>
#include <objbase.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <tlhelp32.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <fcntl.h>
#include <io.h>
#include <wchar.h>

static ULONGLONG creation(HANDLE p) {
    FILETIME c,e,k,u;
    if (!GetProcessTimes(p,&c,&e,&k,&u)) return 0;
    return ((ULONGLONG)c.dwHighDateTime<<32)|c.dwLowDateTime;
}
static void json_string(const WCHAR *s) {
    /* JSON Unicode escapes avoid locale dependence and private path disclosure. */
    putchar('"');
    for (;*s;s++) {unsigned c=(unsigned short)*s;
        if (c=='"'||c=='\\') printf("\\%c",c);
        else if(c>=32&&c<127) putchar(c); else printf("\\u%04x",c);
    } putchar('"');
}
static DWORD seen[128];static unsigned seen_count;
static BOOL CALLBACK list_window(HWND w,LPARAM unused) {
    (void)unused;DWORD pid=0;
    if(!IsWindowVisible(w)||GetWindow(w,GW_OWNER)||GetWindowTextLengthW(w)==0) return TRUE;
    GetWindowThreadProcessId(w,&pid);
    for(unsigned i=0;i<seen_count;i++) if(seen[i]==pid) return TRUE;
    if(seen_count>=128) return FALSE;
    HANDLE p=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,FALSE,pid);if(!p)return TRUE;
    WCHAR path[32768];DWORD n=32768;ULONGLONG start=creation(p);
    if(start&&QueryFullProcessImageNameW(p,0,path,&n)) {
        WCHAR *name=wcsrchr(path,L'\\');name=name?name+1:path;
        if(seen_count)putchar(',');seen[seen_count++]=pid;
        printf("{\"pid\":%lu,\"started\":\"%llu\",\"name\":",pid,start);json_string(name);putchar('}');
    }CloseHandle(p);return TRUE;
}
static DWORD parent_pid(void) {
    DWORD result=0;HANDLE s=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);
    if(s==INVALID_HANDLE_VALUE)return 0;
    PROCESSENTRY32W p={0};p.dwSize=sizeof(p);
    if(Process32FirstW(s,&p))do{if(p.th32ProcessID==GetCurrentProcessId()){result=p.th32ParentProcessID;break;}}while(Process32NextW(s,&p));
    CloseHandle(s);return result;
}
/* Resolve only the authenticated extension's local TCP peer, not any browser
 * guessed from a user agent or whichever process happens to be running. */
static DWORD peer_owner(unsigned port) {
    if(!port||port>65535)return 0;
    DWORD size=0,result=0;
    if(GetExtendedTcpTable(NULL,&size,FALSE,AF_INET,TCP_TABLE_OWNER_PID_ALL,0)!=ERROR_INSUFFICIENT_BUFFER)return 0;
    for(int attempt=0;attempt<3;attempt++){
        if(size>16*1024*1024||size<sizeof(DWORD))return 0;
        MIB_TCPTABLE_OWNER_PID *table=malloc(size);if(!table)return 0;
        DWORD allocated=size,status=GetExtendedTcpTable(table,&size,FALSE,AF_INET,TCP_TABLE_OWNER_PID_ALL,0);
        if(status==ERROR_INSUFFICIENT_BUFFER){free(table);continue;}
        if(status==NO_ERROR&&table->dwNumEntries<=(allocated-sizeof(DWORD))/sizeof(MIB_TCPROW_OWNER_PID)){
            for(DWORD i=0;i<table->dwNumEntries;i++){
                MIB_TCPROW_OWNER_PID *r=&table->table[i];
                if(r->dwState==MIB_TCP_STATE_ESTAB&&r->dwLocalAddr==htonl(INADDR_LOOPBACK)&&r->dwRemoteAddr==htonl(INADDR_LOOPBACK)&&ntohs((u_short)r->dwLocalPort)==port&&ntohs((u_short)r->dwRemotePort)==8888){result=r->dwOwningPid;break;}
            }
        }free(table);return result;
    }return 0;
}
static const WCHAR *process_names[]={L"",L"Spotify.exe",L"chrome.exe",L"msedge.exe",L"brave.exe",L"opera.exe",L"vivaldi.exe",L"firefox.exe"};
static int process_kind(const WCHAR *name){for(int i=1;i<8;i++)if(!_wcsicmp(name,process_names[i]))return i;return 0;}
static void emit_process(DWORD pid,const WCHAR *name,unsigned *count,int peer) {
    HANDLE p=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,FALSE,pid);if(!p)return;
    ULONGLONG start=creation(p);
    if(start){if((*count)++)putchar(',');printf("{\"pid\":%lu,\"started\":\"%llu\",\"name\":",pid,start);json_string(name);if(peer)printf(",\"peer\":true");putchar('}');}
    CloseHandle(p);
}
static int follow_list(unsigned port) {
    struct candidate {DWORD pid,parent;int kind;} rows[4096];unsigned count=0,out=0;
    DWORD owner=peer_owner(port);
    HANDLE snap=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);
    if(snap==INVALID_HANDLE_VALUE)return 1;
    PROCESSENTRY32W p={0};p.dwSize=sizeof(p);
    if(Process32FirstW(snap,&p))do{
        int kind=process_kind(p.szExeFile);
        if(kind&&count<4096)rows[count++]=(struct candidate){p.th32ProcessID,p.th32ParentProcessID,kind};
    }while(Process32NextW(snap,&p));CloseHandle(snap);
    putchar('[');
    for(unsigned i=0;i<count&&out<126;i++){
        if(rows[i].kind!=1)continue;
        int child=0;for(unsigned j=0;j<count;j++)if(rows[i].parent==rows[j].pid&&rows[j].kind==1){child=1;break;}
        if(!child)emit_process(rows[i].pid,L"Spotify.exe",&out,0);
    }
    int selected=-1;
    for(unsigned i=0;i<count;i++)if(rows[i].pid==owner&&rows[i].kind>1){selected=(int)i;break;}
    for(unsigned depth=0;selected>=0&&depth<count;depth++){
        int parent=-1;
        for(unsigned i=0;i<count;i++)if(rows[i].pid==rows[selected].parent&&rows[i].kind==rows[selected].kind){parent=(int)i;break;}
        if(parent<0)break;
        HANDLE child_handle=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,FALSE,rows[selected].pid);
        HANDLE parent_handle=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,FALSE,rows[parent].pid);
        ULONGLONG child_start=child_handle?creation(child_handle):0,parent_start=parent_handle?creation(parent_handle):0;
        if(child_handle)CloseHandle(child_handle);if(parent_handle)CloseHandle(parent_handle);
        if(parent==selected||!child_start||!parent_start||parent_start>child_start){selected=-1;break;}
        selected=parent;
        if(depth+1==count)selected=-1;
    }
    /* Require that the same peer still owns the live connection after discovery. */
    if(selected>=0&&owner&&peer_owner(port)==owner)emit_process(rows[selected].pid,process_names[rows[selected].kind],&out,1);
    emit_process(parent_pid(),L"NextUp",&out,0);puts("]");return 0;
}
#include "audio_completion.h"
typedef HRESULT (WINAPI *ActivateFn)(LPCWSTR,REFIID,PROPVARIANT*,IActivateAudioInterfaceCompletionHandler*,IActivateAudioInterfaceAsyncOperation**);
static int fail(const char *where,HRESULT hr){fprintf(stderr,"ERROR %s 0x%08lx\n",where,(unsigned long)hr);fflush(stderr);return 1;}
static HRESULT completion_create(Completion **out){
    *out=NULL;Completion *c=calloc(1,sizeof(*c));if(!c)return E_OUTOFMEMORY;
    c->iface.lpVtbl=&completion_vtbl;c->refs=1;c->result=E_FAIL;
    c->ready=CreateEventW(NULL,TRUE,FALSE,NULL);
    if(!c->ready){HRESULT hr=HRESULT_FROM_WIN32(GetLastError());free(c);return hr;}
    HRESULT hr=CoCreateFreeThreadedMarshaler((IUnknown*)&c->iface,&c->marshal);
    if(FAILED(hr)){release(&c->iface);return hr;}
    *out=c;return S_OK;
}
static HRESULT completion_check(Completion *c){
    IUnknown *agile=NULL,*identity=NULL,*marshal=NULL;
    HRESULT hr=query(&c->iface,&IID_IAgileObject,(void**)&agile);
    if(SUCCEEDED(hr)){
        hr=IUnknown_QueryInterface(agile,&IID_IUnknown,(void**)&identity);
        if(SUCCEEDED(hr)&&identity!=(IUnknown*)&c->iface)hr=E_FAIL;
    }
    if(SUCCEEDED(hr))hr=query(&c->iface,&IID_IMarshal,(void**)&marshal);
    if(marshal)IUnknown_Release(marshal);
    if(identity)IUnknown_Release(identity);
    if(agile)IUnknown_Release(agile);
    return hr;
}
static int completion_self_test(void){
    HRESULT hr=CoInitializeEx(NULL,COINIT_MULTITHREADED);if(FAILED(hr))return fail("COM",hr);
    Completion *c=NULL;hr=completion_create(&c);
    if(SUCCEEDED(hr))hr=completion_check(c);
    if(c)release(&c->iface);CoUninitialize();
    if(FAILED(hr))return fail("Callback interfaces",hr);
    puts("PASS: MTA callback exposes IAgileObject, IUnknown identity and IMarshal.");return 0;
}
static int capture(DWORD pid,ULONGLONG start){
    HANDLE process=OpenProcess(SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,pid);
    if(!process||!start||creation(process)!=start){if(process)CloseHandle(process);fprintf(stderr,"APP_CLOSED\n");return 2;}
    HANDLE parent=OpenProcess(SYNCHRONIZE,FALSE,parent_pid());
    HRESULT hr=CoInitializeEx(NULL,COINIT_MULTITHREADED);if(FAILED(hr))return fail("COM",hr);
    HMODULE mm=LoadLibraryExW(L"Mmdevapi.dll",NULL,LOAD_LIBRARY_SEARCH_SYSTEM32);
    ActivateFn activate=mm?(ActivateFn)(void*)GetProcAddress(mm,"ActivateAudioInterfaceAsync"):NULL;
    if(!activate)return fail("Windows application capture unavailable",E_NOTIMPL);
    Completion *c=NULL;hr=completion_create(&c);if(FAILED(hr))return fail("Callback creation",hr);
    hr=completion_check(c);if(FAILED(hr))return fail("Callback interfaces",hr);
    /* AUDIOCLIENT_ACTIVATION_PARAMS: PROCESS_LOOPBACK (1), PID, INCLUDE_TREE (0).
       Layout is three 32-bit fields; supported starting at Windows build 20348. */
    struct {DWORD type,pid,mode;} parameters={1,pid,0};
    PROPVARIANT variant;ZeroMemory(&variant,sizeof(variant));variant.vt=VT_BLOB;variant.blob.cbSize=sizeof(parameters);variant.blob.pBlobData=(BYTE*)&parameters;
    IActivateAudioInterfaceAsyncOperation *operation=NULL;
    hr=activate(L"VAD\\Process_Loopback",&IID_IAudioClient,&variant,&c->iface,&operation);
    if(FAILED(hr))return fail("Activate",hr);
    /* Terminate the helper on timeout so a late callback cannot touch freed data. */
    if(WaitForSingleObject(c->ready,8000)!=WAIT_OBJECT_0){fail("Activation timed out",HRESULT_FROM_WIN32(WAIT_TIMEOUT));ExitProcess(1);}
    if(operation)IActivateAudioInterfaceAsyncOperation_Release(operation);
    if(FAILED(c->result))return fail("Activation result",c->result);
    WAVEFORMATEX format={WAVE_FORMAT_PCM,2,48000,192000,4,16,0};
    hr=IAudioClient_Initialize(c->client,AUDCLNT_SHAREMODE_SHARED,AUDCLNT_STREAMFLAGS_LOOPBACK|AUDCLNT_STREAMFLAGS_EVENTCALLBACK|AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM,0,0,&format,NULL);
    if(FAILED(hr))return fail("Initialize",hr);
    IAudioCaptureClient *reader=NULL;hr=IAudioClient_GetService(c->client,&IID_IAudioCaptureClient,(void**)&reader);
    if(FAILED(hr))return fail("Capture service",hr);
    HANDLE event=CreateEventW(NULL,FALSE,FALSE,NULL);if(!event)return fail("Audio event",E_FAIL);
    hr=IAudioClient_SetEventHandle(c->client,event);if(FAILED(hr))return fail("Event handle",hr);
    _setmode(_fileno(stdout),_O_BINARY);setvbuf(stdout,NULL,_IONBF,0);
    hr=IAudioClient_Start(c->client);if(FAILED(hr))return fail("Start",hr);
    fprintf(stderr,"READY\n");fflush(stderr);int code=0;
    for(;;){
        if(WaitForSingleObject(process,0)==WAIT_OBJECT_0){fprintf(stderr,"APP_CLOSED\n");code=2;break;}
        if(parent&&WaitForSingleObject(parent,0)==WAIT_OBJECT_0)break;
        DWORD wait=WaitForSingleObject(event,100);if(wait==WAIT_TIMEOUT)continue;if(wait!=WAIT_OBJECT_0){code=fail("Wait",E_FAIL);break;}
        UINT32 packets=0;hr=IAudioCaptureClient_GetNextPacketSize(reader,&packets);
        while(SUCCEEDED(hr)&&packets){
            BYTE *data=NULL;UINT32 frames=0;DWORD flags=0;
            hr=IAudioCaptureClient_GetBuffer(reader,&data,&frames,&flags,NULL,NULL);if(FAILED(hr))break;
            size_t bytes=(size_t)frames*4;int ok=1;
            if(frames>48000*5)ok=0;
            else if(flags&AUDCLNT_BUFFERFLAGS_SILENT){static BYTE zeros[4096];while(bytes&&ok){size_t n=bytes>sizeof(zeros)?sizeof(zeros):bytes;ok=fwrite(zeros,1,n,stdout)==n;bytes-=n;}}
            else if(!data)ok=0;else ok=fwrite(data,1,bytes,stdout)==bytes;
            HRESULT released=IAudioCaptureClient_ReleaseBuffer(reader,frames);
            if(!ok||FAILED(released)){hr=FAILED(released)?released:E_ABORT;break;}
            hr=IAudioCaptureClient_GetNextPacketSize(reader,&packets);
        }
        if(FAILED(hr)){code=fail("Read",hr);break;}
    }
    IAudioClient_Stop(c->client);IAudioCaptureClient_Release(reader);CloseHandle(event);release(&c->iface);
    if(parent)CloseHandle(parent);CloseHandle(process);CoUninitialize();FreeLibrary(mm);return code;
}
int wmain(int argc,WCHAR **argv){
    if(argc==2&&!wcscmp(argv[1],L"--self-test"))return completion_self_test();
    if(argc==3&&!wcscmp(argv[1],L"--follow-list")){WCHAR *end=NULL;unsigned long port=wcstoul(argv[2],&end,10);if(end&&!*end&&port<=65535)return follow_list((unsigned)port);return 64;}
    if(argc==2&&!wcscmp(argv[1],L"--list")){putchar('[');EnumWindows(list_window,0);puts("]");return 0;}
    if(argc==4&&!wcscmp(argv[1],L"--capture")){
        WCHAR *end1=NULL,*end2=NULL;unsigned long pid=wcstoul(argv[2],&end1,10);ULONGLONG started=wcstoull(argv[3],&end2,10);
        if(pid&&started&&end1&&!*end1&&end2&&!*end2)return capture((DWORD)pid,started);
    }
    fprintf(stderr,"Use --list or --capture PID CREATION_TIME\n");return 64;
}
