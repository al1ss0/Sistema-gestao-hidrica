# Sistema Inteligente de Suporte à Decisão para Gestão Hídrica em Propriedades Rurais

Protótipo acadêmico que informa ao produtor rural se ele precisa irrigar. O usuário informa cultura, solo, data de semeadura, data da análise e (opcionalmente) a última irrigação. O sistema usa o clima da localidade (Passo Fundo – RS) e responde com uma de três classes: *Sem necessidade de irrigação*, *Atenção: irrigação em breve* ou *Irrigação recomendada*.

O sistema **apenas recomenda**: não controla equipamentos, não usa sensores e não garante economia de água. Detalhes em [spec.md](spec.md).

## Instalação

```
py -3.14 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
```

`requirements.txt` tem só o necessário para rodar (é o que a hospedagem instala); `requirements-dev.txt` acrescenta o pytest.

(Testado com Python 3.14.3. Se alguma biblioteca não instalar, use `py -3.12`.)

## Gerar o modelo

```
.venv\Scripts\python pipeline.py
```

Baixa o clima diário da NASA POWER (de 2010-01-01 até o último dia completo disponível), simula as safras, gera o dataset e treina e compara os modelos. Leva cerca de 3 minutos. Sem internet, use `python pipeline.py --clima-sintetico` (clima gerado artificialmente; o arquivo `data/fonte_clima.txt` registra qual fonte foi usada).

Saídas: `data/clima.csv`, `data/clima_meta.json`, `data/dataset.csv`, `models/modelo.joblib`, `models/metadata.json` (inclui a calibração conforme), `reports/metricas.csv`, `reports/conformal.csv`, `reports/selecao.txt`.

`python pipeline.py --so-treino` reaproveita o `data/dataset.csv` existente e só retreina e recalibra (não baixa o clima nem refaz o dataset).

## Abrir a aplicação

```
.venv\Scripts\python app.py
```

Acesse http://127.0.0.1:5000. A interface tem quatro páginas: **Início**, **Plataforma de análise** (formulário em cinco grupos e painel de resultados com indicadores, gráficos e recomendações), **Metodologia** (fontes, variáveis, cálculos, critérios, modelo e limitações) e **Sobre o projeto**.

## Localização da propriedade

O agricultor escolhe o local da propriedade que quer analisar, onde quer que ela fique; a posição de quem acessa o sistema nunca é usada. Na plataforma há três opções:

- **Local de referência (Passo Fundo – RS):** onde o modelo foi treinado.
- **Município:** digite o nome (há sugestões) e, se houver homônimos, o estado. Usa-se a sede do município. A busca e a altitude vêm da API do Open-Meteo.
- **Coordenadas:** latitude e longitude em graus decimais (aceita vírgula), com altitude opcional (se vazia, é buscada). Apenas coordenadas no Brasil.

Para cada análise o clima do período (da semeadura à data da análise) é buscado na NASA POWER para aquele ponto, em grade de cerca de 50 km, com cache de 6 horas.

**O modelo só conhece um lugar.** Foi treinado com o clima de Passo Fundo e com análises de outubro a maio. Em localidades a mais de 50 km dali, ou em datas de junho a setembro, o resultado do modelo seria extrapolação. Nesses casos o resultado principal passa a ser o **cálculo de referência (balanço hídrico FAO-56)**, que vale em qualquer lugar, e o modelo aparece só como estimativa complementar, com aviso na tela. Para que o modelo valha em outras regiões é preciso treiná-lo com o clima delas.

## Dados climáticos: atualização e período

Não há data máxima fixa. A análise pode usar qualquer data desde 2010-01-01 até o **último dia completo** disponível na fonte, sem passar de hoje. O padrão do campo "data da análise" é esse último dia, e o rodapé de todas as páginas mostra até quando o clima vai e quando foi atualizado.

- **Atualização automática:** ao iniciar o app, uma vez por dia, se houver internet.
- **Atualização manual:** botão "Atualizar dados climáticos agora" na plataforma, ou `python atualizar_clima.py`. A atualização é incremental: baixa só o trecho recente (repetindo os últimos 30 dias, porque a fonte pode revisar valores) e preserva o histórico.
- **Defasagem:** a NASA POWER tem alguns dias de atraso, e a radiação solar é a última variável a ficar pronta. Dias ainda incompletos são **descartados, nunca preenchidos**.
- **Natureza do dado:** a NASA POWER fornece estimativas de reanálise/modelagem e satélite, não medições de estação meteorológica, e não são previsões do tempo. Valores recentes são provisórios.
- Os modelos foram treinados com safras de 2010 a 2024. Atualizar o clima não retreina o modelo; para incluir safras mais novas no treino, altere `config.py` (`ANOS_SEMEADURA` e a divisão por anos) e rode `python pipeline.py`.

## Publicação na internet

O sistema é uma única aplicação Flask que serve a interface e a API. O repositório já traz `Dockerfile`, `render.yaml` (hospedagem no Render), `wsgi.py` (gunicorn) e um workflow de testes do GitHub Actions. O passo a passo está em [DEPLOY.md](DEPLOY.md). O GitHub Pages não serve para este projeto, porque ele só hospeda páginas estáticas e não executa Python.

## Testes

```
.venv\Scripts\python -m pytest
```

## Resultados da comparação de modelos

