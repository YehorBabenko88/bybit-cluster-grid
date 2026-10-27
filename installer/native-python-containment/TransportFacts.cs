using System.Buffers.Binary;
using System.Net;
using System.Runtime.InteropServices;

// Read-only diagnostic snapshots, not identity attestation or policy attribution.
// Caller must enforce the hosted-only invocation gate before calling Snapshot.
// Layout/API: learn.microsoft.com/windows/win32/api/{tcpmib,iphlpapi}/
// MIB_TCPROW_OWNER_PID, MIB_TCP6ROW_OWNER_PID, GetExtendedTcpTable.
internal static class TransportFacts {
 const int MaxBytes=4*1024*1024,MaxRows=65536;
 const uint Insufficient=122;
 [DllImport("iphlpapi.dll",ExactSpelling=true)]
 static extern uint GetExtendedTcpTable(IntPtr table,ref uint size,[MarshalAs(UnmanagedType.Bool)]bool order,uint family,int tableClass,uint reserved);
 internal sealed record Row(string local_address,int local_port,string? remote_address,int? remote_port,uint state,uint owning_pid);
 // complete describes buffer decoding, not exhaustive ownership/transport evidence.
 // Exclusions count only known owned rows omitted by the literal address filter.
 internal sealed record Decoded(bool complete,uint? total_row_count,IReadOnlyList<Row> rows,string? reason,uint? excluded_owned_rows=null);
 internal sealed record Family(uint family,uint? raw_api_status,bool complete,uint? total_row_count,IReadOnlyList<Row> rows,string? reason,uint? excluded_owned_rows=null);
 static Decoded Unknown(string reason)=>new(false,null,Array.Empty<Row>(),reason);
 static uint U32(byte[] bytes,int offset)=>BinaryPrimitives.ReadUInt32LittleEndian(bytes.AsSpan(offset,4));
 // DWORD port's upper 16 bits are documented as undefined. Read only its low
 // two bytes, which contain a network-byte-order ushort; never export padding.
 static int Port(byte[] bytes,int offset)=>BinaryPrimitives.ReadUInt16BigEndian(bytes.AsSpan(offset,2));
 static bool Zero(ReadOnlySpan<byte> bytes){foreach(byte value in bytes)if(value!=0)return false;return true;}
 internal static Decoded Decode(byte[] bytes,uint family,IReadOnlySet<uint> allowedPIDs){
  if(bytes==null||bytes.Length<4||bytes.Length>MaxBytes||family is not (2 or 23)||allowedPIDs==null||allowedPIDs.Count is <1 or >2||allowedPIDs.Contains(0))return Unknown("INPUT_UNKNOWN");
  uint count=U32(bytes,0);int stride=family==2?24:56;
  if(count>MaxRows||4L+(long)count*stride>bytes.Length)return Unknown("LAYOUT_UNKNOWN");
  var result=new List<Row>();uint excluded=0;
  for(int i=0;i<(int)count;i++){
   int offset=4+i*stride;uint state=U32(bytes,offset+(family==2?0:48));
   uint pid=U32(bytes,offset+(family==2?20:52));
   if(!allowedPIDs.Contains(pid))continue;
   if(state is <1 or >12)return Unknown("OWNED_STATE_UNKNOWN_"+state);
   int localOffset=offset+(family==2?4:0),remoteOffset=offset+(family==2?12:24),length=family==2?4:16;
   var local=bytes.AsSpan(localOffset,length);var remote=bytes.AsSpan(remoteOffset,length);
   // Preserve implicit-bind SYN_SENT (wildcard local) without disclosing an
   // actual interface. Remote allowlist is exactly the fixture's literal targets.
   bool localLoop=family==2?local.SequenceEqual(new byte[]{127,0,0,1}):Zero(local[..15])&&local[15]==1;
   bool localWild=Zero(local);
   bool remoteLoop=family==2?remote.SequenceEqual(new byte[]{127,0,0,1}):Zero(remote[..15])&&remote[15]==1;
   bool remoteDocumentation=family==2?remote.SequenceEqual(new byte[]{192,0,2,1}):remote.SequenceEqual(new byte[]{0x20,0x01,0x0d,0xb8,0,0,0,0,0,0,0,0,0,0,0,1});
   if((!localLoop&&!localWild)||(state!=2&&!remoteLoop&&!remoteDocumentation)){excluded++;continue;}
   if(family==23&&(U32(bytes,offset+16)!=0||(state!=2&&U32(bytes,offset+40)!=0)))return Unknown("LITERAL_SCOPE_UNKNOWN");
   int localPort=Port(bytes,offset+(family==2?8:20));
   if(localPort==0)return Unknown("LOCAL_PORT_UNKNOWN");
   int? remotePort=state==2?null:Port(bytes,offset+(family==2?16:44));
   if(remotePort==0)return Unknown("REMOTE_PORT_UNKNOWN");
   result.Add(new Row(new IPAddress(local).ToString(),localPort,state==2?null:new IPAddress(remote).ToString(),remotePort,state,pid));
  }
  return new(true,count,result,null,excluded);
 }
 static Family Capture(uint family,IReadOnlySet<uint> pids){
  uint size=0;uint? status=null;
  try{
   status=GetExtendedTcpTable(IntPtr.Zero,ref size,false,family,5,0); // TCP_TABLE_OWNER_PID_ALL
   if(status!=Insufficient)return new(family,status,false,null,Array.Empty<Row>(),"SIZE_QUERY_UNKNOWN");
   for(int retry=0;retry<3;retry++){
    if(size<4||size>MaxBytes)return new(family,status,false,null,Array.Empty<Row>(),"SIZE_BOUND");
    int allocated=checked((int)size);IntPtr buffer=Marshal.AllocHGlobal(allocated);
    try{
     // Clear memory so any documented undefined field cannot disclose heap data.
     Marshal.Copy(new byte[allocated],0,buffer,allocated);
     status=GetExtendedTcpTable(buffer,ref size,false,family,5,0);
     if(status==Insufficient)continue;
     if(status!=0)return new(family,status,false,null,Array.Empty<Row>(),"API_UNKNOWN");
     if(size<4||size>allocated)return new(family,status,false,null,Array.Empty<Row>(),"RETURNED_SIZE_UNKNOWN");
     uint count=unchecked((uint)Marshal.ReadInt32(buffer));int stride=family==2?24:56;
     if(count>MaxRows||4L+(long)count*stride>size)return new(family,status,false,null,Array.Empty<Row>(),"LAYOUT_UNKNOWN");
     var rows=new List<Row>();uint excluded=0;
     for(int i=0;i<(int)count;i++){
      IntPtr row=IntPtr.Add(buffer,4+i*stride);
      uint state=unchecked((uint)Marshal.ReadInt32(row,family==2?0:48));
      uint pid=unchecked((uint)Marshal.ReadInt32(row,family==2?20:52));
      if(!pids.Contains(pid))continue;
      if(state is <1 or >12)return new(family,status,false,null,Array.Empty<Row>(),"OWNED_STATE_UNKNOWN_"+state);
      // Never copy a foreign PID's row out of the API-owned snapshot buffer.
      var bytes=new byte[4+stride];BinaryPrimitives.WriteUInt32LittleEndian(bytes,1);Marshal.Copy(row,bytes,4,stride);
      var decoded=Decode(bytes,family,pids);
      if(!decoded.complete)return new(family,status,false,null,Array.Empty<Row>(),decoded.reason);
      rows.AddRange(decoded.rows);
      excluded+=decoded.excluded_owned_rows!.Value;
     }
     return new(family,status,true,count,rows,null,excluded);
    }finally{Marshal.FreeHGlobal(buffer);}
   }
   return new(family,status,false,null,Array.Empty<Row>(),"SIZE_RETRY_BOUND");
  }catch(Exception error) when(error is DllNotFoundException or EntryPointNotFoundException or BadImageFormatException or OutOfMemoryException or OverflowException){return new(family,status,false,null,Array.Empty<Row>(),"CAPTURE_UNKNOWN_"+error.GetType().Name);}
 }
 internal static object Snapshot(uint parent,uint child){
  if(parent==0||child==0||parent==child)return new{complete=false,reason="PID_INPUT_UNKNOWN",families=Array.Empty<Family>()};
  var pids=new HashSet<uint>{parent,child};var families=new[]{Capture(2,pids),Capture(23,pids)};
  return new{complete=families.All(x=>x.complete),reason="OBSERVED_NOT_ATTESTED",families};
 }
 internal static bool ModelTests(){
  var pids=new HashSet<uint>{10,20};var v4=new byte[28];
  BinaryPrimitives.WriteUInt32LittleEndian(v4.AsSpan(0),1);BinaryPrimitives.WriteUInt32LittleEndian(v4.AsSpan(4),2);
  new byte[]{127,0,0,1}.CopyTo(v4,8);v4[12]=0x12;v4[13]=0x34;v4[14]=0xff;v4[15]=0xff;
  BinaryPrimitives.WriteUInt32LittleEndian(v4.AsSpan(24),10);
  var good=Decode(v4,2,pids);
  if(!good.complete||good.total_row_count!=1||good.rows.Count!=1||good.rows[0].local_port!=4660||good.rows[0].remote_address!=null)return false;
  if(Decode(v4[..27],2,pids).complete||Decode(v4,23,pids).complete)return false;
  var high=(byte[])v4.Clone();BinaryPrimitives.WriteUInt32LittleEndian(high,65537);if(Decode(high,2,pids).complete)return false;
  var invalid=(byte[])v4.Clone();BinaryPrimitives.WriteUInt32LittleEndian(invalid.AsSpan(4),13);if(Decode(invalid,2,pids).complete)return false;
  BinaryPrimitives.WriteUInt32LittleEndian(invalid.AsSpan(24),99);if(!Decode(invalid,2,pids).complete||Decode(invalid,2,pids).rows.Count!=0)return false;
  if(Decode(v4,2,new HashSet<uint>{99}).rows.Count!=0)return false;
  var v6=new byte[60];BinaryPrimitives.WriteUInt32LittleEndian(v6,1);v6[19]=1;v6[24]=0x12;v6[25]=0x34;v6[43]=1;v6[48]=0x45;v6[49]=0x67;
  BinaryPrimitives.WriteUInt32LittleEndian(v6.AsSpan(52),3);BinaryPrimitives.WriteUInt32LittleEndian(v6.AsSpan(56),20);
  var six=Decode(v6,23,pids);if(!six.complete||six.rows.Count!=1||six.rows[0].local_address!="::1"||six.rows[0].remote_port!=17767)return false;
  v6[20]=1;if(Decode(v6,23,pids).complete)return false;
  v6[20]=0;v6[19]=0; // implicit IPv6 local bind
  var wild6=Decode(v6,23,pids);if(!wild6.complete||wild6.rows.Count!=1||wild6.rows[0].local_address!="::")return false;
  new byte[]{0x20,0x01,0x0d,0xb8,0,0,0,0,0,0,0,0,0,0,0,1}.CopyTo(v6,28);
  if(Decode(v6,23,pids).rows.Count!=1)return false;
  v6[28]=0x21;var foreign6=Decode(v6,23,pids);if(!foreign6.complete||foreign6.rows.Count!=0||foreign6.excluded_owned_rows!=1)return false;
  var wild4=(byte[])v4.Clone();Array.Clear(wild4,8,4);BinaryPrimitives.WriteUInt32LittleEndian(wild4.AsSpan(4),3);
  new byte[]{127,0,0,1}.CopyTo(wild4,16);wild4[20]=0x45;wild4[21]=0x67;
  var four=Decode(wild4,2,pids);if(!four.complete||four.rows.Count!=1||four.rows[0].local_address!="0.0.0.0")return false;
  new byte[]{192,0,2,1}.CopyTo(wild4,16);if(Decode(wild4,2,pids).rows.Count!=1)return false;
  wild4[16]=193;var foreign4=Decode(wild4,2,pids);if(!foreign4.complete||foreign4.rows.Count!=0||foreign4.excluded_owned_rows!=1)return false;
  return true;
 }
}
