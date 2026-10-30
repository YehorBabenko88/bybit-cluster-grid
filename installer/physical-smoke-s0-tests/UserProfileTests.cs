// Hosted-only fixture adapter. This mode is never part of production API.
using System;
using System.IO;
using System.Collections;
using System.Reflection;
using System.Security.Principal;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;
using GridS0;
public static class ProfileApi {
 public static bool UserProfile;
 public static string Parent() { if(!UserProfile) return Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData); using(var p=Bootstrap.HoldUserProfileV1(WindowsIdentity.GetCurrent().User.Value)) return p.ParentPath; }
 public static Bootstrap.TransferSenderLease OpenTransferSender(string root,string rootId,string payloadSHA,string knownHostsSHA,string sid) { return UserProfile?Bootstrap.OpenTransferSenderAtUserProfileV1(root,rootId,payloadSHA,knownHostsSHA,sid):Bootstrap.OpenTransferSender(root,rootId,payloadSHA,knownHostsSHA,sid); }
 public static Bootstrap.TransferSlotLease OpenTransferSlot(string root,string expectedRootId,string expectedFileId,string head,string run,string sha,long size,string sid,bool approved) { return UserProfile?Bootstrap.OpenTransferSlotAtUserProfileV1(root,expectedRootId,expectedFileId,head,run,sha,size,sid,approved):Bootstrap.OpenTransferSlot(root,expectedRootId,expectedFileId,head,run,sha,size,sid,approved); }
 public static BootstrapReceipt PlanInput(byte[] canonicalPlan,string expectedSha,string expectedHead,string expectedRunId,string targetRoot,string expectedSid) { return UserProfile?Bootstrap.PlanInputAtUserProfileV1(canonicalPlan,expectedSha,expectedHead,expectedRunId,targetRoot,expectedSid):Bootstrap.PlanInput(canonicalPlan,expectedSha,expectedHead,expectedRunId,targetRoot,expectedSid); }
 public static BootstrapReceipt PlanRoleImport(byte[] sixFileZip,string expectedSha,string expectedHead,string expectedRunId,string expectedPackageSha,string targetRoot,string expectedSid) { return UserProfile?Bootstrap.PlanRoleImportAtUserProfileV1(sixFileZip,expectedSha,expectedHead,expectedRunId,expectedPackageSha,targetRoot,expectedSid):Bootstrap.PlanRoleImport(sixFileZip,expectedSha,expectedHead,expectedRunId,expectedPackageSha,targetRoot,expectedSid); }
 public static TransferExportReceipt PlanTransferExport(string sourcePC4RoleRoot,string head,string run,string packageSha,string targetRoot,string sid) { return UserProfile?Bootstrap.PlanTransferExportAtUserProfileV1(sourcePC4RoleRoot,head,run,packageSha,targetRoot,sid):Bootstrap.PlanTransferExport(sourcePC4RoleRoot,head,run,packageSha,targetRoot,sid); }
 public static TransferKnownHostsReceipt PlanTransferKnownHosts(string exportRoot,string rootId,string payloadSHA,string head,string run,string hostIP,string ed25519Base64Blob,string fullSHA256Fingerprint,string sid) { return UserProfile?Bootstrap.PlanTransferKnownHostsAtUserProfileV1(exportRoot,rootId,payloadSHA,head,run,hostIP,ed25519Base64Blob,fullSHA256Fingerprint,sid):Bootstrap.PlanTransferKnownHosts(exportRoot,rootId,payloadSHA,head,run,hostIP,ed25519Base64Blob,fullSHA256Fingerprint,sid); }
 public static TransferProbeReceipt PlanTransferProbe(string head,string run,string hostIP,string ed25519Base64Blob,string fullSHA256Fingerprint,string targetNewInputUUID,string sid) { return UserProfile?Bootstrap.PlanTransferProbeAtUserProfileV1(head,run,hostIP,ed25519Base64Blob,fullSHA256Fingerprint,targetNewInputUUID,sid):Bootstrap.PlanTransferProbe(head,run,hostIP,ed25519Base64Blob,fullSHA256Fingerprint,targetNewInputUUID,sid); }
 public static TransferSlotReceipt PlanTransferSlot(string head,string run,string payloadSha,long size,string targetRoot,string sid) { return UserProfile?Bootstrap.PlanTransferSlotAtUserProfileV1(head,run,payloadSha,size,targetRoot,sid):Bootstrap.PlanTransferSlot(head,run,payloadSha,size,targetRoot,sid); }
 public static BootstrapReceipt StagePlanInput(byte[] canonicalPlan,string expectedSha,string expectedHead,string expectedRunId,string targetRoot,string expectedSid,bool approved) { return UserProfile?Bootstrap.StagePlanInputAtUserProfileV1(canonicalPlan,expectedSha,expectedHead,expectedRunId,targetRoot,expectedSid,approved):Bootstrap.StagePlanInput(canonicalPlan,expectedSha,expectedHead,expectedRunId,targetRoot,expectedSid,approved); }
 public static BootstrapReceipt StageRoleImport(byte[] sixFileZip,string expectedSha,string expectedHead,string expectedRunId,string expectedPackageSha,string targetRoot,string expectedSid,bool approved) { return UserProfile?Bootstrap.StageRoleImportAtUserProfileV1(sixFileZip,expectedSha,expectedHead,expectedRunId,expectedPackageSha,targetRoot,expectedSid,approved):Bootstrap.StageRoleImport(sixFileZip,expectedSha,expectedHead,expectedRunId,expectedPackageSha,targetRoot,expectedSid,approved); }
 public static TransferExportReceipt StageTransferExport(string sourcePC4RoleRoot,string head,string run,string packageSha,string targetRoot,string sid,bool approved) { return UserProfile?Bootstrap.StageTransferExportAtUserProfileV1(sourcePC4RoleRoot,head,run,packageSha,targetRoot,sid,approved):Bootstrap.StageTransferExport(sourcePC4RoleRoot,head,run,packageSha,targetRoot,sid,approved); }
 public static TransferKnownHostsReceipt StageTransferKnownHosts(string exportRoot,string rootId,string payloadSHA,string head,string run,string hostIP,string ed25519Base64Blob,string fullSHA256Fingerprint,string sid,bool approved) { return UserProfile?Bootstrap.StageTransferKnownHostsAtUserProfileV1(exportRoot,rootId,payloadSHA,head,run,hostIP,ed25519Base64Blob,fullSHA256Fingerprint,sid,approved):Bootstrap.StageTransferKnownHosts(exportRoot,rootId,payloadSHA,head,run,hostIP,ed25519Base64Blob,fullSHA256Fingerprint,sid,approved); }
 public static TransferProbeReceipt StageTransferProbe(string head,string run,string hostIP,string ed25519Base64Blob,string fullSHA256Fingerprint,string targetNewInputUUID,string sid,bool approved) { return UserProfile?Bootstrap.StageTransferProbeAtUserProfileV1(head,run,hostIP,ed25519Base64Blob,fullSHA256Fingerprint,targetNewInputUUID,sid,approved):Bootstrap.StageTransferProbe(head,run,hostIP,ed25519Base64Blob,fullSHA256Fingerprint,targetNewInputUUID,sid,approved); }
 public static TransferSlotReceipt StageTransferSlot(string head,string run,string payloadSha,long size,string targetRoot,string sid,bool approved) { return UserProfile?Bootstrap.StageTransferSlotAtUserProfileV1(head,run,payloadSha,size,targetRoot,sid,approved):Bootstrap.StageTransferSlot(head,run,payloadSha,size,targetRoot,sid,approved); }
}
public static class UserProfileTests {
 public static string Phase="FIXTURE_PROFILE_START";
 static readonly System.Collections.Generic.List<string> passed=new System.Collections.Generic.List<string>();
 static void Need(bool value) { if(!value) throw new InvalidOperationException("FIXTURE_USER_PROFILE_CHECK"); }
 static void Block(Action action) {
  try { action(); } catch(InvalidOperationException) { return; }
  catch(TargetInvocationException error) { if(error.InnerException is InvalidOperationException) return; throw; }
  throw new InvalidOperationException("FIXTURE_USER_PROFILE_EXPECTED_BLOCK");
 }
 static string Hash(byte[] b) { using(var sha=SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(b)).Replace("-","").ToLowerInvariant(); }
 static void Done(string name) { passed.Add(name); }
 static string Fresh(string parent,string prefix) { return Path.Combine(parent,prefix+Guid.NewGuid().ToString("D")); }
 static IDisposable Pins(string path,string sid) { return (IDisposable)Activator.CreateInstance(typeof(Bootstrap).GetNestedType("Pins",BindingFlags.NonPublic),BindingFlags.Instance|BindingFlags.NonPublic,null,new object[]{path,sid,true},null); }
 static void Check(IDisposable pins) { pins.GetType().GetMethod("Check",BindingFlags.Instance|BindingFlags.NonPublic).Invoke(pins,null); }
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool CreateHardLinkW(string link,string existing,IntPtr attributes);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern SafeFileHandle CreateFileW(string path,uint access,uint share,IntPtr attributes,uint disposition,uint flags,IntPtr template);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool DeviceIoControl(SafeFileHandle file,uint code,byte[] input,int length,IntPtr output,int outLength,out int returned,IntPtr overlapped);
 static void Junction(string path,string target) {
  Directory.CreateDirectory(path); byte[] sub=Encoding.Unicode.GetBytes("\\??\\"+target),print=Encoding.Unicode.GetBytes(target);
  byte[] data=new byte[20+sub.Length+print.Length];
  Array.Copy(BitConverter.GetBytes(0xa0000003u),0,data,0,4);Array.Copy(BitConverter.GetBytes((ushort)(data.Length-8)),0,data,4,2);
  Array.Copy(BitConverter.GetBytes((ushort)sub.Length),0,data,10,2);Array.Copy(BitConverter.GetBytes((ushort)(sub.Length+2)),0,data,12,2);Array.Copy(BitConverter.GetBytes((ushort)print.Length),0,data,14,2);
  Array.Copy(sub,0,data,16,sub.Length);Array.Copy(print,0,data,18+sub.Length,print.Length);
  using(var handle=CreateFileW(path,0x40000000,7,IntPtr.Zero,3,0x2200000,IntPtr.Zero)) { int count;Need(!handle.IsInvalid && DeviceIoControl(handle,0x900a4,data,data.Length,IntPtr.Zero,0,out count,IntPtr.Zero)); }
 }
 static string Slot(string parent,string sid,string head) {
  string target=Fresh(parent,"GridS0Input-");Bootstrap.StageTransferSlotAtUserProfileV1(head,Guid.NewGuid().ToString("D"),new string('a',64),1,target,sid,true);return target;
 }
 static void RuntimeActions(string sourceRoot,string package,string parent,string sid,string head,string packageSha) {
  string run=Guid.NewGuid().ToString("D"),pair=Path.Combine(parent,"GridS0-"+run),role=Path.Combine(pair,"LS5"),input=Fresh(parent,"GridS0Input-");
  string plan=(string)typeof(InputTests).GetField("Plan",BindingFlags.Static|BindingFlags.NonPublic).GetRawConstantValue();
  plan=plan.Replace(new string('a',40),head).Replace("12345678-1234-4234-8234-123456789abc",run).Replace("S-1-5-21-1-2-3-1001",sid).Replace("\"LS5\":\"LS5\"","\"LS5\":\""+Environment.MachineName.ToUpperInvariant()+"\"").Replace("\"PC4\":\"PC4\"","\"PC4\":\"NOT-A-NODE\"");
  var occupied=new System.Collections.Generic.HashSet<int>();foreach(var endpoint in System.Net.NetworkInformation.IPGlobalProperties.GetIPGlobalProperties().GetActiveTcpListeners()) occupied.Add(endpoint.Port);
  int port=62044;while(occupied.Contains(port) && port<65535) port++;Need(!occupied.Contains(port));plan=plan.Replace("49152",port.ToString());
  byte[] bytes=Encoding.ASCII.GetBytes(plan);Bootstrap.StagePlanInputAtUserProfileV1(bytes,Hash(bytes),head,run,input,sid,true);
  foreach(string action in new[]{"prepare","preflight","status","stop","execute","evidence"}) {
   Phase="FIXTURE_PROFILE_RUNTIME_"+action.ToUpperInvariant();string dataRoot=action=="prepare"?pair:role;
   string config=action=="prepare"?Path.Combine(input,"s0-plan.json"):Path.Combine(role,"config.json");
   byte[] errors;int exit;byte[] raw=BootstrapTests.HostedRuntimeAction(package,head,packageSha,action,dataRoot,config,sourceRoot,action=="prepare" || action=="stop" || action=="evidence",out errors,out exit);
   Need(raw.Length<=65536 && errors.Length<=65536);
   using(var saved=new FileStream(Path.Combine(sourceRoot,"temp","profile-cli-"+action+".json"),FileMode.CreateNew,FileAccess.Write,FileShare.None)) saved.Write(raw,0,raw.Length);
   using(var saved=new FileStream(Path.Combine(sourceRoot,"temp","profile-cli-"+action+".stderr"),FileMode.CreateNew,FileAccess.Write,FileShare.None)) saved.Write(errors,0,errors.Length);
   string text=Encoding.UTF8.GetString(raw),errorText=Encoding.UTF8.GetString(errors);
   if(action=="execute") Need(exit!=0 && errorText.Contains("S0_EXPLICIT_APPROVAL_REQUIRED"));
   else if(action=="evidence") Need(exit!=0 && text.Contains("BLOCKED") && errorText.Contains("S0_COMMAND_FAILED"));
   else {
    string expected=action=="prepare"?"S0_PREPARED_NOT_EXECUTED":action=="preflight"?"APPLICATION_PREFLIGHT_PASS_NOT_AUTHORIZATION":action=="status"?"S0_NOT_STARTED":"OWN_STOP_NOTIFICATION_WRITTEN_NO_SIGNALS";
    Need(exit==0 && errors.Length==0 && text.Contains(expected));
   }
  }
  Done("runtime_prepare_preflight_status_stop");Done("runtime_execute_evidence_blocked");
 }
 public static void Hosted(string sourceRoot,string head,string sid) {
  Need(Environment.GetEnvironmentVariable("GITHUB_ACTIONS")=="true" && Environment.GetEnvironmentVariable("RUNNER_ENVIRONMENT")=="github-hosted" && Environment.GetEnvironmentVariable("GITHUB_JOB")=="s0-windows");
  Need(!String.Equals(Environment.MachineName,"LS5",StringComparison.OrdinalIgnoreCase) && !String.Equals(Environment.MachineName,"PC4",StringComparison.OrdinalIgnoreCase));
  TokenObserver.RequireStandard(sid);passed.Clear();ProfileApi.UserProfile=true;
  try {
   string parent,parentId;using(var proof=Bootstrap.HoldUserProfileV1(sid)) { parent=proof.ParentPath;parentId=proof.ParentIdentity;proof.Check(); }
   Phase="FIXTURE_PROFILE_COLD_LOADER";byte[] zip=File.ReadAllBytes(Path.Combine(sourceRoot,"source.zip"));string sha=Hash(zip);
   BootstrapTests.HostedLoaderPlan(sourceRoot,sha,head,sid,true);Done("cold_first_loader");
   string target=Fresh(parent,"GridS0Package-");Phase="FIXTURE_PROFILE_PLAN";
   BootstrapReceipt plan=Bootstrap.PlanPackageAtUserProfileV1(zip,sha,head,target,sid);Need(plan.Status=="PLAN_ONLY" && plan.ParentScope=="UserProfileV1" && plan.ParentIdentity==parentId && !Directory.Exists(target));Done("native_profile_plan");
   Block(delegate { Bootstrap.StagePackageAtUserProfileV1(zip,sha,head,target,sid,false); });Done("unapproved_stage");
   Block(delegate { Bootstrap.PlanPackageAtUserProfileV1(zip,sha,head,target,"S-1-5-18"); });Done("sid_mismatch");
   Block(delegate { Bootstrap.PlanPackageAtUserProfileV1(zip,sha,head,Fresh(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"GridS0Package-"),sid); });Done("no_local_fallback");
   Phase="FIXTURE_PROFILE_STAGE";BootstrapReceipt staged=Bootstrap.StagePackageAtUserProfileV1(zip,sha,head,target,sid,true);Need(staged.ParentIdentity==parentId && staged.RootIdentity!=null);Done("atomic_protected_stage");
   Block(delegate { Bootstrap.StagePackageAtUserProfileV1(zip,sha,head,target,sid,true); });Done("uuid_reuse");
   Phase="FIXTURE_PROFILE_SOURCE_CUSTODY";
   MethodInfo hold=typeof(Bootstrap).GetMethod("HoldUserProfileSourceV1",BindingFlags.Static|BindingFlags.NonPublic);
   using(var source=(IDisposable)hold.Invoke(null,new object[]{target,sid,sha,head})) {
    bool write=false,rename=false;
    try { using(var writer=new FileStream(Path.Combine(target,"runtime","python.exe"),FileMode.Open,FileAccess.Write,FileShare.ReadWrite)) {} } catch(IOException) { write=true; }
    try { Directory.Move(target,Fresh(parent,"GridS0Package-")); } catch(IOException) { rename=true; }
    Need(write && rename);Done("source_write_and_replacement");
   }
   Phase="FIXTURE_PROFILE_NATIVE_PROCESS";
   var env=new Hashtable();foreach(string name in new[]{"SystemRoot","WINDIR","USERPROFILE","LOCALAPPDATA","USERNAME","COMPUTERNAME"}) env[name]=Environment.GetEnvironmentVariable(name);
   string runtimeTemp=Path.Combine(Slot(parent,sid,head),"temp");
   var tempAcl=new DirectorySecurity();tempAcl.SetAccessRuleProtection(true,false);tempAcl.SetOwner(new SecurityIdentifier(sid));
   foreach(string trustee in new[]{sid,"S-1-5-18","S-1-5-32-544"}) tempAcl.AddAccessRule(new FileSystemAccessRule(new SecurityIdentifier(trustee),FileSystemRights.FullControl,AccessControlType.Allow));
   Directory.CreateDirectory(runtimeTemp,tempAcl);
   env["TEMP"]=runtimeTemp;env["TMP"]=env["TEMP"];env["PATH"]=Path.Combine((string)env["SystemRoot"],"System32");
   string imageSha=Hash(File.ReadAllBytes(Path.Combine(target,"runtime","python.exe")));
   string probe="-I -S -B -c \"from s0_smoke.profile import ParentLease; p=ParentLease('UserProfileV1','"+sid+"'); p.__enter__(); p.guard(); import os,sys,json; f=open(os.path.join(os.environ['TEMP'],'python-profile.json'),'x'); json.dump({'python':sys.version.split()[0]},f); f.close(); p.__exit__(); raise SystemExit(0)\"";
   Result normal=ProcessHost.RunAtUserProfileV1(target,probe,env,sid,imageSha,head,5,sha);
   Need(normal.ExitCode==0 && !normal.TimedOut && normal.Pid>0 && normal.CreationFileTime>0 && normal.JobMember && !normal.ObservedElevated && !normal.ObservedAdminEnabled);Done("native_python_token_job");
   string versionRecord=File.ReadAllText(Path.Combine(runtimeTemp,"python-profile.json"));Need(versionRecord.Contains("3.12."));Done("native_python_profile_resolution");
   Result deadline=ProcessHost.RunAtUserProfileV1(target,"-I -S -B -c \"import time; time.sleep(10)\"",env,sid,imageSha,head,1,sha);Need(deadline.TimedOut && deadline.ExitCode!=259);Done("owned_deadline_shutdown");
   RuntimeActions(sourceRoot,target,parent,sid,head,sha);
   Phase="FIXTURE_PROFILE_INPUTS";InputTests.Hosted(sid,head);Done("input_and_import");
   Phase="FIXTURE_PROFILE_RECEIVER";TransferTests.Hosted(sid,head);Done("receiver_replay_race");
   Phase="FIXTURE_PROFILE_EXPORT";TransferExportTests.Hosted(sid,head);Done("export_identity_and_scope");
   Phase="FIXTURE_PROFILE_TRANSPORT";TransferTransportTests.Hosted(sid,head);Done("sender_and_known_hosts");
   foreach(int mask in new[]{0x40,0x40000,0x80000,0x10,0x100}) {
    Phase="FIXTURE_PROFILE_PARENT_DANGEROUS_ACE";string owned=Slot(parent,sid,head);var acl=Directory.GetAccessControl(owned);
    acl.AddAccessRule(new FileSystemAccessRule(new SecurityIdentifier("S-1-5-32-545"),(FileSystemRights)mask,AccessControlType.Allow));Directory.SetAccessControl(owned,acl);
    Block(delegate { using(var rejected=Pins(owned,sid)) {} });
   }Done("parent_delete_child_dac_owner");
   Phase="FIXTURE_PROFILE_ACL_DRIFT";string drift=Slot(parent,sid,head);
   using(var pins=Pins(drift,sid)) {
    var acl=Directory.GetAccessControl(drift);acl.AddAccessRule(new FileSystemAccessRule(new SecurityIdentifier("S-1-5-32-545"),FileSystemRights.ReadAndExecute,AccessControlType.Allow));Directory.SetAccessControl(drift,acl);
    Block(delegate { Check(pins); });
   }Done("same_file_acl_drift");
   Phase="FIXTURE_PROFILE_FILE_ID_FAULT";string identityFault=Slot(parent,sid,head);
   using(var pins=Pins(identityFault,sid)) {
    var ids=(System.Collections.Generic.List<string>)pins.GetType().GetField("ids",BindingFlags.Instance|BindingFlags.NonPublic).GetValue(pins);
    ids[ids.Count-1]="00000000:0000000000000000";Block(delegate { Check(pins); });
   }Done("file_id_fault_rejected");
   Phase="FIXTURE_PROFILE_JUNCTION";string fixture=Slot(parent,sid,head),link=Path.Combine(fixture,"junction"),destination=Path.Combine(fixture,"destination");Directory.CreateDirectory(destination);Junction(link,destination);
   Block(delegate { using(var pins=Pins(link,sid)) {} });Done("junction_reparse");
   Phase="FIXTURE_PROFILE_HARDLINK";Need(CreateHardLinkW(Path.Combine(fixture,"image-hardlink"),Path.Combine(target,"runtime","python.exe"),IntPtr.Zero));
   Block(delegate { using(var source=(IDisposable)hold.Invoke(null,new object[]{target,sid,sha,head})) {} });Done("hardlink_source");
   Need(passed.Count==22);Phase="FIXTURE_PROFILE_RECEIPT";
   string cases="["+String.Join(",",passed.ConvertAll(delegate(string name) { return "\""+name+"\""; }).ToArray())+"]";
   string json="{\"scope\":\"HOSTED_NATIVE_USER_PROFILE_NOT_PHYSICAL\",\"head\":\""+head+"\",\"package_sha256\":\""+sha+"\",\"cases\":"+cases+",\"pid\":"+normal.Pid+",\"creation_filetime\":"+normal.CreationFileTime+",\"exit_code\":"+normal.ExitCode+",\"deadline_pid\":"+deadline.Pid+" ,\"deadline_timed_out\":true,\"deadline_exit_code\":"+deadline.ExitCode+",\"execute\":false,\"cleanup\":false}";
   using(var output=new FileStream(Path.Combine(sourceRoot,"temp","user-profile.json"),FileMode.CreateNew,FileAccess.Write,FileShare.None)) { byte[] bytes=Encoding.ASCII.GetBytes(json);output.Write(bytes,0,bytes.Length);output.Flush(true); }
  } finally { ProfileApi.UserProfile=false; }
 }
}
