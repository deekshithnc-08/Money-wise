import hashlib, http.client, json, os, tempfile, threading, time, unittest
from unittest.mock import patch
import server

class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(); server.DB=cls.temp.name+'/test.sqlite3'; server.OTP=False
        server.init_db(); server.create_admin('admin@example.test','test-password-long-123')
        cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.port=cls.http.server_port; server.BASE='http://localhost:'+str(cls.port)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.temp.cleanup()
    def setUp(self):
        with server.db() as c:
            for table in ['audit','bookings','referrals','visits','visitors','sessions','limits','verifications']: c.execute('DELETE FROM '+table)
        self.cookies={}; self.csrf=''
    def request(self,path,data=None,origin=True,csrf=True):
        conn=http.client.HTTPConnection('127.0.0.1',self.port)
        headers={'Content-Type':'application/json','Cookie':'; '.join(k+'='+v for k,v in self.cookies.items())}
        if origin: headers['Origin']=server.BASE
        if csrf: headers['X-CSRF-Token']=self.csrf
        conn.request('GET' if data is None else 'POST',path,None if data is None else json.dumps(data),headers)
        r=conn.getresponse();body=r.read();status=r.status
        for k,v in r.getheaders():
            if k.lower()=='set-cookie':
                name,val=v.split(';')[0].split('=',1);self.cookies[name]=val
        conn.close()
        try:return status,json.loads(body)
        except ValueError:return status,body.decode()
    def referral(self,**kwargs):
        d={'name':'Ananya','consent':True};d.update(kwargs);status,result=self.request('/api/referrals',d);self.assertEqual(status,200);return result['code']
    def visit(self,**kwargs):
        status,result=self.request('/api/visit',kwargs);self.assertEqual(status,200);return result
    def book(self,**kwargs):
        d={'name':'Priya','phone':'+919876543210','email':'priya@example.test','city':'Bengaluru','consent':True};d.update(kwargs);return self.request('/api/bookings',d)
    def login(self):
        status,result=self.request('/api/admin/login',{'email':'admin@example.test','password':'test-password-long-123'});self.assertEqual(status,200);self.csrf=result['csrf']
    def test_first_touch_referral_latest_source_and_mapping(self):
        a=self.referral();b=self.referral(name='Other')
        self.visit(ref=a,source='flyer',campaign='launch',partner='college')
        self.visit(ref=b,source='whatsapp')
        status,result=self.book();self.assertEqual(status,201)
        self.login();status,data=self.request('/api/admin/data');row=data['bookings'][0]
        self.assertEqual(row['ref'],a);self.assertEqual(row['source'],'whatsapp');self.assertEqual(row['campaign'],'launch');self.assertEqual(row['partner'],'college');self.assertEqual(data['metrics']['visitors'],1);self.assertEqual(data['metrics']['visits'],2)
    def test_referral_expiry_invalid_ref_and_self_referral(self):
        a=self.referral(phone='+919876543210');self.visit(ref=a);self.assertEqual(self.book()[0],201)
        with server.db() as c:self.assertIsNone(c.execute('SELECT ref FROM bookings').fetchone()[0]);c.execute('DELETE FROM bookings');c.execute('UPDATE visitors SET ref_at=?',(time.time()-31*86400,))
        self.assertTrue(self.visit(ref='unknown')['invalidRef']);self.book()
        with server.db() as c:self.assertIsNone(c.execute('SELECT ref FROM bookings').fetchone()[0])
    def test_remove_referral_duplicate_and_validation(self):
        a=self.referral();self.visit(ref=a)
        self.assertEqual(self.book(consent=False)[0],400);self.assertEqual(self.book(phone='bad')[0],400)
        self.assertEqual(self.book(removeReferral=True)[0],201);status,result=self.book();self.assertEqual(status,200);self.assertTrue(result['duplicate']);self.assertNotIn('id',result)
        with server.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM bookings').fetchone()[0],1);self.assertIsNone(c.execute('SELECT ref FROM bookings').fetchone()[0])
    def test_auth_csrf_logout_and_payment_audit(self):
        self.assertEqual(self.request('/api/admin/data')[0],401)
        self.assertEqual(self.request('/api/admin/export')[0],401)
        self.assertEqual(self.request('/api/admin/login',{'email':'admin@example.test','password':'wrong'})[0],401)
        ref=self.referral();self.visit(ref=ref);bid=self.book()[1]['id'];self.login()
        d={'id':bid,'status':'confirmed','payment':'paid','amount':500000,'reference':'receipt-1'}
        self.assertEqual(self.request('/api/admin/booking',d,csrf=False)[0],403)
        self.assertEqual(self.request('/api/admin/booking',{**d,'reference':''})[0],400)
        self.assertEqual(self.request('/api/admin/booking',d)[0],200)
        data=self.request('/api/admin/data')[1];self.assertEqual(data['metrics']['revenue'],500000);self.assertEqual(data['referrals'][0]['paid'],1);self.assertEqual(len(data['audit']),1)
        self.request('/api/admin/booking',{**d,'payment':'refunded','reference':'refund-1'})
        data=self.request('/api/admin/data')[1];self.assertEqual(data['metrics']['revenue'],0);self.assertEqual(data['referrals'][0]['paid'],0);self.assertEqual(len(data['audit']),2)
        self.request('/api/admin/logout',{});self.assertEqual(self.request('/api/admin/data')[0],401)
    def test_origin_rate_limit_and_csv_injection(self):
        self.assertEqual(self.request('/api/visit',{},origin=False)[0],403)
        self.book(name='=DANGEROUS()');self.login();status,csv=self.request('/api/admin/export');self.assertEqual(status,200);self.assertIn("'=DANGEROUS()",csv)
        with server.db() as c:c.execute('INSERT OR REPLACE INTO limits VALUES (?,?,?)',('booking:127.0.0.1',20,time.time()+3600))
        self.assertEqual(self.book()[0],429)
    def test_verified_mobile_reuses_link_and_consumes_token(self):
        with patch.object(server,'OTP',True),patch.object(server,'twilio',return_value={'status':'approved'}):
            phone='+919888888888';token=self.request('/api/otp/check',{'phone':phone,'code':'123456'})[1]['token']
            a=self.referral(phone=phone,token=token)
            self.assertEqual(self.request('/api/referrals',{'name':'A','phone':phone,'token':token,'consent':True})[0],400)
            token=self.request('/api/otp/check',{'phone':phone,'code':'123456'})[1]['token'];b=self.referral(phone=phone,token=token);self.assertEqual(a,b)
    def test_name_and_mobile_are_enough_for_an_enquiry(self):
        status,result=self.book(email='',city='')
        self.assertEqual(status,201)
        with server.db() as c:
            lead=c.execute('SELECT * FROM bookings WHERE id=?',(result['id'],)).fetchone()
            self.assertEqual(lead['phone'],'+919876543210')
            self.assertEqual(lead['status'],'requested')
            self.assertEqual(lead['email'],'')
        self.assertEqual(self.book(phone='+919876543211',email='invalid')[0],400)

    def test_public_routes_no_secrets_and_persistence(self):
        for path in ['/','/refer','/admin','/privacy','/app.js','/admin.js','/styles.css','/api/config']:self.assertEqual(self.request(path)[0],200)
        for path in ['/server.py','/.env','/data/app.sqlite3']:self.assertEqual(self.request(path)[0],404)
        self.book();server.init_db()
        with server.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM bookings').fetchone()[0],1)

if __name__=='__main__':unittest.main()
