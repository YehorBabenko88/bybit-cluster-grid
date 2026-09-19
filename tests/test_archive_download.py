import os,tempfile
from grid.archive_download import safe_delete_owned
def test_archive_cleanup_cannot_escape_grid_owned_root(tmp_path):
    root=tmp_path/"grid";root.mkdir();inside=root/"x";inside.write_text("x")
    assert safe_delete_owned(str(inside),str(root))
    outside=tmp_path/"outside";outside.write_text("x")
    try:safe_delete_owned(str(outside),str(root));assert False
    except ValueError:pass
