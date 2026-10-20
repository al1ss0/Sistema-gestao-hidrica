# spec.md — Sistema Inteligente de Suporte à Decisão para Gestão Hídrica

Projeto acadêmico de Ciência da Computação. Referência funcional: `Pré - Projeto.pdf`.
Tarefas de execução: [todo.md](todo.md).

## 1. O que é

Um protótipo web local que diz ao produtor rural se ele precisa irrigar. O usuário informa a cultura, o tipo de solo, a data de semeadura, a data da análise e a última irrigação. O sistema usa dados climáticos da localidade e responde com uma de três classes:

| Classe | Texto exibido |
|---|---|
| 0 | Sem necessidade de irrigação |
| 1 | Atenção: irrigação em breve |
| 2 | Irrigação recomendada |

A resposta vem de um modelo de Machine Learning escolhido entre Random Forest, XGBoost, regressão logística regularizada e MLP. O pré-projeto citava Decision Tree e KNN; a equipe os substituiu por XGBoost, regressão logística regularizada e MLP.

**O sistema apenas recomenda.** Ele não controla nenhum equipamento, não usa sensores e não garante economia de água.

## 2. Escopo fixo do protótipo

| Item | Valor |
|---|---|
| Localidade | Passo Fundo – RS (lat −28,26; lon −52,41; altitude 687 m) |
| Fonte do clima | NASA POWER, série diária (fallback: clima sintético gerado pelo próprio sistema) |
| Período do clima | 2010-01-01 a 2025-06-30 |
| Culturas | milho, soja, feijão |
| Solos | arenoso, médio, argiloso |
| Linguagem | Python 3.14 (fallback: 3.12) |
| Bibliotecas | pandas, numpy, scikit-learn, xgboost, joblib, matplotlib, flask, pytest |
| Interface | Flask, uma única página |
| Persistência | Arquivos CSV e joblib; sem banco de dados |

## 3. Como o sistema funciona

```
NASA POWER → data/clima.csv → simulação de safras (balanço hídrico FAO-56)
  → dataset rotulado → treino RF / XGBoost / Reg. logística / MLP → melhor modelo → models/modelo.joblib
Usuário → formulário Flask → features do dia → modelo → classe + gráfico
```

**Origem dos rótulos (limitação principal).** Não existem dados reais rotulados de "precisa irrigar". Os rótulos são gerados por um balanço hídrico do solo (método FAO-56) aplicado a clima real e a safras simuladas. O modelo aprende a reproduzir esse cálculo a partir de informações resumidas: clima dos últimos dias, cultura, solo e última irrigação. Acurácia alta significa concordância com a simulação, **não** validade agronômica. Isso deve ser dito na interface, no relatório e na apresentação.

## 4. Dados climáticos

URL de download (uma requisição):

```
https://power.larc.nasa.gov/api/temporal/daily/point?parameters=T2M_MAX,T2M_MIN,RH2M,WS2M,ALLSKY_SFC_SW_DWN,PRECTOTCORR&community=AG&longitude=-52.41&latitude=-28.26&start=20100101&end=20250630&format=JSON
```

Arquivo `data/clima.csv`, uma linha por dia:

| Coluna | Origem NASA | Unidade |
|---|---|---|
| data | chave da data (AAAAMMDD) | AAAA-MM-DD |
| tmax | T2M_MAX | °C |
| tmin | T2M_MIN | °C |
| ur | RH2M | % |
| vento | WS2M | m/s a 2 m |
| rad | ALLSKY_SFC_SW_DWN | MJ/m²/dia |
| chuva | PRECTOTCORR | mm/dia |

O valor −999 indica ausência. Faltas devem ser preenchidas por interpolação linear, exceto na chuva, onde viram 0.

**Clima sintético (fallback, seed 42)**, por dia, com `doy` = dia do ano e `s = cos(2π·(doy−15)/365)`:

- `tmax = 24 + 6·s + N(0,2)`
- `tmin = tmax − 10 + N(0,1)`
- `ur = clip(75 + N(0,8), 30, 100)`
- `vento = 2 + |N(0,0,7)|`
- `rad = clip(18 + 7·s + N(0,2), 2, 32)`
- `chuva`: chove com probabilidade de 0,3; quando chove, o volume é exponencial com média de 15 mm.

## 5. Parâmetros agronômicos

São valores de referência do FAO-56 (Tabelas 11, 12, 19 e 22). **A equipe deve conferi-los antes da entrega.**

| Cultura | Kc ini | Kc mid | Kc end | Estágios ini/dev/mid/late (dias) | Zr (m) | p |
|---|---|---|---|---|---|---|
| milho | 0,30 | 1,20 | 0,60 | 30 / 40 / 50 / 30 | 1,0 | 0,55 |
| soja | 0,40 | 1,15 | 0,50 | 20 / 30 / 60 / 25 | 1,0 | 0,50 |
| feijão | 0,40 | 1,15 | 0,35 | 20 / 30 / 40 / 20 | 0,7 | 0,45 |

