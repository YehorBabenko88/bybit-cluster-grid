using System;
using System.Reflection;
using System.IO;
using System.Text;
using System.Security.Cryptography;
using GridS0;
public static class InputTests {
 public static string Phase="FIXTURE_INPUTS_START";
 const string Head="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", Run="12345678-1234-4234-8234-123456789abc";
 const string Plan="{\"bybit_url\":\"wss://stream.bybit.com/v5/public/linear\",\"coordinator_ip\":\"100.64.0.1\",\"duration_seconds\":300,\"head\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"hostnames\":{\"LS5\":\"LS5\",\"PC4\":\"PC4\"},\"operator_sids\":{\"LS5\":\"S-1-5-21-1-2-3-1001\",\"PC4\":\"S-1-5-21-4-5-6-1002\"},\"port\":49152,\"profile\":\"PHYSICAL_SMOKE_S0\",\"run_id\":\"12345678-1234-4234-8234-123456789abc\",\"schema\":1,\"symbol\":\"BTCUSDT\",\"worker_ip\":\"100.64.0.2\"}";
 static string Hash(byte[] b) { using(var sha=SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(b)).Replace("-","").ToLowerInvariant(); }
 static object Decode(byte[] raw) { Type type=typeof(Bootstrap).GetNestedType("Json",BindingFlags.NonPublic); object json=Activator.CreateInstance(type,BindingFlags.NonPublic|BindingFlags.Instance,null,new object[]{raw},null); return type.GetMethod("Read",BindingFlags.NonPublic|BindingFlags.Instance).Invoke(json,null); }
 static void Validate(string value) { object plan=Decode(Encoding.ASCII.GetBytes(value)); typeof(Bootstrap).GetMethod("ValidateInputPlan",BindingFlags.NonPublic|BindingFlags.Static).Invoke(null,new object[]{plan,Head,Run}); }
 static void Reject(string value) { try { Validate(value); } catch(TargetInvocationException e) { if(e.InnerException is InvalidOperationException) return; throw; } throw new Exception("INPUT_NEGATIVE_ACCEPTED"); }
 static void Need(bool value) { if(!value) throw new InvalidOperationException("FIXTURE_INPUT_CHECK"); }
 static void Block(Action action) { try { action(); } catch(InvalidOperationException) { return; } throw new InvalidOperationException("FIXTURE_INPUT_EXPECTED_BLOCK"); }
 public static void Hosted(string sid,string head) {
  Need(Environment.GetEnvironmentVariable("GITHUB_ACTIONS")=="true" && Environment.GetEnvironmentVariable("RUNNER_ENVIRONMENT")=="github-hosted" && Environment.GetEnvironmentVariable("GITHUB_REPOSITORY")=="YehorBabenko88/bybit-cluster-grid" && Environment.GetEnvironmentVariable("GITHUB_JOB")=="s0-windows");
  Need(!String.Equals(Environment.MachineName,"LS5",StringComparison.OrdinalIgnoreCase) && !String.Equals(Environment.MachineName,"PC4",StringComparison.OrdinalIgnoreCase));
  TokenObserver.RequireStandard(sid);
  string run=Guid.NewGuid().ToString("D"); byte[] raw=Encoding.ASCII.GetBytes(Plan.Replace(Head,head).Replace(Run,run).Replace("S-1-5-21-1-2-3-1001",sid)); string sha=Hash(raw);
  string local=Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), target=Path.Combine(local,"GridS0Input-"+Guid.NewGuid().ToString("D"));
  int count=Directory.GetDirectories(local,".GridS0Transaction-*").Length;
  Phase="FIXTURE_INPUT_PLAN"; BootstrapReceipt plan=Bootstrap.PlanInput(raw,sha,head,run,target,sid); Need(plan.Status=="PLAN_ONLY" && plan.FileCount==1 && plan.Bytes==raw.LongLength && plan.RootIdentity==null && !Directory.Exists(target));
  Need(Directory.GetDirectories(local,".GridS0Transaction-*").Length==count);
  Block(delegate { Bootstrap.StagePlanInput(raw,sha,head,run,target,sid,false); });
  Block(delegate { Bootstrap.StagePlanInput(raw,sha,head,run,target,"S-1-5-18",true); });
  Need(!Directory.Exists(target) && Directory.GetDirectories(local,".GridS0Transaction-*").Length==count);
  Phase="FIXTURE_INPUT_STAGE"; BootstrapReceipt staged=Bootstrap.StagePlanInput(raw,sha,head,run,target,sid,true);
  Phase="FIXTURE_INPUT_RECEIPT"; string input=Path.Combine(target,"s0-plan.json"); Need(staged.Status=="STAGED_NO_EXECUTION_AUTHORITY" && staged.RootIdentity!=null && staged.ParentIdentity==plan.ParentIdentity && staged.FileCount==1 && staged.Bytes==raw.LongLength && !staged.S0Execute && !staged.G1Execute && !staged.Cleanup);
  Phase="FIXTURE_INPUT_READBACK"; Need(Directory.GetFiles(target,"*",SearchOption.AllDirectories).Length==1 && Directory.GetDirectories(target).Length==0 && Hash(File.ReadAllBytes(input))==sha);
  Phase="FIXTURE_INPUT_REUSE"; Block(delegate { Bootstrap.StagePlanInput(raw,sha,head,run,target,sid,true); });
  Need(Hash(File.ReadAllBytes(input))==sha && Directory.GetFiles(target).Length==1);
  // Retain the owned hosted fixture; no cleanup and no physical execution.
 }
 public static void Pure() {
  Validate(Plan);
  foreach(string text in new[]{Plan.Replace("49152","55432"),Plan.Replace("300","299"),Plan.Replace("100.64.0.1","8.8.8.8"),Plan.Replace("100.64.0.1","100.064.0.1"),Plan.Replace("100.64.0.2","100.64.0.1"),Plan.Replace("\"schema\":1","\"schema\":true"),Plan.Replace("S-1-5-21-1-2-3-1001","S-1-5-21-4294967296-2-3-1001")}) Reject(text);
  byte[] bytes=Encoding.ASCII.GetBytes(Plan);
  // SID binding fails before token observation; this pure test never invokes Win32.
  try { Bootstrap.PlanInput(bytes,Hash(bytes),Head,Run,"invalid","S-1-5-18"); } catch(InvalidOperationException) { return; }
  throw new Exception("INPUT_SID_BINDING_ACCEPTED");
 }
}
