// READ-ONLY EXPERIMENTAL OBSERVER. Not an ACL custody proof or Apply executor.
// Windows-only .NET 8. No DACL mutation, task operations, or remote access.
// This opens a single named object, not a verified ancestor handle chain.
using System;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

internal static class Program
{
    const uint FILE_READ_ATTRIBUTES = 0x80;
    const uint FILE_SHARE_READ = 1, FILE_SHARE_WRITE = 2, FILE_SHARE_DELETE = 4;
    const uint OPEN_EXISTING = 3;
    const uint FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000;
    const uint FILE_FLAG_BACKUP_SEMANTICS = 0x02000000;
    const uint FILE_ATTRIBUTE_REPARSE_POINT = 0x400;

    [StructLayout(LayoutKind.Sequential)]
    struct BY_HANDLE_FILE_INFORMATION
    {
        public uint FileAttributes;
        public System.Runtime.InteropServices.ComTypes.FILETIME CreationTime, LastAccessTime, LastWriteTime;
        public uint VolumeSerialNumber, FileSizeHigh, FileSizeLow, NumberOfLinks, FileIndexHigh, FileIndexLow;
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true, EntryPoint = "CreateFileW")]
    static extern SafeFileHandle CreateFile(string name, uint access, uint share, IntPtr security,
        uint creation, uint flags, IntPtr template);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    static extern bool GetFileInformationByHandle(SafeFileHandle handle, out BY_HANDLE_FILE_INFORMATION info);

    static int Main(string[] args)
    {
        // Intentionally never returns a PASS or approval; no write-capable API exists.
        if (!OperatingSystem.IsWindows() || args.Length != 1 || !Path.IsPathFullyQualified(args[0]))
        {
            Console.Error.WriteLine("BLOCKED: Windows and one absolute path required");
            return 2;
        }
        try
        {
            using var handle = CreateFile(args[0], FILE_READ_ATTRIBUTES,
                FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, IntPtr.Zero, OPEN_EXISTING,
                FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS, IntPtr.Zero);
            if (handle.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error());
            if (!GetFileInformationByHandle(handle, out var info))
                throw new Win32Exception(Marshal.GetLastWin32Error());
            bool reparse = (info.FileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) != 0;
            ulong fileIndex = ((ulong)info.FileIndexHigh << 32) | info.FileIndexLow;
            // A single observed handle does NOT establish no-replacement custody.
            Console.WriteLine("status=BLOCKED");
            Console.WriteLine("host_verified=false");
            Console.WriteLine("apply_authorized=false");
            Console.WriteLine("volume_serial=" + info.VolumeSerialNumber.ToString("X8"));
            Console.WriteLine("file_index=" + fileIndex.ToString("X16"));
            Console.WriteLine("hardlink_count=" + info.NumberOfLinks);
            Console.WriteLine("reparse=" + reparse.ToString().ToLowerInvariant());
            Console.WriteLine("reason=ANCESTOR_AND_EFFECTIVE_RIGHTS_CUSTODY_NOT_PROVEN");
            return reparse ? 3 : 0; // 0 = observation succeeded, NOT a security PASS.
        }
        catch (Exception e) when (e is Win32Exception or IOException or UnauthorizedAccessException or ArgumentException)
        {
            Console.Error.WriteLine("BLOCKED: " + e.GetType().Name);
            return 2;
        }
    }
}
