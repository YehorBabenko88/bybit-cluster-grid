using System;
using GridS0;
public static class TokenObserverTests
{
    static void Need(bool x) { if(!x) throw new Exception("TOKEN_TEST"); }
    static void Block(Action f) { try { f(); } catch(InvalidOperationException) { return; } throw new Exception("EXPECTED_BLOCK"); }
    static void Put(byte[] b,int at,uint n) { Array.Copy(BitConverter.GetBytes(n),0,b,at,4); }
    public static void Run()
    {
        Need(TokenObserver.ProbeValid(20,false,24,4));
        Need(!TokenObserver.ProbeValid(3,false,24,4));
        Need(!TokenObserver.ProbeValid(20,false,122,8));
        Need(TokenObserver.ProbeValid(3,false,122,4));
        TokenObserver.ValidateGroupAttributes(16);
        TokenObserver.ValidateGroupAttributes(0x20000007);
        Block(delegate { TokenObserver.ValidateGroupAttributes(20); });
        Block(delegate { TokenObserver.ValidateGroupAttributes(0x80); });
        Block(delegate { TokenObserver.ValidateGroupAttributes(0x40000000); });
        Block(delegate { TokenObserver.DecodeGroups(new byte[8],0,3); });
        byte[] tooMany=new byte[8]; tooMany[1]=17;
        Block(delegate { TokenObserver.DecodeGroups(tooMany,0,8); });
        byte[] valid=new byte[40]; Put(valid,0,1); Put(valid,8,0x1018); Put(valid,16,16);
        valid[24]=1; valid[25]=2; valid[31]=5; Put(valid,32,32); Put(valid,36,544);
        TokenGroupFact[] decoded=TokenObserver.DecodeGroups(valid,0x1000,8);
        Need(decoded.Length==1 && decoded[0].Sid=="S-1-5-32-544" && decoded[0].Attributes==16);
        Put(valid,8,0x1010); Block(delegate { TokenObserver.DecodeGroups(valid,0x1000,8); });
        Put(valid,8,0x1018); valid[24]=2; Block(delegate { TokenObserver.DecodeGroups(valid,0x1000,8); });
        valid[24]=1; valid[25]=16; Block(delegate { TokenObserver.DecodeGroups(valid,0x1000,8); });
        byte[] pointer=new byte[24]; pointer[0]=1;
        Block(delegate { TokenObserver.DecodeGroups(pointer,0x1000,8); });
        Block(delegate { TokenObserver.DecodePrivileges(new byte[5],delegate(uint l,int h) { return "SeChangeNotifyPrivilege"; }); });
        byte[] priv=new byte[16]; priv[0]=1; priv[12]=4;
        Block(delegate { TokenObserver.DecodePrivileges(priv,delegate(uint l,int h) { return "SeChangeNotifyPrivilege"; }); });
        priv[12]=8; Block(delegate { TokenObserver.DecodePrivileges(priv,delegate(uint l,int h) { return "SeChangeNotifyPrivilege"; }); });
        priv[12]=2;
        Block(delegate { TokenObserver.DecodePrivileges(priv,delegate(uint l,int h) { return null; }); });
        TokenPrivilegeFact[] goodPriv=TokenObserver.DecodePrivileges(priv,delegate(uint l,int h) { return "SeChangeNotifyPrivilege"; });
        Need(goodPriv.Length==1 && goodPriv[0].Attributes==2);
        byte[] duplicate=new byte[28]; Put(duplicate,0,2);
        Block(delegate { TokenObserver.DecodePrivileges(duplicate,delegate(uint l,int h) { return "SeChangeNotifyPrivilege"; }); });
        TokenObservation o=new TokenObservation { Sid="S-1-5-21-1", Pid=1,CreationFileTime=1,Integrity="S-1-16-8192",Groups=new TokenGroupFact[0],Privileges=new TokenPrivilegeFact[]{new TokenPrivilegeFact { Name="SeChangeNotifyPrivilege",Attributes=2 }}};
        Need(TokenObserver.IsStandard(o));
        o.Privileges[0].Name="SeDebugPrivilege"; Need(!TokenObserver.IsStandard(o));
        o.Privileges=new TokenPrivilegeFact[0]; o.Groups=new TokenGroupFact[]{new TokenGroupFact{Sid="S-1-5-32-544",Attributes=4}};
        Need(!TokenObserver.IsStandard(o)); o.Groups[0].Attributes=16; Need(TokenObserver.IsStandard(o));
        o.Elevated=true; Need(!TokenObserver.IsStandard(o));
        o.Elevated=false; o.Integrity="S-1-16-12288"; Need(!TokenObserver.IsStandard(o));
        o.Integrity="S-1-16-4096"; Need(!TokenObserver.IsStandard(o));
    }
}
