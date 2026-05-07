import os
import hashlib
import json
import time
from datetime import datetime, timedelta
from flask import Flask, request, Response, session, jsonify, redirect
import requests as req_lib

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')

GOOGLE_ADS_DEVELOPER_TOKEN = os.environ.get('GOOGLE_ADS_DEVELOPER_TOKEN', '')
GOOGLE_ADS_CLIENT_ID = os.environ.get('GOOGLE_ADS_CLIENT_ID', '')
GOOGLE_ADS_CLIENT_SECRET = os.environ.get('GOOGLE_ADS_CLIENT_SECRET', '')
GOOGLE_ADS_REFRESH_TOKEN = os.environ.get('GOOGLE_ADS_REFRESH_TOKEN', '')
GOOGLE_ADS_LOGIN_CUSTOMER_ID = os.environ.get('GOOGLE_ADS_LOGIN_CUSTOMER_ID', '')
PASSWORD_HASH = os.environ.get('PASSWORD_HASH', '')

_token_cache = {'token': None, 'expires': 0}

def get_access_token():
    now = time.time()
    if _token_cache['token'] and now < _token_cache['expires'] - 60:
        return _token_cache['token']
    r = req_lib.post('https://oauth2.googleapis.com/token', data={
        'client_id': GOOGLE_ADS_CLIENT_ID,
        'client_secret': GOOGLE_ADS_CLIENT_SECRET,
        'refresh_token': GOOGLE_ADS_REFRESH_TOKEN,
        'grant_type': 'refresh_token'
    })
    data = r.json()
    _token_cache['token'] = data.get('access_token')
    _token_cache['expires'] = now + data.get('expires_in', 3600)
    return _token_cache['token']

def google_ads_search(customer_id, query):
    token = get_access_token()
    cid = str(customer_id).replace('-', '')
    login_cid = GOOGLE_ADS_LOGIN_CUSTOMER_ID.replace('-', '')
    headers = {
        'Authorization': f'Bearer {token}',
        'developer-token': GOOGLE_ADS_DEVELOPER_TOKEN,
        'login-customer-id': login_cid,
        'Content-Type': 'application/json'
    }
    url = f'https://googleads.googleapis.com/v23/customers/{cid}/googleAds:searchStream'
    r = req_lib.post(url, headers=headers, json={'query': query})
    if r.status_code != 200:
        return {'error': r.text, 'status': r.status_code}
    results = r.json()
    rows = []
    if isinstance(results, list):
        for batch in results:
            if 'results' in batch:
                rows.extend(batch['results'])
    return rows

def get_accounts_list():
    login_cid = GOOGLE_ADS_LOGIN_CUSTOMER_ID.replace('-', '')
    query = """
        SELECT customer_client.id, customer_client.descriptive_name,
               customer_client.status, customer_client.manager
        FROM customer_client
        WHERE customer_client.manager = FALSE AND customer_client.status = 'ENABLED'
    """
    rows = google_ads_search(login_cid, query)
    if isinstance(rows, dict) and 'error' in rows:
        return rows
    accounts = []
    for row in rows:
        cc = row.get('customerClient', {})
        accounts.append({'id': cc.get('id'), 'name': cc.get('descriptiveName', ''), 'status': cc.get('status', '')})
    accounts.sort(key=lambda a: a.get('name', ''))
    return accounts

def fetch_campaigns(customer_id, date_from, date_to):
    query = f"""
        SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type,
               campaign_budget.amount_micros, metrics.impressions, metrics.clicks, metrics.ctr,
               metrics.average_cpc, metrics.cost_micros, metrics.conversions, metrics.cost_per_conversion,
               metrics.conversions_from_interactions_rate, metrics.all_conversions,
               metrics.search_impression_share, metrics.conversions_value
        FROM campaign
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}' AND campaign.status != 'REMOVED'
        ORDER BY metrics.cost_micros DESC
    """
    rows = google_ads_search(customer_id, query)
    if isinstance(rows, dict) and 'error' in rows:
        return None, rows
    campaigns = []
    totals = {'spend': 0, 'impressions': 0, 'clicks': 0, 'conversions': 0, 'all_conversions': 0, 'conv_value': 0}
    for row in rows:
        c = row.get('campaign', {})
        m = row.get('metrics', {})
        b = row.get('campaignBudget', {})
        cost = int(m.get('costMicros', 0)) / 1_000_000
        avg_cpc = int(m.get('averageCpc', 0)) / 1_000_000
        budget = int(b.get('amountMicros', 0)) / 1_000_000
        impressions = int(m.get('impressions', 0))
        clicks = int(m.get('clicks', 0))
        conversions = float(m.get('conversions', 0))
        all_conversions = float(m.get('allConversions', 0))
        ctr = float(m.get('ctr', 0))
        conv_rate = float(m.get('conversionsFromInteractionsRate', 0))
        cost_per_conv = float(m.get('costPerConversion', 0)) / 1_000_000 if m.get('costPerConversion') else 0
        search_is = float(m.get('searchImpressionShare', 0)) if m.get('searchImpressionShare') else None
        conv_value = float(m.get('conversionsValue', 0))
        totals['spend'] += cost
        totals['impressions'] += impressions
        totals['clicks'] += clicks
        totals['conversions'] += conversions
        totals['all_conversions'] += all_conversions
        totals['conv_value'] += conv_value
        campaigns.append({
            'id': c.get('id'), 'name': c.get('name', ''), 'status': c.get('status', ''),
            'type': c.get('advertisingChannelType', ''), 'budget': budget, 'spend': cost,
            'impressions': impressions, 'clicks': clicks, 'ctr': ctr, 'avg_cpc': avg_cpc,
            'conversions': conversions, 'cost_per_conv': cost_per_conv, 'conv_rate': conv_rate,
            'all_conversions': all_conversions, 'search_is': search_is, 'conv_value': conv_value,
            'roas': conv_value / cost if cost > 0 else 0
        })
    totals['ctr'] = totals['clicks'] / totals['impressions'] if totals['impressions'] > 0 else 0
    totals['avg_cpc'] = totals['spend'] / totals['clicks'] if totals['clicks'] > 0 else 0
    totals['cost_per_conv'] = totals['spend'] / totals['conversions'] if totals['conversions'] > 0 else 0
    totals['conv_rate'] = totals['conversions'] / totals['clicks'] if totals['clicks'] > 0 else 0
    totals['roas'] = totals['conv_value'] / totals['spend'] if totals['spend'] > 0 else 0
    return campaigns, totals

