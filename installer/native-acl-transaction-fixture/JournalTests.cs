#nullable enable
using System;
using System.Collections.Generic;
using System.Text;
using System.Text.Json;
internal static class JournalTests
{
 public static List<string> Run(){
  var cases=new List<string>();
  void Test(string name,Action a,bool reject=false){bool refused=false;try{a();}catch(Blocked){refused=true;}if(refused!=reject)throw new Exception("JOURNAL_TEST_FAILED:"+name);cases.Add(name);}
  var id=new Identity(1,"00000000000000000000000000000001",1,0x80);
  var b=new TxBinding(1,new string('a',40),"1","1",Guid.NewGuid().ToString("D"),id with{Attributes=16},id with{FileId="00000000000000000000000000000002"},"AQ==","Ag==");
  var prepared=JournalModel.Append(new(),b,"PREPARED");
  var intent=JournalModel.Append(prepared,b,"INTENT");
  var applied=JournalModel.Append(intent,b,"APPLIED");
  var verified=JournalModel.Append(applied,b,"VERIFIED");
  var committed=JournalModel.Append(verified,b,"COMMITTED");
  Test("prepared-valid",()=>JournalModel.Validate(prepared,b,prepared[^1].Digest));
  Test("committed-valid",()=>JournalModel.Validate(committed,b,committed[^1].Digest));
  Test("commit-without-intent",()=>JournalModel.Append(prepared,b,"COMMITTED"),true);
  Test("duplicate-prepared",()=>JournalModel.Append(prepared,b,"PREPARED"),true);
  Test("unknown-phase",()=>JournalModel.Append(prepared,b,"ACTIVE"),true);
  Test("head-substitution",()=>JournalModel.Validate(committed,b with{Head=new string('b',40)},committed[^1].Digest),true);
  Test("run-replay",()=>JournalModel.Validate(committed,b with{Run="2"},committed[^1].Digest),true);
  Test("attempt-replay",()=>JournalModel.Validate(committed,b with{Attempt="2"},committed[^1].Digest),true);
  Test("target-ABA",()=>JournalModel.Validate(committed,b with{Target=id},committed[^1].Digest),true);
  Test("stale-prefix-anchor",()=>JournalModel.Validate(intent,b,committed[^1].Digest),true);
  Test("missing-anchor",()=>JournalModel.Validate(committed,b,""),true);
  Test("changed-record",()=>{var x=new List<TxRecord>(committed);x[1]=x[1] with{Phase="APPLIED"};JournalModel.Validate(x,b,committed[^1].Digest);},true);
  Test("reordered-records",()=>{var x=new List<TxRecord>(committed);(x[0],x[1])=(x[1],x[0]);JournalModel.Validate(x,b,committed[^1].Digest);},true);
  byte[] bytes=JournalModel.Encode(committed);
  Test("roundtrip",()=>JournalModel.Validate(JournalModel.Parse(bytes),b,committed[^1].Digest));
  Test("truncated-tail",()=>JournalModel.Parse(bytes[..^1]),true);
  Test("duplicate-json-key",()=>JournalModel.Parse(Encoding.UTF8.GetBytes("{\"Sequence\":0,\"Sequence\":1}\n")),true);
  Test("unknown-json-field",()=>JournalModel.Parse(Encoding.UTF8.GetBytes(Encoding.UTF8.GetString(bytes).Replace("\"Sequence\":0","\"Authority\":true,\"Sequence\":0"))),true);
  Test("missing-journal",()=>JournalModel.Parse(Array.Empty<byte>()),true);
  Test("oversized-journal",()=>JournalModel.Parse(new byte[262145]),true);
  Test("recovery-original",()=>{if(JournalModel.Classify(intent,b,b.Old)!="UNCHANGED")throw new Exception();});
  Test("recovery-poststate",()=>{if(JournalModel.Classify(intent,b,b.New)!="RESTORE_REQUIRES_FIXTURE_APPROVAL")throw new Exception();});
  Test("recovery-drift",()=>JournalModel.Classify(intent,b,"Aw=="),true);
  Test("prepared-with-mutation",()=>JournalModel.Classify(prepared,b,b.New),true);
  Test("invalid-binding",()=>JournalModel.Append(new(),b with{Id="not-guid"},"PREPARED"),true);
  foreach(var rows in new[]{applied,verified,committed})Test("old-after-"+rows[^1].Phase+"-refused",()=>JournalModel.Classify(rows,b,b.Old),true);
  var restoring=JournalModel.Append(committed,b,"RESTORE_INTENT");var restored=JournalModel.Append(restoring,b,"RESTORED");
  Test("restore-intent-old-valid",()=>JournalModel.Classify(restoring,b,b.Old));
  Test("restored-old-valid",()=>JournalModel.Classify(restored,b,b.Old));
  Test("restored-new-refused",()=>JournalModel.Classify(restored,b,b.New),true);
  return cases;
 }
}
