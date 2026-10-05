"""Linux health readings; network speed is observed interface throughput."""
import os,time,shutil
from pathlib import Path
class Metrics:
    def __init__(self,interface): self.interface=interface;self.cpu_previous=None;self.net_previous=None
    def read(self):
        cpu=list(map(int,Path('/proc/stat').read_text().splitlines()[0].split()[1:9]));total=sum(cpu);idle=cpu[3]+cpu[4]
        previous=self.cpu_previous;self.cpu_previous=(total,idle)
        percent=100*(1-(idle-previous[1])/max(1,total-previous[0])) if previous else 0
        mem={x.split(':')[0]:int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if len(x.split())>1 and x.split()[1].isdigit()}
        disk=shutil.disk_usage('/');now=time.time()
        try:
            path=Path('/sys/class/net')/self.interface/'statistics';rx=int((path/'rx_bytes').read_text());tx=int((path/'tx_bytes').read_text())
            prev=self.net_previous;self.net_previous=(rx,tx,now)
            rates={'rx_rate':max(0,(rx-prev[0])/(now-prev[2])) if prev else 0,'tx_rate':max(0,(tx-prev[1])/(now-prev[2])) if prev else 0}
        except OSError: rates={'rx_rate':None,'tx_rate':None}
        return {'cpu':max(0,min(100,percent)),'ram_used':mem['MemTotal']-mem.get('MemAvailable',mem['MemFree']),'ram_total':mem['MemTotal'],'disk_used':disk.used,'disk_total':disk.total,'load':list(os.getloadavg()),'cores':os.cpu_count(),'uptime':float(Path('/proc/uptime').read_text().split()[0]),'interface':self.interface,**rates}
