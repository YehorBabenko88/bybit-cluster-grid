"""Packaged console entry. Always isolated; no site, dotenv or production imports."""
import argparse,sys

def main():
 if not(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
  print('{"status":"BLOCKED","reason":"S0_ISOLATED_RUNTIME_REQUIRED"}');return 1
 p=argparse.ArgumentParser(add_help=False);p.add_argument('--action',default='plan');p.add_argument('--approved',action='store_true')
 a,_=p.parse_known_args()
 if a.action=='execute' and a.approved:
  from s0_smoke.lifecycle import arm_deadline
  arm_deadline()
 from s0_smoke.cli import main as dispatch
 return dispatch()

if __name__=='__main__':raise SystemExit(main())
