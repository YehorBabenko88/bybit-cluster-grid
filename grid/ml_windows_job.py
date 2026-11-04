"""Windows Job Object containment for ML subprocesses.

KILL_ON_JOB_CLOSE covers descendants when the owning Python process exits.
The primary thread is suspended until assignment completes; failure closes the job.
"""
import ctypes
import os
import time
import math


class _BasicAccounting(ctypes.Structure):
    # JOBOBJECT_BASIC_ACCOUNTING_INFORMATION, fixed Win32 ABI (48 bytes).
    _fields_ = [(name, ctypes.c_int64) for name in
                ('TotalUserTime','TotalKernelTime','ThisPeriodTotalUserTime','ThisPeriodTotalKernelTime')] + [
                (name, ctypes.c_uint32) for name in
                ('TotalPageFaultCount','TotalProcesses','ActiveProcesses','TotalTerminatedProcesses')]


class WindowsJob:
    def __init__(self, pid, resume_primary_thread=False):
        if os.name != "nt":
            raise OSError("Windows Job Objects require Windows")
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.SetInformationJobObject.restype = wintypes.BOOL
        kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.TerminateJobObject.restype = wintypes.BOOL
        kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        kernel.QueryInformationJobObject.restype = wintypes.BOOL
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        kernel.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenThread.restype = wintypes.HANDLE
        kernel.ResumeThread.argtypes = [wintypes.HANDLE]
        kernel.ResumeThread.restype = wintypes.DWORD

        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                        ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class Io(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in
                        ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                         "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class Extended(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", Basic),
                        ("IoInfo", Io),
                        ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        self._kernel = kernel
        self._job = kernel.CreateJobObjectW(None, None)
        if not self._job:
            raise ctypes.WinError(ctypes.get_last_error())
        process = None
        try:
            limits = Extended()
            limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel.SetInformationJobObject(self._job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise ctypes.WinError(ctypes.get_last_error())
            process = kernel.OpenProcess(0x0100 | 0x0001 | 0x1000, False, int(pid))
            if not process:
                raise ctypes.WinError(ctypes.get_last_error())
            if not kernel.AssignProcessToJobObject(self._job, process):
                raise ctypes.WinError(ctypes.get_last_error())
            if resume_primary_thread:
                import psutil
                threads = psutil.Process(int(pid)).threads()
                if len(threads) != 1:
                    raise RuntimeError("suspended ML child must have exactly one thread")
                thread = kernel.OpenThread(0x0002, False, threads[0].id)
                if not thread:
                    raise ctypes.WinError(ctypes.get_last_error())
                try:
                    if kernel.ResumeThread(thread) == 0xFFFFFFFF:
                        raise ctypes.WinError(ctypes.get_last_error())
                finally:
                    kernel.CloseHandle(thread)
        except BaseException:
            self.close()
            raise
        finally:
            if process:
                kernel.CloseHandle(process)

    def terminate_and_wait(self, timeout):
        """Terminate this owned Job and prove ActiveProcesses=0 before closing.

        True means an empty Job was actually observed. Missing handles, query/
        termination/close failure or deadline expiry raise and retain the handle
        for the caller's best-effort close. close() keeps its older semantics.
        """
        if type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise ValueError('WINDOWS_JOB_WAIT_BUDGET')
        handle = getattr(self, '_job', None)
        if not handle:
            raise RuntimeError('WINDOWS_JOB_HANDLE_UNAVAILABLE')
        deadline = time.monotonic() + timeout
        if not self._kernel.TerminateJobObject(handle, 1):
            raise OSError('WINDOWS_JOB_TERMINATE_FAILED')
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError('WINDOWS_JOB_NOT_EMPTY')
            info = _BasicAccounting()
            if not self._kernel.QueryInformationJobObject(handle, 1, ctypes.byref(info), ctypes.sizeof(info), None):
                raise OSError('WINDOWS_JOB_QUERY_FAILED')
            if time.monotonic() >= deadline:
                raise TimeoutError('WINDOWS_JOB_NOT_EMPTY')
            if info.ActiveProcesses == 0:
                if not self._kernel.CloseHandle(handle):
                    raise OSError('WINDOWS_JOB_CLOSE_FAILED')
                self._job = None
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('WINDOWS_JOB_NOT_EMPTY')
            time.sleep(min(.01, remaining))

    def close(self):
        handle = getattr(self, "_job", None)
        if handle:
            self._job = None
            self._kernel.CloseHandle(handle)
