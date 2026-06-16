"""
StockAI Terminal - IIT Final Project
Professional US Stock Market Intelligence Platform
Fixed version: No Anthropic API needed. Uses Finnhub + AlphaVantage (both free).
"""
from flask import Flask, request, jsonify, Response, send_from_directory
import requests
from datetime import datetime, timedelta
import os

app = Flask(__name__, static_folder='static')

# ── FREE API KEYS ──────────────────────────────────────────────────────────────
# Finnhub  → Sign up FREE at https://finnhub.io  (60 calls/min free tier)
# AlphaVantage → Sign up FREE at https://www.alphavantage.co/support/#api-key
# Set these in Render → Environment Variables (never hardcode real keys!)
FINNHUB_API_KEY      = os.environ.get('FINNHUB_API_KEY', '')
ALPHAVANTAGE_API_KEY = os.environ.get('ALPHAVANTAGE_API_KEY', '')

PLACEHOLDER_FH = ''
PLACEHOLDER_AV = ''

# ── DATA FETCHERS ──────────────────────────────────────────────────────────────

def get_price(sym):
    if not FINNHUB_API_KEY:
        return None
    try:
        d = requests.get(
            f'https://finnhub.io/api/v1/quote?symbol={sym}&token={FINNHUB_API_KEY}',
            timeout=6).json()
        if d.get('c'):
            return {
                'price':      round(d['c'], 2),
                'change':     round(d.get('d', 0), 2),
                'change_pct': round(d.get('dp', 0), 2),
                'high':       round(d.get('h', 0), 2),
                'low':        round(d.get('l', 0), 2),
                'open':       round(d.get('o', 0), 2),
                'prev_close': round(d.get('pc', 0), 2),
            }
    except Exception:
        pass
    return None


def get_profile(sym):
    if not FINNHUB_API_KEY:
        return None
    try:
        d = requests.get(
            f'https://finnhub.io/api/v1/stock/profile2?symbol={sym}&token={FINNHUB_API_KEY}',
            timeout=6).json()
        if not d.get('name'):
            return None
        mc  = d.get('marketCapitalization', 0)
        mcs = (f'${mc/1000:.2f}T' if mc >= 1000
               else (f'${mc:.1f}B' if mc >= 1 else '—'))
        return {
            'name':     d.get('name', sym),
            'logo':     d.get('logo', ''),
            'exchange': d.get('exchange', ''),
            'industry': d.get('finnhubIndustry', ''),
            'country':  d.get('country', ''),
            'currency': d.get('currency', 'USD'),
            'ipo':      d.get('ipo', ''),
            'weburl':   d.get('weburl', ''),
            'mktcap':   mcs,
        }
    except Exception:
        return None


def get_metrics(sym):
    if not FINNHUB_API_KEY:
        return None
    try:
        d = requests.get(
            f'https://finnhub.io/api/v1/stock/metric?symbol={sym}&metric=all&token={FINNHUB_API_KEY}',
            timeout=6).json()
        m = d.get('metric', {})

        def f(v, pre='', suf='', dec=2):
            if v is None or v == 0:
                return '—'
            return f'{pre}{round(float(v), dec)}{suf}'

        return {
            'pe':          f(m.get('peNormalizedAnnual')),
            'eps':         f(m.get('epsNormalizedAnnual'), '$'),
            'beta':        f(m.get('beta')),
            'roe':         f(m.get('roeRfy'), suf='%'),
            '52w_high':    f(m.get('52WeekHigh'), '$'),
            '52w_low':     f(m.get('52WeekLow'), '$'),
            'div_yield':   f(m.get('dividendYieldIndicatedAnnual'), suf='%'),
            'revenue_ttm': f(m.get('revenuePerShareTTM'), '$'),
            'pb':          f(m.get('pbAnnual')),
            'net_margin':  f(m.get('netMarginTTM'), suf='%'),
        }
    except Exception:
        return None


def get_history(sym):
    if not ALPHAVANTAGE_API_KEY:
        return None
    try:
        d = requests.get(
            f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY'
            f'&symbol={sym}&outputsize=compact&apikey={ALPHAVANTAGE_API_KEY}',
            timeout=12).json()
        ts = d.get('Time Series (Daily)', {})
        if not ts:
            return None
        dates = sorted(ts.keys(), reverse=True)[:10]
        dates.reverse()
        return {
            'dates':  [x[5:] for x in dates],
            'prices': [round(float(ts[x]['4. close']), 2) for x in dates],
        }
    except Exception:
        return None


def get_dividends(sym):
    if not ALPHAVANTAGE_API_KEY:
        return None
    try:
        d = requests.get(
            f'https://www.alphavantage.co/query?function=DIVIDENDS'
            f'&symbol={sym}&apikey={ALPHAVANTAGE_API_KEY}',
            timeout=10).json()
        items = d.get('data', [])
        return [
            {'date': x.get('ex_dividend_date', '—'),
             'amount': round(float(x.get('amount', 0) or 0), 4)}
            for x in items[:5]
        ] if items else None
    except Exception:
        return None


