import os
import hashlib
import json
import time
from datetime import datetime, timedelta
from flask import Flask, request, Response, session, jsonify, redirect

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')

# ============================================================
# CONFIG
# ============================================================
GOOGLE_ADS_DEVELOPER_TOKEN = os.environ.get('GOOGLE_ADS_DEVELOPER_TOKEN', '')
GOOGLE_ADS_CLIENT_ID = os.environ.get('GOOGLE_ADS_CLIENT_ID', '')
GOOGLE_ADS_CLIENT_SECRET = os.environ.get('GOOGLE_ADS_CLIENT_SECRET', '')
GOOGLE_ADS_REFRESH_TOKEN = os.environ.get('GOOGLE_ADS_REFRESH_TOKEN', '')
GOOGLE_ADS_LOGIN_CUSTOMER_ID = os.environ.get('GOOGLE_ADS_LOGIN_CUSTOMER_ID', '')
PASSWORD_HASH = os.environ.get('PASSWORD_HASH', '')

import requests as req_lib

# ============================================================
# HELPERS
# ============================================================
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
# OAUTH2 FLOW (para generar Refresh Token)
# ============================================================
OAUTH_SCOPES = 'https://www.googleapis.com/auth/adwords'

@app.route('/oauth/start')
def oauth_start():
    redirect_uri = request.host_url.rstrip('/') + '/oauth/callback'
    auth_url = (
        'https://accounts.google.com/o/oauth2/v2/auth'
        f'?client_id={GOOGLE_ADS_CLIENT_ID}'
        f'&redirect_uri={redirect_uri}'
        f'&response_type=code'
        f'&scope={OAUTH_SCOPES}'
        f'&access_type=offline'
        f'&prompt=consent'
    )
    return redirect(auth_url)

@app.route('/oauth/callback')
def oauth_callback():
    code = request.args.get('code')
    error = request.args.get('error')
    if error:
        return Response(f'<h1>Error: {error}</h1>', content_type='text/html')
    if not code:
        return Response('<h1>No code received</h1>', content_type='text/html')
    redirect_uri = request.host_url.rstrip('/') + '/oauth/callback'
    r = req_lib.post('https://oauth2.googleapis.com/token', data={
        'code': code,
        'client_id': GOOGLE_ADS_CLIENT_ID,
        'client_secret': GOOGLE_ADS_CLIENT_SECRET,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code'
    })
    data = r.json()
    refresh_token = data.get('refresh_token', '')
    access_token = data.get('access_token', '')
    error_desc = data.get('error_description', '')
    if data.get('error'):
        return Response(f'<html><body style="background:#0f1117;color:#fff;font-family:sans-serif;padding:40px"><h1 style="color:#ea4335">Error</h1><p>{data.get("error")}: {error_desc}</p></body></html>', content_type='text/html')
    html = f'''<html><body style="background:#0f1117;color:#fff;font-family:sans-serif;padding:40px;max-width:800px;margin:0 auto">
    <h1 style="color:#34a853">Refresh Token generado!</h1>
    <p>Copia este Refresh Token y ponlo como variable de entorno <code>GOOGLE_ADS_REFRESH_TOKEN</code> en Vercel:</p>
    <div style="background:#1a1d27;border:1px solid #2d3148;border-radius:8px;padding:16px;margin:16px 0;word-break:break-all">
    <code style="color:#4285f4;font-size:14px">{refresh_token}</code>
    </div>
    <p style="color:#8b8fa3">Despues de anadirlo en Vercel, haz Redeploy y el dashboard funcionara.</p>
    <p style="color:#8b8fa3;font-size:12px">Access Token (temporal, no lo necesitas guardar): {access_token[:20]}...</p>
    </body></html>'''
    return Response(html, content_type='text/html')

# ============================================================
# API ROUTES
# ============================================================
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    pwd = data.get('password', '')
    pwd_hash = hashlib.sha256(pwd.encode()).hexdigest()
    if pwd_hash == PASSWORD_HASH:
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
        login_cid = GOOGLE_ADS_LOGIN_CUSTOMER_ID.replace('-', '')
        query = """
            SELECT
                customer_client.id,
                customer_client.descriptive_name,
                customer_client.status,
                customer_client.manager
            FROM customer_client
            WHERE customer_client.manager = FALSE
              AND customer_client.status = 'ENABLED'
        """
        rows = google_ads_search(login_cid, query)
        if isinstance(rows, dict) and 'error' in rows:
            return jsonify(rows), rows.get('status', 500)
        accounts = []
        for row in rows:
            cc = row.get('customerClient', {})
            accounts.append({
                'id': cc.get('id'),
                'name': cc.get('descriptiveName', ''),
                'status': cc.get('status', '')
            })
        accounts.sort(key=lambda a: a.get('name', ''))
        return jsonify({'accounts': accounts})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/campaigns')
