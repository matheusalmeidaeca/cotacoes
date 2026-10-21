#!/usr/bin/env python3
"""Busca preço (B3 -> Google -> Yahoo) e dividendos (StatusInvest) e grava em cotacoes.json.
Roda no GitHub Actions. Preço: a cada execução. Dividendos: no máximo 1x por dia por ativo."""
import html, json, re, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone

TICKERS = ["BBAS3", "ITUB4", "TAEE11", "CPFE3", "CMIG4", "BBSE3", "VBBR3", "HGLG11", "KNRI11", "XPML11", "VISC11", "BTLG11", "GGRC11", "RBRP11", "MXRF11", "KNCR11", "IRDM11", "VGIR11", "KNIP11", "HGCR11"]
UNITS_ACAO = {"TAEE11", "KLBN11", "SAPR11", "ALUP11", "BPAC11"}  # terminam em 11 mas são ações (units)
UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
OUT = "cotacoes.json"
DIV_MAX_AGE_S = 20 * 3600


def get(url, tries=2):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Accept-Language": "pt-BR,pt;q=0.9"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            print("  falha", url[:70], "HTTP", e.code)
            return None  # 403/404/429: repetir não adianta
        except Exception as e:
            print("  falha", url[:70], type(e).__name__)
            time.sleep(2)
    return None


def price_b3(t):
    txt = get(f"https://cotacao.b3.com.br/mds/api/v1/instrumentQuotation/{t}")
    try:
        p = float(json.loads(txt)["Trad"][0]["scty"]["SctyQtn"]["curPrc"])
        return round(p, 2) if p > 0 else None
    except Exception:
        return None


def price_google(t):
    m = re.search(r'data-last-price="([\d.]+)"', get(f"https://www.google.com/finance/quote/{t}:BVMF?hl=pt") or "")
    return round(float(m.group(1)), 2) if m and float(m.group(1)) > 0 else None


def price_yahoo(t):
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        txt = get(f"https://{host}/v8/finance/chart/{t}.SA?range=1d&interval=1d")
        try:
            return round(float(json.loads(txt)["chart"]["result"][0]["meta"]["regularMarketPrice"]), 2)
        except Exception:
            continue
    return None


def div12m_statusinvest(t):
    """Total de proventos por cota nos últimos 12 meses, lido da página do ativo no StatusInvest."""
    paths = ["fundos-imobiliarios", "acoes"] if (t.endswith("11") and t not in UNITS_ACAO) else ["acoes", "fundos-imobiliarios"]
    for path in paths:
        page = get(f"https://statusinvest.com.br/{path}/{t.lower()}")
        if not page:
            continue
        text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))
        i = text.find("Dividend Yield")
        seg = text[i:i + 700] if i >= 0 else text
        m = re.search(r"[Úú]ltimos 12 meses\s*(?:R\$)?\s*([\d.]+,\d+)", seg)
        if m:
            v = float(m.group(1).replace(".", "").replace(",", "."))
            if v >= 0:
                return v
    return None


def main():
    try:
        prev = json.load(open(OUT, encoding="utf-8")).get("quotes", {})
    except Exception:
        prev = {}
    now_s = time.time()
    quotes, ok, divs = {}, 0, 0
    for t in TICKERS:
        old = prev.get(t) or {}
        price, src = None, None
        for name, fn in (("b3", price_b3), ("google", price_google), ("yahoo", price_yahoo)):
            price = fn(t)
            if price:
                src = name
                break
        q = {"price": price if price else old.get("price"), "src": src or old.get("src"),
             "divMonthly": old.get("divMonthly"), "divAtMs": old.get("divAtMs")}
        if price:
            ok += 1
        # dividendos: só busca de novo se o dado tem mais de ~20 h
        if not old.get("divAtMs") or now_s - old["divAtMs"] / 1000 > DIV_MAX_AGE_S or old.get("divMonthly") is None:
            total = div12m_statusinvest(t)
            if total is not None and total > 0:
                q["divMonthly"] = round(total / 12, 4)
                q["divAtMs"] = int(now_s * 1000)
                divs += 1
            time.sleep(0.8)
        print(t, q)
        if q["price"]:
            quotes[t] = q
        time.sleep(0.4)
    if ok == 0:
        print("Nenhuma fonte de preço respondeu."); sys.exit(1)
    now = datetime.now(timezone.utc)
    json.dump({"updatedAt": now.isoformat(), "updatedAtMs": int(now.timestamp() * 1000), "quotes": quotes},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"preços: {ok}/{len(TICKERS)} | dividendos atualizados: {divs}")


main()
