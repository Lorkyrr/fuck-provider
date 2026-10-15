# fuck-provider

Monitor contínuo da qualidade da internet (ping, jitter, perda, quedas, velocidade e sinal Wi-Fi) que gera evidência para denúncias de serviço mal prestado à Anatel.

## Nível do projeto

**Nível 1**: ferramenta pessoal de poucos arquivos, sem serviço exposto nem dados de terceiros. Exigências de cada nível nas Diretrizes de Código.

```diretrizes
nome: fuck-provider
nivel: 1
linguagens: python
resumo: Monitor contínuo da qualidade da internet (ping, jitter, perda, quedas, velocidade e sinal Wi-Fi) que gera evidência para denúncias de serviço mal prestado à Anatel.
```

## Status

Em desenvolvimento. A coleta (`monitor.py`) funciona e grava em SQLite. O relatório (`report.py`) depende do critério de classificação de culpa (`classify`), ainda a definir.

## Instalação

Requer Linux com `ping`, `iw`, `mtr` e `speedtest-cli` (comando `speedtest`) e Python 3.11 ou mais recente. Não há dependências Python além da biblioteca padrão. Ajuste `interface`, `targets` e o plano contratado em `config.toml`.

## Uso

Rodar à mão, em primeiro plano:

```sh
python3 monitor.py   # coleta a cada 60 s e grava em monitor.db
python3 report.py    # imprime o resumo e gera relatorio.html e samples.csv
```

Rodar como serviço systemd de usuário (recomendado). O serviço usa `systemd-inhibit` para o computador não suspender enquanto mede. O caminho em `WorkingDirectory` de `fuck-provider.service` aponta para `~/Documentos/Coding/fuck-provider`; ajuste se o projeto estiver em outro lugar.

```sh
# Instalar e iniciar (uma vez)
mkdir -p ~/.config/systemd/user
cp fuck-provider.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now fuck-provider

# Acompanhar
systemctl --user status fuck-provider      # estado do serviço
journalctl --user -u fuck-provider -f      # logs ao vivo
sqlite3 monitor.db "select count(distinct ts) from samples"   # ciclos coletados

# Gerar o relatório para a denúncia
python3 report.py

# Controlar
systemctl --user restart fuck-provider     # depois de editar o config.toml
systemctl --user stop fuck-provider        # parar a coleta
systemctl --user disable --now fuck-provider   # parar e não iniciar mais

# Opcional: manter o serviço rodando mesmo sem sessão de usuário aberta
loginctl enable-linger "$USER"
```

Testes:

```sh
python3 -m unittest test_monitor test_report
```

O monitor deve rodar por dias, com o computador ligado, na tomada e sem suspender, para a evidência ser relevante.

## Denúncia à Anatel

1. Abra reclamação na operadora e guarde o número do **protocolo**.
2. Rode `python3 report.py` e anexe `relatorio.html` e `samples.csv`.
3. Complemente com medições do SIMET ([simet.nic.br](https://simet.nic.br/)).
4. Registre a reclamação na Anatel: telefone **1331**, app Anatel Consumidor ou site, com login gov.br.

Os limites de latência (80 ms), jitter (40 ms) e perda (2%) usados em `report.py` vêm de fontes secundárias e não foram confirmados no texto oficial da Resolução 717/2019. Confirme antes de citá-los.

## Desenvolvimento

Depois de clonar, ative os hooks (a configuração não vem junto com o repositório):

```sh
git config core.hooksPath .githooks
```

Testes: `python3 -m unittest test_monitor`. Testes e auditoria: chaves `testar` e `auditar` do bloco `diretrizes`. Sem essas chaves, vale o padrão da linguagem.

## Arquitetura

| Módulo | Responsabilidade | Depende de |
| --- | --- | --- |
| `monitor.py` | Coleta ping, Wi-Fi, DNS, speedtest e quedas; grava em SQLite | `ping`, `iw`, `mtr`, `speedtest` |
| `report.py` | Classifica ciclos, calcula estatísticas e exporta HTML e CSV | `monitor.db` |
| `config.toml` | Interface, alvos, intervalos e plano contratado | — |

## Dados pessoais

| Dado | Por que é tratado | Por quanto tempo |
| --- | --- | --- |
| SSID e IP do gateway da rede local | Distinguir falha do Wi-Fi de falha da operadora | Só no `monitor.db` local, fora do git, até o usuário apagar |

## Decisões

Decisões de arquitetura e desvios das diretrizes ficam em `docs/adr/`.

## Licença

GNU General Public License v3.0 ou posterior. Texto completo em `LICENSE`.
