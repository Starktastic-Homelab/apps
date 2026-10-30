import pathlib,subprocess,sys
p=pathlib.Path(__file__).parent/'.runtime'
def ssh(port,command,**kw):
 return subprocess.run(['ssh','-F','/dev/null','-o','ConnectTimeout=10','-i',str(p/'id_ed25519'),'-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(p/'known_hosts'),'-p',str(port),'lab@127.0.0.1',command],check=True,**kw)
if __name__=='__main__':ssh(int(sys.argv[1]),sys.argv[2])
