#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
internal static class FixtureMain
{
 static int Main(string[] args){
  try{
   if(args.Length==1 && args[0]=="--model-tests"){
    Console.WriteLine(JsonSerializer.Serialize(new{kind="SYNTHETIC_JOURNAL_MODEL",cases=JournalTests.Run(),status="OFFLINE_TEST_PASS",host_verified=false,physical_attestation=false,apply_authorized=false,execute_authorized=false,cleanup_authorized=false}));return 0;
   }
   // Execution restriction, not an unforgeable attestation. This project is test tooling only.
   string Env(string key)=>Environment.GetEnvironmentVariable(key)??"";
   string head=Env("EXACT_HEAD_SHA"),run=Env("GITHUB_RUN_ID"),attempt=Env("GITHUB_RUN_ATTEMPT");
   if(args.Length!=1 || args[0]!="--hosted-fixture-tests" || !OperatingSystem.IsWindows() || Env("GITHUB_ACTIONS")!="true" ||
     Env("RUNNER_ENVIRONMENT")!="github-hosted" || Env("GITHUB_REPOSITORY")!="YehorBabenko88/bybit-cluster-grid" || Env("GITHUB_JOB")!="observer-fixture" ||
     !System.Text.RegularExpressions.Regex.IsMatch(head,"^[0-9a-f]{40}$"))throw new Blocked("HOSTED_TRANSACTION_FIXTURE_ONLY");
   using var token=Native.CaptureToken();string sid=Native.TokenFacts(token).User;
   var cases=new List<object>();
   var snapshots=new List<object>();
   void Snapshot(string name,OwnedFixture f){snapshots.Add(new{@case=name,binding=f.Binding,journal_id=f.JournalId,root_observed=Native.Id(f.Root),target_observed=Native.Id(f.Target),
    current_descriptor=FixtureNative.Descriptor(f.Target),journal_base64=Convert.ToBase64String(FixtureNative.Read(f.Journal))});}
   void Test(string name,Action action){action();cases.Add(new{@case=name,outcome="PASS",kind="HOSTED_GUID_TRANSACTION_TEST",head,run_id=run,attempt,
    host_verified=false,physical_attestation=false,apply_authorized=false,execute_authorized=false,cleanup_authorized=false});}
   OwnedFixture New()=>new(head,run,attempt,sid);
   static void Require(bool value){if(!value)throw new Blocked("FIXTURE_ASSERTION");}
   static void Refused(Action action,string code){try{action();}catch(Blocked b)when(b.Code==code){return;}throw new Blocked("EXPECTED_FIXTURE_REFUSAL_MISSING");}
   static int MoveError(string path){try{File.Move(path,path+".replacement");return 0;}catch(IOException e){return e.HResult&0xffff;}}
   List<TxRecord> Write(OwnedFixture f,List<TxRecord> rows,string phase){
    f.Guard(rows.Count>=3?f.New:f.Old);
    var next=JournalModel.Append(rows,f.Binding,phase);
    FixtureNative.AppendFlush(f.Journal,Encoding.UTF8.GetBytes(JsonSerializer.Serialize(next[^1])+"\n"));
    JournalModel.Validate(JournalModel.Parse(FixtureNative.Read(f.Journal)),f.Binding,next[^1].Digest);return next;
   }
   using(var f=New()){
    Test("protected-native-create",()=>f.Guard(f.Old));
    Test("exclusive-target-reopen-refused",()=>Refused(()=>{using var h=Native.OpenChild(f.Root,"target.fixture",false);},"NT_OPEN_FAILED"));
    Test("exclusive-journal-reopen-refused",()=>Refused(()=>{using var h=Native.OpenChild(f.Root,"journal.jsonl",false);},"NT_OPEN_FAILED"));
    foreach(string leaf in new[]{"target.fixture","journal.jsonl"})foreach(bool write in new[]{false,true}){
     Test("exclusive-data-"+leaf+"-"+(write?"write":"read"),()=>{
      try{using var h=FixtureNative.ProbeData(f.Root,leaf,write);}catch(Blocked b)when(b.Code=="FIXTURE_CREATE_REFUSED" && b.NativeError==unchecked((int)0xc0000043)){return;}
      throw new Blocked("EXCLUSIVE_DATA_SHARING_NOT_PROVEN");
     });
    }
    Test("existing-target-create-refused",()=>Refused(()=>{using var h=FixtureNative.Create(f.Root,"target.fixture",false,new System.Security.AccessControl.RawSecurityDescriptor("D:P(A;;FA;;;SY)"));},"FIXTURE_CREATE_REFUSED"));
    Test("concurrent-leaf-moves-refused",()=>{
     var tasks=Enumerable.Range(0,8).Select(_=>Task.Run(()=>MoveError(System.IO.Path.Combine(f.Path,"target.fixture")))).ToArray();
     Require(Task.WaitAll(tasks,10000) && tasks.All(t=>t.Result==32));f.Guard(f.Old);
    });
    var rows=new List<TxRecord>();
    Test("prepared-before-mutation",()=>{rows=Write(f,rows,"PREPARED");f.Guard(f.Old);});
    Test("commit-native-readback",()=>{
     rows=Write(f,rows,"INTENT");f.Change(f.Old,f.New);
     // Mutation occurs after durable INTENT and before APPLIED. Readback is mandatory.
     var next=JournalModel.Append(rows,f.Binding,"APPLIED");FixtureNative.AppendFlush(f.Journal,Encoding.UTF8.GetBytes(JsonSerializer.Serialize(next[^1])+"\n"));rows=next;
     rows=Write(f,rows,"VERIFIED");rows=Write(f,rows,"COMMITTED");f.Guard(f.New);
     JournalModel.Validate(JournalModel.Parse(FixtureNative.Read(f.Journal)),f.Binding,rows[^1].Digest);
     Snapshot("commit-native-readback",f);
    });
   }
   foreach(string stop in new[]{"PREPARED","INTENT","AFTER_SET","APPLIED","VERIFIED","COMMITTED"}){
    Test("simulated-reopen-"+stop,()=>{
     using var f=New();var rows=Write(f,new(),"PREPARED");
     if(stop!="PREPARED")rows=Write(f,rows,"INTENT");
     if(stop is "AFTER_SET" or "APPLIED" or "VERIFIED" or "COMMITTED")f.Change(f.Old,f.New);
     if(stop is "APPLIED" or "VERIFIED" or "COMMITTED"){
      var next=JournalModel.Append(rows,f.Binding,"APPLIED");FixtureNative.AppendFlush(f.Journal,Encoding.UTF8.GetBytes(JsonSerializer.Serialize(next[^1])+"\n"));rows=next;
     }
     if(stop is "VERIFIED" or "COMMITTED")rows=Write(f,rows,"VERIFIED");
     if(stop=="COMMITTED")rows=Write(f,rows,"COMMITTED");
     string anchor=rows[^1].Digest;f.ReopenChildren();
     var recovered=JournalModel.Parse(FixtureNative.Read(f.Journal));JournalModel.Validate(recovered,f.Binding,anchor);
     string current=FixtureNative.Descriptor(f.Target);string decision=JournalModel.Classify(recovered,f.Binding,current);
     if(decision=="RESTORE_REQUIRES_FIXTURE_APPROVAL"){
      // Approval is hard-coded for this freshly-created test file only, never inherited by production.
      var restore=JournalModel.Append(recovered,f.Binding,"RESTORE_INTENT");
      FixtureNative.AppendFlush(f.Journal,Encoding.UTF8.GetBytes(JsonSerializer.Serialize(restore[^1])+"\n"));
      f.Change(f.New,f.Old);var restored=JournalModel.Append(restore,f.Binding,"RESTORED");
      FixtureNative.AppendFlush(f.Journal,Encoding.UTF8.GetBytes(JsonSerializer.Serialize(restored[^1])+"\n"));
      JournalModel.Validate(JournalModel.Parse(FixtureNative.Read(f.Journal)),f.Binding,restored[^1].Digest);
     }else Require(decision=="UNCHANGED");f.Guard(f.Old);Snapshot("simulated-reopen-"+stop,f);
    });
   }
   Test("descriptor-drift-stop",()=>{using var f=New();f.Change(f.Old,f.New);Refused(()=>f.Guard(f.Old),"FIXTURE_CUSTODY_CHANGED");});
   Test("injected-flush-stop-before-mutation",()=>{
    using var f=New();var rows=JournalModel.Append(new(),f.Binding,"PREPARED");
    Refused(()=>FixtureNative.AppendFlush(f.Journal,JournalModel.Encode(rows),true),"INJECTED_FIXTURE_FLUSH_FAILURE");f.Guard(f.Old);
   });
   Test("native-truncated-journal-blocked",()=>{
    using var f=New();var rows=Write(f,new(),"PREPARED");FixtureNative.AppendFlush(f.Journal,new byte[]{123});
    Refused(()=>JournalModel.Parse(FixtureNative.Read(f.Journal)),"FIXTURE_JOURNAL_BLOCKED");f.Guard(f.Old);
   });
   Console.WriteLine(JsonSerializer.Serialize(new{schema=1,status="OFFLINE_FIXTURE_PASS",head,run_id=run,attempt,cases,snapshots,
    crash_model="SIMULATED_BARRIER_REOPEN_RETAINED_ROOT",journal_authentication="NOT_PROVEN",durable_antirollback="BLOCKED",host_verified=false,
    physical_attestation=false,apply_authorized=false,execute_authorized=false,cleanup_authorized=false}));return 0;
  }catch(Exception e){Console.WriteLine(JsonSerializer.Serialize(new{schema=1,status="BLOCKED",reason=e is Blocked b?b.Code:"FIXTURE_FAILURE",host_verified=false,
   physical_attestation=false,apply_authorized=false,execute_authorized=false,cleanup_authorized=false}));return 2;}
 }
}
