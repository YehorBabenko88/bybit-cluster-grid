// Tests call ONLY FakeApi and managed parsing, never NativeApi.
namespace GridLab.LsaReadOnly.Tests {
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using GridLab.LsaReadOnly;
public sealed class FakePolicyApi : IPolicyApi {
    public uint OpenStatus, EnumStatus, FreeStatus, CloseStatus, Count=1;
    public uint? ConvertedError;
    public bool ThrowOpen, ThrowEnum, ThrowFree, ThrowClose, ThrowConvert, NullHandle, NullBuffer;
    public string Text="SeBatchLogonRight";
    public int Length=-1, Maximum=-1;
    public bool NullString;
    public int Opens, Closes, Frees, Enums;
    public string Calls="";
    readonly List<IntPtr> allocated = new List<IntPtr>();
    public uint Open(uint access, out IntPtr h) {
        Calls+="O"; Opens++; if(access!=0x800) throw new Exception("ACCESS_MASK");
        h=NullHandle?IntPtr.Zero:new IntPtr(123);
        if(ThrowOpen) throw new Exception(); return OpenStatus;
    }
    public uint Enumerate(IntPtr h, byte[] sid, out IntPtr b, out uint count) {
        Calls+="E"; Enums++; if(sid.Length<8 || sid.Length>68) throw new Exception("SID_BUFFER");
        b=IntPtr.Zero; count=Count;
        if(!NullBuffer) {
            var text=Marshal.StringToHGlobalUni(Text); allocated.Add(text);
            var s=new UnicodeString { Buffer=NullString?IntPtr.Zero:text,
                Length=(ushort)(Length<0?Text.Length*2:Length),
                MaximumLength=(ushort)(Maximum<0?Text.Length*2:Maximum) };
            int size=Marshal.SizeOf(typeof(UnicodeString));
            b=Marshal.AllocHGlobal(size*2); allocated.Add(b);
            Marshal.StructureToPtr(s,b,false); Marshal.StructureToPtr(s,IntPtr.Add(b,size),false);
        }
        if(ThrowEnum) throw new Exception(); return EnumStatus;
    }
    public uint Free(IntPtr p) { Calls+="F"; Frees++; if(ThrowFree) throw new Exception(); return FreeStatus; }
    public uint Close(IntPtr h) { Calls+="C"; Closes++; if(ThrowClose) throw new Exception(); return CloseStatus; }
    public uint WinError(uint s) { if(ThrowConvert) throw new Exception(); return ConvertedError ?? (s==Reader.NotAssigned?2U:5U); }
    public void ReleaseFixture() { foreach(var p in allocated) Marshal.FreeHGlobal(p); }
}
public static class LsaMockTests {
    static void Check(bool b) { if(!b) throw new Exception("MOCK_ASSERTION_FAILED"); }
    static int cases;
    static void Run(Action<FakePolicyApi> setup, string code, string right, uint? status=null, uint? win32=null) {
        var api=new FakePolicyApi(); setup(api);
        try {
            var r=Reader.Read(api,"S-1-5-21-1-2-3-1003");
            if(r.Code!=code) throw new Exception("CASE_"+(cases+1)+"_EXPECTED_"+code+"_GOT_"+r.Code);
            if(status.HasValue) Check(r.Status==status.Value);
            if(win32.HasValue) Check(r.Win32Error==win32.Value);
            Check((r.State=="DIRECT_ONLY")== (code=="ENUMERATED" || code=="NO_DIRECT_ASSIGNMENTS"));
            Check(api.Opens==1 && api.Closes==(api.NullHandle?0:1));
            Check(api.Frees==(!api.NullBuffer && api.Enums>0?1:0));
            Check(api.Calls==("O"+(api.Enums>0?"E":"")+(api.Frees>0?"F":"")+(api.Closes>0?"C":"")));
            Check(right==null?r.Rights.Length==0:r.Rights.Length==1 && r.Rights[0]==right);
            if(code=="CLEANUP_FAILED") Check(r.CleanupFailed);
            if((code=="OPEN_FAILED" || code=="ENUMERATE_FAILED") && !win32.HasValue) Check(r.Win32Error==5);
            cases++;
        } finally { api.ReleaseFixture(); }
    }
    public static int RunAll() {
        cases=0;
        Run(a=>{},"ENUMERATED","SeBatchLogonRight");
        foreach(var right in new[]{"SeDenyBatchLogonRight","SeDenyInteractiveLogonRight",
            "SeDenyServiceLogonRight","SeDenyNetworkLogonRight","SeDenyRemoteInteractiveLogonRight"})
            Run(a=>a.Text=right,"ENUMERATED",right);
        Run(a=>{a.EnumStatus=Reader.NotAssigned;a.Count=0;a.NullBuffer=true;},"NO_DIRECT_ASSIGNMENTS",null);
        Run(a=>{a.Count=0;a.NullBuffer=true;},"API_OR_DATA_ERROR",null);
        Run(a=>a.Count=0,"API_OR_DATA_ERROR",null);
        Run(a=>a.OpenStatus=0xC0000022,"OPEN_FAILED",null);
        Run(a=>a.EnumStatus=0xC0000022,"ENUMERATE_FAILED",null);
        Run(a=>a.EnumStatus=0xC0000001,"ENUMERATE_FAILED",null);
        Run(a=>a.ThrowOpen=true,"API_OR_DATA_ERROR",null);
        Run(a=>a.ThrowEnum=true,"API_OR_DATA_ERROR",null);
        Run(a=>{a.EnumStatus=0xC0000022;a.ThrowConvert=true;},"API_OR_DATA_ERROR",null);
        Run(a=>a.NullHandle=true,"INVALID_HANDLE",null);
        Run(a=>a.NullBuffer=true,"API_OR_DATA_ERROR",null);
        Run(a=>a.Count=257,"API_OR_DATA_ERROR",null);
        Run(a=>a.Count=2,"API_OR_DATA_ERROR",null); // Duplicate rights.
        Run(a=>a.Length=1,"API_OR_DATA_ERROR",null);
        Run(a=>a.Length=0,"API_OR_DATA_ERROR",null);
        Run(a=>a.Length=514,"API_OR_DATA_ERROR",null);
        Run(a=>a.Maximum=2,"API_OR_DATA_ERROR",null);
        Run(a=>a.Maximum=35,"API_OR_DATA_ERROR",null);
        Run(a=>a.NullString=true,"API_OR_DATA_ERROR",null);
        Run(a=>a.Text="SeBatchLogonRight\0hidden","API_OR_DATA_ERROR",null);
        Run(a=>a.FreeStatus=1,"CLEANUP_FAILED",null);
        Run(a=>a.CloseStatus=1,"CLEANUP_FAILED",null);
        Run(a=>a.ThrowFree=true,"CLEANUP_FAILED",null);
        Run(a=>a.ThrowClose=true,"CLEANUP_FAILED",null);
        // Native status, never a converted Win32 code, selects the no-assignment branch.
        Run(a=>{a.EnumStatus=2;a.Count=0;a.NullBuffer=true;},"ENUMERATE_FAILED",null,2,5);
        Run(a=>{a.EnumStatus=0x80000005;a.NullBuffer=true;},"ENUMERATE_FAILED",null,0x80000005,5);
        Run(a=>{a.OpenStatus=Reader.NotAssigned;a.NullHandle=true;},"OPEN_FAILED",null,0xC0000034,2);
        Run(a=>{a.EnumStatus=Reader.NotAssigned;a.Count=0;},"ENUMERATE_FAILED",null,0xC0000034,2);
        Run(a=>{a.EnumStatus=Reader.NotAssigned;a.Count=1;a.NullBuffer=true;},"ENUMERATE_FAILED",null,0xC0000034,2);
        Run(a=>{a.EnumStatus=Reader.NotAssigned;a.Count=0;a.NullBuffer=true;a.ThrowConvert=true;},"API_OR_DATA_ERROR",null,0xC0000034,0);
        Run(a=>{a.OpenStatus=0xC0000022;a.ThrowConvert=true;},"API_OR_DATA_ERROR",null,0xC0000022,0);
        Run(a=>{a.OpenStatus=0xC0000022;a.CloseStatus=0xC0000001;},"CLEANUP_FAILED",null,0xC0000022,5);
        Run(a=>{a.EnumStatus=0xC0000022;a.ThrowFree=true;a.ThrowClose=true;},"CLEANUP_FAILED",null,0xC0000022,5);
        Run(a=>{a.FreeStatus=0xC0000001;a.CloseStatus=0xC0000022;},"CLEANUP_FAILED",null,0,0);
        Run(a=>{a.EnumStatus=Reader.NotAssigned;a.Count=0;a.NullBuffer=true;a.ThrowClose=true;},"CLEANUP_FAILED",null,0xC0000034,2);
        Run(a=>{a.Length=1;a.ThrowFree=true;},"CLEANUP_FAILED",null,0,0);
        Run(a=>{a.EnumStatus=0xC0000022;a.ConvertedError=0;},"ENUMERATE_FAILED",null,0xC0000022,0);
        Run(a=>{a.EnumStatus=0xC0000001;a.ConvertedError=317;},"ENUMERATE_FAILED",null,0xC0000001,317);
        foreach(var sid in new[]{null,"","not-a-sid","s-1-5-21-1-2-3-1003","S-1-5-21-01-2-3-1003"}) {
            var invalid=new FakePolicyApi();
            var result=Reader.Read(invalid,sid);
            Check(result.State=="UNKNOWN" && result.Rights.Length==0 && invalid.Opens==0); cases++;
        }
        return cases;
    }
}
}
