"""Inert closed-wheel controls; no SDK import, installation or child process."""
import base64,contextlib,csv,hashlib,io,json,pathlib,runpy,sys,tarfile,tempfile,warnings,zipfile

def write_wheel(path,payload,distribution,modules,scripts,mode,math=False):
 prefix=distribution.replace('-','_')+'-0.1.0.dist-info/'
 values=dict(payload)
 values[prefix+'METADATA']=('Metadata-Version: 2.4\nName: '+('foreign-owner' if mode=='metadata_owner' and not math else distribution)+'\nVersion: 0.1.0\n').encode()
 values[prefix+'WHEEL']=b'Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n'
 values[prefix+'top_level.txt']=('\n'.join(modules)+'\n').encode()
 if scripts:values[prefix+'entry_points.txt']=('[console_scripts]\n'+''.join(k+' = '+v+(' _unapproved' if mode=='entrypoint_suffix' else '')+'\n' for k,v in scripts.items())).encode()
 if math and mode=='math_metadata_native':values[prefix+'native.exe']=b'INERT_NOT_EXECUTABLE'
 records=[]
 for name,raw in values.items():records.append([name,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode(),str(len(raw))])
 records.append([prefix+'RECORD','',''])
 if mode=='record_bad_hash' and not math:records[0][1]='sha256=incorrect'
 buffer=io.StringIO();csv.writer(buffer,lineterminator='\n').writerows(records);values[prefix+'RECORD']=buffer.getvalue().encode()
 with zipfile.ZipFile(path,'w') as z:
  for name,raw in values.items():z.writestr(name,raw)
  if (mode=='duplicate_zip' and not math) or (mode=='math_duplicate' and math):
   name=next(iter(payload))
   with warnings.catch_warnings():warnings.simplefilter('ignore');z.writestr(name,payload[name])

def fixture(root,mode):
 files={'market_data/__init__.py':b'# inert source\n','market_data/schema.sql':b'CREATE TABLE inert(value TEXT);\n','market_data/history_contract.py':b'# inert turnover contract\n','market_data/history_export_v12.py':b'# inert opt-in export\n'}
 math={name:b'# inert source shape only\n' for name in ('market_math.py','market_compute_api.py','history_statistics.py')}
 for name,raw in files.items():p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
 for name,raw in math.items():p=root/'.source/math/python'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
 (root/'pyproject.toml').write_text('[project]\nname="market-data"\nversion="0.1.0"\n[project.scripts]\nmarket-data="market_data.cli:main"\n')
 (root/'.source/math/pyproject.toml').write_text('[project]\nname="unified-math-kernels"\nversion="0.1.0"\n')
 wheels=dict(files);numbers=dict(math);archive=dict(files)
 if mode=='turnover_contract_missing':del wheels['market_data/history_contract.py']
 if mode=='turnover_export_changed':wheels['market_data/history_export_v12.py']+=b'# changed\n'
 if mode=='sql_changed':wheels['market_data/schema.sql']+=b'-- changed\n'
 if mode=='sql_missing':del wheels['market_data/schema.sql']
 if mode=='sql_extra':wheels['market_data/extra.sql']=b'-- extra\n'
 if mode=='python_crlf':wheels['market_data/__init__.py']=files['market_data/__init__.py'].replace(b'\n',b'\r\n')
 if mode=='math_changed':numbers['market_math.py']+=b'# changed\n'
 if mode=='math_missing':del numbers['history_statistics.py']
 if mode=='math_retired':numbers['market_profile_math.py']=b'# retired\n'
 if mode=='math_crlf':numbers['market_math.py']=numbers['market_math.py'].replace(b'\n',b'\r\n')
 if mode=='sdist_sql_changed':archive['market_data/schema.sql']+=b'-- changed\n'
 if mode=='data_extra_root':wheels['canonical_test_gate.py']=b'# unapproved guard shadow\n'
 if mode=='data_foreign_owner':wheels['terminan/hidden.py']=b'# foreign owner\n'
 dist=root/'.candidate-dist';dist.mkdir()
 write_wheel(dist/'market_data-0.1.0-py3-none-any.whl',wheels,'market-data',('market_data',),{'market-data':'market_data.cli:main'},mode)
 sdk=root/'math.whl';write_wheel(sdk,numbers,'unified-math-kernels',tuple(n[:-3] for n in math),{},mode,math=True)
 with tarfile.open(dist/'market_data-0.1.0.tar.gz','w:gz') as t:
  for name,raw in archive.items():member=tarfile.TarInfo('market_data-0.1.0/'+name);member.size=len(raw);t.addfile(member,io.BytesIO(raw))
 return sdk

def main():
 checker=pathlib.Path(sys.argv[1]) if len(sys.argv)>1 else pathlib.Path(__file__).with_name('check_market_package.py')
 modes=('positive','turnover_contract_missing','turnover_export_changed','sql_changed','sql_missing','sql_extra','python_crlf','math_changed','math_missing','math_retired','math_crlf','sdist_sql_changed','duplicate_zip','data_extra_root','data_foreign_owner','entrypoint_suffix','math_duplicate','math_metadata_native','metadata_owner','record_bad_hash')
 results={}
 for mode in modes:
  with tempfile.TemporaryDirectory(prefix='package-gate-control-') as directory:
   root=pathlib.Path(directory);sdk=fixture(root,mode);previous=sys.argv;sys.argv=[str(checker),str(root),str(sdk)]
   try:
    with contextlib.redirect_stdout(io.StringIO()):runpy.run_path(str(checker),run_name='__main__')
   except (AssertionError,KeyError,ValueError):accepted=False
   else:accepted=True
   finally:sys.argv=previous
   results[mode]=accepted
 print(json.dumps({'accepted':results,'scope':'INERT_PACKAGE_BYTES_NO_SDK_EXECUTION'}))
 assert results['positive'] and not any(v for k,v in results.items() if k!='positive'),'malformed/unowned package accepted'

if __name__=='__main__':main()
