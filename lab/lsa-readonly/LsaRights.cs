// Local, read-only policy lookup. No actor tokens are created or inspected.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text.RegularExpressions;

namespace GridLab.LsaReadOnly {
    [StructLayout(LayoutKind.Sequential)]
    public struct UnicodeString { public ushort Length, MaximumLength; public IntPtr Buffer; }
    [StructLayout(LayoutKind.Sequential)]
    struct ObjectAttributes {
        public uint Length; public IntPtr RootDirectory, ObjectName;
        public uint Attributes; public IntPtr SecurityDescriptor, SecurityQualityOfService;
    }
    public interface IPolicyApi {
        uint Open(uint access, out IntPtr handle);
        uint Enumerate(IntPtr handle, byte[] sid, out IntPtr buffer, out uint count);
        uint Free(IntPtr buffer);
        uint Close(IntPtr handle);
        uint WinError(uint status);
    }
    public sealed class NativeApi : IPolicyApi {
        [DllImport("advapi32.dll")] static extern uint LsaOpenPolicy(IntPtr system,
            ref ObjectAttributes attributes, uint access, out IntPtr handle);
        [DllImport("advapi32.dll")] static extern uint LsaEnumerateAccountRights(
            IntPtr handle, byte[] sid, out IntPtr buffer, out uint count);
        [DllImport("advapi32.dll")] static extern uint LsaFreeMemory(IntPtr buffer);
        [DllImport("advapi32.dll")] static extern uint LsaClose(IntPtr handle);
        [DllImport("advapi32.dll")] static extern uint LsaNtStatusToWinError(uint status);
        public uint Open(uint access, out IntPtr handle) {
            var a = new ObjectAttributes(); a.Length = (uint)Marshal.SizeOf(typeof(ObjectAttributes));
            return LsaOpenPolicy(IntPtr.Zero, ref a, access, out handle);
        }
        public uint Enumerate(IntPtr h, byte[] s, out IntPtr b, out uint c) { return LsaEnumerateAccountRights(h,s,out b,out c); }
        public uint Free(IntPtr p) { return LsaFreeMemory(p); }
        public uint Close(IntPtr p) { return LsaClose(p); }
        public uint WinError(uint s) { return LsaNtStatusToWinError(s); }
    }
    public sealed class Result {
        public string State = "UNKNOWN";
        public string Code = "UNQUERIED";
        public uint Status, Win32Error;
        public bool CleanupFailed;
        public string[] Rights = new string[0];
    }
    public static class Reader {
        public const uint LookupNames = 0x800;
        public const uint NotAssigned = 0xC0000034;
        public static string[] Parse(IntPtr buffer, uint count) {
            if (count > 256 || (count > 0 && buffer == IntPtr.Zero)) throw new FormatException();
            var values = new List<string>();
            int stride = Marshal.SizeOf(typeof(UnicodeString));
            for (int i=0; i<count; i++) {
                var s = (UnicodeString)Marshal.PtrToStructure(IntPtr.Add(buffer, checked(i*stride)), typeof(UnicodeString));
                if (s.Length == 0 || s.Length > 512 || (s.Length % 2) != 0 ||
                    s.MaximumLength < s.Length || (s.MaximumLength % 2) != 0 || s.Buffer == IntPtr.Zero)
                    throw new FormatException();
                string value = Marshal.PtrToStringUni(s.Buffer, s.Length/2);
                if (!Regex.IsMatch(value, "\\ASe[A-Za-z]+(?:Right|Privilege)\\z") || values.Contains(value)) throw new FormatException();
                values.Add(value);
            }
            return values.ToArray();
        }
        public static Result Read(IPolicyApi api, string sidText) {
            var r = new Result(); IntPtr handle = IntPtr.Zero, buffer = IntPtr.Zero;
            try {
                var sid = new SecurityIdentifier(sidText);
                if (sid.Value != sidText) throw new FormatException();
                var bytes = new byte[sid.BinaryLength]; sid.GetBinaryForm(bytes,0);
                uint status = api.Open(LookupNames, out handle);
                r.Status = status;
                if (status != 0) { r.Win32Error = api.WinError(status); r.Code="OPEN_FAILED"; }
                else if (handle == IntPtr.Zero) { r.Code="INVALID_HANDLE"; }
                else {
                    uint count; status = api.Enumerate(handle, bytes, out buffer, out count);
                    r.Status = status;
                    if (status == NotAssigned && count == 0 && buffer == IntPtr.Zero) {
                        r.Win32Error=api.WinError(status); r.State="DIRECT_ONLY"; r.Code="NO_DIRECT_ASSIGNMENTS";
                    } else if (status != 0) { r.Win32Error=api.WinError(status); r.Code="ENUMERATE_FAILED"; }
                    else {
                        r.Rights=Parse(buffer,count); r.State="DIRECT_ONLY"; r.Code="ENUMERATED";
                    }
                }
            } catch { r.State="UNKNOWN"; r.Code="API_OR_DATA_ERROR"; r.Rights=new string[0]; }
            finally {
                // A failed enumeration can still return a buffer. Release everything we received.
                if (buffer != IntPtr.Zero) {
                    try { if (api.Free(buffer)!=0) r.CleanupFailed=true; } catch { r.CleanupFailed=true; }
                }
                if (handle != IntPtr.Zero) {
                    try { if (api.Close(handle)!=0) r.CleanupFailed=true; } catch { r.CleanupFailed=true; }
                }
                if (r.CleanupFailed) { r.State="UNKNOWN"; r.Code="CLEANUP_FAILED"; r.Rights=new string[0]; }
            }
            return r;
        }
    }
}
