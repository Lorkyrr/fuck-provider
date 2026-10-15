#!/usr/bin/env python3
"""Coleta contínua de qualidade da internet (ping/jitter/perda/Wi-Fi/speedtest/quedas) em SQLite."""
import json
import re
import socket
import sqlite3
import subprocess
import sys
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
DNS_PROBES = ["example.com", "wikipedia.org", "gov.br", "globo.com", "cloudflare.com"]
MTR_CYCLES = 10
CMD_TIMEOUT_S = 120

SCHEMA = """
create table if not exists samples (
  ts text, target text, is_gateway integer,
  loss real, rtt_min real, rtt_avg real, rtt_max real, jitter real,
  signal_dbm integer, tx_mbps real, freq_mhz integer, ssid text, dns_ms real
);
create table if not exists speedtests (
  ts text, down_mbps real, up_mbps real, ping_ms real, server text, signal_dbm integer
);
create table if not exists outages (
  started_at text, ended_at text, duration_s integer, mtr text
);
create index if not exists idx_samples_ts on samples(ts);
"""


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ping(out):
    loss = re.search(r"([\d.]+)% packet loss", out)
    rtt = re.search(r"= ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms", out)
    r = {"loss": float(loss.group(1)) if loss else 100.0,
         "min": None, "avg": None, "max": None, "jitter": None}
    if rtt:
        r["min"], r["avg"], r["max"], r["jitter"] = (float(x) for x in rtt.groups())
    return r


def parse_wifi(out):
    def grab(pattern, cast):
        m = re.search(pattern, out)
        return cast(m.group(1)) if m else None
    return {"signal_dbm": grab(r"signal: (-?\d+) dBm", int),
            "tx_mbps": grab(r"tx bitrate: ([\d.]+) MBit/s", float),
            "freq_mhz": grab(r"freq: (\d+)", int),
            "ssid": grab(r"SSID: (.+)", str)}


def parse_speedtest(out):
    d = json.loads(out)
    srv = d.get("server", {})
    return {"down_mbps": d["download"] / 1e6, "up_mbps": d["upload"] / 1e6,
            "ping_ms": d["ping"], "server": f"{srv.get('sponsor')} - {srv.get('name')}"}


def init_db(db):
    db.executescript(SCHEMA)


def run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=CMD_TIMEOUT_S)
        return p.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def ping(host, count):
    return parse_ping(run(["ping", "-c", str(count), "-i", "0.2", "-W", "2", "-q", host]))


def dns_ms(i):
    t0 = time.monotonic()
    try:
        socket.getaddrinfo(DNS_PROBES[i % len(DNS_PROBES)], None)
    except socket.gaierror:
        return None
    return (time.monotonic() - t0) * 1000


def mtr(host):
    return run(["mtr", "-rwn", "-c", str(MTR_CYCLES), host])


class OutageTracker:
    """Abre uma queda após `min_cycles` ciclos seguidos sem nenhum alvo externo respondendo."""

    def __init__(self, db, min_cycles, mtr=mtr, mtr_host="1.1.1.1"):
        self.db, self.min_cycles, self.mtr, self.mtr_host = db, min_cycles, mtr, mtr_host
        self.first_dead_ts, self.dead_count, self.open_rowid = None, 0, None

    def update(self, ts, all_external_dead):
        if all_external_dead:
            if self.dead_count == 0:
                self.first_dead_ts = ts
            self.dead_count += 1
            if self.dead_count == self.min_cycles and self.open_rowid is None:
                cur = self.db.execute("insert into outages(started_at, mtr) values (?, ?)",
                                      (self.first_dead_ts, self.mtr(self.mtr_host)))
                self.open_rowid = cur.lastrowid
        else:
            if self.open_rowid is not None:
                dur = int((datetime.fromisoformat(ts) - datetime.fromisoformat(self.first_dead_ts)).total_seconds())
                self.db.execute("update outages set ended_at=?, duration_s=? where rowid=?",
                                (ts, dur, self.open_rowid))
            self.dead_count, self.open_rowid = 0, None
        self.db.commit()


def gateway_ip(iface):
    out = run(["ip", "route", "show", "default", "dev", iface])
    m = re.search(r"default via (\S+)", out)
    return m.group(1) if m else None


def main():
    cfg = tomllib.loads((HERE / "config.toml").read_text())
    db = sqlite3.connect(HERE / cfg.get("db", "monitor.db"))
    init_db(db)
    iface, cycle_s = cfg["interface"], cfg["cycle_seconds"]
    tracker = OutageTracker(db, cfg["outage_min_cycles"])
    next_speedtest, i = 0.0, 0

    while True:
        started = time.monotonic()
        ts = now_utc()
        wifi = parse_wifi(run(["iw", "dev", iface, "link"]))
        gw = gateway_ip(iface)
        targets = ([(gw, 1)] if gw else []) + [(t, 0) for t in cfg["targets"]]
        external_loss = []
        dns = dns_ms(i)
        for host, is_gw in targets:
            p = ping(host, cfg["pings_per_cycle"])
            if not is_gw:
                external_loss.append(p["loss"])
            db.execute("insert into samples values (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (ts, host, is_gw, p["loss"], p["min"], p["avg"], p["max"], p["jitter"],
                        wifi["signal_dbm"], wifi["tx_mbps"], wifi["freq_mhz"], wifi["ssid"], dns))
        db.commit()
        tracker.update(ts, bool(external_loss) and all(x >= 100 for x in external_loss))

        # Depois dos pings: o speedtest satura o link e distorceria as medidas do ciclo.
        if time.monotonic() >= next_speedtest:
            next_speedtest = time.monotonic() + cfg["speedtest_minutes"] * 60
            try:
                s = parse_speedtest(run(["speedtest", "--json"]))
                db.execute("insert into speedtests values (?,?,?,?,?,?)",
                           (ts, s["down_mbps"], s["up_mbps"], s["ping_ms"], s["server"], wifi["signal_dbm"]))
                db.commit()
            except (ValueError, KeyError) as e:
                print(f"{ts} speedtest falhou: {e}", file=sys.stderr)

        i += 1
        time.sleep(max(0, cycle_s - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
