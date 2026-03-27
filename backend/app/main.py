from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.db.init_db import init_db
from app.middleware.rate_limit import RateLimitMiddleware


app = FastAPI(title="AI Narrative & Sentiment Investing Platform", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Inner layer (runs after CORS on the way in) — 429 responses still get CORS headers.
app.add_middleware(RateLimitMiddleware)


# Dev/internal bootstrap: permanent admin test account (change/remove for production).
_ADMIN_EMAIL = "admin@internal.test"
_ADMIN_PASSWORD = "admin"


@app.on_event("startup")
def _startup() -> None:
    init_db()
    _seed_admin_if_missing()
    # Seed instruments whenever the table is empty (safe in all envs)
    _seed_instruments_if_empty()
    _ensure_local_instruments()
    # Warm market quote snapshots asynchronously (Celery also runs on a schedule)
    try:
        from app.worker.tasks import refresh_market_quotes

        refresh_market_quotes.delay()
    except Exception:
        pass


def _seed_admin_if_missing() -> None:
    """Create admin username / admin@internal.test with password 'admin' if missing. Idempotent, dev bootstrap only."""
    from sqlalchemy import select
    from app.core.security import hash_password
    from app.db.session import SessionLocal
    from app.models.user import User

    db = SessionLocal()
    try:
        existing = db.scalar(select(User).where(User.username == "admin"))
        if existing:
            if not getattr(existing, "is_admin", False):
                existing.is_admin = True
                db.commit()
            return
        user = User(
            username="admin",
            email=_ADMIN_EMAIL,
            password_hash=hash_password(_ADMIN_PASSWORD),
            credits_balance=100_000,
            is_admin=True,
        )
        db.add(user)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _seed_instruments_if_empty() -> None:
    from sqlalchemy import select
    from app.db.session import SessionLocal
    from app.models.portfolio import Instrument
    db = SessionLocal()
    try:
        if db.scalar(select(Instrument).limit(1)) is None:
            samples = [
                # Equities
                ("OKLO", "Oklo Inc.", "equity", "US", "NASDAQ", "USD"),
                ("NVDA", "NVIDIA Corporation", "equity", "US", "NASDAQ", "USD"),
                ("TSLA", "Tesla Inc.", "equity", "US", "NASDAQ", "USD"),
                # Crypto
                ("BTC", "Bitcoin", "crypto", "CRYPTO", None, "USD"),
                ("ETH", "Ethereum", "crypto", "CRYPTO", None, "USD"),
                # Forex
                ("EURUSD", "Euro / US Dollar", "forex", "FX", None, "USD"),
                # Futures (Crude oil)
                ("CL", "Crude Oil Futures", "futures", "NYMEX", None, "USD"),
                # Gold / precious metals
                ("XAUUSD", "Gold Spot", "commodity_spot", "FX", None, "USD"),
                ("GLD", "SPDR Gold Shares", "etf", "US", "NYSE Arca", "USD"),
                # Index
                ("SPX", "S&P 500 Index", "index", "US", None, "USD"),
            ]
            for sym, name, ac, market, exchange, currency in samples:
                db.add(
                    Instrument(
                        symbol=sym,
                        display_name=name,
                        asset_class=ac,
                        market=market,
                        exchange=exchange,
                        currency=currency,
                    )
                )
            db.commit()
    finally:
        db.close()


def _ensure_local_instruments() -> None:
    """
    Ensure a richer set of common instruments exists locally.

    Safe and idempotent: checks for existing symbol+asset_class+exchange before inserting.
    Does not touch existing rows or external providers.
    """
    import logging
    from sqlalchemy import and_, func, select
    from app.db.session import SessionLocal
    from app.models.portfolio import Instrument

    logger = logging.getLogger(__name__)

    # symbol, name, description, asset_class, market, exchange, country, currency
    LOCAL_INSTRUMENTS = [
        # US stocks & ETFs (subset to keep seed small but useful)
        ("AAPL", "Apple Inc.", "AAPL — Apple Inc., US large-cap tech stock listed on NASDAQ", "equity", "US", "NASDAQ", "US", "USD"),
        ("MSFT", "Microsoft Corporation", "MSFT — Microsoft Corporation, US software & cloud stock listed on NASDAQ", "equity", "US", "NASDAQ", "US", "USD"),
        ("NVDA", "NVIDIA Corporation", "NVDA — NVIDIA, US semiconductor and GPU stock listed on NASDAQ", "equity", "US", "NASDAQ", "US", "USD"),
        ("AMD", "Advanced Micro Devices", "AMD — Advanced Micro Devices, US semiconductor stock listed on NASDAQ", "equity", "US", "NASDAQ", "US", "USD"),
        ("TSLA", "Tesla Inc.", "TSLA — Tesla, US electric vehicle and energy stock listed on NASDAQ", "equity", "US", "NASDAQ", "US", "USD"),
        ("META", "Meta Platforms Inc.", "META — Meta Platforms, US social media and advertising stock listed on NASDAQ", "equity", "US", "NASDAQ", "US", "USD"),
        ("GOOGL", "Alphabet Inc. Class A", "GOOGL — Alphabet Class A, US search and cloud stock listed on NASDAQ", "equity", "US", "NASDAQ", "US", "USD"),
        ("AMZN", "Amazon.com Inc.", "AMZN — Amazon.com, US e-commerce and cloud stock listed on NASDAQ", "equity", "US", "NASDAQ", "US", "USD"),
        ("AVGO", "Broadcom Inc.", "AVGO — Broadcom, US semiconductor and infrastructure software stock listed on NASDAQ", "equity", "US", "NASDAQ", "US", "USD"),
        ("ORCL", "Oracle Corporation", "ORCL — Oracle, US enterprise software and database stock listed on NYSE", "equity", "US", "NYSE", "US", "USD"),
        ("JPM", "JPMorgan Chase & Co.", "JPM — JPMorgan Chase, US money-center bank listed on NYSE", "equity", "US", "NYSE", "US", "USD"),
        ("GS", "Goldman Sachs Group Inc.", "GS — Goldman Sachs, US investment bank listed on NYSE", "equity", "US", "NYSE", "US", "USD"),
        ("MS", "Morgan Stanley", "MS — Morgan Stanley, US investment bank listed on NYSE", "equity", "US", "NYSE", "US", "USD"),
        ("BAC", "Bank of America Corporation", "BAC — Bank of America, US diversified bank listed on NYSE", "equity", "US", "NYSE", "US", "USD"),
        ("WFC", "Wells Fargo & Company", "WFC — Wells Fargo, US bank listed on NYSE", "equity", "US", "NYSE", "US", "USD"),
        ("XOM", "Exxon Mobil Corporation", "XOM — Exxon Mobil, US integrated oil & gas stock listed on NYSE", "equity", "US", "NYSE", "US", "USD"),
        ("CVX", "Chevron Corporation", "CVX — Chevron, US integrated oil & gas stock listed on NYSE", "equity", "US", "NYSE", "US", "USD"),
        ("UNH", "UnitedHealth Group Incorporated", "UNH — UnitedHealth, US managed care stock listed on NYSE", "equity", "US", "NYSE", "US", "USD"),
        ("JNJ", "Johnson & Johnson", "JNJ — Johnson & Johnson, US diversified healthcare stock listed on NYSE", "equity", "US", "NYSE", "US", "USD"),
        ("PFE", "Pfizer Inc.", "PFE — Pfizer, US pharmaceuticals stock listed on NYSE", "equity", "US", "NYSE", "US", "USD"),
        ("MRK", "Merck & Co., Inc.", "MRK — Merck, US pharmaceuticals stock listed on NYSE", "equity", "US", "NYSE", "US", "USD"),
        ("HD", "Home Depot Inc.", "HD — Home Depot, US home improvement retail stock listed on NYSE", "equity", "US", "NYSE", "US", "USD"),
        ("COST", "Costco Wholesale Corporation", "COST — Costco, US warehouse club retailer stock listed on NASDAQ", "equity", "US", "NASDAQ", "US", "USD"),
        ("WMT", "Walmart Inc.", "WMT — Walmart, US big-box retail stock listed on NYSE", "equity", "US", "NYSE", "US", "USD"),
        ("KO", "Coca-Cola Company", "KO — Coca-Cola, US beverage stock listed on NYSE", "equity", "US", "NYSE", "US", "USD"),
        ("PEP", "PepsiCo, Inc.", "PEP — PepsiCo, US beverage and snacks stock listed on NASDAQ", "equity", "US", "NASDAQ", "US", "USD"),
        ("NFLX", "Netflix Inc.", "NFLX — Netflix, US streaming media stock listed on NASDAQ", "equity", "US", "NASDAQ", "US", "USD"),
        ("DIS", "Walt Disney Company", "DIS — Walt Disney, US media and entertainment stock listed on NYSE", "equity", "US", "NYSE", "US", "USD"),
        ("INTC", "Intel Corporation", "INTC — Intel, US semiconductor stock listed on NASDAQ", "equity", "US", "NASDAQ", "US", "USD"),
        ("QCOM", "QUALCOMM Incorporated", "QCOM — Qualcomm, US wireless semiconductor stock listed on NASDAQ", "equity", "US", "NASDAQ", "US", "USD"),
        ("PLTR", "Palantir Technologies Inc.", "PLTR — Palantir, US data analytics software stock listed on NYSE", "equity", "US", "NYSE", "US", "USD"),
        ("SNOW", "Snowflake Inc.", "SNOW — Snowflake, US cloud data platform stock listed on NYSE", "equity", "US", "NYSE", "US", "USD"),
        ("NET", "Cloudflare, Inc.", "NET — Cloudflare, US edge network & security stock listed on NYSE", "equity", "US", "NYSE", "US", "USD"),
        ("UBER", "Uber Technologies Inc.", "UBER — Uber, US ride-hailing and delivery stock listed on NYSE", "equity", "US", "NYSE", "US", "USD"),
        ("DASH", "DoorDash Inc.", "DASH — DoorDash, US food delivery platform stock listed on NYSE", "equity", "US", "NYSE", "US", "USD"),
        ("CCJ", "Cameco Corporation", "CCJ — Cameco, Canadian uranium producer stock listed on NYSE", "equity", "US", "NYSE", "CA", "USD"),
        ("NNE", "Nano Nuclear Energy Inc.", "NNE — Nano Nuclear Energy, US advanced nuclear technology stock listed on NASDAQ", "equity", "US", "NASDAQ", "US", "USD"),
        ("OKLO", "Oklo Inc.", "OKLO — Oklo, US advanced nuclear fission startup stock listed on NYSE American", "equity", "US", "NYSE American", "US", "USD"),
        ("ENPH", "Enphase Energy, Inc.", "ENPH — Enphase, US residential solar inverter stock listed on NASDAQ", "equity", "US", "NASDAQ", "US", "USD"),
        ("FSLR", "First Solar, Inc.", "FSLR — First Solar, US utility-scale solar panel stock listed on NASDAQ", "equity", "US", "NASDAQ", "US", "USD"),
        ("RUN", "Sunrun Inc.", "RUN — Sunrun, US residential solar leasing stock listed on NASDAQ", "equity", "US", "NASDAQ", "US", "USD"),
        ("CAT", "Caterpillar Inc.", "CAT — Caterpillar, US heavy machinery stock listed on NYSE", "equity", "US", "NYSE", "US", "USD"),
        ("DE", "Deere & Company", "DE — Deere, US agricultural machinery stock listed on NYSE", "equity", "US", "NYSE", "US", "USD"),
        ("BA", "Boeing Company", "BA — Boeing, US aerospace manufacturer stock listed on NYSE", "equity", "US", "NYSE", "US", "USD"),
        ("LMT", "Lockheed Martin Corporation", "LMT — Lockheed Martin, US defense contractor stock listed on NYSE", "equity", "US", "NYSE", "US", "USD"),
        ("SPY", "SPDR S&P 500 ETF Trust", "SPY — S&P 500 ETF tracking US large-cap index, listed on NYSE Arca", "etf", "US", "NYSE Arca", "US", "USD"),
        ("QQQ", "Invesco QQQ Trust", "QQQ — ETF tracking the NASDAQ-100 index, listed on NASDAQ", "etf", "US", "NASDAQ", "US", "USD"),
        # Indices
        ("SPX", "S&P 500 Index", "SPX — S&P 500 index of 500 large US companies", "index", "US", None, "US", "USD"),
        ("NDX", "NASDAQ 100 Index", "NDX — NASDAQ 100 index of large non-financial NASDAQ-listed companies", "index", "US", None, "US", "USD"),
        ("DJI", "Dow Jones Industrial Average", "DJI — Dow Jones Industrial Average of 30 US blue-chip stocks", "index", "US", None, "US", "USD"),
        ("VIX", "CBOE Volatility Index", "VIX — CBOE S&P 500 implied volatility index", "index", "US", None, "US", "USD"),
        ("HS300", "CSI 300 Index", "HS300 — CSI 300 index of 300 A-shares listed in Shanghai and Shenzhen", "index", "CN", None, "CN", "CNY"),
        ("SSE", "Shanghai Composite Index", "SSE — Shanghai Composite index of A-shares listed on the Shanghai Stock Exchange", "index", "CN", "SSE", "CN", "CNY"),
        ("SZSE", "Shenzhen Component Index", "SZSE — Shenzhen Component index of A-shares listed on SZSE", "index", "CN", "SZSE", "CN", "CNY"),
        ("STAR50", "STAR 50 Index", "STAR50 — STAR Market 50 index of large tech-focused A-shares listed in Shanghai (STAR Market)", "index", "CN", "SSE", "CN", "CNY"),
        ("CHINEXT", "ChiNext Index", "CHINEXT — ChiNext index of growth-oriented A-shares listed in Shenzhen (ChiNext)", "index", "CN", "SZSE", "CN", "CNY"),
        ("EUROSTOXX50", "EURO STOXX 50 Index", "EUROSTOXX50 — Eurozone blue-chip equity index of 50 large companies", "index", "EU", None, "EU", "EUR"),
        # Futures
        ("ES", "E-mini S&P 500 Futures", "ES — CME E-mini S&P 500 futures contract family", "futures", "US", "CME", "US", "USD"),
        ("NQ", "E-mini NASDAQ 100 Futures", "NQ — CME E-mini NASDAQ 100 futures contract family", "futures", "US", "CME", "US", "USD"),
        ("YM", "E-mini Dow Jones Futures", "YM — CBOT E-mini Dow Jones Industrial Average futures contract family", "futures", "US", "CBOT", "US", "USD"),
        ("CL", "Crude Oil Futures", "CL — NYMEX WTI crude oil futures contract family", "futures", "US", "NYMEX", "US", "USD"),
        ("GC", "Gold Futures", "GC — COMEX gold futures contract family", "futures", "US", "COMEX", "US", "USD"),
        ("SI", "Silver Futures", "SI — COMEX silver futures contract family", "futures", "US", "COMEX", "US", "USD"),
        # Crypto
        ("BTC", "Bitcoin", "BTC — Bitcoin, leading proof-of-work crypto asset", "crypto", "CRYPTO", None, "Global", "USD"),
        ("ETH", "Ethereum", "ETH — Ethereum, smart contract platform crypto asset", "crypto", "CRYPTO", None, "Global", "USD"),
        # Europe (selected)
        ("ASML", "ASML Holding N.V.", "ASML — ASML, Dutch lithography equipment maker listed on Euronext Amsterdam", "equity", "NL", "EURONEXT", "NL", "EUR"),
        ("SAP", "SAP SE", "SAP — SAP, German enterprise software company listed in Frankfurt", "equity", "DE", "XETRA", "DE", "EUR"),
        ("MC.PA", "LVMH Moet Hennessy Louis Vuitton SE", "MC.PA — LVMH, French luxury conglomerate A-share in Paris", "equity", "FR", "EPA", "FR", "EUR"),
        ("OR.PA", "L'Oréal S.A.", "OR.PA — L'Oréal, French cosmetics company listed in Paris", "equity", "FR", "EPA", "FR", "EUR"),
        ("TTE.PA", "TotalEnergies SE", "TTE.PA — TotalEnergies, French integrated oil & gas company listed in Paris", "equity", "FR", "EPA", "FR", "EUR"),
        ("AIR.PA", "Airbus SE", "AIR.PA — Airbus, European aircraft manufacturer listed in Paris", "equity", "FR", "EPA", "FR", "EUR"),
        ("BNP.PA", "BNP Paribas SA", "BNP.PA — BNP Paribas, French universal bank listed in Paris", "equity", "FR", "EPA", "FR", "EUR"),
        ("SIE.DE", "Siemens AG", "SIE.DE — Siemens, German industrial conglomerate listed in Frankfurt", "equity", "DE", "XETRA", "DE", "EUR"),
        ("ALV.DE", "Allianz SE", "ALV.DE — Allianz, German insurance group listed in Frankfurt", "equity", "DE", "XETRA", "DE", "EUR"),
        ("BAS.DE", "BASF SE", "BAS.DE — BASF, German chemicals company listed in Frankfurt", "equity", "DE", "XETRA", "DE", "EUR"),
        ("BMW.DE", "Bayerische Motoren Werke AG", "BMW.DE — BMW, German premium auto manufacturer listed in Frankfurt", "equity", "DE", "XETRA", "DE", "EUR"),
        ("MBG.DE", "Mercedes-Benz Group AG", "MBG.DE — Mercedes-Benz, German premium auto manufacturer listed in Frankfurt", "equity", "DE", "XETRA", "DE", "EUR"),
        ("VOW3.DE", "Volkswagen AG Pref", "VOW3.DE — Volkswagen preference shares, German automaker listed in Frankfurt", "equity", "DE", "XETRA", "DE", "EUR"),
        ("SAN.PA", "Sanofi SA", "SAN.PA — Sanofi, French pharmaceutical company listed in Paris", "equity", "FR", "EPA", "FR", "EUR"),
        ("DG.PA", "Vinci SA", "DG.PA — Vinci, French concessions and construction group listed in Paris", "equity", "FR", "EPA", "FR", "EUR"),
        ("ADS.DE", "adidas AG", "ADS.DE — adidas, German sportswear company listed in Frankfurt", "equity", "DE", "XETRA", "DE", "EUR"),
        ("RACE.MI", "Ferrari N.V.", "RACE.MI — Ferrari, Italian luxury sports car maker listed in Milan", "equity", "IT", "MIL", "IT", "EUR"),
        ("RIO.L", "Rio Tinto plc", "RIO.L — Rio Tinto, UK-listed diversified mining group on LSE", "equity", "GB", "LSE", "GB", "GBP"),
        ("BP.L", "BP p.l.c.", "BP.L — BP, UK integrated oil & gas company listed on LSE", "equity", "GB", "LSE", "GB", "GBP"),
        ("SHEL.L", "Shell plc", "SHEL.L — Shell, UK-headquartered energy company listed on LSE", "equity", "GB", "LSE", "GB", "GBP"),
        ("AZN.L", "AstraZeneca plc", "AZN.L — AstraZeneca, UK pharmaceuticals company listed on LSE", "equity", "GB", "LSE", "GB", "GBP"),
        ("HSBA.L", "HSBC Holdings plc", "HSBA.L — HSBC, global bank headquartered in London and listed on LSE", "equity", "GB", "LSE", "GB", "GBP"),
        ("NESN.SW", "Nestlé S.A.", "NESN.SW — Nestlé, Swiss food and beverage company listed on SIX", "equity", "CH", "SIX", "CH", "CHF"),
        ("NOVN.SW", "Novartis AG", "NOVN.SW — Novartis, Swiss pharmaceuticals company listed on SIX", "equity", "CH", "SIX", "CH", "CHF"),
        ("UBSG.SW", "UBS Group AG", "UBSG.SW — UBS, Swiss banking group listed on SIX", "equity", "CH", "SIX", "CH", "CHF"),
        ("ENEL.MI", "Enel S.p.A.", "ENEL.MI — Enel, Italian utility and renewables group listed in Milan", "equity", "IT", "MIL", "IT", "EUR"),
        ("ISP.MI", "Intesa Sanpaolo S.p.A.", "ISP.MI — Intesa Sanpaolo, major Italian bank listed in Milan", "equity", "IT", "MIL", "IT", "EUR"),
        ("DTE.DE", "Deutsche Telekom AG", "DTE.DE — Deutsche Telekom, German telecom company listed in Frankfurt (XETRA)", "equity", "DE", "XETRA", "DE", "EUR"),
        ("CS.PA", "AXA SA", "CS.PA — AXA, French insurance group listed in Paris", "equity", "FR", "EPA", "FR", "EUR"),
        ("RMS.PA", "Hermès International SCA", "RMS.PA — Hermès, French luxury goods company listed in Paris", "equity", "FR", "EPA", "FR", "EUR"),
        # China A-shares (subset)
        ("600519.SH", "Kweichow Moutai Co., Ltd.", "600519.SH — Kweichow Moutai A-share listed on Shanghai Stock Exchange", "equity", "CN", "SH", "CN", "CNY"),
        ("000858.SZ", "Wuliangye Yibin Co., Ltd.", "000858.SZ — Wuliangye Yibin A-share listed on Shenzhen Stock Exchange", "equity", "CN", "SZ", "CN", "CNY"),
        ("601318.SH", "Ping An Insurance (Group) Company of China, Ltd.", "601318.SH — Ping An Insurance A-share listed in Shanghai", "equity", "CN", "SH", "CN", "CNY"),
        ("600036.SH", "China Merchants Bank Co., Ltd.", "600036.SH — China Merchants Bank A-share listed in Shanghai", "equity", "CN", "SH", "CN", "CNY"),
        ("601166.SH", "Industrial Bank Co., Ltd.", "601166.SH — Industrial Bank A-share listed in Shanghai", "equity", "CN", "SH", "CN", "CNY"),
        ("600276.SH", "Jiangsu Hengrui Pharmaceuticals Co., Ltd.", "600276.SH — Hengrui Pharma A-share listed in Shanghai", "equity", "CN", "SH", "CN", "CNY"),
        ("002594.SZ", "BYD Company Limited", "002594.SZ — BYD, Chinese EV and battery maker A-share listed in Shenzhen", "equity", "CN", "SZ", "CN", "CNY"),
        ("300750.SZ", "Contemporary Amperex Technology Co., Limited", "300750.SZ — CATL, Chinese EV battery leader A-share listed in Shenzhen", "equity", "CN", "SZ", "CN", "CNY"),
        ("600900.SH", "China Yangtze Power Co., Ltd.", "600900.SH — China Yangtze Power A-share listed in Shanghai", "equity", "CN", "SH", "CN", "CNY"),
        ("601899.SH", "Zijin Mining Group Co., Ltd.", "601899.SH — Zijin Mining A-share listed in Shanghai", "equity", "CN", "SH", "CN", "CNY"),
        ("600030.SH", "CITIC Securities Co., Ltd.", "600030.SH — CITIC Securities A-share listed on Shanghai Stock Exchange", "equity", "CN", "SH", "CN", "CNY"),
        ("000001.SZ", "Ping An Bank Co., Ltd.", "000001.SZ — Ping An Bank A-share listed on Shenzhen Stock Exchange", "equity", "CN", "SZ", "CN", "CNY"),
        ("600104.SH", "SAIC Motor Corporation Limited", "600104.SH — SAIC Motor A-share listed on Shanghai Stock Exchange", "equity", "CN", "SH", "CN", "CNY"),
        ("601888.SH", "China Tourism Group Duty Free Corporation Limited", "601888.SH — China Duty Free A-share listed on Shanghai Stock Exchange", "equity", "CN", "SH", "CN", "CNY"),
        ("002415.SZ", "Hangzhou Hikvision Digital Technology Co., Ltd.", "002415.SZ — Hikvision A-share listed on Shenzhen Stock Exchange", "equity", "CN", "SZ", "CN", "CNY"),
        ("300059.SZ", "East Money Information Co., Ltd.", "300059.SZ — East Money A-share listed on Shenzhen Stock Exchange", "equity", "CN", "SZ", "CN", "CNY"),
        ("600887.SH", "Inner Mongolia Yili Industrial Group Co., Ltd.", "600887.SH — Yili Group A-share listed on Shanghai Stock Exchange", "equity", "CN", "SH", "CN", "CNY"),
        ("600309.SH", "Wanhua Chemical Group Co., Ltd.", "600309.SH — Wanhua Chemical A-share listed on Shanghai Stock Exchange", "equity", "CN", "SH", "CN", "CNY"),
        ("600703.SH", "Sany Heavy Industry Co., Ltd.", "600703.SH — Sany Heavy Industry A-share listed on Shanghai Stock Exchange", "equity", "CN", "SH", "CN", "CNY"),
        ("601012.SH", "LONGi Green Energy Technology Co., Ltd.", "601012.SH — LONGi Green Energy A-share listed on Shanghai Stock Exchange", "equity", "CN", "SH", "CN", "CNY"),
        ("300760.SZ", "Shenzhen Mindray Bio-Medical Electronics Co., Ltd.", "300760.SZ — Mindray A-share listed on Shenzhen Stock Exchange", "equity", "CN", "SZ", "CN", "CNY"),
        ("600031.SH", "Sany Heavy Industry Co., Ltd.", "600031.SH — Sany Heavy Industry A-share listed on Shanghai Stock Exchange", "equity", "CN", "SH", "CN", "CNY"),
        ("600111.SH", "China Northern Rare Earth (Group) High-Tech Co., Ltd.", "600111.SH — China Northern Rare Earth A-share listed on Shanghai Stock Exchange", "equity", "CN", "SH", "CN", "CNY"),
        ("600745.SH", "Wingtech Technology Co., Ltd.", "600745.SH — Wingtech Technology A-share listed on Shanghai Stock Exchange", "equity", "CN", "SH", "CN", "CNY"),
        ("601390.SH", "China Railway Group Limited", "601390.SH — China Railway Group A-share listed on Shanghai Stock Exchange", "equity", "CN", "SH", "CN", "CNY"),
        ("600050.SH", "China United Network Communications Limited", "600050.SH — China Unicom A-share listed on Shanghai Stock Exchange", "equity", "CN", "SH", "CN", "CNY"),
        ("601988.SH", "Bank of China Limited", "601988.SH — Bank of China A-share listed on Shanghai Stock Exchange", "equity", "CN", "SH", "CN", "CNY"),
        ("600028.SH", "China Petroleum & Chemical Corporation", "600028.SH — Sinopec A-share listed on Shanghai Stock Exchange", "equity", "CN", "SH", "CN", "CNY"),
        ("601857.SH", "PetroChina Company Limited", "601857.SH — PetroChina A-share listed on Shanghai Stock Exchange", "equity", "CN", "SH", "CN", "CNY"),
        ("601398.SH", "Industrial and Commercial Bank of China Limited", "601398.SH — ICBC A-share listed on Shanghai Stock Exchange", "equity", "CN", "SH", "CN", "CNY"),
        # Hong Kong (Yahoo format: TICKER.HK)
        ("0700.HK", "Tencent Holdings Limited", "0700.HK — Tencent, Chinese tech conglomerate listed on Hong Kong Stock Exchange", "equity", "HK", "HKEX", "HK", "HKD"),
        ("9988.HK", "Alibaba Group Holding Limited", "9988.HK — Alibaba, Chinese e-commerce and cloud company listed on Hong Kong Stock Exchange", "equity", "HK", "HKEX", "HK", "HKD"),
        ("3690.HK", "Meituan", "3690.HK — Meituan, Chinese delivery and local services platform listed on Hong Kong Stock Exchange", "equity", "HK", "HKEX", "HK", "HKD"),
        ("0941.HK", "China Mobile Limited", "0941.HK — China Mobile, Chinese telecom operator listed on Hong Kong Stock Exchange", "equity", "HK", "HKEX", "HK", "HKD"),
        ("1299.HK", "AIA Group Limited", "1299.HK — AIA, pan-Asian life insurer listed on Hong Kong Stock Exchange", "equity", "HK", "HKEX", "HK", "HKD"),
        ("0388.HK", "Hong Kong Exchanges and Clearing Limited", "0388.HK — HKEX, Hong Kong stock exchange operator listed on its own venue", "equity", "HK", "HKEX", "HK", "HKD"),
        ("2628.HK", "China Life Insurance Company Limited", "2628.HK — China Life, Chinese life insurer listed on Hong Kong Stock Exchange", "equity", "HK", "HKEX", "HK", "HKD"),
        ("2382.HK", "Sunny Optical Technology Group Company Limited", "2382.HK — Sunny Optical, Chinese optical components maker listed on Hong Kong Stock Exchange", "equity", "HK", "HKEX", "HK", "HKD"),
        ("1810.HK", "Xiaomi Corporation", "1810.HK — Xiaomi, Chinese consumer electronics and smart devices company listed on Hong Kong Stock Exchange", "equity", "HK", "HKEX", "HK", "HKD"),
        ("0960.HK", "Longfor Group Holdings Limited", "0960.HK — Longfor, Chinese property developer listed on Hong Kong Stock Exchange", "equity", "HK", "HKEX", "HK", "HKD"),
        ("2318.HK", "Ping An Insurance (Group) Company of China, Ltd.", "2318.HK — Ping An H-share, Chinese insurer listed on Hong Kong Stock Exchange", "equity", "HK", "HKEX", "HK", "HKD"),
        ("1398.HK", "Industrial and Commercial Bank of China Limited", "1398.HK — ICBC H-share, Chinese bank listed on Hong Kong Stock Exchange", "equity", "HK", "HKEX", "HK", "HKD"),
        ("0939.HK", "China Construction Bank Corporation", "0939.HK — CCB H-share, Chinese bank listed on Hong Kong Stock Exchange", "equity", "HK", "HKEX", "HK", "HKD"),
        ("^HSI", "Hang Seng Index", "^HSI — Hang Seng Index, benchmark of Hong Kong listed companies", "index", "HK", "HKEX", "HK", "HKD"),
        ("^HSCEI", "Hang Seng China Enterprises Index", "^HSCEI — HSCEI, H-share index of Chinese companies listed in Hong Kong", "index", "HK", "HKEX", "HK", "HKD"),
    ]

    db = SessionLocal()
    inserted = 0
    skipped = 0
    try:
        for sym, name, desc, ac, market, exchange, country, currency in LOCAL_INSTRUMENTS:
            exists = db.scalar(
                select(Instrument.id).where(
                    and_(
                        Instrument.symbol == sym,
                        Instrument.asset_class == ac,
                        Instrument.exchange.is_(exchange) if exchange is None else Instrument.exchange == exchange,
                    )
                )
            )
            if exists:
                skipped += 1
                continue
            inst = Instrument(
                symbol=sym,
                display_name=name,
                description=desc,
                asset_class=ac,
                market=market,
                exchange=exchange,
                country=country,
                currency=currency,
                provider="local_seed",
                provider_symbol=sym,
                source_priority=10,
            )
            db.add(inst)
            inserted += 1
        db.commit()
        logger.info("Local instruments seed: inserted=%d, existing=%d", inserted, skipped)

        # Startup summary counts by group (local_seed only)
        def count_where(where_clause) -> int:
            return int(db.scalar(select(func.count()).select_from(Instrument).where(where_clause)) or 0)

        us = count_where(and_(Instrument.provider == "local_seed", Instrument.country == "US", Instrument.asset_class.in_(["equity", "etf"])))
        europe = count_where(and_(Instrument.provider == "local_seed", Instrument.country.in_(["FR", "DE", "GB", "CH", "IT", "NL"]), Instrument.asset_class == "equity"))
        china = count_where(and_(Instrument.provider == "local_seed", Instrument.exchange.in_(["SH", "SZ"]), Instrument.asset_class == "equity"))
        indices = count_where(and_(Instrument.provider == "local_seed", Instrument.asset_class == "index"))
        futures = count_where(and_(Instrument.provider == "local_seed", Instrument.asset_class == "futures"))
        crypto = count_where(and_(Instrument.provider == "local_seed", Instrument.asset_class == "crypto"))

        logger.info(
            "Local instruments totals (provider=local_seed): US=%d Europe=%d China=%d Indices=%d Futures=%d Crypto=%d",
            us,
            europe,
            china,
            indices,
            futures,
            crypto,
        )
    finally:
        db.close()


app.include_router(api_router)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}

