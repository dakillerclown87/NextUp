/* NextUp WASAPI completion callback. MIT. Shared by the helper and regression test. */
#ifndef NEXTUP_AUDIO_COMPLETION_H
#define NEXTUP_AUDIO_COMPLETION_H
typedef struct {
    IActivateAudioInterfaceCompletionHandler iface;
    LONG refs;HANDLE ready;IUnknown *marshal;IAudioClient *client;HRESULT result;
} Completion;
static ULONG STDMETHODCALLTYPE addref(IActivateAudioInterfaceCompletionHandler *i){return InterlockedIncrement(&((Completion*)i)->refs);}
static ULONG STDMETHODCALLTYPE release(IActivateAudioInterfaceCompletionHandler *i){
    Completion *c=(Completion*)i;LONG r=InterlockedDecrement(&c->refs);
    if(!r){if(c->client)IAudioClient_Release(c->client);if(c->marshal)IUnknown_Release(c->marshal);if(c->ready)CloseHandle(c->ready);free(c);}return r;
}
static HRESULT STDMETHODCALLTYPE query(IActivateAudioInterfaceCompletionHandler *i,REFIID iid,void **out){
    if(!out)return E_POINTER;*out=NULL;
    /* ActivateAudioInterfaceAsync checks the agile marker as well as IMarshal.
       IAgileObject has only IUnknown methods and shares this COM identity. */
    if(IsEqualIID(iid,&IID_IUnknown)||IsEqualIID(iid,&IID_IActivateAudioInterfaceCompletionHandler)||IsEqualIID(iid,&IID_IAgileObject)){*out=i;addref(i);return S_OK;}
    if(IsEqualIID(iid,&IID_IMarshal)&&((Completion*)i)->marshal)return IUnknown_QueryInterface(((Completion*)i)->marshal,iid,out);
    return E_NOINTERFACE;
}
static HRESULT STDMETHODCALLTYPE completed(IActivateAudioInterfaceCompletionHandler *i,IActivateAudioInterfaceAsyncOperation *op){
    Completion *c=(Completion*)i;IUnknown *object=NULL;HRESULT activated=E_FAIL;
    c->result=IActivateAudioInterfaceAsyncOperation_GetActivateResult(op,&activated,&object);
    if(SUCCEEDED(c->result))c->result=activated;
    if(SUCCEEDED(c->result)&&object)c->result=IUnknown_QueryInterface(object,&IID_IAudioClient,(void**)&c->client);
    else if(SUCCEEDED(c->result))c->result=E_NOINTERFACE;
    if(object)IUnknown_Release(object);SetEvent(c->ready);return S_OK;
}
static IActivateAudioInterfaceCompletionHandlerVtbl completion_vtbl={query,addref,release,completed};
#endif
