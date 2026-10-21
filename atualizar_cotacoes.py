#!/usr/bin/env python3
"""Cotações e dividendos para o app Meu Banco & Patrimônio.

Modos:
  precos       preços (B3 -> Google -> Yahoo) + junta os dividendos já coletados -> cotacoes.json
  dividendos   dividendos dos últimos 12 meses (B3 -> Yahoo -> StatusInvest) -> div_servidor.json (GitHub)
               ou div_celular.json (Termux). Nunca apaga dado antigo se a fonte falhar.
  teste        mostra, ativo por ativo e fonte por fonte, o que funciona (não grava nada)

Opções: --forcar  ignora o cache de 20 h dos dividendos
Por que dois lugares? O Yahoo e o StatusInvest bloqueiam os servidores do GitHub (erros 429/403),
mas aceitam o seu celular. A B3 aceita os dois.
"""
import base64, html, json, os, re, sys, time, urllib.request, urllib.error
from datetime import date, datetime, timedelta, timezone

TICKERS = ["BBAS3", "ITUB4", "TAEE11", "CPFE3", "CMIG4", "BBSE3", "VBBR3", "HGLG11", "KNRI11", "XPML11", "VISC11", "BTLG11", "GGRC11", "RBRP11", "MXRF11", "KNCR11", "IRDM11", "VGIR11", "KNIP11", "HGCR11"]
UNITS_ACAO = {"TAEE11", "KLBN11", "SAPR11", "ALUP11", "BPAC11"}  # terminam em 11, mas são ações (units)
UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
NO_GITHUB = os.environ.get("GITHUB_ACTIONS") == "true"
ARQ_COT = "cotacoes.json"
ARQ_DIV_SERVIDOR = "div_servidor.json"
ARQ_DIV_CELULAR = "div_celular.json"
DIV_MAX_AGE_S = 20 * 3600
FORCAR = "--forcar" in sys.argv
B3_EMP = "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/"


# ---------------------------------------------------------------- utilidades
def get(url, tries=2):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Accept-Language": "pt-BR,pt;q=0.9"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            print("    falha HTTP", e.code, url[:80])
            return None  # 403/404/429: repetir não adianta
        except Exception as e:
            print("    falha", type(e).__name__, url[:80])
            time.sleep(2)
    return None


def load(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}


def save(path, data):
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def num(x):
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x or "").strip()
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def pdate(s):
    s = str(s or "")
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def b64(d):
    return base64.b64encode(json.dumps(d, separators=(",", ":")).encode()).decode()


def is_fii(t):
    return t.endswith("11") and t not in UNITS_ACAO


# ---------------------------------------------------------------- preços
def price_b3(t):
    try:
        q = json.loads(get(f"https://cotacao.b3.com.br/mds/api/v1/instrumentQuotation/{t}"))["Trad"][0]["scty"]["SctyQtn"]
    except Exception:
        return None
    # sem negócio hoje (ativo de pouca liquidez ou mercado fechado), usa o último preço conhecido
    for k in ("curPrc", "prvsDayClsgPric", "clsgPric", "opngPric"):
        try:
            p = float(q.get(k))
            if p > 0:
                return round(p, 2)
        except (TypeError, ValueError):
            pass
    return None


def price_google(t):
    m = re.search(r'data-last-price="([\d.]+)"', get(f"https://www.google.com/finance/quote/{t}:BVMF?hl=pt") or "")
    return round(float(m.group(1)), 2) if m and float(m.group(1)) > 0 else None


def yahoo_chart(t, rng):
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        txt = get(f"https://{host}/v8/finance/chart/{t}.SA?range={rng}&interval=1mo&events=div")
        try:
            return json.loads(txt)["chart"]["result"][0]
        except Exception:
            continue
    return None


def price_yahoo(t):
    r = yahoo_chart(t, "1d")
    try:
        return round(float(r["meta"]["regularMarketPrice"]), 2)
    except Exception:
        return None


PRICE_SOURCES = [("b3", price_b3), ("google", price_google)] + ([] if NO_GITHUB else [("yahoo", price_yahoo)])


# ---------------------------------------------------------------- dividendos (total por cota em 12 meses)
def div_b3(t):
    """Só ações (a B3 não tem fonte confirmada para FIIs)."""
    if is_fii(t):
        return None
    code = t[:4]
    try:
        res = json.loads(get(B3_EMP + "GetInitialCompanies/" + b64({"language": "pt-br", "pageNumber": 1, "pageSize": 20, "company": code})))["results"]
        name = next((r["tradingName"] for r in res if str(r.get("issuingCompany", "")).upper() == code), res[0]["tradingName"])
    except Exception:
        return None
    today = date.today()
    start = today - timedelta(days=366)
    rows, page = [], 1
    while page <= 6:
        try:
            j = json.loads(get(B3_EMP + "GetListedCashDividends/" + b64({"language": "pt-br", "pageNumber": page, "pageSize": 120, "tradingName": name})))
        except Exception:
            break
        rows += j.get("results") or []
        if page >= int((j.get("page") or {}).get("totalPages", 1) or 1):
            break
        page += 1
    want = {"3": "ON", "4": "PN", "5": "PNA", "6": "PNB"}.get(t[4:])
    sel = [r for r in rows if want and str(r.get("typeStock", "")).upper().startswith(want)] if any(r.get("typeStock") for r in rows) else []
    total = 0.0
    for r in (sel or rows):
        d = next((pdate(r.get(k)) for k in ("lastDatePrior", "paymentDate", "dateApproval", "approvedOn") if pdate(r.get(k))), None)
        v = next((num(r.get(k)) for k in ("rate", "value", "valueCash", "valor") if num(r.get(k)) is not None), None)
        if d and v and start <= d <= today:
            total += v
    return round(total, 4) if total > 0 else None