Conteúdo de `reports/metricas.csv`, gerado com clima real da NASA POWER. Validação: 2020–2021; teste: 2022–2024. Todos os modelos, inclusive o selecionado (XGBoost), foram ajustados só com os anos de treino (2010–2019): a validação serve para escolher o modelo e calibrar os intervalos de predição, e o teste só para avaliar.

| modelo | f1_macro_validacao | acuracia_balanceada_validacao | recall_classe2_validacao | f1_macro_teste | acuracia_balanceada_teste | recall_classe2_teste | selecionado |
|---|---|---|---|---|---|---|---|
| RegressaoLogistica | 0.6976 | 0.7237 | 0.9248 | 0.7412 | 0.7488 | 0.8186 | False |
| RandomForest | 0.7983 | 0.8042 | 0.9299 | 0.8501 | 0.8493 | 0.9154 | False |
| XGBoost | 0.8285 | 0.8338 | 0.9467 | 0.8641 | 0.8584 | 0.9032 | True |
| MLP | 0.7817 | 0.7962 | 0.9401 | 0.8401 | 0.8324 | 0.8724 | False |
| Dummy | 0.2211 | 0.3333 | 0.0 | 0.2267 | 0.3333 | 0.0 | False |

## Intervalos de predição (predição conformal)

Para classificação, o equivalente do intervalo de predição é um **conjunto de classes** que contém a classe verdadeira em pelo menos 90% dos casos (`CONFORMAL_ALFA = 0,10` em `config.py`). Na tela principal aparece só uma linha: "✓ Resultado confiável" (conjunto com 1 classe) ou "⚠ Resultado incerto: pode ser também ..." (2 ou 3 classes). O conjunto, o nível de 90% e a cobertura medida no teste ficam em "Ver detalhes técnicos".

- **Método:** predição conformal *split*, com a nota 1 − probabilidade da classe verdadeira, programada à mão com numpy (módulo `hidrica/conformal.py`; sem MAPIE, para não somar dependências). O conjunto nunca fica vazio: sempre inclui a classe mais provável.
- **Calibração:** nos anos de validação (2020–2021). Por isso **o modelo final é ajustado só com 2010–2019**: se ele tivesse visto os anos de calibração, pareceria mais certo do que é e todos os conjuntos teriam 1 classe. O limiar calibrado fica em `models/metadata.json`, no campo `conformal`, e o site não recalcula nada.
- **Escolha do método:** o modo `auto` usa o LAC global, mas troca para **Mondrian** (um limiar por classe) se, na própria calibração, alguma classe ficar abaixo de 85% de cobertura. A decisão é tomada sem olhar o teste. Aqui foi escolhido o método **mondrian**.
- **Fora do domínio de treino** (localidade a mais de 50 km de Passo Fundo ou análise de junho a setembro) o resultado vem do cálculo FAO-56 e **o intervalo não é mostrado**: a garantia de cobertura só vale para casos parecidos com os da calibração.

Medido no teste (2022–2024, nunca usado para treinar nem calibrar), conteúdo de `reports/conformal.csv`:

| método | cobertura no teste | tamanho médio | 1 classe | 2 classes | 3 classes | cobertura: sem necessidade | cobertura: atenção | cobertura: irrigação recomendada |
|---|---|---|---|---|---|---|---|---|
| lac | 93.1% | 1.09 | 91.0% | 8.9% | 0.0% | 97.9% | 80.1% | 93.7% |
| **mondrian (usado)** | 93.5% | 1.14 | 86.4% | 13.6% | 0.0% | 95.8% | 91.9% | 90.3% |
| aps | 98.9% | 1.53 | 46.9% | 53.1% | 0.0% | 99.5% | 99.0% | 97.8% |

O método usado cobriu **93.5%** dos casos (meta 90%), com conjuntos de **1.14** classes em média. A cobertura por classe fica em 95.8% (sem necessidade), 91.9% (atenção) e 90.3% (irrigação recomendada). A cobertura global ficou acima da meta, o que se explica em boa parte por os anos de calibração terem sido mais difíceis para o modelo do que os de teste (F1-macro menor na calibração); é o lado seguro do erro, mas mostra que a cobertura depende do clima dos anos usados.

## Limitações

- **Os rótulos são simulados.** Não existem dados reais rotulados de "precisa irrigar". Os rótulos vêm de um balanço hídrico do solo (método FAO-56) aplicado a clima real e a safras simuladas. O modelo aprende a reproduzir esse cálculo a partir de um resumo do clima recente, da cultura, do solo e da última irrigação.
- **Métrica alta não é validade agronômica.** F1 e acurácia medem a concordância com a simulação, não o acerto de uma decisão de irrigação em campo. Não foi feita validação em campo.
- **Parâmetros a conferir.** Os valores de Kc, estágios, profundidade de raiz, fator p e umidade do solo (spec.md, seção 5) são valores de referência do FAO-56 e precisam ser conferidos pela equipe. O limiar da classe "Atenção" (metade do RAW) é uma escolha de produto, não um valor agronômico.
- O balanço assume solo na capacidade de campo na semeadura, precipitação efetiva igual à total e sem ascensão capilar.
- Três culturas (milho, soja, feijão) e três classes de solo. O modelo foi treinado com um único ponto de clima; fora dele o resultado principal é o cálculo de referência (ver "Localização da propriedade").
- O clima é de reanálise/satélite para um ponto, com defasagem de alguns dias; não é medição na propriedade.