def get_news(sym):
    if not FINNHUB_API_KEY:
        return None
    try:
        from_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
        data = requests.get(
            f'https://finnhub.io/api/v1/company-news?symbol={sym}'
            f'&from={from_date}&token={FINNHUB_API_KEY}',
            timeout=6).json()
        if not isinstance(data, list):
            return None
        pos_w = ['gain','rise','up','beat','surge','strong','profit','record',
                 'high','buy','grow','soar','jump','launch','expand','win']
        neg_w = ['fall','drop','down','loss','miss','weak','crash','cut',
                 'decline','sell','risk','warn','slip','layoff','sue','fine']
        result = []
        for item in data[:8]:
            hl  = item.get('headline', '')
            p   = sum(1 for w in pos_w if w in hl.lower())
            n   = sum(1 for w in neg_w if w in hl.lower())
            s   = 'Positive' if p > n else ('Negative' if n > p else 'Neutral')
            try:
                dt = datetime.fromtimestamp(item.get('datetime', 0)).strftime('%b %d')
            except Exception:
                dt = '—'
            result.append({
                'headline':  hl,
                'source':    item.get('source', ''),
                'sentiment': s,
                'date':      dt,
            })
        return result if result else None
    except Exception:
        return None


# ── SYMBOL EXTRACTOR ──────────────────────────────────────────────────────────

KNOWN_COMPANIES = {
    'APPLE':'AAPL', 'MICROSOFT':'MSFT', 'GOOGLE':'GOOGL', 'ALPHABET':'GOOGL',
    'AMAZON':'AMZN', 'TESLA':'TSLA', 'NVIDIA':'NVDA', 'META':'META',
    'FACEBOOK':'META', 'NETFLIX':'NFLX', 'UBER':'UBER', 'AMD':'AMD',
    'INTEL':'INTC', 'DISNEY':'DIS', 'SPOTIFY':'SPOT', 'ADOBE':'ADBE',
    'SALESFORCE':'CRM', 'PAYPAL':'PYPL', 'SHOPIFY':'SHOP',
    'BERKSHIRE':'BRK.B', 'JP MORGAN':'JPM', 'JPMORGAN':'JPM',
    'GOLDMAN':'GS', 'VISA':'V', 'MASTERCARD':'MA',
    'COCA COLA':'KO', 'COCA-COLA':'KO', 'COKE':'KO',
    'PEPSICO':'PEP', 'PEPSI':'PEP', 'WALMART':'WMT',
    'NIKE':'NKE', 'STARBUCKS':'SBUX', 'MCDONALDS':'MCD',
    "MCDONALD'S":'MCD', 'BOEING':'BA', 'IBM':'IBM',
    'ORACLE':'ORCL', 'QUALCOMM':'QCOM', 'CISCO':'CSCO',
    'EXXON':'XOM', 'CHEVRON':'CVX', 'PFIZER':'PFE',
    'JOHNSON':'JNJ', 'PROCTER':'PG', 'COSTCO':'COST',
    'HOME DEPOT':'HD', 'TARGET':'TGT', 'FORD':'F',
    'GENERAL MOTORS':'GM', 'SAMSUNG':'005930.KS',
    'TWITTER':'X', 'AIRBNB':'ABNB', 'PALANTIR':'PLTR',
    'SNAPCHAT':'SNAP', 'SNAP':'SNAP', 'ZOOM':'ZM',
    'ROBINHOOD':'HOOD', 'COINBASE':'COIN', 'RIVIAN':'RIVN',
    'LUCID':'LCID', 'MICRON':'MU', 'BROADCOM':'AVGO',
    'STARLINK':'TSLA', 'SPACEX':'TSLA',
}

def extract_symbol(msg):
    up = msg.upper()
    # Sort by length descending so multi-word names match before short ones
    for name in sorted(KNOWN_COMPANIES.keys(), key=len, reverse=True):
        if name in up:
            return KNOWN_COMPANIES[name]
    skip = {'WHAT','SHOW','TELL','GIVE','WILL','SHOULD','ABOUT','PRICE','STOCK',
            'BUY','SELL','HOLD','THE','AND','FOR','WITH','THIS','THAT','NEXT',
            'DAYS','LAST','NEWS','DATA','INFO','GET','ME','IS','IN','OF','AT',
            'HOW','ANY','TODAY','WEEK','MONTH','YEAR','MARKET','WORTH','VALUE',
            'GOOD','BAD','VS','COMPARE','VERSUS','OR','BE','DO','SO','TO','BY',
            'CAN','MAY','ARE','WAS','WERE'}
    # Only trust an ALL-CAPS standalone token in the ORIGINAL (non-uppercased)
    # message as a ticker guess — prevents random short words like "be" from
    # matching after .upper().
    for word in msg.split():
        c = ''.join(x for x in word if x.isalpha())
        if 2 <= len(c) <= 5 and word.isupper() and c.upper() not in skip:
            return c.upper()
    return None