def div_yahoo(t):
    r = yahoo_chart(t, "1y")
    if not r:
        return None
    now = time.time()
    divs = (r.get("events") or {}).get("dividends") or {}
    total = sum(float(d["amount"]) for d in divs.values() if d["date"] >= now - 366 * 86400)
    return round(total, 4) if total > 0 else None


def div_statusinvest(t):
    for path in (["fundos-imobiliarios", "acoes"] if is_fii(t) else ["acoes", "fundos-imobiliarios"]):
        page = get(f"https://statusinvest.com.br/{path}/{t.lower()}")
        if not page:
            continue
        text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))
        i = text.find("Dividend Yield")
        m = re.search(r"[Úú]ltimos 12 meses\s*(?:R\$)?\s*([\d.]+,\d+)", text[i:i + 700] if i >= 0 else text)
        if m:
            v = num(m.group(1))
            if v and v > 0:
                return v
    return None


DIV_SOURCES = [("b3", div_b3)] + ([] if NO_GITHUB else [("yahoo", div_yahoo), ("statusinvest", div_statusinvest)])


# ---------------------------------------------------------------- modos
def modo_dividendos():
    arq = ARQ_DIV_SERVIDOR if NO_GITHUB else ARQ_DIV_CELULAR
    data = load(arq)
    now, got, sem = time.time(), 0, []
    for t in TICKERS:
        old = data.get(t) or {}
        if not FORCAR and old.get("divMonthly") and old.get("atMs") and now - old["atMs"] / 1000 < DIV_MAX_AGE_S:
            continue
        total, src = None, None
        for name, fn in DIV_SOURCES:
            total = fn(t)
            if total:
                src = name
                break
            time.sleep(0.5)
        if total:
            data[t] = {"total12m": total, "divMonthly": round(total / 12, 4), "src": src, "atMs": int(now * 1000)}
            got += 1
            print("ok", t, data[t])
        else:
            sem.append(t)
            print("sem dividendos agora:", t, "(mantendo o dado anterior)" if old else "")
        time.sleep(0.6)
    save(arq, data)
    print(f"dividendos atualizados: {got} | sem fonte: {len(sem)} {sem if sem else ''}")


def modo_precos():
    prev = load(ARQ_COT).get("quotes", {})
    div_s, div_c = load(ARQ_DIV_SERVIDOR), load(ARQ_DIV_CELULAR)
    quotes, ok = {}, 0
    for t in TICKERS:
        old = prev.get(t) or {}
        price, src = None, None
        for name, fn in PRICE_SOURCES:
            price = fn(t)
            if price:
                src = name
                break
        if price:
            ok += 1
        cands = [d[t] for d in (div_s, div_c) if (d.get(t) or {}).get("divMonthly")]
        best = max(cands, key=lambda d: d.get("atMs", 0)) if cands else {}
        q = {"price": price or old.get("price"), "src": src or old.get("src"),
             "divMonthly": best.get("divMonthly", old.get("divMonthly")), "divSrc": best.get("src", old.get("divSrc"))}
        if q["price"]:
            quotes[t] = q
        print(t, q)
        time.sleep(0.3)
    if ok == 0:
        print("Nenhuma fonte de preço respondeu."); sys.exit(1)
    now = datetime.now(timezone.utc)
    save(ARQ_COT, {"updatedAt": now.isoformat(), "updatedAtMs": int(now.timestamp() * 1000), "quotes": quotes})
    com_div = sum(1 for q in quotes.values() if q.get("divMonthly"))
    print(f"preços: {ok}/{len(TICKERS)} | com dividendo: {com_div}/{len(quotes)}")


def modo_teste():
    print("TESTE — nada é gravado. Ambiente:", "GitHub" if NO_GITHUB else "celular/computador")
    for t in ["HGLG11", "MXRF11", "ITUB4"]:
        print("\n==", t)
        for name, fn in [("b3", price_b3), ("google", price_google), ("yahoo", price_yahoo)]:
            print(f"  preço {name}:", fn(t) or "FALHOU")
        for name, fn in [("b3", div_b3), ("yahoo", div_yahoo), ("statusinvest", div_statusinvest)]:
            v = fn(t)
            print(f"  dividendos {name}:", f"R$ {v} em 12 meses" if v else "FALHOU")


if __name__ == "__main__":
    modo = next((a for a in sys.argv[1:] if not a.startswith("--")), "precos")
    {"precos": modo_precos, "dividendos": modo_dividendos, "teste": modo_teste}.get(modo, modo_teste)()