| Solo | θFC (m³/m³) | θWP (m³/m³) |
|---|---|---|
| arenoso | 0,12 | 0,045 |
| médio | 0,25 | 0,12 |
| argiloso | 0,36 | 0,22 |

## 6. Cálculos (FAO-56)

### ET0 (Penman-Monteith diária)

Entradas: tmax, tmin, ur, vento (u2), rad (Rs), latitude (graus), altitude z (m) e dia do ano J.

```
T     = (tmax + tmin) / 2
P     = 101.3 * ((293 - 0.0065*z) / 293) ** 5.26
γ     = 0.000665 * P
e0(x) = 0.6108 * exp(17.27*x / (x + 237.3))
Δ     = 4098 * e0(T) / (T + 237.3) ** 2
es    = (e0(tmax) + e0(tmin)) / 2
ea    = ur / 100 * es
φ     = radians(latitude)
dr    = 1 + 0.033 * cos(2π*J/365)
δ     = 0.409 * sin(2π*J/365 - 1.39)
ωs    = arccos(-tan(φ) * tan(δ))
Ra    = (24*60/π) * 0.0820 * dr * (ωs*sin(φ)*sin(δ) + cos(φ)*cos(δ)*sin(ωs))
Rso   = (0.75 + 2e-5*z) * Ra
Rnl   = 4.903e-9 * ((tmax+273.16)**4 + (tmin+273.16)**4) / 2
        * (0.34 - 0.14*sqrt(ea)) * (1.35*min(Rs/Rso, 1.0) - 0.35)
Rn    = 0.77*Rs - Rnl
ET0   = (0.408*Δ*Rn + γ*(900/(T+273))*u2*(es-ea)) / (Δ + γ*(1 + 0.34*u2))
```

Teste de referência (Exemplo 18 do FAO-56): tmax 21,5; tmin 12,3; ur 70,56; u2 2,78; Rs 22,07; lat 50,8; z 100; J 187 → ET0 = 3,9 ± 0,1 mm/dia.

### Kc e ETc

O valor `d` é o número de dias após a semeadura, começando em 0. O Kc varia por estágio:

- **Inicial:** `Kc = Kc_ini`.
- **Desenvolvimento:** interpolação linear de Kc_ini a Kc_mid.
- **Intermediário:** `Kc = Kc_mid`.
- **Final:** interpolação linear de Kc_mid a Kc_end.

`ETc = Kc · ET0`. O ciclo termina em `d = ini + dev + mid + late`.

### Balanço hídrico e classe

```
TAW = 1000 * (θFC - θWP) * Zr
RAW = p * TAW
Dr(dia) = clip(Dr(dia anterior) - chuva - irrigação + ETc, 0, TAW)   # Dr no dia da semeadura (antes do dia 0) = 0
classe = 0 se Dr < 0.5*RAW;  1 se 0.5*RAW <= Dr < RAW;  2 se Dr >= RAW
lâmina recomendada (mm) = Dr   (repõe até a capacidade de campo; exibida só nas classes 1 e 2)
```

O fator 0,5 da classe 1 é uma escolha de produto, não um valor agronômico.

## 7. Simulação e dataset

Cada **cenário** combina:

- uma cultura;
- um solo;
- uma data de semeadura, em anos de 2010 a 2024, nos dias 01/10, 15/10, 01/11, 15/11 e 01/12;
- uma política de irrigação: `sequeiro` (nunca irriga) ou `irrigado`.

Na política `irrigado`, o sistema avalia cada dia: se o Dr do dia anterior for ≥ RAW, há 50% de chance de irrigar com lâmina igual a esse Dr. O gerador aleatório usa seed 42.

O total é de 3 × 3 × 5 × 2 × 15 = 1.350 cenários. Cada cenário vai do dia 0 ao fim do ciclo.

**Features** (calculadas para cada dia usando apenas aquele dia e os anteriores):

| Feature | Definição |
|---|---|
| cultura, solo | categóricas (one-hot) |
| dias_apos_semeadura, kc | — |
| et0_7d, etc_7d, chuva_7d, chuva_14d | somas dos últimos 7/14 dias, incluindo o dia |
| tmax_7d, ur_7d, vento_7d, rad_7d | médias dos últimos 7 dias |
| dias_desde_chuva | dias desde a última chuva ≥ 5 mm (máx. 60) |
| dias_desde_irrigacao | dias desde a última irrigação (0 se no dia; 60 se nunca; máx. 60) |
| lamina_ultima_irrigacao | mm (0 se nunca) |
| etc_menos_chuva_desde_irrigacao | soma de (ETc − chuva) desde a última irrigação, ou desde a semeadura se nunca houve |

**Alvo:** `classe`. **É proibido usar como feature:** Dr, TAW, RAW e qualquer valor de dias futuros.

