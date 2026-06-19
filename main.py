"""
StockAI Terminal - IIT Final Project
Professional US Stock Market Intelligence Platform
Fixed version: No Anthropic API needed. Uses Finnhub + AlphaVantage (both free).
"""
from flask import Flask, request, jsonify, Response, send_from_directory
import requests
from datetime import datetime, timedelta
import os
import re

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
    """Returns a dict with 'dates'/'prices' on success, or
    {'error': '<reason>'} when AlphaVantage can't provide data (e.g. daily
    rate limit hit) — distinct from None so callers can tell the two cases
    apart and respond helpfully instead of silently dropping the chart."""
    if not ALPHAVANTAGE_API_KEY:
        return None
    try:
        d = requests.get(
            f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY'
            f'&symbol={sym}&outputsize=compact&apikey={ALPHAVANTAGE_API_KEY}',
            timeout=12).json()
        # AlphaVantage returns these instead of an HTTP error code when the
        # free-tier daily/per-minute quota is exhausted or the call is malformed.
        if 'Note' in d or 'Information' in d:
            return {'error': d.get('Note') or d.get('Information')}
        if 'Error Message' in d:
            return {'error': d.get('Error Message')}
        ts = d.get('Time Series (Daily)', {})
        if not ts:
            return {'error': 'No price history returned for this symbol.'}
        dates = sorted(ts.keys(), reverse=True)[:10]
        dates.reverse()
        return {
            'dates':  [x[5:] for x in dates],
            'prices': [round(float(ts[x]['4. close']), 2) for x in dates],
        }
    except Exception as e:
        return {'error': f'History request failed: {e}'}


def calc_prediction(prices):
    """Simple moving-average / trend model — mirrors the frontend JS so backend
    chat text and the on-screen prediction card always agree with each other."""
    if not prices or len(prices) < 3:
        return None
    n = len(prices)
    sma3 = sum(prices[-3:]) / 3
    sma5 = sum(prices[-5:]) / 5 if n >= 5 else sma3
    recent = prices[-min(5, n):]
    slope = (recent[-1] - recent[0]) / len(recent)
    last = prices[-1]
    pred1   = round(last + slope, 2)
    pred3   = round(last + slope * 3, 2)
    pred7   = round(last + slope * 7, 2)
    # Dampen the slope for longer horizons — a 10-day trend shouldn't be
    # extrapolated at full strength out to 30 days or 6 months.
    pred30  = round(last + slope * 0.6 * 30, 2)
    pred180 = round(last + slope * 0.25 * 180, 2)
    trend = 'Bullish' if slope > 0.5 else ('Bearish' if slope < -0.5 else 'Neutral')
    gains = losses = 0.0
    for i in range(1, n):
        diff = prices[i] - prices[i - 1]
        if diff > 0:
            gains += diff
        else:
            losses += abs(diff)
    rs = 100 if losses == 0 else gains / losses
    rsi = round(100 - (100 / (1 + rs)), 1)
    return {
        'pred1': pred1, 'pred3': pred3, 'pred7': pred7,
        'pred30': pred30, 'pred180': pred180,
        'trend': trend, 'sma3': round(sma3, 2), 'sma5': round(sma5, 2),
        'rsi': rsi, 'slope': round(slope, 2),
    }


def calc_signal(pred, current_price, target_price, news_list):
    """Produce a simple Buy / Hold / Sell style suggestion for a given time
    horizon, combining: (1) projected % move to the target price, (2) RSI
    overbought/oversold zone, (3) trend direction, (4) news sentiment mix.
    This is a rule-based heuristic for an educational project — NOT a real
    trading signal."""
    if not pred or not current_price or not target_price:
        return None

    pct_move = ((target_price - current_price) / current_price) * 100
    score = 0

    # 1. Projected move contributes the most weight
    if pct_move > 5:
        score += 2
    elif pct_move > 1.5:
        score += 1
    elif pct_move < -5:
        score -= 2
    elif pct_move < -1.5:
        score -= 1

    # 2. RSI — overbought (>70) leans against buying more; oversold (<30) leans toward buying
    rsi = pred.get('rsi', 50)
    if rsi < 30:
        score += 1
    elif rsi > 70:
        score -= 1

    # 3. Trend direction
    if pred.get('trend') == 'Bullish':
        score += 1
    elif pred.get('trend') == 'Bearish':
        score -= 1

    # 4. News sentiment mix (if available)
    if news_list:
        pos = sum(1 for x in news_list if x.get('sentiment') == 'Positive')
        neg = sum(1 for x in news_list if x.get('sentiment') == 'Negative')
        if pos > neg + 1:
            score += 1
        elif neg > pos + 1:
            score -= 1

    if score >= 3:
        label, color = 'BUY', 'green'
    elif score >= 1:
        label, color = 'WEAK BUY', 'green'
    elif score <= -3:
        label, color = 'SELL', 'red'
    elif score <= -1:
        label, color = 'WEAK SELL', 'red'
    else:
        label, color = 'HOLD', 'yellow'

    return {'label': label, 'color': color, 'score': score, 'pct_move': round(pct_move, 2)}


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

