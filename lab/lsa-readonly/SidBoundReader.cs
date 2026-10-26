namespace GridLab.LsaReadOnly {
using System;
using System.Security.Principal;
 public static class SidBoundReader {
  public static Result Read(IPolicyApi api,string expectedSid,string observedSid) {
   try {
    if(expectedSid==null || observedSid==null || expectedSid.Length>184 || observedSid.Length>184 || new SecurityIdentifier(expectedSid).Value!=expectedSid || new SecurityIdentifier(observedSid).Value!=observedSid || expectedSid!=observedSid)
     return new Result {Code="SID_MISMATCH"};
   }catch{return new Result {Code="SID_MISMATCH"};}
   return Reader.Read(api,observedSid);
  }
 }
}