def extract_all_symbols(msg):
    """Detect multiple companies/tickers mentioned in one message (for compare-style queries)."""
    up = msg.upper()
    found = []
    for name in sorted(KNOWN_COMPANIES.keys(), key=len, reverse=True):
        if name in up:
            sym = KNOWN_COMPANIES[name]
            if sym not in found:
                found.append(sym)
    if len(found) >= 2:
        return found[:2]
    return None


# ── API ROUTES ────────────────────────────────────────────────────────────────

@app.route('/api/ticker')
def ticker_api():
    sym = request.args.get('symbol', '').upper()
    if not sym:
        return jsonify({'error': 'no symbol'}), 400
    p = get_price(sym)
    if p:
        return jsonify({'price': p['price'], 'change': p['change'],
                        'change_pct': p['change_pct']})
    return jsonify({'error': 'no data'}), 404


@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        body = request.get_json(force=True)
        msg  = body.get('message', '').strip()
        if not msg:
            return jsonify({'error': 'empty'}), 400

        multi = extract_all_symbols(msg)
        sym = extract_symbol(msg)
        if not sym:
            return jsonify({
                'response': ('💡 Please mention a stock — e.g. <b>AAPL</b>, '
                             '<b>Tesla</b>, <b>Should I buy NVDA?</b>'),
                'status': 'hint'
            })

        # If two companies were mentioned (e.g. "coca cola and pepsico"),
        # default to showing the FIRST one fully, and hint the second can be compared.
        compare_hint = None
        if multi and len(multi) == 2:
            sym = multi[0]
            compare_hint = multi[1]

        price     = get_price(sym)
        profile   = get_profile(sym)
        metrics   = get_metrics(sym)
        history   = get_history(sym)
        dividends = get_dividends(sym)
        news      = get_news(sym)

        ml   = msg.lower()
        name = profile['name'] if profile else sym

        if not FINNHUB_API_KEY:
            return jsonify({
                'response': ('⚠️ <b>API keys not configured.</b> '
                             'Please set <code>FINNHUB_API_KEY</code> and '
                             '<code>ALPHAVANTAGE_API_KEY</code> in your '
                             'Render environment variables. '
                             'Both are <b>free</b> — see README for links.'),
                'status': 'no_key'
            })

        long_range = any(w in ml for w in ['month', 'months', 'year', 'years', '6 month', 'half year'])

        if long_range:
            ai = (f"For <b>{name} ({sym})</b>, see the <b>30-Day</b> and <b>6-Month</b> estimates "
                  f"in the AI Price Prediction section below. These are rough trend-based "
                  f"extrapolations from the last 10 days of data — "
                  f"<b>long-range forecasts like this carry low confidence</b> since real "
                  f"prices are driven by earnings, news, and macro events this simple model "
                  f"can't see. <b>This is NOT financial advice.</b>")
        elif 'buy' in ml or 'should' in ml:
            ai = (f"Based on current data, {name} ({sym}) is trading at "
                  f"${price['price'] if price else 'N/A'}. "
                  f"Review the fundamentals and news sentiment below before deciding. "
                  f"<b>This is NOT financial advice.</b>")
        elif compare_hint:
            ai = (f"Showing complete data for <b>{name} ({sym})</b> first. "
                  f"I've pre-filled <b>{compare_hint}</b> in the Compare box below "
                  f"— click Compare to see them side by side.")
        elif 'sell' in ml:
            ai = (f"{name} ({sym}) is currently at "
                  f"${price['price'] if price else 'N/A'}. "
                  f"Check the 10-day trend and sentiment indicators. "
                  f"<b>This is NOT financial advice.</b>")
        elif 'vs' in ml or 'compare' in ml:
            ai = (f"Showing complete data for <b>{name} ({sym})</b>. "
                  f"Use the Compare box below to check it against another ticker.")
        else:
            ai = (f"Complete real-time intelligence report for "
                  f"<b>{name} ({sym})</b> — live price, AI prediction, 10-day chart, "
                  f"fundamentals, news sentiment & dividend history.")

        return jsonify({
            'status':      'success',
            'symbol':      sym,
            'response':    ai,
            'price_data':  price,
            'profile':     profile,
            'metrics':     metrics,
            'chart_data':  history,
            'dividends':   dividends,
            'news':        news,
            'compare_with': compare_hint,
        })

    except Exception as e:
        return jsonify({'error': str(e), 'response': '❌ Server error',
                        'status': 'error'}), 500


@app.route('/api/health')
def health():
    return jsonify({
        'status':       'ok',
        'finnhub':      bool(FINNHUB_API_KEY),
        'alphavantage': bool(ALPHAVANTAGE_API_KEY),
    })


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    print(f"StockAI Terminal starting on port {port}")
    print(f"Finnhub API key:      {'SET ✓' if FINNHUB_API_KEY else 'MISSING ✗'}")
    print(f"AlphaVantage API key: {'SET ✓' if ALPHAVANTAGE_API_KEY else 'MISSING ✗'}")
    app.run(host='0.0.0.0', port=port, debug=False)
    