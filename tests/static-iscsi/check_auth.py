"""Negative login probes on a quiesced lab initiator; secrets stay on stdin."""
import json,shlex
from lab import PRIVATE,receipt
from ssh import ssh
r=next(r for r in json.loads((PRIVATE/'native-records.json').read_text()) if r['service']=='service-a');r['chap']=json.loads((PRIVATE/'chap.json').read_text())
script='''import json,sys,subprocess
r=json.load(sys.stdin)
def run(args):return subprocess.run(args,capture_output=True,text=True)
assert run(['iscsiadm','-m','session']).returncode!=0,'Probe requires no live sessions'
results=[]
for case in ('wrong-chap','wrong-initiator'):
 iface='lab-'+case
 assert run(['iscsiadm','-m','iface','-I',iface,'--op','new']).returncode==0
 try:
  iqn=r['initiators'][2] if case=='wrong-chap' else 'iqn.2026-09.lab.rejected:foreign'
  assert run(['iscsiadm','-m','iface','-I',iface,'--op','update','-n','iface.initiatorname','-v',iqn]).returncode==0
  base=['iscsiadm','-m','node','-T',r['iqn'],'-p',r['portal'],'-I',iface]
  assert run(base+['--op','new']).returncode==0
  for key,value in [('node.session.auth.authmethod','CHAP'),('node.session.auth.username',r['chap']['user']),('node.session.auth.password',('wrong-lab-password' if case=='wrong-chap' else r['chap']['secret'])),('node.session.initial_login_retry_max','1'),('node.conn[0].timeo.login_timeout','5')]:
   assert run(base+['--op','update','-n',key,'-v',value]).returncode==0
  login=run(base+['--login'])
  assert login.returncode not in (0,15),'Invalid access unexpectedly logged in'
  assert run(['iscsiadm','-m','session']).returncode!=0
  results.append({'test':case,'login_rejected':True,'exit_code':login.returncode})
 finally:
  run(base+['--logout']);run(base+['--op','delete']);run(['iscsiadm','-m','iface','-I',iface,'--op','delete'])
print(json.dumps(results))
'''
result=ssh(19113,'sudo python3 -c '+shlex.quote(script),input=json.dumps(r),capture_output=True,text=True)
checks=json.loads(result.stdout);receipt({'authentication_negative_checks':checks});print(json.dumps(checks))
