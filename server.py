#!/usr/bin/env python3
"""Money Wise Women. Standard-library application, SQLite persistence."""
import base64, csv, hashlib, hmac, io, json, os, re, secrets, sqlite3, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
# Minimal .env loader; process environment always wins.
if (ROOT / '.env').exists():
    for line in (ROOT / '.env').read_text().splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('\"\''))
DB = os.getenv('DATABASE_PATH', str(ROOT / 'data/app.sqlite3'))
BASE = os.getenv('PUBLIC_URL', ('https://' + os.environ['VERCEL_PROJECT_PRODUCTION_URL']) if os.getenv('VERCEL_PROJECT_PRODUCTION_URL') else 'http://localhost:8000').rstrip('/')
SECURE = BASE.startswith('https://')
OTP = all(os.getenv(k) for k in ('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_VERIFY_SERVICE_SID'))

def db():
    if os.getenv('TURSO_DATABASE_URL') and os.getenv('TURSO_AUTH_TOKEN'):
        from database import RemoteConnection
        return RemoteConnection(os.environ['TURSO_DATABASE_URL'], os.environ['TURSO_AUTH_TOKEN'])
    if os.getenv('VERCEL'):
        raise RuntimeError('Persistent Turso database configuration is required on Vercel.')
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

def init_db():
    remote = bool(os.getenv('TURSO_DATABASE_URL'))
    if not remote and not os.getenv('VERCEL'):
        Path(DB).parent.mkdir(parents=True, exist_ok=True)
    with db() as c:
        if not remote:
            c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS admins (email TEXT PRIMARY KEY, salt TEXT NOT NULL, password TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, email TEXT, csrf TEXT, expires REAL);
        CREATE TABLE IF NOT EXISTS visitors (id TEXT PRIMARY KEY, ref TEXT, ref_at REAL, source TEXT, campaign TEXT, partner TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS visits (id INTEGER PRIMARY KEY, visitor TEXT, ref TEXT, source TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS referrals (code TEXT PRIMARY KEY, name TEXT, phone TEXT, verified INTEGER, created REAL);
        CREATE UNIQUE INDEX IF NOT EXISTS verified_phone ON referrals(phone) WHERE verified=1;
        CREATE TABLE IF NOT EXISTS bookings (id TEXT PRIMARY KEY, name TEXT, phone TEXT, email TEXT, city TEXT, batch TEXT,
          ref TEXT REFERENCES referrals(code), source TEXT, campaign TEXT, partner TEXT, status TEXT, payment TEXT,
          amount INTEGER DEFAULT 0, reference TEXT DEFAULT '', consent TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, booking TEXT, actor TEXT, before_state TEXT, after_state TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS limits (key TEXT PRIMARY KEY, count INTEGER, resets REAL);
        CREATE TABLE IF NOT EXISTS verifications (token TEXT PRIMARY KEY, phone TEXT, expires REAL);
        ''')

def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()

def create_admin(email, password):
    if len(password) < 12:
        raise ValueError('Use at least 12 characters for the admin password.')
    salt = secrets.token_hex(16)
    with db() as c:
        c.execute('INSERT OR REPLACE INTO admins VALUES (?,?,?)', (email.lower().strip(), salt, password_hash(password, salt)))
        c.execute('DELETE FROM sessions WHERE email=?', (email.lower().strip(),))

def field(data, key, maximum=120, required=True):
    value = data.get(key, '')
    if not isinstance(value, str): raise ValueError('Invalid ' + key)
    value = value.strip()
    if (required and not value) or len(value) > maximum: raise ValueError('Please check ' + key + '.')
    return value

def phone_number(data):
    value = re.sub(r'[\s()-]', '', field(data, 'phone', 24))
    if re.fullmatch(r'[6-9]\d{9}', value): value = '+91' + value
    if not re.fullmatch(r'\+[1-9]\d{7,14}', value): raise ValueError('Enter a valid mobile number, including country code.')
    return value

def twilio(action, values):
    auth = base64.b64encode((os.environ['TWILIO_ACCOUNT_SID'] + ':' + os.environ['TWILIO_AUTH_TOKEN']).encode()).decode()
    request = Request('https://verify.twilio.com/v2/Services/' + os.environ['TWILIO_VERIFY_SERVICE_SID'] + '/' + action,
                      urlencode(values).encode(), {'Authorization': 'Basic ' + auth})
    try:
        with urlopen(request, timeout=15) as response: return json.load(response)
    except Exception: raise ValueError('Mobile verification could not be completed. Check the code or try again later.')

class Handler(BaseHTTPRequestHandler):
    server_version = 'MoneyWise'
    def log_message(self, fmt, *args):
        # Never log query strings (referral codes), request bodies or personal information.
        print('%s %s' % (self.command, urlparse(self.path).path))

    def send(self, status, body, mime='application/json', cookies=None):
        if mime == 'application/json': body = json.dumps(body).encode()
        elif isinstance(body, str): body = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        if SECURE: self.send_header('Strict-Transport-Security', 'max-age=31536000')
        for cookie in cookies or []: self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(body)

    def cookie(self, key):
        cookies = SimpleCookie()
        try: cookies.load(self.headers.get('Cookie', ''))
        except Exception: return ''
        return cookies[key].value if key in cookies else ''

    def set_cookie(self, key, value, age):
        return '%s=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=%d%s' % (key, value, age, '; Secure' if SECURE else '')

    def session(self):
        token = hashlib.sha256(self.cookie('mw_admin').encode()).hexdigest()
        with db() as c: result = c.execute('SELECT * FROM sessions WHERE token=? AND expires>?', (token, time.time())).fetchone()
        if not result: raise PermissionError('Please sign in to continue.')
        return result

    def rate(self, key, limit, seconds=3600):
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('DELETE FROM limits WHERE resets<?', (time.time(),))
            row = c.execute('SELECT count FROM limits WHERE key=?', (key,)).fetchone()
            if row and row[0] >= limit: raise OverflowError('Too many attempts. Please try again later.')
            c.execute('INSERT INTO limits VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1', (key, time.time()+seconds))

    def visitor(self, c):
        return c.execute('SELECT * FROM visitors WHERE id=?', (self.cookie('mw_visitor'),)).fetchone()

    def do_GET(self):
        try: self.get()
        except PermissionError as e: self.send(401, {'error': str(e)})
        except Exception: self.send(500, {'error': 'Unable to load this page. Please try again.'})

    def get(self):
        path = urlparse(self.path).path
        if path == '/api/config':
            return self.send(200, {'otp': OTP, 'batch': os.getenv('PROGRAMME_BATCH', 'Upcoming cohort'),
                'schedule': os.getenv('PROGRAMME_SCHEDULE', 'Dates to be announced'),
                'venue': os.getenv('PROGRAMME_VENUE', 'Venue to be announced'),
                'fee': os.getenv('PROGRAMME_FEE_LABEL', 'Fee shared before confirmation')})
        if path.startswith('/api/admin/'):
            session = self.session()
            if path == '/api/admin/session': return self.send(200, {'email':session['email'], 'csrf':session['csrf']})
            if path in ('/api/admin/data', '/api/admin/export'):
                with db() as c:
                    bookings = [dict(x) for x in c.execute('SELECT b.*, r.name referrer FROM bookings b LEFT JOIN referrals r ON b.ref=r.code ORDER BY b.created DESC')]
                    referrals = [dict(x) for x in c.execute('''SELECT r.*, (SELECT COUNT(*) FROM visits v WHERE v.ref=r.code) visits,
                      (SELECT COUNT(*) FROM bookings b WHERE b.ref=r.code) leads,
                      (SELECT COUNT(*) FROM bookings b WHERE b.ref=r.code AND payment='paid') paid,
                      (SELECT COALESCE(SUM(amount),0) FROM bookings b WHERE b.ref=r.code AND payment='paid') revenue
                      FROM referrals r ORDER BY leads DESC, created DESC''')]
                    metrics = dict(c.execute('SELECT COUNT(*) visits, COUNT(DISTINCT visitor) visitors FROM visits').fetchone())
                    sources = [dict(x) for x in c.execute('SELECT source, COUNT(*) leads FROM bookings GROUP BY source ORDER BY leads DESC')]
                    audit = [dict(x) for x in c.execute('SELECT * FROM audit ORDER BY created DESC LIMIT 100')]
                if path.endswith('export'):
                    output = io.StringIO(); writer = csv.writer(output)
                    keys = ['id','name','phone','email','city','batch','referrer','ref','source','campaign','partner','status','payment','amount','reference']
                    writer.writerow(keys)
                    for booking in bookings:
                        writer.writerow([("'"+str(booking[k])) if str(booking[k] or '').startswith(('=','+','-','@','\t','\r','\n')) else booking[k] for k in keys])
                    return self.send(200, output.getvalue(), 'text/csv; charset=utf-8')
                metrics.update(leads=len(bookings), paid=sum(b['payment']=='paid' for b in bookings), revenue=sum(b['amount'] for b in bookings if b['payment']=='paid'), referrals=len(referrals))
                return self.send(200, {'bookings':bookings, 'referrals':referrals, 'metrics':metrics, 'sources':sources, 'audit':audit})
        files = {'/':'index.html','/refer':'index.html','/admin':'admin.html','/privacy':'privacy.html','/styles.css':'styles.css','/app.js':'app.js','/admin.js':'admin.js','/programme-poster.png':'programme-poster.png'}
        if path not in files: return self.send(404, {'error':'Page not found.'})
        file = ROOT / 'public' / files[path]
        mime = {'.html':'text/html; charset=utf-8','.css':'text/css','.js':'text/javascript','.png':'image/png'}[file.suffix]
        self.send(200, file.read_bytes(), mime)

    def do_POST(self):
        try:
            if self.headers.get('Origin') != BASE: return self.send(403, {'error':'Request origin not allowed.'})
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json': return self.send(415, {'error':'JSON required.'})
            size = int(self.headers.get('Content-Length', '0'))
            if size < 2 or size > 16384: return self.send(413, {'error':'Invalid request size.'})
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict): raise ValueError('Invalid request.')
            self.post(urlparse(self.path).path, data)
        except PermissionError as e: self.send(401, {'error':str(e)})
        except OverflowError as e: self.send(429, {'error':str(e)})
        except (ValueError, TypeError) as e: self.send(400, {'error':str(e)})
        except Exception: self.send(500, {'error':'Something went wrong. Please try again.'})

    def post(self, path, data):
        now = time.time()
        ip = self.client_address[0]
        # Vercel overwrites this header at its edge. Never trust it locally.
        if os.getenv('VERCEL') == '1':
            ip = self.headers.get('x-vercel-forwarded-for', ip).split(',')[0].strip()
        if path == '/api/visit':
            self.rate('visit:'+ip, 300, 3600)
            ref = field(data,'ref',40,False); source = field(data,'source',80,False)
            campaign = field(data,'campaign',120,False); partner = field(data,'partner',80,False)
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                visitor = self.visitor(c)
                valid = c.execute('SELECT code FROM referrals WHERE code=?',(ref,)).fetchone()
                ref = ref if valid else None
                vid = visitor['id'] if visitor else secrets.token_urlsafe(24)
                old_ref = visitor['ref'] if visitor and visitor['ref_at'] and visitor['ref_at'] > now-30*86400 else None
                assigned = old_ref or ref
                ref_at = visitor['ref_at'] if old_ref else (now if ref else None)
                channel = source or (visitor['source'] if visitor else 'direct')
                c.execute('INSERT OR REPLACE INTO visitors VALUES (?,?,?,?,?,?,?)',(vid,assigned,ref_at,channel,campaign or (visitor['campaign'] if visitor else ''),partner or (visitor['partner'] if visitor else ''),visitor['created'] if visitor else now))
                c.execute('INSERT INTO visits(visitor,ref,source,created) VALUES (?,?,?,?)',(vid,assigned,channel,now))
                owner = c.execute('SELECT name FROM referrals WHERE code=?',(assigned,)).fetchone()
            return self.send(200, {'referrer':owner['name'] if owner else None, 'invalidRef':bool(data.get('ref') and not valid)}, cookies=[self.set_cookie('mw_visitor',vid,30*86400)])
        if path == '/api/otp/send':
            if not OTP: raise ValueError('Mobile verification is not configured.')
            phone = phone_number(data)
            self.rate('otp:'+ip,10); self.rate('otp-phone:'+phone,3,600)
            twilio('Verifications', {'To':phone,'Channel':'sms'})
            return self.send(200, {'sent':True})
        if path == '/api/otp/check':
            if not OTP: raise ValueError('Mobile verification is not configured.')
            self.rate('otp-check:'+ip,20)
            phone=phone_number(data); code=field(data,'code',10)
            if twilio('VerificationCheck',{'To':phone,'Code':code}).get('status') != 'approved': raise ValueError('The code is incorrect or expired.')
            token=secrets.token_urlsafe(32)
            with db() as c:
                c.execute('DELETE FROM verifications WHERE expires<?',(now,))
                c.execute('INSERT INTO verifications VALUES (?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),phone,now+600))
            return self.send(200,{'token':token})
        if path == '/api/referrals':
            self.rate('referral:'+ip,20)
            name=field(data,'name',100)
            if data.get('consent') is not True: raise ValueError('Please agree to the privacy notice.')
            phone=phone_number(data) if data.get('phone') else ''
            verified=0
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                if OTP:
                    token=hashlib.sha256(field(data,'token',100).encode()).hexdigest()
                    check=c.execute('SELECT * FROM verifications WHERE token=? AND phone=? AND expires>?',(token,phone,now)).fetchone()
                    if not check: raise ValueError('Verify your mobile number first.')
                    verified=1
                    c.execute('DELETE FROM verifications WHERE token=?',(token,))
                existing=c.execute('SELECT code FROM referrals WHERE phone=? AND verified=1',(phone,)).fetchone() if verified else None
                code=existing['code'] if existing else 'MW'+secrets.token_hex(6).upper()
                if not existing: c.execute('INSERT INTO referrals VALUES (?,?,?,?,?)',(code,name,phone,verified,now))
            return self.send(200,{'code':code,'url':BASE+'/?ref='+code,'verified':bool(verified)})
        if path == '/api/bookings':
            self.rate('booking:'+ip,20)
            name=field(data,'name',100); phone=phone_number(data); email=field(data,'email',200); city=field(data,'city',100)
            if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email): raise ValueError('Enter a valid email address.')
            if data.get('consent') is not True: raise ValueError('Please agree to the privacy notice.')
            if data.get('website'): raise ValueError('Unable to submit this request.')
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                v=self.visitor(c)
                ref=v['ref'] if v and v['ref_at'] and v['ref_at']>now-30*86400 else None
                if data.get('removeReferral') is True: ref=None
                if ref and c.execute('SELECT code FROM referrals WHERE code=? AND phone=?',(ref,phone)).fetchone(): ref=None
                # Idempotent retry without revealing any existing personal data or identifiers.
                existing=c.execute('SELECT id FROM bookings WHERE phone=? AND batch=? AND status!=?',(phone,os.getenv('PROGRAMME_BATCH','Upcoming cohort'),'cancelled')).fetchone()
                if existing: return self.send(200, {'duplicate':True,'message':'A request for this mobile number is already on file. The myPAL team will follow up.'})
                bid='MWB-'+secrets.token_hex(5).upper()
                c.execute('INSERT INTO bookings(id,name,phone,email,city,batch,ref,source,campaign,partner,status,payment,consent,created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (bid,name,phone,email,city,os.getenv('PROGRAMME_BATCH','Upcoming cohort'),ref,v['source'] if v else 'direct',v['campaign'] if v else '',v['partner'] if v else '','requested','pending','privacy-v1; booking follow-up consent',now))
            return self.send(201,{'id':bid,'message':'Your booking request is received. The myPAL team will contact you with dates, fees and confirmation details.'})
        if path == '/api/admin/login':
            self.rate('login:'+ip,10,900)
            email=field(data,'email',200).lower(); password=field(data,'password',300)
            with db() as c:
                admin=c.execute('SELECT * FROM admins WHERE email=?',(email,)).fetchone()
                computed=password_hash(password,admin['salt'] if admin else '00'*16)
                if not admin or not hmac.compare_digest(computed,admin['password']): raise PermissionError('Email or password is incorrect.')
                token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(24)
                c.execute('DELETE FROM sessions WHERE expires<?',(now,))
                c.execute('INSERT INTO sessions VALUES (?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),email,csrf,now+28800))
            return self.send(200,{'email':email,'csrf':csrf},cookies=[self.set_cookie('mw_admin',token,28800)])
        if path.startswith('/api/admin/'):
            session=self.session()
            if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),session['csrf']): return self.send(403,{'error':'Refresh the page and try again.'})
            if path == '/api/admin/logout':
                with db() as c: c.execute('DELETE FROM sessions WHERE token=?',(session['token'],))
                return self.send(200,{'ok':True},cookies=[self.set_cookie('mw_admin','',0)])
            if path == '/api/admin/booking':
                bid=field(data,'id',40); status=field(data,'status',30); payment=field(data,'payment',30)
                if status not in ('requested','contacted','confirmed','cancelled'): raise ValueError('Invalid booking status.')
                if payment not in ('pending','paid','failed','refunded'): raise ValueError('Invalid payment status.')
                amount=data.get('amount',0)
                if type(amount) is not int or not 0 <= amount <= 100000000: raise ValueError('Enter a valid amount in paise.')
                reference=field(data,'reference',200,False)
                if payment in ('paid','refunded') and (not reference or amount<=0): raise ValueError('A positive amount and receipt or refund reference are required.')
                with db() as c:
                    c.execute('BEGIN IMMEDIATE')
                    before=c.execute('SELECT status,payment,amount,reference FROM bookings WHERE id=?',(bid,)).fetchone()
                    if not before: raise ValueError('Booking not found.')
                    c.execute('UPDATE bookings SET status=?,payment=?,amount=?,reference=? WHERE id=?',(status,payment,amount,reference,bid))
                    c.execute('INSERT INTO audit(booking,actor,before_state,after_state,created) VALUES (?,?,?,?,?)',(bid,session['email'],json.dumps(dict(before)),json.dumps({'status':status,'payment':payment,'amount':amount,'reference':reference}),now))
                return self.send(200,{'ok':True})
        self.send(404,{'error':'Endpoint not found.'})

if __name__ == '__main__':
    import argparse, getpass
    parser=argparse.ArgumentParser(); parser.add_argument('command',nargs='?',default='serve',choices=['serve','create-admin']); parser.add_argument('--email')
    args=parser.parse_args(); init_db()
    if args.command == 'create-admin':
        create_admin(args.email or input('Admin email: '), getpass.getpass('Admin password (12+ characters): ')); print('Admin saved. Existing sessions revoked.')
    else:
        server=ThreadingHTTPServer((os.getenv('HOST','127.0.0.1'),int(os.getenv('PORT','8000'))),Handler)
        print('Money Wise Women running at '+BASE); server.serve_forever()
