#!/usr/bin/env python3
"""Gera resumo (stdout), relatorio.html e samples.csv a partir do monitor.db."""

import csv
import html
import sqlite3
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import tomllib

HERE = Path(__file__).parent
# Regras de qualidade da Anatel (RQUAL): confirme na resolução vigente antes de citar na denúncia.
ANATEL_AVG_MIN = 0.80
ANATEL_INSTANT_MIN = 0.40
# Referências de latência/jitter/perda da banda larga fixa. A Res. 717/2019 delega esses valores a
# documento separado; os números abaixo vêm de fontes secundárias e NÃO foram confirmados no texto
# oficial. Confirme antes de citá-los na denúncia.
LATENCY_MAX_MS = 80
JITTER_MAX_MS = 40
LOSS_MAX_PCT = 2
# Critérios locais (escolha deste projeto, não da Anatel): acima disso a culpa é do Wi-Fi.
WIFI_SIGNAL_MIN_DBM = -70
LOCAL_LATENCY_MAX_MS = 30


def classify(c):
    """Classifica um ciclo de medição. Retorna "ok", "operadora" ou "wifi".

    c = {
      "gw_loss": perda % no gateway,   "gw_avg": latência média (ms) no gateway,
      "signal_dbm": sinal Wi-Fi,       "ext_loss": MAIOR perda % entre alvos externos,
      "ext_avg": latência média (ms) dos alvos externos, "ext_jitter": jitter médio (ms) externo,
    }
    """
    # Primeiro o lado local: só se acusa a operadora quando o Wi-Fi e o gateway estavam limpos.
    signal = c["signal_dbm"]
    if signal is None or signal < WIFI_SIGNAL_MIN_DBM:
        return "wifi"
    if (
        c["gw_loss"] > LOSS_MAX_PCT
        or c["gw_avg"] is None
        or c["gw_avg"] > LOCAL_LATENCY_MAX_MS
    ):
        return "wifi"

    # ext_avg None = nenhum pacote voltou (perda total).
    if (
        c["ext_loss"] > LOSS_MAX_PCT
        or c["ext_avg"] is None
        or c["ext_avg"] > LATENCY_MAX_MS
        or (c["ext_jitter"] is not None and c["ext_jitter"] > JITTER_MAX_MS)
    ):
        return "operadora"
    return "ok"


def load_cycles(db):
    by_ts = defaultdict(list)
    for row in db.execute("select * from samples order by ts"):
        by_ts[row[0]].append(row)
    cycles = []
    for ts, rows in by_ts.items():
        gw = [r for r in rows if r[2]]
        ext = [r for r in rows if not r[2]]
        if not gw or not ext:
            continue
        avg = lambda xs: (
            statistics.fmean(x for x in xs if x is not None)
            if any(x is not None for x in xs)
            else None
        )
        c = {
            "ts": ts,
            "gw_loss": gw[0][3],
            "gw_avg": gw[0][5],
            "signal_dbm": gw[0][8],
            "ext_loss": max(r[3] for r in ext),
            "ext_avg": avg([r[5] for r in ext]),
            "ext_jitter": avg([r[7] for r in ext]),
            "dns_ms": gw[0][12],
        }
        c["class"] = classify(c)
        cycles.append(c)
    return cycles


def pct(xs, p):
    xs = sorted(x for x in xs if x is not None)
    return (
        statistics.quantiles(xs, n=100)[p - 1]
        if len(xs) >= 2
        else (xs[0] if xs else None)
    )


def fmt(x, unit=""):
    return "n/d" if x is None else f"{x:.1f}{unit}"