def api_campaigns():
    try:
        customer_id = request.args.get('customer_id', '')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')
        if not customer_id:
            return jsonify({'error': 'customer_id required'}), 400
        if not date_from or not date_to:
            today = datetime.now()
            date_to = today.strftime('%Y-%m-%d')
            date_from = (today - timedelta(days=30)).strftime('%Y-%m-%d')
        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                campaign.status,
                campaign.advertising_channel_type,
                campaign_budget.amount_micros,
                metrics.impressions,
                metrics.clicks,
                metrics.ctr,
                metrics.average_cpc,
                metrics.cost_micros,
                metrics.conversions,
                metrics.cost_per_conversion,
                metrics.conversions_from_interactions_rate,
                metrics.all_conversions,
                metrics.search_impression_share
            FROM campaign
            WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'
              AND campaign.status != 'REMOVED'
            ORDER BY metrics.cost_micros DESC
        """
        rows = google_ads_search(customer_id, query)
        if isinstance(rows, dict) and 'error' in rows:
            return jsonify(rows), rows.get('status', 500)
        campaigns = []
        totals = {'spend': 0, 'impressions': 0, 'clicks': 0, 'conversions': 0, 'all_conversions': 0}
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
            totals['spend'] += cost
            totals['impressions'] += impressions
            totals['clicks'] += clicks
            totals['conversions'] += conversions
            totals['all_conversions'] += all_conversions
            campaigns.append({
                'id': c.get('id'),
                'name': c.get('name', ''),
                'status': c.get('status', ''),
                'type': c.get('advertisingChannelType', ''),
                'budget': budget,
                'spend': cost,
                'impressions': impressions,
                'clicks': clicks,
                'ctr': ctr,
                'avg_cpc': avg_cpc,
                'conversions': conversions,
                'cost_per_conv': cost_per_conv,
                'conv_rate': conv_rate,
                'all_conversions': all_conversions,
                'search_is': search_is
            })
        totals['ctr'] = totals['clicks'] / totals['impressions'] if totals['impressions'] > 0 else 0
        totals['avg_cpc'] = totals['spend'] / totals['clicks'] if totals['clicks'] > 0 else 0
        totals['cost_per_conv'] = totals['spend'] / totals['conversions'] if totals['conversions'] > 0 else 0
        totals['conv_rate'] = totals['conversions'] / totals['clicks'] if totals['clicks'] > 0 else 0
        return jsonify({'campaigns': campaigns, 'totals': totals})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================
# LOGIN HTML
# ============================================================
LOGIN_HTML = '''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Google Ads Dashboard - Login</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f1117;color:#e1e4e8;display:flex;align-items:center;justify-content:center;min-height:100vh}
.login-box{background:#1a1d27;border:1px solid #2d3148;border-radius:16px;padding:48px;width:100%;max-width:400px;box-shadow:0 8px 32px rgba(0,0,0,0.4)}
.login-box h1{text-align:center;margin-bottom:8px;font-size:24px;color:#fff}
.login-box .subtitle{text-align:center;color:#8b8fa3;margin-bottom:32px;font-size:14px}
.login-box .logo{text-align:center;font-size:48px;margin-bottom:16px}
.form-group{margin-bottom:20px}
.form-group label{display:block;margin-bottom:6px;font-size:13px;color:#8b8fa3}
.form-group input{width:100%;padding:12px 16px;background:#0f1117;border:1px solid #2d3148;border-radius:8px;color:#fff;font-size:15px;outline:none;transition:border-color .2s}
.form-group input:focus{border-color:#4285f4}
.btn{width:100%;padding:12px;background:#4285f4;color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer;transition:background .2s}
.btn:hover{background:#3367d6}
.error-msg{color:#f44336;text-align:center;margin-top:12px;font-size:13px;display:none}
</style>
</head>
<body>
<div class="login-box">
<div class="logo">&#x1F4CA;</div>
<h1>Google Ads Dashboard</h1>
<p class="subtitle">Introduce tu password para acceder</p>
<div class="form-group">
<label>Password</label>
<input type="password" id="pwd" placeholder="Tu password" autofocus>
</div>
<button class="btn" onclick="doLogin()">Acceder</button>
<div class="error-msg" id="err"></div>
</div>
<script>
document.getElementById('pwd').addEventListener('keydown',function(e){if(e.key==='Enter')doLogin()});
async function doLogin(){
  const pwd=document.getElementById('pwd').value;
  const err=document.getElementById('err');
  err.style.display='none';
  try{
    const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pwd})});
    if(r.ok){window.location.href='/';}
    else{const d=await r.json();err.textContent=d.error||'Error';err.style.display='block';}
  }catch(e){err.textContent='Error de conexion';err.style.display='block';}
}
</script>
</body>
</html>'''

# ============================================================
# INDEX HTML (DASHBOARD)
# ============================================================
INDEX_HTML = '''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Google Ads Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f1117;color:#e1e4e8;min-height:100vh}
a{color:#4285f4;text-decoration:none}

/* HEADER */
.header{background:#1a1d27;border-bottom:1px solid #2d3148;padding:12px 24px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100}
.header-left{display:flex;align-items:center;gap:16px}
.header h1{font-size:18px;color:#fff;white-space:nowrap}
.header h1 span{color:#4285f4}
.header-right{display:flex;align-items:center;gap:12px}
.btn-logout{background:transparent;border:1px solid #2d3148;color:#8b8fa3;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:13px;transition:all .2s}
.btn-logout:hover{border-color:#4285f4;color:#fff}

/* CONTROLS BAR */
.controls{background:#1a1d27;border-bottom:1px solid #2d3148;padding:12px 24px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.control-group{display:flex;align-items:center;gap:8px}
.control-group label{font-size:12px;color:#8b8fa3;white-space:nowrap}
select,input[type="date"]{background:#0f1117;border:1px solid #2d3148;color:#fff;padding:8px 12px;border-radius:6px;font-size:13px;outline:none}
select:focus,input[type="date"]:focus{border-color:#4285f4}
.date-presets{display:flex;gap:4px;flex-wrap:wrap}
.date-presets button{background:#0f1117;border:1px solid #2d3148;color:#8b8fa3;padding:6px 10px;border-radius:6px;cursor:pointer;font-size:11px;white-space:nowrap;transition:all .2s}
.date-presets button:hover,.date-presets button.active{background:#4285f4;color:#fff;border-color:#4285f4}
.search-box{margin-left:auto}
.search-box input{background:#0f1117;border:1px solid #2d3148;color:#fff;padding:8px 12px;border-radius:6px;font-size:13px;outline:none;width:200px}
.search-box input:focus{border-color:#4285f4}
.btn-refresh{background:#4285f4;border:none;color:#fff;padding:8px 16px;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;transition:background .2s}
.btn-refresh:hover{background:#3367d6}

/* KPI CARDS */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;padding:20px 24px}
.kpi-card{background:#1a1d27;border:1px solid #2d3148;border-radius:12px;padding:16px 20px;transition:border-color .2s}
.kpi-card:hover{border-color:#4285f4}
.kpi-label{font-size:11px;color:#8b8fa3;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px}
.kpi-value{font-size:24px;font-weight:700;color:#fff}
.kpi-value.spend{color:#4285f4}
.kpi-value.clicks{color:#34a853}
.kpi-value.conv{color:#fbbc04}

/* TABLE */
.table-wrap{padding:0 24px 24px;overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
thead th{background:#1a1d27;color:#8b8fa3;font-weight:600;text-transform:uppercase;font-size:11px;letter-spacing:0.5px;padding:10px 12px;text-align:left;border-bottom:2px solid #2d3148;cursor:pointer;white-space:nowrap;position:sticky;top:0;user-select:none}
thead th:hover{color:#4285f4}
thead th .sort-arrow{margin-left:4px;font-size:10px}
tbody tr{border-bottom:1px solid #1e2235;transition:background .15s}
tbody tr:hover{background:#1e2235}
tbody td{padding:10px 12px;white-space:nowrap}
.status-badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}
.status-ENABLED{background:rgba(52,168,83,0.15);color:#34a853}
.status-PAUSED{background:rgba(251,188,4,0.15);color:#fbbc04}
.status-REMOVED{background:rgba(234,67,53,0.15);color:#ea4335}
.type-badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:600;background:rgba(66,133,244,0.15);color:#4285f4}
.type-DISPLAY{background:rgba(52,168,83,0.15);color:#34a853}
.type-SHOPPING{background:rgba(251,188,4,0.15);color:#fbbc04}
.type-VIDEO{background:rgba(234,67,53,0.15);color:#ea4335}
.type-PERFORMANCE_MAX{background:rgba(168,85,247,0.15);color:#a855f7}
td.num{text-align:right;font-variant-numeric:tabular-nums}

/* LOADING & EMPTY */
.loading{display:none;text-align:center;padding:60px;color:#8b8fa3}
.loading.show{display:block}
.spinner{display:inline-block;width:32px;height:32px;border:3px solid #2d3148;border-top-color:#4285f4;border-radius:50%;animation:spin .8s linear infinite;margin-bottom:12px}
@keyframes spin{to{transform:rotate(360deg)}}
.empty-state{text-align:center;padding:60px;color:#8b8fa3}
.toast{position:fixed;top:20px;right:20px;background:#ea4335;color:#fff;padding:12px 20px;border-radius:8px;font-size:13px;z-index:999;display:none;max-width:400px;box-shadow:0 4px 16px rgba(0,0,0,0.3)}
.toast.show{display:block;animation:slideIn .3s ease}
@keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}

/* RESPONSIVE */
@media(max-width:768px){
  .controls{flex-direction:column;align-items:stretch}
  .search-box{margin-left:0}
  .search-box input{width:100%}
  .kpis{grid-template-columns:repeat(2,1fr)}
  .header{flex-direction:column;gap:8px}
}
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <h1>&#x1F4CA; Google <span>Ads</span> Dashboard</h1>
  </div>
  <div class="header-right">
    <span id="accountName" style="color:#8b8fa3;font-size:13px"></span>
    <button class="btn-logout" onclick="doLogout()">Cerrar sesion</button>
  </div>
</div>

<div class="controls">
  <div class="control-group">
    <label>Cuenta:</label>
    <select id="accountSelect" onchange="onAccountChange()">
      <option value="">Cargando cuentas...</option>
    </select>
  </div>
  <div class="control-group">
    <label>Desde:</label>
    <input type="date" id="dateFrom">
  </div>
  <div class="control-group">
    <label>Hasta:</label>
    <input type="date" id="dateTo">
  </div>
  <div class="date-presets">
    <button onclick="setPreset('today')">Hoy</button>
    <button onclick="setPreset('yesterday')">Ayer</button>
    <button onclick="setPreset('7d')" class="active">7 dias</button>
    <button onclick="setPreset('30d')">30 dias</button>
    <button onclick="setPreset('thisMonth')">Este mes</button>
    <button onclick="setPreset('lastMonth')">Mes anterior</button>
  </div>
  <div class="search-box">
    <input type="text" id="searchInput" placeholder="Buscar campanas..." oninput="filterTable()">
  </div>
  <button class="btn-refresh" onclick="loadCampaigns()">Actualizar</button>
</div>

<div class="kpis">
  <div class="kpi-card"><div class="kpi-label">Gasto Total</div><div class="kpi-value spend" id="kpiSpend">-</div></div>
  <div class="kpi-card"><div class="kpi-label">Impresiones</div><div class="kpi-value" id="kpiImpressions">-</div></div>
  <div class="kpi-card"><div class="kpi-label">Clics</div><div class="kpi-value clicks" id="kpiClicks">-</div></div>
  <div class="kpi-card"><div class="kpi-label">CTR</div><div class="kpi-value" id="kpiCtr">-</div></div>
  <div class="kpi-card"><div class="kpi-label">CPC Medio</div><div class="kpi-value" id="kpiCpc">-</div></div>
  <div class="kpi-card"><div class="kpi-label">Conversiones</div><div class="kpi-value conv" id="kpiConv">-</div></div>
  <div class="kpi-card"><div class="kpi-label">Coste/Conv</div><div class="kpi-value" id="kpiCostConv">-</div></div>
  <div class="kpi-card"><div class="kpi-label">Tasa Conv</div><div class="kpi-value" id="kpiConvRate">-</div></div>
</div>

<div class="loading" id="loading"><div class="spinner"></div><div>Cargando datos de Google Ads...</div></div>

<div class="table-wrap">
  <table id="campaignTable">
    <thead>
      <tr>
        <th data-col="status" onclick="sortBy('status')">Estado <span class="sort-arrow"></span></th>
        <th data-col="name" onclick="sortBy('name')">Campana <span class="sort-arrow"></span></th>
        <th data-col="type" onclick="sortBy('type')">Tipo <span class="sort-arrow"></span></th>
        <th data-col="spend" onclick="sortBy('spend')">Gasto <span class="sort-arrow"></span></th>
        <th data-col="budget" onclick="sortBy('budget')">Presupuesto <span class="sort-arrow"></span></th>
        <th data-col="impressions" onclick="sortBy('impressions')">Impresiones <span class="sort-arrow"></span></th>
        <th data-col="clicks" onclick="sortBy('clicks')">Clics <span class="sort-arrow"></span></th>
        <th data-col="ctr" onclick="sortBy('ctr')">CTR <span class="sort-arrow"></span></th>
        <th data-col="avg_cpc" onclick="sortBy('avg_cpc')">CPC <span class="sort-arrow"></span></th>
        <th data-col="conversions" onclick="sortBy('conversions')">Conv <span class="sort-arrow"></span></th>
        <th data-col="cost_per_conv" onclick="sortBy('cost_per_conv')">Coste/Conv <span class="sort-arrow"></span></th>
        <th data-col="conv_rate" onclick="sortBy('conv_rate')">Tasa Conv <span class="sort-arrow"></span></th>
        <th data-col="all_conversions" onclick="sortBy('all_conversions')">All Conv <span class="sort-arrow"></span></th>
        <th data-col="search_is" onclick="sortBy('search_is')">IS Busqueda <span class="sort-arrow"></span></th>
      </tr>
    </thead>
    <tbody id="tableBody"></tbody>
  </table>
</div>

<div class="empty-state" id="emptyState" style="display:none">
  <p>Selecciona una cuenta para ver las campanas</p>
</div>

<div class="toast" id="toast"></div>

<script>
let campaigns = [];
let sortCol = 'spend';
let sortDir = -1;

// FORMAT HELPERS
function fmtCur(v){return v!=null?v.toLocaleString('es-ES',{style:'currency',currency:'EUR',minimumFractionDigits:2}):'-'}
function fmtNum(v){return v!=null?v.toLocaleString('es-ES'):'-'}
function fmtPct(v){return v!=null?(v*100).toFixed(2)+'%':'-'}
function fmtPctDirect(v){return v!=null?v.toFixed(2)+'%':'-'}

// TOAST
function showToast(msg,ms){const t=document.getElementById('toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),ms||4000)}

// DATE PRESETS
function pad(n){return String(n).padStart(2,'0')}
function fmtDate(d){return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())}

function setPreset(p){
  const now=new Date();
  let f,t;
  document.querySelectorAll('.date-presets button').forEach(b=>b.classList.remove('active'));
  event.target.classList.add('active');
  switch(p){
    case 'today':f=t=now;break;
    case 'yesterday':f=t=new Date(now-86400000);break;
    case '7d':t=now;f=new Date(now-6*86400000);break;
    case '30d':t=now;f=new Date(now-29*86400000);break;
    case 'thisMonth':f=new Date(now.getFullYear(),now.getMonth(),1);t=now;break;
    case 'lastMonth':f=new Date(now.getFullYear(),now.getMonth()-1,1);t=new Date(now.getFullYear(),now.getMonth(),0);break;
  }
  document.getElementById('dateFrom').value=fmtDate(f);
  document.getElementById('dateTo').value=fmtDate(t);
  loadCampaigns();
}

// INIT DATES (last 7 days)
(function(){
  const now=new Date();
  document.getElementById('dateTo').value=fmtDate(now);
  document.getElementById('dateFrom').value=fmtDate(new Date(now-6*86400000));
})();

// LOGOUT
async function doLogout(){
  await fetch('/api/logout',{method:'POST'});
  window.location.href='/login';
}

// LOAD ACCOUNTS
async function loadAccounts(){
  try{
    const r=await fetch('/api/accounts');
    if(r.status===401){window.location.href='/login';return}
    const d=await r.json();
    if(d.error){showToast('Error cargando cuentas: '+d.error);return}
    const sel=document.getElementById('accountSelect');
    sel.innerHTML='<option value="">-- Selecciona cuenta --</option>';
    (d.accounts||[]).forEach(a=>{
      const o=document.createElement('option');
      o.value=a.id;
      o.textContent=a.name?a.name+' ('+a.id+')':a.id;
      sel.appendChild(o);
    });
    if(d.accounts&&d.accounts.length===1){sel.value=d.accounts[0].id;onAccountChange()}
  }catch(e){showToast('Error de conexion cargando cuentas')}
}

function onAccountChange(){
  const sel=document.getElementById('accountSelect');
  const opt=sel.options[sel.selectedIndex];
  document.getElementById('accountName').textContent=opt?opt.textContent:'';
  loadCampaigns();
}

// LOAD CAMPAIGNS
async function loadCampaigns(){
  const cid=document.getElementById('accountSelect').value;
  if(!cid){document.getElementById('emptyState').style.display='block';return}
  document.getElementById('emptyState').style.display='none';
  document.getElementById('loading').classList.add('show');
  try{
    const df=document.getElementById('dateFrom').value;
    const dt=document.getElementById('dateTo').value;
    const r=await fetch('/api/campaigns?customer_id='+cid+'&date_from='+df+'&date_to='+dt);
    if(r.status===401){window.location.href='/login';return}
    const d=await r.json();
    if(d.error){showToast('Error: '+JSON.stringify(d.error));document.getElementById('loading').classList.remove('show');return}
    campaigns=d.campaigns||[];
    updateKPIs(d.totals||{});
    renderTable();
  }catch(e){showToast('Error de conexion')}
  document.getElementById('loading').classList.remove('show');
}

// UPDATE KPIS
function updateKPIs(t){
  document.getElementById('kpiSpend').textContent=fmtCur(t.spend);
  document.getElementById('kpiImpressions').textContent=fmtNum(t.impressions);
  document.getElementById('kpiClicks').textContent=fmtNum(t.clicks);
  document.getElementById('kpiCtr').textContent=fmtPct(t.ctr);
  document.getElementById('kpiCpc').textContent=fmtCur(t.avg_cpc);
  document.getElementById('kpiConv').textContent=t.conversions!=null?t.conversions.toFixed(1):'-';
  document.getElementById('kpiCostConv').textContent=fmtCur(t.cost_per_conv);
  document.getElementById('kpiConvRate').textContent=fmtPct(t.conv_rate);
}

// SORT
function sortBy(col){
  if(sortCol===col)sortDir*=-1;
  else{sortCol=col;sortDir=col==='name'||col==='status'||col==='type'?1:-1}
  document.querySelectorAll('thead th .sort-arrow').forEach(s=>s.textContent='');
  const th=document.querySelector('thead th[data-col="'+col+'"] .sort-arrow');
  if(th)th.textContent=sortDir>0?' ▲':' ▼';
  renderTable();
}

// RENDER TABLE
function renderTable(){
  const filter=document.getElementById('searchInput').value.toLowerCase();
  let data=campaigns.filter(c=>!filter||c.name.toLowerCase().includes(filter));
  data.sort((a,b)=>{
    let va=a[sortCol],vb=b[sortCol];
    if(va==null)va=sortDir>0?Infinity:-Infinity;
    if(vb==null)vb=sortDir>0?Infinity:-Infinity;
    if(typeof va==='string')return va.localeCompare(vb)*sortDir;
    return (va-vb)*sortDir;
  });
  const tbody=document.getElementById('tableBody');
  tbody.innerHTML=data.map(c=>`<tr>
    <td><span class="status-badge status-${c.status}">${c.status}</span></td>
    <td>${esc(c.name)}</td>
    <td><span class="type-badge type-${c.type}">${fmtType(c.type)}</span></td>
    <td class="num">${fmtCur(c.spend)}</td>
    <td class="num">${fmtCur(c.budget)}</td>
    <td class="num">${fmtNum(c.impressions)}</td>
    <td class="num">${fmtNum(c.clicks)}</td>
    <td class="num">${fmtPct(c.ctr)}</td>
    <td class="num">${fmtCur(c.avg_cpc)}</td>
    <td class="num">${c.conversions!=null?c.conversions.toFixed(1):'-'}</td>
    <td class="num">${fmtCur(c.cost_per_conv)}</td>
    <td class="num">${fmtPct(c.conv_rate)}</td>
    <td class="num">${c.all_conversions!=null?c.all_conversions.toFixed(1):'-'}</td>
    <td class="num">${c.search_is!=null?fmtPctDirect(c.search_is*100):'-'}</td>
  </tr>`).join('');
}

function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}
function fmtType(t){
  const m={'SEARCH':'Search','DISPLAY':'Display','SHOPPING':'Shopping','VIDEO':'Video','PERFORMANCE_MAX':'PMax','MULTI_CHANNEL':'Multi','SMART':'Smart','LOCAL':'Local','DISCOVERY':'Discovery','DEMAND_GEN':'Demand Gen'};
  return m[t]||t;
}
function filterTable(){renderTable()}

// INIT
loadAccounts();
</script>
</body>
</html>'''