def fetch_daily(customer_id, date_from, date_to):
    query = f"""
        SELECT segments.date, metrics.cost_micros, metrics.clicks, metrics.impressions,
               metrics.conversions, metrics.conversions_value
        FROM campaign
        WHERE segments.date BETWEEN '{date_from}' AND '{date_to}' AND campaign.status != 'REMOVED'
    """
    rows = google_ads_search(customer_id, query)
    if isinstance(rows, dict) and 'error' in rows:
        return []
    daily = {}
    for row in rows:
        d = row.get('segments', {}).get('date', '')
        m = row.get('metrics', {})
        if d not in daily:
            daily[d] = {'date': d, 'spend': 0, 'clicks': 0, 'impressions': 0, 'conversions': 0, 'conv_value': 0}
        daily[d]['spend'] += int(m.get('costMicros', 0)) / 1_000_000
        daily[d]['clicks'] += int(m.get('clicks', 0))
        daily[d]['impressions'] += int(m.get('impressions', 0))
        daily[d]['conversions'] += float(m.get('conversions', 0))
        daily[d]['conv_value'] += float(m.get('conversionsValue', 0))
    return sorted(daily.values(), key=lambda x: x['date'])

def calc_prev_period(date_from, date_to):
    df = datetime.strptime(date_from, '%Y-%m-%d')
    dt = datetime.strptime(date_to, '%Y-%m-%d')
    delta = (dt - df).days + 1
    prev_to = df - timedelta(days=1)
    prev_from = prev_to - timedelta(days=delta - 1)
    return prev_from.strftime('%Y-%m-%d'), prev_to.strftime('%Y-%m-%d')

# ============================================================
# AUTH MIDDLEWARE
# ============================================================
@app.before_request
def check_auth():
    if request.path in ('/', '/login', '/favicon.ico'):
        return None
    if request.path == '/api/login':
        return None
    if request.path.startswith('/oauth/'):
        return None
    if request.path.startswith('/api/'):
        if not session.get('authenticated'):
            return jsonify({'error': 'Not authenticated'}), 401
    return None

# ============================================================
# PAGE ROUTES
# ============================================================
@app.route('/')
def index_page():
    if not session.get('authenticated'):
        return redirect('/login')
    return Response(INDEX_HTML, content_type='text/html')

@app.route('/login')
def login_page():
    return Response(LOGIN_HTML, content_type='text/html')

# ============================================================
# OAUTH2 FLOW
# ============================================================
@app.route('/oauth/start')
def oauth_start():
    redirect_uri = request.host_url.rstrip('/') + '/oauth/callback'
    auth_url = (
        'https://accounts.google.com/o/oauth2/v2/auth'
        f'?client_id={GOOGLE_ADS_CLIENT_ID}'
        f'&redirect_uri={redirect_uri}'
        f'&response_type=code&scope=https://www.googleapis.com/auth/adwords'
        f'&access_type=offline&prompt=consent'
    )
    return redirect(auth_url)

@app.route('/oauth/callback')
def oauth_callback():
    code = request.args.get('code')
    if request.args.get('error'):
        return Response(f'<h1>Error: {request.args.get("error")}</h1>', content_type='text/html')
    redirect_uri = request.host_url.rstrip('/') + '/oauth/callback'
    r = req_lib.post('https://oauth2.googleapis.com/token', data={
        'code': code, 'client_id': GOOGLE_ADS_CLIENT_ID,
        'client_secret': GOOGLE_ADS_CLIENT_SECRET,
        'redirect_uri': redirect_uri, 'grant_type': 'authorization_code'
    })
    data = r.json()
    if data.get('error'):
        return Response(f'<h1>Error: {data.get("error_description","")}</h1>', content_type='text/html')
    rt = data.get('refresh_token', '')
    html = f'''<html><body style="background:#0f1117;color:#fff;font-family:sans-serif;padding:40px;max-width:800px;margin:0 auto">
    <h1 style="color:#34a853">Refresh Token generado!</h1>
    <p>Copia y pon como <code>GOOGLE_ADS_REFRESH_TOKEN</code> en Vercel:</p>
    <div style="background:#1a1d27;border:1px solid #2d3148;border-radius:8px;padding:16px;word-break:break-all">
    <code style="color:#4285f4">{rt}</code></div></body></html>'''
    return Response(html, content_type='text/html')

# ============================================================
# API ROUTES
# ============================================================
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    pwd = data.get('password', '')
    if hashlib.sha256(pwd.encode()).hexdigest() == PASSWORD_HASH:
        session['authenticated'] = True
        return jsonify({'ok': True})
    return jsonify({'error': 'Password incorrecto'}), 401

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'ok': True})

@app.route('/api/accounts')
def api_accounts():
    try:
        accounts = get_accounts_list()
        if isinstance(accounts, dict) and 'error' in accounts:
            return jsonify(accounts), accounts.get('status', 500)
        return jsonify({'accounts': accounts})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/campaigns')