def build_report(db, cfg):
    cycles = load_cycles(db)
    L = [f"Relatório de qualidade da conexão — {len(cycles)} ciclos medidos"]
    if not cycles:
        return "\n".join(L + ["Sem dados ainda."])
    L.append(f"Período (UTC): {cycles[0]['ts']} a {cycles[-1]['ts']}")

    counts = Counter(c["class"] for c in cycles)
    L += ["", "== Classificação dos ciclos =="]
    for k in ("ok", "operadora", "wifi"):
        L.append(f"  {k:10s} {counts[k]:6d}  ({100 * counts[k] / len(cycles):.1f}%)")
    L.append(
        "  (ciclos 'wifi' ficam FORA das estatísticas abaixo, para não culpar a operadora por problema local)"
    )

    valid = [c for c in cycles if c["class"] != "wifi"]
    L += ["", "== Link externo (ciclos válidos) =="]
    for label, key, unit in (
        ("Latência média", "ext_avg", " ms"),
        ("Jitter", "ext_jitter", " ms"),
        ("Perda (pior alvo)", "ext_loss", " %"),
        ("DNS", "dns_ms", " ms"),
    ):
        xs = [c[key] for c in valid]
        L.append(
            f"  {label:18s} p50={fmt(pct(xs, 50), unit)}  p95={fmt(pct(xs, 95), unit)}  p99={fmt(pct(xs, 99), unit)}"
        )

    L += ["", "== Quedas =="]
    outs = db.execute(
        "select started_at, ended_at, duration_s from outages where ended_at is not null"
    ).fetchall()
    L.append(f"  {len(outs)} quedas, {sum(o[2] for o in outs)} s fora do ar no total")
    L += [f"  {s} -> {e}  ({d} s)" for s, e, d in outs]

    L += [
        "",
        f"== Speedtest vs plano ({cfg['plan_down_mbps']}/{cfg['plan_up_mbps']} Mbps) ==",
    ]
    st = db.execute("select down_mbps, up_mbps from speedtests").fetchall()
    if st:
        down, up = [s[0] for s in st], [s[1] for s in st]
        avg_d, avg_u = statistics.fmean(down), statistics.fmean(up)
        L.append(
            f"  {len(st)} testes. Download médio {avg_d:.1f} Mbps = {100 * avg_d / cfg['plan_down_mbps']:.0f}% do contratado (mín. Anatel {ANATEL_AVG_MIN:.0%})"
        )
        L.append(
            f"  Upload   médio {avg_u:.1f} Mbps = {100 * avg_u / cfg['plan_up_mbps']:.0f}% do contratado"
        )
        bad = sum(d < ANATEL_INSTANT_MIN * cfg["plan_down_mbps"] for d in down)
        L.append(
            f"  {bad}/{len(st)} testes abaixo de {ANATEL_INSTANT_MIN:.0%} do contratado (limite instantâneo)"
        )

    L += ["", "== Por hora do dia (horário local, ciclos válidos) =="]
    by_hour = defaultdict(list)
    for c in valid:
        h = datetime.fromisoformat(c["ts"]).astimezone().hour
        by_hour[h].append(c)
    for h in sorted(by_hour):
        cs = by_hour[h]
        L.append(
            f"  {h:02d}h  n={len(cs):4d}  lat={fmt(statistics.fmean(c['ext_avg'] for c in cs if c['ext_avg'] is not None), ' ms'):>10s}"
            f"  perda máx média={fmt(statistics.fmean(c['ext_loss'] for c in cs), ' %')}"
        )
    return "\n".join(L)


def main():
    cfg = tomllib.loads((HERE / "config.toml").read_text())
    db = sqlite3.connect(HERE / cfg.get("db", "monitor.db"))
    text = build_report(db, cfg)
    print(text)
    (HERE / "relatorio.html").write_text(
        f"<!doctype html><meta charset=utf-8><title>Relatório de conexão</title><pre>{html.escape(text)}</pre>"
    )
    with open(HERE / "samples.csv", "w", newline="") as f:
        cur = db.execute("select * from samples order by ts")
        w = csv.writer(f)
        w.writerow([d[0] for d in cur.description])
        w.writerows(cur)


if __name__ == "__main__":
    main()
