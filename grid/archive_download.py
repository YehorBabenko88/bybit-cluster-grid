import hashlib,os,tempfile,aiohttp

class ArchiveUnavailable(FileNotFoundError):
    pass

async def download_verified(url,directory,expected_sha256=None,expected_bytes=None,chunk_size=1024*1024):
    os.makedirs(directory,exist_ok=True)
    fd,path=tempfile.mkstemp(prefix="grid-archive-",suffix=".part",dir=directory);os.close(fd)
    h=hashlib.sha256();size=0
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url,timeout=aiohttp.ClientTimeout(total=None,sock_read=60)) as r:
                if r.status==404:
                    raise ArchiveUnavailable(url)
                r.raise_for_status()
                with open(path,"wb") as f:
                    async for chunk in r.content.iter_chunked(int(chunk_size)):
                        if not chunk:continue
                        size+=len(chunk)
                        if expected_bytes and size>int(expected_bytes)*1.05:
                            raise ValueError("download exceeded expected archive size")
                        h.update(chunk);f.write(chunk)
                    f.flush();os.fsync(f.fileno())
        digest=h.hexdigest()
        if expected_sha256 and digest.lower()!=expected_sha256.lower():
            raise ValueError("archive sha256 mismatch")
        final=path[:-5]
        os.replace(path,final)
        return {"path":final,"bytes":size,"sha256":digest}
    except BaseException:
        try:os.remove(path)
        except FileNotFoundError:pass
        raise

def safe_delete_owned(path,root):
    rp=os.path.realpath(path);rr=os.path.realpath(root)
    if os.path.commonpath([rp,rr])!=rr:raise ValueError("refusing to delete outside Grid archive root")
    if os.path.isfile(rp):os.remove(rp);return True
    return False
