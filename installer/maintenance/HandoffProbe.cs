// C#5 hosted-only adapter. Reuses the original restricted-token/owned-Job parent.
// Does not write Core20/Runtime2 receipts, modify the package or grant acceptance.
using System;
using System.Collections;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using GridS0;
public static class HandoffProbe {
 static void Need(bool ok) { if(!ok)throw new InvalidOperationException("FIXTURE_HANDOFF_BLOCKED"); }
 static string Hash(byte[] b) { using(var h=SHA256.Create())return BitConverter.ToString(h.ComputeHash(b)).Replace("-","").ToLowerInvariant(); }
 static void Trace(FileStream file,string stage) {
  byte[] raw=Encoding.ASCII.GetBytes("{\"scope\":\"HOSTED_DIAGNOSTIC_NOT_ACCEPTANCE\",\"stage\":\""+stage+"\"}\n");file.Write(raw,0,raw.Length);file.Flush(true);
 }
 static string Q(string s) { Need(s!=null && s.IndexOf('"')<0 && !s.EndsWith("\\",StringComparison.Ordinal));return "\""+s+"\""; }
 public static void Run(string sourceRoot,string head,string sid) {
  Need(Environment.GetEnvironmentVariable("GITHUB_ACTIONS")=="true" && Environment.GetEnvironmentVariable("RUNNER_ENVIRONMENT")=="github-hosted" && Environment.GetEnvironmentVariable("GITHUB_JOB")=="s0-windows" && Environment.GetEnvironmentVariable("EXACT_HEAD_SHA")==head);
  Need(!String.Equals(Environment.MachineName,"LS5",StringComparison.OrdinalIgnoreCase) && !String.Equals(Environment.MachineName,"PC4",StringComparison.OrdinalIgnoreCase));
  TokenObserver.RequireStandard(sid);
  using(var log=new FileStream(Path.Combine(sourceRoot,"temp","handoff-core.jsonl"),FileMode.CreateNew,FileAccess.Write,FileShare.Read)) {
   byte[] zip=File.ReadAllBytes(Path.Combine(sourceRoot,"source.zip"));string sha=Hash(zip),parent;
   using(var held=Bootstrap.HoldUserProfileV1(sid)) { parent=held.ParentPath;held.Check(); }
   string target=Path.Combine(parent,"GridS0Package-"+Guid.NewGuid().ToString("D"));
   Trace(log,"SOURCE_STAGE");Bootstrap.StagePackageAtUserProfileV1(zip,sha,head,target,sid,true);
   MethodInfo method=typeof(Bootstrap).GetMethod("HoldUserProfileSourceV1",BindingFlags.Static|BindingFlags.NonPublic);Need(method!=null);
   Trace(log,"SOURCE_HASH_BEGIN");
   using(var source=(IDisposable)method.Invoke(null,new object[]{target,sid,sha,head})) {
    Trace(log,"SOURCE_HASH_HELD");
   }
   Trace(log,"SOURCE_HASH_RELEASED");
   string build=Environment.GetEnvironmentVariable("S0_NATIVE_BUILD_ROOT"),shell=Environment.GetEnvironmentVariable("S0_TEST_SHELL_PATH");
   Need(build!=null && shell!=null && Path.IsPathRooted(build) && Path.IsPathRooted(shell));
   string driver=Path.Combine(build,"HandoffChild.ps1"),imageSha=Hash(File.ReadAllBytes(Path.Combine(target,"runtime","python.exe")));
   string args="-NoLogo -NoProfile -NonInteractive -File "+Q(driver)+" -Root "+Q(target)+" -Head "+head+" -Sid "+sid+" -ImageSha "+imageSha+" -PackageSha "+sha+" -Evidence "+Q(Path.Combine(sourceRoot,"temp","handoff-child.jsonl"));
   var info=new ProcessStartInfo {FileName=shell,Arguments=args,UseShellExecute=false,CreateNoWindow=true,WorkingDirectory=target,RedirectStandardInput=true,RedirectStandardOutput=true,RedirectStandardError=true};
   Trace(log,"HANDOFF_BEGIN");
   using(var child=Process.Start(info)) {
    Need(child!=null);child.StandardInput.Close();
    var output=child.StandardOutput.ReadToEndAsync();var errors=child.StandardError.ReadToEndAsync();
    Trace(log,"SHELL_CREATED");
    byte[] identity=Encoding.ASCII.GetBytes("{\"scope\":\"HOSTED_DIAGNOSTIC_NOT_ACCEPTANCE\",\"stage\":\"OWN_SHELL_IDENTITY\",\"pid\":"+child.Id+",\"creation_filetime\":"+child.StartTime.ToUniversalTime().ToFileTimeUtc()+"}\n");log.Write(identity,0,identity.Length);log.Flush(true);
    if(!child.WaitForExit(30000)) {Trace(log,"CHILD_30S_DEADLINE");throw new InvalidOperationException("FIXTURE_HANDOFF_30_SECOND_BOUND");}
    Trace(log,"SHELL_EXITED");
    Need(output.Wait(1000) && errors.Wait(1000));
    Need(output.Result.Length<=4096 && errors.Result.Length<=4096 && child.ExitCode==0);
    Trace(log,"CHILD_EXIT_VERIFIED");
   }
  }
 }
}
