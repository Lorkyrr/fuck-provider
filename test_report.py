import unittest

import report

SAUDAVEL = {
    "gw_loss": 0.0,
    "gw_avg": 2.0,
    "signal_dbm": -45,
    "ext_loss": 0.0,
    "ext_avg": 30.0,
    "ext_jitter": 5.0,
}


def ciclo(**mudancas):
    return {**SAUDAVEL, **mudancas}


class Classify(unittest.TestCase):
    def test_tudo_bom_e_ok(self):
        self.assertEqual(report.classify(ciclo()), "ok")

    def test_externo_ruim_com_gateway_limpo_e_operadora(self):
        for ruim in (
            {"ext_loss": 5.0},
            {"ext_avg": 250.0},
            {"ext_jitter": 120.0},
            {"ext_avg": None, "ext_loss": 100.0},
        ):
            self.assertEqual(report.classify(ciclo(**ruim)), "operadora", ruim)

    def test_sinal_fraco_e_wifi_mesmo_com_externo_ruim(self):
        self.assertEqual(report.classify(ciclo(signal_dbm=-78, ext_avg=250.0)), "wifi")

    def test_gateway_ruim_e_wifi(self):
        self.assertEqual(report.classify(ciclo(gw_loss=10.0, ext_loss=40.0)), "wifi")
        self.assertEqual(report.classify(ciclo(gw_avg=90.0, ext_avg=300.0)), "wifi")

    def test_sem_wifi_conectado_e_wifi(self):
        self.assertEqual(report.classify(ciclo(signal_dbm=None)), "wifi")

    def test_limites_nao_acusam(self):
        self.assertEqual(
            report.classify(ciclo(ext_loss=2.0, ext_avg=80.0, ext_jitter=40.0)), "ok"
        )


if __name__ == "__main__":
    unittest.main()