def lookup_symbol_via_api(name_guess):
    """Fallback for companies not in KNOWN_COMPANIES: ask Finnhub's free
    symbol-lookup endpoint to resolve a company name/phrase to a real ticker.
    This is what lets the chatbot answer for ANY company, not just the
    pre-mapped list, without needing a paid LLM API."""
    if not FINNHUB_API_KEY or not name_guess or len(name_guess) < 2:
        return None
    try:
        d = requests.get(
            f'https://finnhub.io/api/v1/search?q={name_guess}&token={FINNHUB_API_KEY}',
            timeout=6).json()
        results = d.get('result', [])
        # Prefer "Common Stock" results on major US exchanges over warrants/ETFs/etc.
        for r in results:
            sym = r.get('symbol', '')
            if r.get('type') == 'Common Stock' and '.' not in sym and sym.isascii():
                return sym
        if results:
            return results[0].get('symbol')
    except Exception:
        pass
    return None


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
            'CAN','MAY','ARE','WAS','WERE','MONTHS','YEARS','PLEASE','PREDICT',
            'PREDICTION','FUTURE','CURRENT','NOW','GO','UP','DOWN','RATING',
            'ANALYSIS','REPORT','INVEST','INVESTING','SHARES','SHARE',
            'I','A','AN','ON','DOING','MY','YOUR','IT','ITS','AS','IF','WE',
            'YOU','THEY','THEIR','OUR','MIGHT','WOULD','COULD','DOES','DID',
            'HAS','HAVE','HAD','ALSO','JUST','LIKE','OK','OKAY','PLZ','PLS',
            'KINDLY','LOOKING','LOOK','CHECK','FIND','SEARCH','OPINION',
            'THINK','THOUGHT','GOING','TODAY','RIGHT','NOW','OVER','WITHIN'}

    # Only trust an ALL-CAPS standalone token in the ORIGINAL (non-uppercased)
    # message as a ticker guess — prevents random short words like "be" from
    # matching after .upper().
    for word in msg.split():
        c = ''.join(x for x in word if x.isalpha())
        if 2 <= len(c) <= 5 and word.isupper() and c.upper() not in skip:
            return c.upper()

    # Generic company-name resolution: strip question/filler words, then try
    # the remaining run of words as ONE phrase against Finnhub's live symbol
    # search. This handles multi-word companies not in KNOWN_COMPANIES, e.g.
    # "Bank of America", "American Express", "Berkshire Hathaway", etc.
    raw_words = re.findall(r"[A-Za-z][A-Za-z&.\-']*", msg)
    meaningful = [w for w in raw_words if w.upper() not in skip]
    if meaningful:
        phrase = ' '.join(meaningful)
        looked_up = lookup_symbol_via_api(phrase)
        if looked_up:
            return looked_up
        # Phrase search found nothing — try the longest individual word as a
        # fallback (handles single, slightly-misspelled, or unusual names).
        guess = max(meaningful, key=len)
        if guess.lower() != phrase.lower():
            looked_up = lookup_symbol_via_api(guess)
            if looked_up:
                return looked_up

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

        price        = get_price(sym)
        profile      = get_profile(sym)
        metrics      = get_metrics(sym)
        history_raw  = get_history(sym)
        dividends    = get_dividends(sym)
        news         = get_news(sym)

        history_error = None
        history = None
        if history_raw and 'error' in history_raw:
            history_error = history_raw['error']
        elif history_raw:
            history = history_raw

        pred = calc_prediction(history['prices']) if history else None

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

        # Detect an explicit horizon in the question: "180 days", "6 months", "1 year"
        horizon_days = None
        m_days = re.search(r'(\d+)\s*day', ml)
        m_months = re.search(r'(\d+)\s*month', ml)
        m_years = re.search(r'(\d+)\s*year', ml)
        if m_days:
            horizon_days = int(m_days.group(1))
        elif m_months:
            horizon_days = int(m_months.group(1)) * 30
        elif m_years:
            horizon_days = int(m_years.group(1)) * 365
        elif 'next year' in ml:
            horizon_days = 365
        elif '6 month' in ml or 'half year' in ml or 'half-year' in ml:
            horizon_days = 180

        long_range = horizon_days is not None or any(
            w in ml for w in ['month', 'months', 'year', 'years'])

        # Always compute a default short-term (7-day) signal for the response
        # card, regardless of which text branch ends up being used below.
        default_signal = (calc_signal(pred, price['price'], pred['pred7'], news)
                           if (pred and price) else None)
        response_signal = default_signal

        if long_range and history_error:
            ai = (f"I can't generate a price prediction for <b>{name} ({sym})</b> right now — "
                  f"the price-history data provider returned: "
                  f"<i>\"{history_error}\"</i>. "
                  f"This usually means the free AlphaVantage API's <b>daily request limit "
                  f"(25 calls/day) has been reached</b> from repeated testing. "
                  f"It resets automatically after 24 hours, or you can use a fresh "
                  f"AlphaVantage API key. Live price and fundamentals below are still "
                  f"accurate since they come from a separate provider (Finnhub).")
        elif long_range and pred and price:
            # Pick the closest pre-computed estimate to the requested horizon,
            # then build a wider sentiment-based RANGE around it (not a single
            # point estimate) so the answer reads like a realistic forecast band.
            if horizon_days is None:
                horizon_days = 180
            if horizon_days <= 1:
                point = pred['pred1']
            elif horizon_days <= 3:
                point = pred['pred3']
            elif horizon_days <= 7:
                point = pred['pred7']
            elif horizon_days <= 30:
                point = pred['pred30']
            else:
                point = pred['pred180']

            # Widen the band further out in time — short horizons stay tight,
            # long horizons (6mo/1yr) get a noticeably wider, more honest range.
            spread_pct = min(0.04 + (horizon_days / 365) * 0.18, 0.22)
            low  = round(point * (1 - spread_pct), 2)
            high = round(point * (1 + spread_pct), 2)
            if low > high:
                low, high = high, low

            horizon_label = (f"{horizon_days} days" if horizon_days < 60
                              else f"{round(horizon_days/30)} months" if horizon_days < 400
                              else f"{round(horizon_days/365,1)} years")

            signal = calc_signal(pred, price['price'], point, news)
            response_signal = signal
            sig_html = ''
            if signal:
                sig_html = (f" Based on the projected move, RSI, trend, and news sentiment, "
                             f"the suggestion for this horizon is "
                             f"<b style='color:var(--{signal['color']})'>{signal['label']}</b>.")

            ai = (f"As per current market sentiment, <b>{name} ({sym})</b> stock price in the "
                  f"next {horizon_label} will likely be approx "
                  f"<b>${low} to ${high}</b> "
                  f"(trend: <b>{pred['trend']}</b>).{sig_html} "
                  f"This is a rough estimate from a simple moving-average model on the last "
                  f"10 days of data — <b>confidence drops sharply over longer horizons</b> "
                  f"since real prices are driven by earnings, news, and macro events this "
                  f"model can't see. See the AI Price Prediction section below for the full "
                  f"breakdown. <b>This is NOT financial advice.</b>")
        elif 'buy' in ml or 'should' in ml or 'sell' in ml:
            # Default to the 7-day horizon when no explicit timeframe is given
            target = pred['pred7'] if pred else None
            signal = calc_signal(pred, price['price'], target, news) if (pred and price) else None
            response_signal = signal
            sig_html = ''
            if signal:
                sig_html = (f" My short-term (7-day) suggestion is "
                             f"<b style='color:var(--{signal['color']})'>{signal['label']}</b>, "
                             f"based on trend, RSI, projected move, and news sentiment.")
            ai = (f"{name} ({sym}) is currently trading at "
                  f"${price['price'] if price else 'N/A'}.{sig_html} "
                  f"Review the fundamentals and news sentiment below before deciding. "
                  f"<b>This is NOT financial advice.</b>")
        elif compare_hint:
            ai = (f"Showing complete data for <b>{name} ({sym})</b> first. "
                  f"I've pre-filled <b>{compare_hint}</b> in the Compare box below "
                  f"— click Compare to see them side by side.")
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
            'signal':      response_signal,
            'dividends':   dividends,
            'news':        news,
            'compare_with': compare_hint,
            'history_error': history_error,
            'prediction':  pred,
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