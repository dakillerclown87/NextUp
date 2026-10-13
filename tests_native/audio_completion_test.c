/* Exercise the production COM callback with deterministic Win32/COM stubs.
 * This validates QueryInterface/refcounts, not actual Windows WASAPI capture. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define STDMETHODCALLTYPE
#define S_OK 0
#define E_NOINTERFACE ((HRESULT)0x80004002u)
#define E_POINTER ((HRESULT)0x80004003u)
#define E_FAIL ((HRESULT)0x80004005u)
#define SUCCEEDED(x) ((x)>=0)
typedef int32_t HRESULT;
typedef int32_t LONG;
typedef unsigned long ULONG;
typedef int HANDLE;
typedef const int *REFIID;
static const int IID_IUnknown=1,IID_IActivateAudioInterfaceCompletionHandler=2,IID_IMarshal=3,IID_IAgileObject=4,IID_IAudioClient=5;
static int IsEqualIID(REFIID a,REFIID b){return *a==*b;}
static ULONG InterlockedIncrement(LONG *p){return ++*p;}
static ULONG InterlockedDecrement(LONG *p){return --*p;}
static unsigned signals=0,closed=0;
static void CloseHandle(HANDLE h){assert(h==1);closed++;}
static void SetEvent(HANDLE h){assert(h==1);signals++;}
typedef struct {unsigned refs;} IUnknown;
typedef IUnknown IAudioClient;
static HRESULT IUnknown_QueryInterface(IUnknown *p,REFIID iid,void **out){*out=NULL;if(*iid==IID_IMarshal||*iid==IID_IAudioClient){p->refs++;*out=p;return S_OK;}return E_NOINTERFACE;}
static ULONG IUnknown_Release(IUnknown *p){return --p->refs;}
#define IAudioClient_Release IUnknown_Release
typedef struct {HRESULT status,activation;IUnknown *object;} IActivateAudioInterfaceAsyncOperation;
static HRESULT IActivateAudioInterfaceAsyncOperation_GetActivateResult(IActivateAudioInterfaceAsyncOperation *p,HRESULT *hr,IUnknown **out){*hr=p->activation;*out=p->object;if(*out)(*out)->refs++;return p->status;}
typedef struct IActivateAudioInterfaceCompletionHandler IActivateAudioInterfaceCompletionHandler;
typedef struct {
 HRESULT (*QueryInterface)(IActivateAudioInterfaceCompletionHandler*,REFIID,void**);
 ULONG (*AddRef)(IActivateAudioInterfaceCompletionHandler*);
 ULONG (*Release)(IActivateAudioInterfaceCompletionHandler*);
 HRESULT (*ActivateCompleted)(IActivateAudioInterfaceCompletionHandler*,IActivateAudioInterfaceAsyncOperation*);
} IActivateAudioInterfaceCompletionHandlerVtbl;
struct IActivateAudioInterfaceCompletionHandler {IActivateAudioInterfaceCompletionHandlerVtbl *lpVtbl;};
#include "../packaging/windows/audio_completion.h"
int main(void){
 IUnknown marshal={1},audio={1};
 Completion *c=calloc(1,sizeof(*c));assert(c);c->iface.lpVtbl=&completion_vtbl;c->refs=1;c->ready=1;c->marshal=&marshal;
 IActivateAudioInterfaceCompletionHandler *iface=&c->iface;void *out=NULL;
 /* Regression: beta.18 returns E_NOINTERFACE here, causing activation rejection. */
 assert(iface->lpVtbl->QueryInterface(iface,&IID_IAgileObject,&out)==S_OK);
 assert(out==iface&&c->refs==2);assert(iface->lpVtbl->Release(out)==1);
 assert(iface->lpVtbl->QueryInterface(iface,&IID_IUnknown,&out)==S_OK);assert(out==iface);iface->lpVtbl->Release(out);
 assert(iface->lpVtbl->QueryInterface(iface,&IID_IMarshal,&out)==S_OK);assert(out==&marshal&&marshal.refs==2);IUnknown_Release(out);
 const int invalid=99;out=(void*)1;assert(iface->lpVtbl->QueryInterface(iface,&invalid,&out)==E_NOINTERFACE&&out==NULL);
 assert(iface->lpVtbl->QueryInterface(iface,&IID_IAgileObject,NULL)==E_POINTER);
 IActivateAudioInterfaceAsyncOperation op={S_OK,S_OK,&audio};
 assert(iface->lpVtbl->ActivateCompleted(iface,&op)==S_OK);assert(c->result==S_OK&&c->client==&audio&&signals==1&&audio.refs==2);
 assert(iface->lpVtbl->Release(iface)==0);assert(closed==1&&marshal.refs==0&&audio.refs==1);
 puts("PASS: production callback supports IAgileObject, preserves COM identity, balances references and signals completion.");return 0;
}
