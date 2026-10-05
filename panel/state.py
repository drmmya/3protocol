"""Root-owned durable VPN users, sampling accounting, and audit history."""
import json, sqlite3, time, uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from .common import hash_password,verify_password,username,PROTOCOLS

class State:
    def __init__(self,path):
        self.path=str(path)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS users(name TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS counters(protocol TEXT,epoch TEXT,sid TEXT,rx INTEGER,tx INTEGER,seen REAL,PRIMARY KEY(protocol,epoch,sid));
            CREATE TABLE IF NOT EXISTS traffic(day TEXT,protocol TEXT,user TEXT,rx INTEGER DEFAULT 0,tx INTEGER DEFAULT 0,PRIMARY KEY(day,protocol,user));
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,at REAL,kind TEXT,message TEXT);
            ''')
    def connect(self):
        db=sqlite3.connect(self.path,timeout=20);db.execute('PRAGMA journal_mode=WAL'); return db
    def setting(self,key,default=None):
        with self.connect() as db: row=db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else default
    def set_setting(self,key,value):
        with self.connect() as db: db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(key,json.dumps(value)))
    def raw_users(self):
        with self.connect() as db: return [json.loads(r[0]) for r in db.execute('SELECT data FROM users ORDER BY name')]
    def users(self):
        return [{k:v for k,v in u.items() if k not in ('password_hash','oc_hash')} for u in self.raw_users()]
    def get(self,name):
        username(name)
        with self.connect() as db: row=db.execute('SELECT data FROM users WHERE name=?',(name,)).fetchone()
        return json.loads(row[0]) if row else None
    def save_user(self,data):
        name=username(data.get('name')); old=self.get(name)
        u=old or {'name':name,'enabled':True,'protocols':list(PROTOCOLS),'uuid':str(uuid.uuid4()),'speed_mbps':0,'quota_gb':0,'quota_period':'daily','created':time.time()}
        for key in ('enabled','protocols','speed_mbps','quota_gb','quota_period'):
            if key in data: u[key]=data[key]
        if not isinstance(u['enabled'],bool): raise ValueError('Enabled must be true or false.')
        if not isinstance(u['protocols'],list) or not u['protocols'] or any(p not in PROTOCOLS for p in u['protocols']): raise ValueError('Invalid protocols.')
        for key in ('speed_mbps','quota_gb'):
            if isinstance(u[key],bool): raise ValueError('Invalid limit.')
            u[key]=float(u[key])
            if not 0<=u[key]<=1000000: raise ValueError('Limits must be between 0 and 1000000.')
        if u['quota_period'] not in ('daily','lifetime'): raise ValueError('Invalid quota period.')
        password=data.get('password')
        if password: u['password_hash']=hash_password(password);u['oc_hash']=None
        if not old and not password: raise ValueError('Password required for a new user.')
        with self.connect() as db: db.execute('INSERT OR REPLACE INTO users VALUES(?,?)',(name,json.dumps(u)))
        return u
    def put_raw(self,u):
        with self.connect() as db: db.execute('INSERT OR REPLACE INTO users VALUES(?,?)',(u['name'],json.dumps(u)))
    def delete(self,name):
        username(name)
        with self.connect() as db: db.execute('DELETE FROM users WHERE name=?',(name,))
    def allowed(self,u,protocol):
        if not u or not u['enabled'] or protocol not in u['protocols']: return False
        if u['quota_gb']:
            day=datetime.now(ZoneInfo(self.setting('timezone','Asia/Dhaka'))).date().isoformat()
            query='SELECT COALESCE(SUM(rx+tx),0) FROM traffic WHERE user=?';args=[u['name']]
            if u['quota_period']=='daily': query+=' AND day=?'; args.append(day)
            with self.connect() as db: used=db.execute(query,args).fetchone()[0]
            if used>=u['quota_gb']*1e9: return False
        return True
    def verify(self,name,password,protocol='openvpn'):
        try: u=self.get(name)
        except ValueError: return False
        return bool(self.allowed(u,protocol) and verify_password(password,u['password_hash']))
    def account(self,protocol,epoch,sessions,now=None):
        now=now or time.time();day=datetime.fromtimestamp(now,ZoneInfo(self.setting('timezone','Asia/Dhaka'))).date().isoformat()
        with self.connect() as db:
            for s in sessions:
                rx=max(0,int(s['rx']));tx=max(0,int(s['tx']));sid=str(s['id'])
                row=db.execute('SELECT rx,tx FROM counters WHERE protocol=? AND epoch=? AND sid=?',(protocol,epoch,sid)).fetchone()
                # Initial counters contribute; resets start another counter interval.
                dr=rx-(row[0] if row and rx>=row[0] else 0);dt=tx-(row[1] if row and tx>=row[1] else 0)
                db.execute('INSERT OR REPLACE INTO counters VALUES(?,?,?,?,?,?)',(protocol,epoch,sid,rx,tx,now))
                db.execute('INSERT INTO traffic VALUES(?,?,?,?,?) ON CONFLICT(day,protocol,user) DO UPDATE SET rx=rx+excluded.rx,tx=tx+excluded.tx',(day,protocol,s.get('user','unknown'),dr,dt))
            db.execute('DELETE FROM counters WHERE seen<?',(now-86400*30,))
            db.execute('DELETE FROM events WHERE at<?',(now-86400*30,))
    def totals(self):
        day=datetime.now(ZoneInfo(self.setting('timezone','Asia/Dhaka'))).date().isoformat()
        with self.connect() as db:
            total=db.execute('SELECT COALESCE(SUM(rx+tx),0) FROM traffic').fetchone()[0]
            today=db.execute('SELECT COALESCE(SUM(rx+tx),0) FROM traffic WHERE day=?',(day,)).fetchone()[0]
            history=[{'day':r[0],'rx':r[1],'tx':r[2]} for r in db.execute('SELECT day,SUM(rx),SUM(tx) FROM traffic GROUP BY day ORDER BY day DESC LIMIT 30')][::-1]
            users=[{'name':r[0],'rx':r[1],'tx':r[2]} for r in db.execute('SELECT user,SUM(rx),SUM(tx) FROM traffic GROUP BY user')]
        return {'total':total,'today':today,'history':history,'users':users,'timezone':self.setting('timezone','Asia/Dhaka'),'accounting':'Sampled payload counters; brief sessions between samples may be missed.'}
    def event(self,kind,message):
        with self.connect() as db: db.execute('INSERT INTO events(at,kind,message) VALUES(?,?,?)',(time.time(),kind,str(message)[:4000]))
    def events(self,limit=200):
        with self.connect() as db: return [{'at':r[0],'kind':r[1],'message':r[2]} for r in db.execute('SELECT at,kind,message FROM events ORDER BY id DESC LIMIT ?',(min(int(limit),1000),))]