def api_campaigns():
    try:
        customer_id = request.args.get('customer_id', '')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')
        compare = request.args.get('compare', 'false') == 'true'
        if not customer_id:
            return jsonify({'error': 'customer_id required'}), 400
        if not date_from or not date_to:
            today = datetime.now()
            date_to = today.strftime('%Y-%m-%d')
            date_from = (today - timedelta(days=30)).strftime('%Y-%m-%d')
        all_campaigns = []
        account_summaries = []
        if customer_id == 'all':
            accounts = get_accounts_list()
            if isinstance(accounts, dict) and 'error' in accounts:
                return jsonify(accounts), accounts.get('status', 500)
            grand_totals = {'spend': 0, 'impressions': 0, 'clicks': 0, 'conversions': 0, 'all_conversions': 0, 'conv_value': 0}
            for acc in accounts:
                camps, tots = fetch_campaigns(acc['id'], date_from, date_to)
                if camps is None:
                    continue
                for c in camps:
                    c['account_name'] = acc.get('name', '')
                    c['account_id'] = acc['id']
                all_campaigns.extend(camps)
                for k in grand_totals:
                    grand_totals[k] += tots.get(k, 0)
                account_summaries.append({
                    'id': acc['id'], 'name': acc.get('name', ''),
                    'spend': tots['spend'], 'impressions': tots['impressions'],
                    'clicks': tots['clicks'], 'conversions': tots['conversions'],
                    'conv_value': tots.get('conv_value', 0),
                    'ctr': tots['ctr'], 'avg_cpc': tots['avg_cpc'],
                    'cost_per_conv': tots['cost_per_conv'], 'conv_rate': tots['conv_rate'],
                    'roas': tots.get('roas', 0)
                })
            grand_totals['ctr'] = grand_totals['clicks'] / grand_totals['impressions'] if grand_totals['impressions'] > 0 else 0
            grand_totals['avg_cpc'] = grand_totals['spend'] / grand_totals['clicks'] if grand_totals['clicks'] > 0 else 0
            grand_totals['cost_per_conv'] = grand_totals['spend'] / grand_totals['conversions'] if grand_totals['conversions'] > 0 else 0
            grand_totals['conv_rate'] = grand_totals['conversions'] / grand_totals['clicks'] if grand_totals['clicks'] > 0 else 0
            grand_totals['roas'] = grand_totals['conv_value'] / grand_totals['spend'] if grand_totals['spend'] > 0 else 0
            totals = grand_totals
        else:
            camps, tots = fetch_campaigns(customer_id, date_from, date_to)
            if camps is None:
                return jsonify(tots), tots.get('status', 500)
            all_campaigns = camps
            totals = tots
        prev_totals = None
        if compare:
            pf, pt = calc_prev_period(date_from, date_to)
            if customer_id == 'all':
                prev_grand = {'spend': 0, 'impressions': 0, 'clicks': 0, 'conversions': 0, 'conv_value': 0}
                for acc in accounts:
                    _, pt2 = fetch_campaigns(acc['id'], pf, pt)
                    if pt2 and not isinstance(pt2, dict):
                        for k in prev_grand:
                            prev_grand[k] += pt2.get(k, 0)
                prev_grand['ctr'] = prev_grand['clicks'] / prev_grand['impressions'] if prev_grand['impressions'] > 0 else 0
                prev_grand['avg_cpc'] = prev_grand['spend'] / prev_grand['clicks'] if prev_grand['clicks'] > 0 else 0
                prev_grand['cost_per_conv'] = prev_grand['spend'] / prev_grand['conversions'] if prev_grand['conversions'] > 0 else 0
                prev_grand['conv_rate'] = prev_grand['conversions'] / prev_grand['clicks'] if prev_grand['clicks'] > 0 else 0
                prev_grand['roas'] = prev_grand['conv_value'] / prev_grand['spend'] if prev_grand['spend'] > 0 else 0
                prev_totals = prev_grand
            else:
                _, prev_totals = fetch_campaigns(customer_id, pf, pt)
                if prev_totals and isinstance(prev_totals, dict) and 'error' in prev_totals:
                    prev_totals = None
        result = {'campaigns': all_campaigns, 'totals': totals}
        if prev_totals:
            result['prev_totals'] = prev_totals
        if account_summaries:
            result['accounts'] = account_summaries
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/daily')
def api_daily():
    try:
        customer_id = request.args.get('customer_id', '')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')
        if not customer_id or not date_from or not date_to:
            return jsonify({'error': 'params required'}), 400
        if customer_id == 'all':
            accounts = get_accounts_list()
            if isinstance(accounts, dict):
                return jsonify(accounts), 500
            merged = {}
            for acc in accounts:
                daily = fetch_daily(acc['id'], date_from, date_to)
                for d in daily:
                    dt = d['date']
                    if dt not in merged:
                        merged[dt] = {'date': dt, 'spend': 0, 'clicks': 0, 'impressions': 0, 'conversions': 0, 'conv_value': 0}
                    for k in ['spend', 'clicks', 'impressions', 'conversions', 'conv_value']:
                        merged[dt][k] += d[k]
            return jsonify({'daily': sorted(merged.values(), key=lambda x: x['date'])})
        else:
            daily = fetch_daily(customer_id, date_from, date_to)
            return jsonify({'daily': daily})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================
# LOGIN HTML
# ============================================================
LOGIN_HTML = '''<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Google Ads Dashboard - Login</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0b10;color:#e1e4e8;display:flex;align-items:center;justify-content:center;min-height:100vh}
.login-box{background:#12141e;border:1px solid #1e2235;border-radius:20px;padding:48px;width:100%;max-width:420px;box-shadow:0 16px 48px rgba(0,0,0,0.5)}
.login-box h1{text-align:center;margin-bottom:8px;font-size:26px;color:#fff;font-weight:700}
.login-box .subtitle{text-align:center;color:#6b7280;margin-bottom:36px;font-size:14px}
.login-box .logo{text-align:center;font-size:52px;margin-bottom:20px}
.form-group{margin-bottom:24px}
.form-group label{display:block;margin-bottom:8px;font-size:13px;color:#6b7280;font-weight:500}
.form-group input{width:100%;padding:14px 18px;background:#0a0b10;border:1px solid #1e2235;border-radius:10px;color:#fff;font-size:15px;outline:none;transition:border-color .2s}
.form-group input:focus{border-color:#4285f4}
.btn{width:100%;padding:14px;background:linear-gradient(135deg,#4285f4,#3367d6);color:#fff;border:none;border-radius:10px;font-size:15px;font-weight:600;cursor:pointer;transition:opacity .2s}
.btn:hover{opacity:0.9}
.error-msg{color:#ef4444;text-align:center;margin-top:14px;font-size:13px;display:none}
</style></head><body>
<div class="login-box">
<div class="logo">&#x1F4CA;</div>
<h1>Google Ads Dashboard</h1>
<p class="subtitle">Introduce tu password para acceder</p>
<div class="form-group"><label>Password</label>
<input type="password" id="pwd" placeholder="Tu password" autofocus></div>
<button class="btn" onclick="doLogin()">Acceder</button>
<div class="error-msg" id="err"></div></div>
<script>
document.getElementById('pwd').addEventListener('keydown',function(e){if(e.key==='Enter')doLogin()});
async function doLogin(){
  const pwd=document.getElementById('pwd').value,err=document.getElementById('err');
  err.style.display='none';
  try{const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pwd})});
  if(r.ok)window.location.href='/';else{const d=await r.json();err.textContent=d.error||'Error';err.style.display='block';}}
  catch(e){err.textContent='Error de conexion';err.style.display='block';}}
</script></body></html>'''

