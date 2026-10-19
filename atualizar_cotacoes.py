#!/usr/bin/env python3
"""Busca preço e dividendos dos ativos e grava em cotacoes.json.
Roda no GitHub Actions (servidor), então não tem problema de CORS nem de ponte pública."""
import json, re, sys, time, urllib.request
from datetime import datetime, timezone

TICKERS = ["BBAS3", "ITUB4", "TAEE11", "CPFE3", "CMIG4", "BBSE3", "VBBR3", "HGLG11", "KNRI11", "XPML11", "VISC11", "BTLG11", "GGRC11", "RBRP11", "MXRF11", "KNCR11", "IRDM11", "VGIR11", "KNIP11", "HGCR11"]
UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
OUT = "cotacoes.json"


def get(url, tries=2):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Accept-Language": "pt-BR,pt;q=0.9"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            print("  falha", url[:75], type(e).__name__, getattr(e, "code", ""))
            time.sleep(2 + i * 2)
    return None


def yahoo(t):
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        txt = get(f"https://{host}/v8/finance/chart/{t}.SA?range=1y&interval=1mo&events=div")
        if not txt:
            continue
        try:
            r = json.loads(txt)["chart"]["result"][0]
            price = float(r["meta"]["regularMarketPrice"])
            now = time.time()
            divs = (r.get("events") or {}).get("dividends") or {}
            total = sum(float(d["amount"]) for d in divs.values() if d["date"] >= now - 366 * 86400)
            first = (r.get("timestamp") or [now - 365 * 86400])[0]
            months = max(1, min(12, round((now - first) / (30.4 * 86400))))
            return {"price": round(price, 2), "divMonthly": round(total / months, 4) if total > 0 else None, "src": "yahoo"}
        except Exception as e:
            print("  yahoo resposta inválida", t, type(e).__name__)
    return None


def b3(t):
    txt = get(f"https://cotacao.b3.com.br/mds/api/v1/instrumentQuotation/{t}")
    if not txt:
        return None
    try:
        p = float(json.loads(txt)["Trad"][0]["scty"]["SctyQtn"]["curPrc"])
        return {"price": round(p, 2), "divMonthly": None, "src": "b3"} if p > 0 else None
    except Exception as e:
        print("  b3 resposta inválida", t, type(e).__name__)
        return None


def google(t):
    txt = get(f"https://www.google.com/finance/quote/{t}:BVMF?hl=pt")
    m = re.search(r'data-last-price="([\d.]+)"', txt or "")
    if not m:
        return None
    p = float(m.group(1))
    return {"price": round(p, 2), "divMonthly": None, "src": "google"} if p > 0 else None


def main():
    try:
        prev = json.load(open(OUT, encoding="utf-8")).get("quotes", {})
    except Exception:
        prev = {}
    quotes, ok = {}, 0
    for t in TICKERS:
        q = yahoo(t) or b3(t) or google(t)
        old = prev.get(t) or {}
        if q:
            if q.get("divMonthly") is None and old.get("divMonthly"):
                q["divMonthly"] = old["divMonthly"]  # mantém o último dividendo conhecido
            ok += 1
            print("ok", t, q)
        elif old:
            q = old  # mantém o último valor se todas as fontes falharem agora
            print("sem resposta, mantendo anterior:", t)
        if q:
            quotes[t] = q
        time.sleep(0.6)
    if ok == 0:
        print("Nenhuma fonte respondeu."); sys.exit(1)
    now = datetime.now(timezone.utc)
    json.dump({"updatedAt": now.isoformat(), "updatedAtMs": int(now.timestamp() * 1000), "quotes": quotes},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{ok}/{len(TICKERS)} atualizados")


main()