**Linhas usadas:** apenas os dias com `dias_apos_semeadura >= 14` e múltiplos de 3, para reduzir o volume.

**Divisão por ano de semeadura** (nunca aleatória):

| Conjunto | Anos |
|---|---|
| Treino | 2010–2019 |
| Validação | 2020–2021 |
| Teste | 2022–2024 |

## 8. Machine Learning

**Tipo de problema:** classificação em 3 classes.

**Pré-processamento:** `Pipeline(ColumnTransformer(OneHotEncoder em cultura/solo, StandardScaler no resto), modelo)`.

**Grades de busca** (`GridSearchCV`, `scoring="f1_macro"`, `cv=GroupKFold(3)` agrupado por ano, somente no treino, `random_state=42`):

| Modelo | Grade |
|---|---|
| Nome no relatório | Classe | Grade |
|---|---|---|
| RegressaoLogistica | `LogisticRegression` (regularização L2, `max_iter=1000`) | C [0.1, 1, 10]; class_weight [None, "balanced"] |
| RandomForest | `RandomForestClassifier` (`n_jobs=-1`) | n_estimators [100]; max_depth [10, None]; class_weight [None, "balanced"] |
| XGBoost | `xgboost.XGBClassifier` (`tree_method="hist"`, `subsample=0.8`, `n_jobs=-1`) | n_estimators [200]; max_depth [4, 6]; learning_rate [0.1] |
| MLP | `MLPClassifier` (`early_stopping=True`, `max_iter=300`) | hidden_layer_sizes [(32,), (64, 32)]; alpha [0.0001, 0.001] |
| Dummy (baseline) | `DummyClassifier` | strategy "most_frequent" |

A regressão logística é o modelo linear de referência; o MLP e a regressão logística dependem do `StandardScaler` do pipeline.

**Seleção:** vence o maior F1-macro na validação. Em empate (diferença < 0,01), a preferência é pelo modelo mais simples: RegressaoLogistica, depois RandomForest, depois XGBoost, depois MLP. O vencedor é retreinado em treino + validação e avaliado **uma única vez** no teste.

**Saídas:**

- `reports/metricas.csv`: para cada modelo, F1-macro na validação e no teste, acurácia balanceada e recall da classe 2.
- `reports/selecao.txt`
- `models/modelo.joblib`
- `models/metadata.json`: nome, hiperparâmetros, lista de features, métricas e data.

## 9. Interface (Flask, página `/`)

**Formulário (GET `/`, POST `/`):**

| Campo | Regra |
|---|---|
| cultura | select |
| solo | select |
| data de semeadura | obrigatória |
| data da análise | obrigatória; posterior à semeadura; até o fim do ciclo; dentro do período de `data/clima.csv` |
| data da última irrigação | opcional; entre a semeadura e a data da análise |
| lâmina da última irrigação (mm) | obrigatória se houver data; maior que 0 |

Se houver erro, a página reexibe o formulário com a mensagem em português e não calcula nada.

**Resultado (na mesma página):**

1. A classe do modelo (texto da seção 1) e as probabilidades de cada classe.
2. A classe de referência calculada pelo balanço FAO-56, com Dr e RAW em mm, e um alerta se for diferente da classe do modelo.
3. A lâmina recomendada (mm), nas classes 1 e 2.
4. Um gráfico PNG dos últimos 30 dias: barras de chuva e irrigação, linha de ETc e, em um segundo painel, Dr com uma linha horizontal no RAW.
5. A tabela `reports/metricas.csv`.
6. Um aviso fixo: "Recomendação de suporte à decisão, baseada em dados climáticos e em rótulos simulados pelo método FAO-56. Não substitui avaliação técnica nem garante economia de água."

## 10. Estrutura de arquivos

```
config.py                 constantes das seções 2, 5 e 7
hidrica/__init__.py
hidrica/clima.py          download NASA POWER, clima sintético, carregar_clima()
hidrica/agro.py           et0(), kc(), balanco(), classificar()
hidrica/dataset.py        simular_cenario(), adicionar_features(), gerar_dataset()
hidrica/modelo.py         treinar_e_avaliar(), carregar_modelo()
hidrica/recomendacao.py   recomendar(entrada) usado pela interface
pipeline.py               executa clima → dataset → treino
app.py                    Flask
templates/index.html
tests/                    testes pytest
data/  models/  reports/  saídas geradas (não versionar data/ e models/)
requirements.txt  .gitignore  README.md
```

## 11. Critérios de pronto

- `python pipeline.py` gera `data/clima.csv`, `data/dataset.csv`, `models/modelo.joblib` e `reports/metricas.csv`.
- `pytest` passa 100%.
- `python app.py` abre em http://127.0.0.1:5000. Um formulário válido mostra a recomendação, o gráfico e o aviso; um formulário inválido mostra o erro.
- O README explica a instalação, a execução e as limitações da seção 3.