# ============================================================
# INDEX HTML (DASHBOARD)
# ============================================================
INDEX_HTML = '''<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Google Ads Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0b10;color:#e1e4e8;min-height:100vh}

.header{background:#12141e;border-bottom:1px solid #1e2235;padding:12px 24px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100}
.header-left{display:flex;align-items:center;gap:12px}
.header h1{font-size:17px;color:#fff;white-space:nowrap;font-weight:700}
.header h1 span{color:#4285f4}
.header-right{display:flex;align-items:center;gap:10px}
.btn-sm{background:transparent;border:1px solid #1e2235;color:#6b7280;padding:6px 12px;border-radius:8px;cursor:pointer;font-size:12px;transition:all .2s;white-space:nowrap}
.btn-sm:hover{border-color:#4285f4;color:#fff}

.controls{background:#12141e;border-bottom:1px solid #1e2235;padding:10px 24px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.control-group{display:flex;align-items:center;gap:6px}
.control-group label{font-size:11px;color:#6b7280;white-space:nowrap;font-weight:500}
select,input[type="date"]{background:#0a0b10;border:1px solid #1e2235;color:#fff;padding:7px 10px;border-radius:8px;font-size:12px;outline:none}
select:focus,input[type="date"]:focus{border-color:#4285f4}
.date-presets{display:flex;gap:3px;flex-wrap:wrap}
.date-presets button{background:#0a0b10;border:1px solid #1e2235;color:#6b7280;padding:5px 9px;border-radius:6px;cursor:pointer;font-size:11px;white-space:nowrap;transition:all .15s}
.date-presets button:hover,.date-presets button.active{background:#4285f4;color:#fff;border-color:#4285f4}
.toggle-compare{display:flex;align-items:center;gap:6px;cursor:pointer;font-size:11px;color:#6b7280}
.toggle-compare input{accent-color:#4285f4}
.search-box input{background:#0a0b10;border:1px solid #1e2235;color:#fff;padding:7px 10px;border-radius:8px;font-size:12px;outline:none;width:180px}
.btn-refresh{background:linear-gradient(135deg,#4285f4,#3367d6);border:none;color:#fff;padding:7px 16px;border-radius:8px;cursor:pointer;font-size:12px;font-weight:600}

.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;padding:16px 24px}
.kpi-card{background:#12141e;border:1px solid #1e2235;border-radius:14px;padding:14px 16px;transition:border-color .2s}
.kpi-card:hover{border-color:#4285f4}
.kpi-label{font-size:10px;color:#6b7280;text-transform:uppercase;letter-spacing:0.6px;margin-bottom:4px;font-weight:600}
.kpi-value{font-size:22px;font-weight:700;color:#fff}
.kpi-value.blue{color:#4285f4}
.kpi-value.green{color:#34a853}
.kpi-value.yellow{color:#fbbc04}
.kpi-value.purple{color:#a855f7}
.kpi-change{font-size:11px;margin-top:3px;font-weight:600}
.kpi-change.up{color:#34a853}
.kpi-change.down{color:#ef4444}
.kpi-change.neutral{color:#6b7280}

.charts-row{display:grid;grid-template-columns:2fr 1fr;gap:10px;padding:0 24px 10px}
.chart-card{background:#12141e;border:1px solid #1e2235;border-radius:14px;padding:16px}
.chart-card h3{font-size:13px;color:#fff;margin-bottom:12px;font-weight:600}
.chart-card canvas{width:100%!important;max-height:220px}

.section-title{padding:8px 24px 4px;font-size:13px;font-weight:700;color:#fff;display:flex;align-items:center;gap:8px}
.section-title .badge{background:#4285f4;color:#fff;font-size:10px;padding:2px 8px;border-radius:10px}

.table-wrap{padding:0 24px 20px;overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:12px}
thead th{background:#12141e;color:#6b7280;font-weight:600;text-transform:uppercase;font-size:10px;letter-spacing:0.5px;padding:8px 10px;text-align:left;border-bottom:2px solid #1e2235;cursor:pointer;white-space:nowrap;position:sticky;top:0;user-select:none}
thead th:hover{color:#4285f4}
thead th .sa{margin-left:3px;font-size:9px}
tbody tr{border-bottom:1px solid #151829;transition:background .1s}
tbody tr:hover{background:#151829}
tbody td{padding:8px 10px;white-space:nowrap}
.status-badge{display:inline-block;padding:2px 7px;border-radius:4px;font-size:10px;font-weight:700}
.status-ENABLED{background:rgba(52,168,83,0.12);color:#34a853}
.status-PAUSED{background:rgba(251,188,4,0.12);color:#fbbc04}
.type-badge{display:inline-block;padding:2px 7px;border-radius:4px;font-size:9px;font-weight:700}
.type-SEARCH{background:rgba(66,133,244,0.12);color:#4285f4}
.type-DISPLAY{background:rgba(52,168,83,0.12);color:#34a853}
.type-SHOPPING{background:rgba(251,188,4,0.12);color:#fbbc04}
.type-VIDEO{background:rgba(234,67,53,0.12);color:#ea4335}
.type-PERFORMANCE_MAX{background:rgba(168,85,247,0.12);color:#a855f7}
.type-DEMAND_GEN{background:rgba(236,72,153,0.12);color:#ec4899}
td.num{text-align:right;font-variant-numeric:tabular-nums}

.loading{display:none;text-align:center;padding:50px;color:#6b7280}
.loading.show{display:block}
.spinner{display:inline-block;width:28px;height:28px;border:3px solid #1e2235;border-top-color:#4285f4;border-radius:50%;animation:spin .7s linear infinite;margin-bottom:10px}
@keyframes spin{to{transform:rotate(360deg)}}
.toast{position:fixed;top:16px;right:16px;background:#ef4444;color:#fff;padding:10px 18px;border-radius:10px;font-size:12px;z-index:999;display:none;max-width:350px;box-shadow:0 8px 24px rgba(0,0,0,0.4)}
.toast.show{display:block;animation:sIn .25s ease}
@keyframes sIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}

.score-section{padding:0 24px 16px}
.score-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:8px}
.score-card{background:#12141e;border:1px solid #1e2235;border-radius:14px;padding:16px;position:relative;overflow:hidden}
.score-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px}
.score-card.scale::before{background:linear-gradient(90deg,#34a853,#22c55e)}
.score-card.maintain::before{background:linear-gradient(90deg,#fbbc04,#f59e0b)}
.score-card.stop::before{background:linear-gradient(90deg,#ef4444,#dc2626)}
.score-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}
.score-title{font-size:14px;font-weight:700;display:flex;align-items:center;gap:6px}
.score-title .icon{font-size:18px}
.score-card.scale .score-title{color:#34a853}
.score-card.maintain .score-title{color:#fbbc04}
.score-card.stop .score-title{color:#ef4444}
.score-count{font-size:20px;font-weight:800}
.score-card.scale .score-count{color:#34a853}
.score-card.maintain .score-count{color:#fbbc04}
.score-card.stop .score-count{color:#ef4444}
.score-list{list-style:none;max-height:200px;overflow-y:auto}
.score-list li{padding:6px 0;border-bottom:1px solid #1a1d2e;display:flex;justify-content:space-between;align-items:center;font-size:12px}
.score-list li:last-child{border-bottom:none}
.score-list .camp-name{color:#e1e4e8;max-width:55%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.score-list .camp-reason{color:#6b7280;font-size:10px;text-align:right;max-width:42%}
.score-pill{display:inline-block;padding:2px 6px;border-radius:3px;font-size:9px;font-weight:700;margin-left:4px}
.pill-green{background:rgba(52,168,83,0.15);color:#34a853}
.pill-yellow{background:rgba(251,188,4,0.15);color:#fbbc04}
.pill-red{background:rgba(239,68,68,0.15);color:#ef4444}
.score-summary{padding:10px 24px;display:flex;gap:8px;flex-wrap:wrap}
.alert-banner{display:flex;align-items:center;gap:8px;padding:10px 14px;border-radius:10px;font-size:12px;font-weight:600;flex:1;min-width:250px}
.alert-banner.critical{background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.25);color:#ef4444}
.alert-banner.warning{background:rgba(251,188,4,0.1);border:1px solid rgba(251,188,4,0.25);color:#fbbc04}
.alert-banner.success{background:rgba(52,168,83,0.1);border:1px solid rgba(52,168,83,0.25);color:#34a853}

@media(max-width:1200px){.kpis{grid-template-columns:repeat(3,1fr)}.charts-row{grid-template-columns:1fr}}
@media(max-width:768px){.controls{flex-direction:column;align-items:stretch}.kpis{grid-template-columns:repeat(2,1fr)}.header{flex-direction:column;gap:8px}.charts-row{grid-template-columns:1fr}}
</style></head><body>

<div class="header">
<div class="header-left"><h1>&#x1F4CA; Google <span>Ads</span> Dashboard</h1></div>
<div class="header-right">
<span id="accountName" style="color:#6b7280;font-size:12px"></span>
<button class="btn-sm" onclick="exportCSV()">&#x2B07; CSV</button>
<button class="btn-sm" onclick="doLogout()">Cerrar sesion</button>
</div></div>

<div class="controls">
<div class="control-group"><label>Cuenta:</label>
<select id="accountSelect" onchange="onAccountChange()"><option value="">Cargando...</option></select></div>
<div class="control-group"><label>Desde:</label><input type="date" id="dateFrom"></div>
<div class="control-group"><label>Hasta:</label><input type="date" id="dateTo"></div>
<div class="date-presets">
<button onclick="setPreset('today')">Hoy</button>
<button onclick="setPreset('yesterday')">Ayer</button>
<button onclick="setPreset('7d')" class="active">7 dias</button>
<button onclick="setPreset('30d')">30 dias</button>
<button onclick="setPreset('thisMonth')">Este mes</button>
<button onclick="setPreset('lastMonth')">Mes anterior</button>
</div>
<label class="toggle-compare"><input type="checkbox" id="compareToggle" onchange="loadData()"> vs periodo anterior</label>
<div class="search-box"><input type="text" id="searchInput" placeholder="Buscar campanas..." oninput="renderCampaignTable()"></div>
<button class="btn-refresh" onclick="loadData()">Actualizar</button>
</div>

<div class="kpis">
<div class="kpi-card"><div class="kpi-label">Gasto Total</div><div class="kpi-value blue" id="kpiSpend">-</div><div class="kpi-change" id="kpiSpendC"></div></div>
<div class="kpi-card"><div class="kpi-label">Impresiones</div><div class="kpi-value" id="kpiImpr">-</div><div class="kpi-change" id="kpiImprC"></div></div>
<div class="kpi-card"><div class="kpi-label">Clics</div><div class="kpi-value green" id="kpiClicks">-</div><div class="kpi-change" id="kpiClicksC"></div></div>
<div class="kpi-card"><div class="kpi-label">CTR</div><div class="kpi-value" id="kpiCtr">-</div><div class="kpi-change" id="kpiCtrC"></div></div>
<div class="kpi-card"><div class="kpi-label">CPC Medio</div><div class="kpi-value" id="kpiCpc">-</div><div class="kpi-change" id="kpiCpcC"></div></div>
<div class="kpi-card"><div class="kpi-label">Conversiones</div><div class="kpi-value yellow" id="kpiConv">-</div><div class="kpi-change" id="kpiConvC"></div></div>
<div class="kpi-card"><div class="kpi-label">Coste/Conv</div><div class="kpi-value" id="kpiCpa">-</div><div class="kpi-change" id="kpiCpaC"></div></div>
<div class="kpi-card"><div class="kpi-label">Tasa Conv</div><div class="kpi-value" id="kpiCr">-</div><div class="kpi-change" id="kpiCrC"></div></div>
<div class="kpi-card"><div class="kpi-label">Valor Conv</div><div class="kpi-value purple" id="kpiVal">-</div><div class="kpi-change" id="kpiValC"></div></div>
<div class="kpi-card"><div class="kpi-label">ROAS</div><div class="kpi-value" id="kpiRoas">-</div><div class="kpi-change" id="kpiRoasC"></div></div>
</div>

<div class="charts-row">
<div class="chart-card"><h3>Tendencia Diaria</h3><canvas id="dailyChart"></canvas></div>
<div class="chart-card"><h3>Distribucion por Tipo</h3><canvas id="typeChart"></canvas></div>
</div>

<div id="alertBanners" class="score-summary"></div>

<div class="score-section">
<div class="section-title">Diagnostico de Campanas <span class="badge" id="diagCount">0</span></div>
<div class="score-grid">
<div class="score-card scale">
<div class="score-header"><div class="score-title"><span class="icon">&#x1F680;</span> ESCALAR</div><div class="score-count" id="scaleCount">0</div></div>
<ul class="score-list" id="scaleList"></ul>
</div>
<div class="score-card maintain">
<div class="score-header"><div class="score-title"><span class="icon">&#x2696;</span> MANTENER</div><div class="score-count" id="maintainCount">0</div></div>
<ul class="score-list" id="maintainList"></ul>
</div>
<div class="score-card stop">
<div class="score-header"><div class="score-title"><span class="icon">&#x1F6D1;</span> REVISAR / PARAR</div><div class="score-count" id="stopCount">0</div></div>
<ul class="score-list" id="stopList"></ul>
</div>
</div>
</div>

<div id="accountsSection" style="display:none">
<div class="section-title">Desglose por Cuenta <span class="badge" id="accCount">0</span></div>
<div class="table-wrap">
<table><thead><tr>
<th onclick="sortAccBy('name')">Cuenta <span class="sa"></span></th>
<th onclick="sortAccBy('spend')">Gasto <span class="sa"></span></th>
<th onclick="sortAccBy('impressions')">Impresiones <span class="sa"></span></th>
<th onclick="sortAccBy('clicks')">Clics <span class="sa"></span></th>
<th onclick="sortAccBy('ctr')">CTR <span class="sa"></span></th>
<th onclick="sortAccBy('avg_cpc')">CPC <span class="sa"></span></th>
<th onclick="sortAccBy('conversions')">Conv <span class="sa"></span></th>
<th onclick="sortAccBy('cost_per_conv')">CPA <span class="sa"></span></th>
<th onclick="sortAccBy('conv_value')">Valor <span class="sa"></span></th>
<th onclick="sortAccBy('roas')">ROAS <span class="sa"></span></th>
</tr></thead><tbody id="accBody"></tbody></table>
</div></div>

<div class="section-title">Campanas <span class="badge" id="campCount">0</span></div>
<div class="loading" id="loading"><div class="spinner"></div><div>Cargando datos...</div></div>
<div class="table-wrap">
<table id="campTable"><thead><tr>
<th data-col="status" onclick="sortBy('status')">Estado</th>
<th data-col="name" onclick="sortBy('name')">Campana</th>
<th data-col="account_name" onclick="sortBy('account_name')" id="thAccount" style="display:none">Cuenta</th>
<th data-col="type" onclick="sortBy('type')">Tipo</th>
<th data-col="spend" onclick="sortBy('spend')">Gasto</th>
<th data-col="budget" onclick="sortBy('budget')">Ppto</th>
<th data-col="impressions" onclick="sortBy('impressions')">Impr</th>
<th data-col="clicks" onclick="sortBy('clicks')">Clics</th>
<th data-col="ctr" onclick="sortBy('ctr')">CTR</th>
<th data-col="avg_cpc" onclick="sortBy('avg_cpc')">CPC</th>
<th data-col="conversions" onclick="sortBy('conversions')">Conv</th>
<th data-col="cost_per_conv" onclick="sortBy('cost_per_conv')">CPA</th>
<th data-col="conv_rate" onclick="sortBy('conv_rate')">%Conv</th>
<th data-col="conv_value" onclick="sortBy('conv_value')">Valor</th>
<th data-col="roas" onclick="sortBy('roas')">ROAS</th>
<th data-col="search_is" onclick="sortBy('search_is')">IS</th>
<th data-col="score" onclick="sortBy('score')">Accion</th>
</tr></thead><tbody id="campBody"></tbody></table>
</div>
<div class="toast" id="toast"></div>

<script>
let campaigns=[],accountsSummary=[],dailyData=[];
let sortCol='spend',sortDir=-1,accSortCol='spend',accSortDir=-1;
let dailyChart=null,typeChart=null;

const FC=(v,d=2)=>v!=null?v.toLocaleString('es-ES',{style:'currency',currency:'EUR',minimumFractionDigits:d,maximumFractionDigits:d}):'-';
const FN=v=>v!=null?v.toLocaleString('es-ES'):'-';
const FP=v=>v!=null?(v*100).toFixed(2)+'%':'-';
const FX=(v,d=1)=>v!=null?v.toFixed(d):'-';
function showToast(m,ms){const t=document.getElementById('toast');t.textContent=m;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),ms||5000)}
function pad(n){return String(n).padStart(2,'0')}
function fmtD(d){return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())}
function pctChange(curr,prev){if(!prev||prev===0)return null;return((curr-prev)/Math.abs(prev))*100}
function renderChange(elId,curr,prev,invert){
  const el=document.getElementById(elId);if(!el)return;
  if(prev==null||prev==undefined){el.textContent='';return}
  const pct=pctChange(curr,prev);
  if(pct==null){el.textContent='';return}
  const up=pct>0,arrow=up?'▲':'▼';
  let cls=up?'up':'down';
  if(invert)cls=up?'down':'up';
  if(Math.abs(pct)<0.5)cls='neutral';
  el.className='kpi-change '+cls;
  el.textContent=arrow+' '+Math.abs(pct).toFixed(1)+'%';
}

function setPreset(p){
  const now=new Date();let f,t;
  document.querySelectorAll('.date-presets button').forEach(b=>b.classList.remove('active'));
  if(event&&event.target)event.target.classList.add('active');
  switch(p){
    case 'today':f=t=now;break;case 'yesterday':f=t=new Date(now-864e5);break;
    case '7d':t=now;f=new Date(now-6*864e5);break;case '30d':t=now;f=new Date(now-29*864e5);break;
    case 'thisMonth':f=new Date(now.getFullYear(),now.getMonth(),1);t=now;break;
    case 'lastMonth':f=new Date(now.getFullYear(),now.getMonth()-1,1);t=new Date(now.getFullYear(),now.getMonth(),0);break;
  }
  document.getElementById('dateFrom').value=fmtD(f);document.getElementById('dateTo').value=fmtD(t);
  loadData();
}

(function(){const n=new Date();document.getElementById('dateTo').value=fmtD(n);document.getElementById('dateFrom').value=fmtD(new Date(n-6*864e5))})();

async function doLogout(){await fetch('/api/logout',{method:'POST'});window.location.href='/login'}

async function loadAccounts(){
  try{const r=await fetch('/api/accounts');if(r.status===401){window.location.href='/login';return}
  const d=await r.json();if(d.error){showToast('Error cuentas: '+d.error);return}
  const sel=document.getElementById('accountSelect');
  sel.innerHTML='<option value="all">&#127760; Todas las cuentas (MCC)</option>';
  (d.accounts||[]).forEach(a=>{const o=document.createElement('option');o.value=a.id;o.textContent=a.name?(a.name+' ('+a.id+')'):a.id;sel.appendChild(o)});
  loadData();
  }catch(e){showToast('Error conexion cuentas')}
}

function onAccountChange(){
  const v=document.getElementById('accountSelect').value;
  const isAll=v==='all';
  document.getElementById('accountsSection').style.display=isAll?'':'none';
  document.getElementById('thAccount').style.display=isAll?'':'none';
  loadData();
}

async function loadData(){
  const cid=document.getElementById('accountSelect').value;if(!cid)return;
  document.getElementById('loading').classList.add('show');
  const df=document.getElementById('dateFrom').value,dt=document.getElementById('dateTo').value;
  const cmp=document.getElementById('compareToggle').checked;
  try{
    const [cr,dr]=await Promise.all([
      fetch('/api/campaigns?customer_id='+cid+'&date_from='+df+'&date_to='+dt+'&compare='+cmp),
      fetch('/api/daily?customer_id='+cid+'&date_from='+df+'&date_to='+dt)
    ]);
    if(cr.status===401){window.location.href='/login';return}
    const cd=await cr.json(),dd=await dr.json();
    if(cd.error){showToast('Error: '+JSON.stringify(cd.error));document.getElementById('loading').classList.remove('show');return}
    campaigns=cd.campaigns||[];accountsSummary=cd.accounts||[];dailyData=dd.daily||[];
    updateKPIs(cd.totals,cd.prev_totals);
    renderDailyChart();renderTypeChart();
    if(cid==='all'&&accountsSummary.length){renderAccountsTable();document.getElementById('accCount').textContent=accountsSummary.length}
    runDiagnostics();renderCampaignTable();document.getElementById('campCount').textContent=campaigns.length;
  }catch(e){showToast('Error conexion')}
  document.getElementById('loading').classList.remove('show');
}

function updateKPIs(t,p){
  document.getElementById('kpiSpend').textContent=FC(t.spend);
  document.getElementById('kpiImpr').textContent=FN(t.impressions);
  document.getElementById('kpiClicks').textContent=FN(t.clicks);
  document.getElementById('kpiCtr').textContent=FP(t.ctr);
  document.getElementById('kpiCpc').textContent=FC(t.avg_cpc);
  document.getElementById('kpiConv').textContent=FX(t.conversions);
  document.getElementById('kpiCpa').textContent=FC(t.cost_per_conv);
  document.getElementById('kpiCr').textContent=FP(t.conv_rate);
  document.getElementById('kpiVal').textContent=FC(t.conv_value||0);
  document.getElementById('kpiRoas').textContent=FX(t.roas||0,2)+'x';
  if(p){
    renderChange('kpiSpendC',t.spend,p.spend);renderChange('kpiImprC',t.impressions,p.impressions);
    renderChange('kpiClicksC',t.clicks,p.clicks);renderChange('kpiCtrC',t.ctr,p.ctr);
    renderChange('kpiCpcC',t.avg_cpc,p.avg_cpc,true);renderChange('kpiConvC',t.conversions,p.conversions);
    renderChange('kpiCpaC',t.cost_per_conv,p.cost_per_conv,true);renderChange('kpiCrC',t.conv_rate,p.conv_rate);
    renderChange('kpiValC',t.conv_value||0,p.conv_value||0);renderChange('kpiRoasC',t.roas||0,p.roas||0);
  }else{['kpiSpendC','kpiImprC','kpiClicksC','kpiCtrC','kpiCpcC','kpiConvC','kpiCpaC','kpiCrC','kpiValC','kpiRoasC'].forEach(id=>{const el=document.getElementById(id);if(el)el.textContent=''})}
}

function renderDailyChart(){
  const ctx=document.getElementById('dailyChart');
  if(dailyChart)dailyChart.destroy();
  const labels=dailyData.map(d=>d.date.substring(5));
  dailyChart=new Chart(ctx,{type:'line',data:{labels,datasets:[
    {label:'Gasto',data:dailyData.map(d=>d.spend),borderColor:'#4285f4',backgroundColor:'rgba(66,133,244,0.1)',fill:true,tension:0.3,pointRadius:2,borderWidth:2,yAxisID:'y'},
    {label:'Conversiones',data:dailyData.map(d=>d.conversions),borderColor:'#fbbc04',backgroundColor:'transparent',tension:0.3,pointRadius:2,borderWidth:2,yAxisID:'y1'}
  ]},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
  plugins:{legend:{labels:{color:'#6b7280',font:{size:11}}}},
  scales:{x:{ticks:{color:'#6b7280',font:{size:10}},grid:{color:'#1e2235'}},
  y:{position:'left',ticks:{color:'#4285f4',font:{size:10},callback:v=>v>=1000?(v/1000).toFixed(1)+'k':v},grid:{color:'#1e2235'}},
  y1:{position:'right',ticks:{color:'#fbbc04',font:{size:10}},grid:{display:false}}}}});
}

function renderTypeChart(){
  const ctx=document.getElementById('typeChart');
  if(typeChart)typeChart.destroy();
  const types={};campaigns.forEach(c=>{const t=fmtType(c.type);types[t]=(types[t]||0)+c.spend});
  const labels=Object.keys(types),data=Object.values(types);
  const colors=['#4285f4','#34a853','#fbbc04','#ea4335','#a855f7','#ec4899','#06b6d4','#f97316'];
  typeChart=new Chart(ctx,{type:'doughnut',data:{labels,datasets:[{data,backgroundColor:colors.slice(0,labels.length),borderWidth:0}]},
  options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{color:'#6b7280',font:{size:10},padding:8}}}}});
}

function scoreCampaign(c,avgCtr,avgCpc,avgConvRate,avgCpa){
  let score=50;const reasons=[];
  if(c.status!=='ENABLED')return{score:0,action:'pause',reasons:['Pausada']};
  if(c.spend===0&&c.impressions===0)return{score:0,action:'stop',reasons:['Sin actividad']};
  if(c.spend>0&&c.conversions===0){score-=30;reasons.push('Sin conversiones')}
  if(c.roas>=3){score+=25;reasons.push('ROAS '+c.roas.toFixed(1)+'x')}
  else if(c.roas>=1.5){score+=10;reasons.push('ROAS aceptable')}
  else if(c.roas>0&&c.roas<1){score-=20;reasons.push('ROAS <1')}
  if(avgCtr>0){
    if(c.ctr>avgCtr*1.3){score+=10;reasons.push('CTR alto')}
    else if(c.ctr<avgCtr*0.5){score-=10;reasons.push('CTR bajo')}
  }
  if(avgCpc>0&&c.avg_cpc>avgCpc*2){score-=10;reasons.push('CPC muy alto')}
  if(avgConvRate>0){
    if(c.conv_rate>avgConvRate*1.5){score+=15;reasons.push('Alta tasa conv')}
    else if(c.conv_rate<avgConvRate*0.3&&c.clicks>20){score-=15;reasons.push('Baja tasa conv')}
  }
  if(c.conversions>0&&avgCpa>0){
    if(c.cost_per_conv<avgCpa*0.7){score+=15;reasons.push('CPA eficiente')}
    else if(c.cost_per_conv>avgCpa*2){score-=15;reasons.push('CPA muy alto')}
  }
  if(c.search_is!=null&&c.search_is<0.3&&c.conversions>0){score+=5;reasons.push('IS bajo: margen escalar')}
  if(c.spend>0&&c.budget>0&&c.spend/c.budget>0.9&&c.conversions>0){score+=5;reasons.push('Ppto agotado: escalar')}
  if(c.clicks>50&&c.conversions===0){score-=20;reasons.push(c.clicks+' clics sin conv')}
  let action;
  if(score>=65)action='scale';
  else if(score>=35)action='maintain';
  else action='stop';
  return{score,action,reasons};
}

function runDiagnostics(){
  const active=campaigns.filter(c=>c.status==='ENABLED'&&c.spend>0);
  if(active.length===0){
    document.getElementById('diagCount').textContent='0';
    ['scaleList','maintainList','stopList'].forEach(id=>document.getElementById(id).innerHTML='');
    ['scaleCount','maintainCount','stopCount'].forEach(id=>document.getElementById(id).textContent='0');
    document.getElementById('alertBanners').innerHTML='';
    return;
  }
  const totalSpend=active.reduce((s,c)=>s+c.spend,0);
  const totalClicks=active.reduce((s,c)=>s+c.clicks,0);
  const totalImpr=active.reduce((s,c)=>s+c.impressions,0);
  const totalConv=active.reduce((s,c)=>s+c.conversions,0);
  const avgCtr=totalImpr>0?totalClicks/totalImpr:0;
  const avgCpc=totalClicks>0?totalSpend/totalClicks:0;
  const avgConvRate=totalClicks>0?totalConv/totalClicks:0;
  const avgCpa=totalConv>0?totalSpend/totalConv:0;
  const scale=[],maintain=[],stop=[];
  campaigns.forEach(c=>{
    const d=scoreCampaign(c,avgCtr,avgCpc,avgConvRate,avgCpa);
    c.score=d.score;c.action=d.action;c.reasons=d.reasons;
    if(c.status!=='ENABLED'){if(c.spend>0)stop.push(c);return}
    if(d.action==='scale')scale.push(c);
    else if(d.action==='maintain')maintain.push(c);
    else stop.push(c);
  });
  scale.sort((a,b)=>b.score-a.score);stop.sort((a,b)=>a.score-b.score);
  document.getElementById('scaleCount').textContent=scale.length;
  document.getElementById('maintainCount').textContent=maintain.length;
  document.getElementById('stopCount').textContent=stop.length;
  document.getElementById('diagCount').textContent=active.length;
  const renderList=(items,elId,max)=>{
    document.getElementById(elId).innerHTML=items.slice(0,max||10).map(c=>`<li>
      <span class="camp-name" title="${esc(c.name)}">${esc(c.name)}</span>
      <span class="camp-reason">${c.reasons.slice(0,2).join(' | ')}</span>
    </li>`).join('');
  };
  renderList(scale,'scaleList',10);renderList(maintain,'maintainList',10);renderList(stop,'stopList',10);
  let banners='';
  const noConv=active.filter(c=>c.conversions===0&&c.spend>50);
  if(noConv.length>0){
    const wastedSpend=noConv.reduce((s,c)=>s+c.spend,0);
    banners+=`<div class="alert-banner critical">&#x26A0; ${noConv.length} campanas gastando ${FC(wastedSpend)} sin conversiones</div>`;
  }
  const highCpa=active.filter(c=>c.cost_per_conv>avgCpa*2&&c.conversions>0);
  if(highCpa.length>0)banners+=`<div class="alert-banner warning">&#x26A0; ${highCpa.length} campanas con CPA >2x la media (${FC(avgCpa)})</div>`;
  const topPerf=active.filter(c=>c.roas>=3&&c.search_is!=null&&c.search_is<0.5);
  if(topPerf.length>0)banners+=`<div class="alert-banner success">&#x1F680; ${topPerf.length} campanas con ROAS >3x y margen de IS para escalar</div>`;
  document.getElementById('alertBanners').innerHTML=banners;
}

function sortBy(col){if(sortCol===col)sortDir*=-1;else{sortCol=col;sortDir=col==='name'||col==='status'||col==='type'||col==='action'?1:-1}renderCampaignTable()}
function sortAccBy(col){if(accSortCol===col)accSortDir*=-1;else{accSortCol=col;accSortDir=col==='name'?1:-1}renderAccountsTable()}

function renderCampaignTable(){
  const f=document.getElementById('searchInput').value.toLowerCase();
  const isAll=document.getElementById('accountSelect').value==='all';
  let data=campaigns.filter(c=>!f||c.name.toLowerCase().includes(f));
  data.sort((a,b)=>{let va=a[sortCol],vb=b[sortCol];if(va==null)va=sortDir>0?Infinity:-Infinity;if(vb==null)vb=sortDir>0?Infinity:-Infinity;if(typeof va==='string')return va.localeCompare(vb)*sortDir;return(va-vb)*sortDir});
  document.getElementById('campBody').innerHTML=data.map(c=>`<tr>
    <td><span class="status-badge status-${c.status}">${c.status==='ENABLED'?'Activa':'Pausada'}</span></td>
    <td>${esc(c.name)}</td>
    ${isAll?'<td>'+esc(c.account_name||'')+'</td>':''}
    <td><span class="type-badge type-${c.type}">${fmtType(c.type)}</span></td>
    <td class="num">${FC(c.spend)}</td><td class="num">${FC(c.budget)}</td>
    <td class="num">${FN(c.impressions)}</td><td class="num">${FN(c.clicks)}</td>
    <td class="num">${FP(c.ctr)}</td><td class="num">${FC(c.avg_cpc)}</td>
    <td class="num">${FX(c.conversions)}</td><td class="num">${FC(c.cost_per_conv)}</td>
    <td class="num">${FP(c.conv_rate)}</td><td class="num">${FC(c.conv_value||0)}</td>
    <td class="num">${FX(c.roas||0,2)}x</td>
    <td class="num">${c.search_is!=null?FP(c.search_is):'-'}</td>
    <td>${c.action?`<span class="score-pill ${c.action==='scale'?'pill-green':c.action==='maintain'?'pill-yellow':'pill-red'}">${c.action==='scale'?'ESCALAR':c.action==='maintain'?'MANTENER':'REVISAR'}</span>`:'-'}</td>
  </tr>`).join('');
}

function renderAccountsTable(){
  let data=[...accountsSummary];
  data.sort((a,b)=>{let va=a[accSortCol],vb=b[accSortCol];if(typeof va==='string')return va.localeCompare(vb)*accSortDir;return(va-vb)*accSortDir});
  document.getElementById('accBody').innerHTML=data.map(a=>`<tr>
    <td><a href="#" onclick="selectAccount('${a.id}');return false" style="color:#4285f4;font-weight:600">${esc(a.name||a.id)}</a></td>
    <td class="num">${FC(a.spend)}</td><td class="num">${FN(a.impressions)}</td>
    <td class="num">${FN(a.clicks)}</td><td class="num">${FP(a.ctr)}</td>
    <td class="num">${FC(a.avg_cpc)}</td><td class="num">${FX(a.conversions)}</td>
    <td class="num">${FC(a.cost_per_conv)}</td><td class="num">${FC(a.conv_value||0)}</td>
    <td class="num">${FX(a.roas||0,2)}x</td>
  </tr>`).join('');
}

function selectAccount(id){document.getElementById('accountSelect').value=id;onAccountChange()}

function exportCSV(){
  const isAll=document.getElementById('accountSelect').value==='all';
  let csv='Estado,Campana,'+(isAll?'Cuenta,':'')+'Tipo,Gasto,Presupuesto,Impresiones,Clics,CTR,CPC,Conversiones,CPA,%Conv,Valor,ROAS,IS\\n';
  campaigns.forEach(c=>{csv+=`"${c.status}","${c.name}",`+(isAll?`"${c.account_name||''}",`:'')+`"${fmtType(c.type)}",${c.spend},${c.budget},${c.impressions},${c.clicks},${(c.ctr*100).toFixed(2)},${c.avg_cpc.toFixed(2)},${c.conversions},${c.cost_per_conv.toFixed(2)},${(c.conv_rate*100).toFixed(2)},${c.conv_value||0},${(c.roas||0).toFixed(2)},${c.search_is!=null?(c.search_is*100).toFixed(2):''}\\n`});
  const blob=new Blob([csv],{type:'text/csv'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);
  a.download='google_ads_'+document.getElementById('dateFrom').value+'_'+document.getElementById('dateTo').value+'.csv';a.click();
}

function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}
function fmtType(t){return{'SEARCH':'Search','DISPLAY':'Display','SHOPPING':'Shopping','VIDEO':'Video','PERFORMANCE_MAX':'PMax','SMART':'Smart','LOCAL':'Local','DISCOVERY':'Discovery','DEMAND_GEN':'Demand Gen','MULTI_CHANNEL':'Multi'}[t]||t}

loadAccounts();
</script></body></html>'''
