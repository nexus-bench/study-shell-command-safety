"""Root-only VM egress policy for agent UID 2000. No host firewall changes."""
import json
import os
from pathlib import Path
import socket
import subprocess

HOSTS=('api2.cursor.sh','api.cursor.com')

def install():
    assert os.geteuid()==0
    addresses={host:sorted({r[4][0] for r in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM) if r[0]==socket.AF_INET}) for host in HOSTS}
    if not all(addresses.values()):raise RuntimeError('Cursor endpoints did not resolve')
    hosts=Path('/etc/hosts');old=hosts.read_text().split('# BENCH-ENDPOINTS')[0].rstrip()
    hosts.write_text(old+'\n# BENCH-ENDPOINTS\n'+''.join(ip+' '+host+'\n' for host,ips in addresses.items() for ip in ips))
    ips=sorted({ip for a in addresses.values() for ip in a})
    rules='''table inet bench_agent {
 chain output {
  type filter hook output priority 0; policy accept;
  meta skuid 2000 ip daddr 127.0.0.1 tcp dport 19001 accept
  meta skuid 2000 ip daddr { %s } tcp dport 443 accept
  meta skuid 2000 counter reject
 }
}
''' % ', '.join(ips)
    subprocess.run(['nft','delete','table','inet','bench_agent'],capture_output=True)
    subprocess.run(['nft','-f','-'],input=rules,text=True,check=True)
    return {'addresses':addresses,'rules':rules,'scope':'all agent-UID processes; root inference relay remains outside; DNS blocked, only fixed Cursor IPs:443 and local relay permitted','limitations':['Shared service IPs are not an application-level destination guarantee.','Native runtime and tools share UID; API endpoint access is permitted to both.']}

if __name__=='__main__':print(json.dumps(install(),indent=2))
