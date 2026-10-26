namespace GridLab.LsaReadOnly.Tests {
using System;
using System.Collections.Generic;
public static class G0MockTests {
 public static string[] RunAll() {
  var cases=new List<string>();const string sid="S-1-5-21-1-2-3-1003";
  foreach(string other in new[]{"S-1-5-21-1-2-3-1004","not-a-sid","s-1-5-21-1-2-3-1003",null}) {
   var api=new FakePolicyApi();var r=SidBoundReader.Read(api,sid,other);
   if(r.State!="UNKNOWN" || r.Code!="SID_MISMATCH" || api.Opens!=0)throw new Exception("IDENTITY_NOT_BLOCKED");
   cases.Add("sid-mismatch-"+cases.Count);
  }
  var shape=new FakePolicyApi {Count=0};
  try{var r=SidBoundReader.Read(shape,sid,sid);if(r.State!="UNKNOWN" || r.Code!="API_OR_DATA_ERROR" || shape.Frees!=1 || shape.Closes!=1)throw new Exception("ZERO_COUNT_SHAPE_ACCEPTED");cases.Add("zero-count-nonnull-buffer");}finally{shape.ReleaseFixture();}
  var valid=new FakePolicyApi();
  try{var r=SidBoundReader.Read(valid,sid,sid);if(r.State!="DIRECT_ONLY" || r.Code!="ENUMERATED")throw new Exception("DIRECT_OBSERVATION");cases.Add("sid-bound-direct-only");}finally{valid.ReleaseFixture();}
  return cases.ToArray();
 }
}
}
