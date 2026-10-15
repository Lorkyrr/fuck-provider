import sqlite3
import unittest

import monitor

PING_OK = """
--- 1.1.1.1 ping statistics ---
20 packets transmitted, 19 received, 5% packet loss, time 3800ms
rtt min/avg/max/mdev = 10.100/22.500/80.000/9.750 ms
"""

PING_DEAD = """
--- 192.0.2.1 ping statistics ---
20 packets transmitted, 0 received, 100% packet loss, time 3900ms
"""

IW_LINK = """Connected to 3c:84:6a:22:82:46 (on wlp3s0)
\tSSID: TP-Link_8244_5G
\tfreq: 5745.0
\tsignal: -44 dBm
\ttx bitrate: 292.5 MBit/s VHT-MCS 7 80MHz VHT-NSS 1
"""

IW_DOWN = "Not connected.\n"

SPEEDTEST_JSON = (
    '{"download": 90000000.0, "upload": 20000000.0, "ping": 18.5,'
    ' "server": {"sponsor": "Foo Telecom", "name": "Sao Paulo", "id": "1234"}}'
)


class ParsePing(unittest.TestCase):
    def test_ok(self):
        r = monitor.parse_ping(PING_OK)
        self.assertEqual(r, {"loss": 5.0, "min": 10.1, "avg": 22.5, "max": 80.0, "jitter": 9.75})

    def test_total_loss_has_no_rtt(self):
        r = monitor.parse_ping(PING_DEAD)
        self.assertEqual(r["loss"], 100.0)
        self.assertIsNone(r["avg"])

    def test_garbage_counts_as_total_loss(self):
        self.assertEqual(monitor.parse_ping("ping: unknown host")["loss"], 100.0)


class ParseWifi(unittest.TestCase):
    def test_connected(self):
        r = monitor.parse_wifi(IW_LINK)
        self.assertEqual(r["signal_dbm"], -44)
        self.assertEqual(r["tx_mbps"], 292.5)
        self.assertEqual(r["ssid"], "TP-Link_8244_5G")
        self.assertEqual(r["freq_mhz"], 5745)

    def test_disconnected(self):
        self.assertEqual(monitor.parse_wifi(IW_DOWN)["signal_dbm"], None)


class ParseSpeedtest(unittest.TestCase):
    def test_converts_bits_to_mbps(self):
        r = monitor.parse_speedtest(SPEEDTEST_JSON)
        self.assertAlmostEqual(r["down_mbps"], 90.0)
        self.assertAlmostEqual(r["up_mbps"], 20.0)
        self.assertEqual(r["ping_ms"], 18.5)
        self.assertEqual(r["server"], "Foo Telecom - Sao Paulo")


class OutageTracker(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        monitor.init_db(self.db)
        self.t = monitor.OutageTracker(self.db, min_cycles=2, mtr=lambda host: "mtr-fake")

    def test_needs_consecutive_cycles(self):
        self.t.update("2026-01-01T00:00:00Z", all_external_dead=True)
        self.assertEqual(self.db.execute("select count(*) from outages").fetchone()[0], 0)
        self.t.update("2026-01-01T00:01:00Z", all_external_dead=True)
        self.assertEqual(self.db.execute("select count(*) from outages").fetchone()[0], 1)

    def test_single_blip_is_not_outage(self):
        self.t.update("2026-01-01T00:00:00Z", all_external_dead=True)
        self.t.update("2026-01-01T00:01:00Z", all_external_dead=False)
        self.t.update("2026-01-01T00:02:00Z", all_external_dead=True)
        self.assertEqual(self.db.execute("select count(*) from outages").fetchone()[0], 0)

    def test_closes_with_duration_and_mtr(self):
        for ts in ("2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z", "2026-01-01T00:02:00Z"):
            self.t.update(ts, all_external_dead=True)
        self.t.update("2026-01-01T00:03:00Z", all_external_dead=False)
        row = self.db.execute("select started_at, ended_at, duration_s, mtr from outages").fetchone()
        self.assertEqual(row, ("2026-01-01T00:00:00Z", "2026-01-01T00:03:00Z", 180, "mtr-fake"))


if __name__ == "__main__":
    unittest.main()
