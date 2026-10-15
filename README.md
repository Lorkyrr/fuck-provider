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

```sh
python3 monitor.py   # coleta a cada 60 s e grava em monitor.db
python3 report.py    # imprime o resumo e gera relatorio.html e samples.csv
```

O monitor deve rodar por dias, com o computador ligado e sem suspender, para a evidência ser relevante.

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
