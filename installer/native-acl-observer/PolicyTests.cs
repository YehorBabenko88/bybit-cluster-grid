#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.IO;
using System.Text.Json;
internal static class PolicyTests
{
 public static int Run(){
  var cases=new List<object>();
  void Test(string name,Action action,string? expected=null){
   string? code=null;try{action();}catch(Blocked b){code=b.Code;}
   if(code!=expected)throw new Exception("PURE_CASE_FAILED:"+name);
   cases.Add(new{ @case=name,outcome="PASS",physical_attestation=false,host_verified=false,apply_authorized=false,execute_authorized=false,cleanup_authorized=false });
  }
  Test("valid-path",()=>{if(Policy.Components(@"C:\fixture\file").Length!=3)throw new Exception();});
  foreach(var p in new[]{@"C:\x\..\f",@"C:\x\f.",@"C:\x\f ",@"C:\x\a:b",@"C:\x\CON",@"C:\x\COM1.txt",@"C:\x\a|b",@"C:\x\a~1",@"C:\x\\f"})
   Test("path-alias-"+cases.Count,()=>Policy.Components(p),"PATH_ALIAS");
  foreach(var p in new[]{@"\\server\share",@"c:\fixture",@"C:relative",@"\\?\C:\file"})Test("path-form-"+cases.Count,()=>Policy.Components(p),"PATH_FORM");
  var id=new Identity(1,"00000000000000000000000000000001",1,0x10);
  Test("directory",()=>Policy.Object(id,true));
  Test("reparse",()=>Policy.Object(id with{Attributes=0x410},true),"REPARSE");
  Test("hardlink",()=>Policy.Object(id with{Attributes=0,Links=2},false),"HARDLINK");
  Test("identity-unknown",()=>Policy.Object(id with{Volume=0},true),"IDENTITY_UNKNOWN");
  Test("identity-length-invalid",()=>Policy.Object(id with{FileId="X"},true),"IDENTITY_UNKNOWN");
  Test("identity-links-zero",()=>Policy.Object(id with{Links=0},true),"IDENTITY_UNKNOWN");
  Test("parent-file",()=>Policy.Object(id with{Attributes=0},true),"PARENT_NOT_DIRECTORY");
  Test("deny-only-group",()=>Policy.GroupFlags(0x10));
  Test("enabled-group",()=>Policy.GroupFlags(4));
  Test("disabled-group",()=>Policy.GroupFlags(0));
  Test("invalid-deny-enabled-group",()=>Policy.GroupFlags(0x14),"GROUP_FLAGS_INVALID");
  var row=new Observation(0,id,"S-1-5-18","S-1-5-18","hash",true,new(),new(){{"WRITE_DAC","DACL_DENY"}});
  Test("stable-snapshot",()=>Policy.Unchanged(row,row));
  Test("identity-ABA",()=>Policy.Unchanged(row,row with{Identity=id with{FileId="replacement"}}),"OBSERVATION_CHANGED");
  Test("descriptor-drift",()=>Policy.Unchanged(row,row with{DescriptorSha256="new"}),"OBSERVATION_CHANGED");
  Test("effective-rights-drift",()=>Policy.Unchanged(row,row with{EffectiveRights=new(){{"WRITE_DAC","DACL_ALLOW"}}}),"OBSERVATION_CHANGED");
  Test("group-layout-valid",()=>Policy.GroupLayout(2,100,8));
  Test("group-count-overflow",()=>Policy.GroupLayout(int.MaxValue,100,8),"TOKEN_GROUP_STRUCTURE");
  Test("group-table-truncated",()=>Policy.GroupLayout(2,20,8),"TOKEN_GROUP_STRUCTURE");
  Test("group-pointer-size",()=>Policy.GroupLayout(1,100,16),"TOKEN_GROUP_STRUCTURE");
  Test("sid-before-array",()=>Policy.SidBounds(4,100,24,1),"TOKEN_SID_BOUNDS");
  Test("sid-after-buffer",()=>Policy.SidBounds(98,100,24,1),"TOKEN_SID_BOUNDS");
  Test("sid-truncated",()=>Policy.SidBounds(80,100,24,4),"TOKEN_SID_BOUNDS");
  Test("sid-count-invalid",()=>Policy.SidBounds(24,100,24,16),"TOKEN_SID_BOUNDS");
  Test("unknown-group-flags",()=>Policy.GroupFlags(0x80),"GROUP_FLAGS_INVALID");
  Test("physical-volume-root",()=>Policy.RootMapping(@"\Device\HarddiskVolume3",@"\Device\HarddiskVolume3\"));
  Test("subst-root-refused",()=>Policy.RootMapping(@"\??\C:\fixture",@"\Device\HarddiskVolume3\fixture"),"ROOT_MAPPING_UNPROVEN");
  Test("root-final-name-mismatch",()=>Policy.RootMapping(@"\Device\HarddiskVolume3",@"\Device\HarddiskVolume4\"),"ROOT_MAPPING_UNPROVEN");
  Test("network-root-refused",()=>Policy.RootMapping(@"\Device\Mup\host",@"\Device\Mup\host\"),"ROOT_MAPPING_UNPROVEN");
  Test("scalar-probe-insufficient-buffer",()=>Policy.ScalarProbe(false,122,4));
  Test("scalar-probe-bad-length",()=>Policy.ScalarProbe(false,24,4));
  Test("scalar-probe-access-denied",()=>Policy.ScalarProbe(false,5,4),"TOKEN_SCALAR_PROBE");
  Test("scalar-probe-invalid-handle",()=>Policy.ScalarProbe(false,6,4),"TOKEN_SCALAR_PROBE");
  Test("scalar-probe-wrong-size",()=>Policy.ScalarProbe(false,24,8),"TOKEN_SCALAR_PROBE");
  Test("scalar-probe-unexpected-success",()=>Policy.ScalarProbe(true,122,4),"TOKEN_SCALAR_PROBE");
  Test("scalar-elevation-zero",()=>Policy.ScalarElevation(0));
  Test("scalar-elevation-one",()=>Policy.ScalarElevation(1));
  Test("scalar-elevation-invalid",()=>Policy.ScalarElevation(2),"TOKEN_SCALAR_VALUE");
  Test("share-bearing-read-only-access",()=>{if((Policy.ShareReadAccess&1)==0 || (Policy.ShareReadAccess&(2|4|0x10000|0x40000|0x80000))!=0)throw new Exception();});
  Test("session-command-exact",()=>Policy.SessionCommand("recheck"));
  Test("session-command-eof",()=>Policy.SessionCommand(null),"SESSION_INPUT_EOF");
  Test("session-command-bom",()=>Policy.SessionCommand("\uFEFFrecheck"),"SESSION_COMMAND_INVALID");
  Test("session-command-space",()=>Policy.SessionCommand("recheck "),"SESSION_COMMAND_INVALID");
  Console.WriteLine(JsonSerializer.Serialize(new{schema=1,status="OFFLINE_TEST_PASS",physical_attestation=false,host_verified=false,apply_authorized=false,execute_authorized=false,cleanup_authorized=false,cases},Program.Json));return 0;
 }
}
