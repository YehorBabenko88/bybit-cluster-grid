"""Source contracts only: this test never compiles or invokes native code."""
from pathlib import Path
import re
import unittest

SOURCE=Path(__file__).resolve().parents[1]/'installer'/'physical-smoke-s0'/'S0Launcher.cs'

class LauncherContract(unittest.TestCase):
    def test_exact_closed_entrypoint_and_forbidden_foreign_process_apis(self):
        source=SOURCE.read_text(encoding='utf-8')
        self.assertRegex(source,r'public static Result Run\(string packageRoot, string arguments, IDictionary environment, string operatorSid, string expectedExeSha, string head, int seconds\)')
        self.assertIn('namespace GridS0',source)
        for prohibited in ('TerminateProcess','GetProcessById','Process.Start','DllImport("advapi32.dll", EntryPoint="CreateProcessAsUser'):
            self.assertNotIn(prohibited,source)
        self.assertNotRegex(source,r'\bOpenProcess\(')
        self.assertNotRegex(source,r'public static .*\b(?:Kill|Stop)\(')

    def test_atomic_job_creation_and_pre_resume_proof(self):
        source=SOURCE.read_text(encoding='utf-8')
        for token in ('0x2000D','0x2008','0x80404','FileShare.Read','SHA256.Create()',
                      'IsProcessInJob','QueryInformationJobObject','GetProcessTimes','QueryFullProcessImageNameW',
                      'GetTokenInformation','S-1-16-8192','Environment.Is64BitProcess','bInheritHandles',
                      'WaitForSingleObject(process.hProcess, 5000)','CloseOwnedJob(ref job)',
                      'S0_STANDARD_TOKEN_JOB_LIMITED_NOT_G1'):
            self.assertIn(token,source)
        self.assertLess(source.index('IsProcessInJob(process.hProcess'),source.index('ResumeThread(process.hThread)'))
        self.assertIn('seconds < 1 || seconds > 300',source)
        self.assertIn('runtime',source)
        self.assertIn('python.exe',source)

    def test_primary_and_created_child_tokens_are_observed_before_resume(self):
        source=SOURCE.read_text(encoding='utf-8')
        self.assertNotIn('WindowsIdentity.GetCurrent()',source)
        self.assertIn('ValidateOwnedProcessToken(GetCurrentProcess(),operatorSid)',source)
        self.assertIn('ValidateOwnedProcessToken(process.hProcess,operatorSid)',source)
        self.assertLess(source.index('ValidateOwnedProcessToken(process.hProcess,operatorSid)'),source.index('ResumeThread(process.hThread)'))
        for name in ('ObservedUserSid','ObservedElevated','ObservedIntegrity','ObservedAdminEnabled','JobMember','JobFlags','ActiveLimit'):
            self.assertRegex(source,r'public \w+ '+name+r' \{ get; internal set; \}')
        self.assertIn('(attributes&4)!=0 && (attributes&16)==0',source)
