# Sistema Inteligente de Suporte à Decisão para Gestão Hídrica em Propriedades Rurais

Protótipo acadêmico que informa ao produtor rural se ele precisa irrigar. O usuário informa cultura, solo, data de semeadura, data da análise e (opcionalmente) a última irrigação. O sistema usa o clima da localidade (Passo Fundo – RS) e responde com uma de três classes: *Sem necessidade de irrigação*, *Atenção: irrigação em breve* ou *Irrigação recomendada*.

O sistema **apenas recomenda**: não controla equipamentos, não usa sensores e não garante economia de água. Detalhes em [spec.md](spec.md).

## Instalação

```
py -3.14 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

(Testado com Python 3.14.3. Se alguma biblioteca não instalar, use `py -3.12`.)

## Gerar o modelo

```
.venv\Scripts\python pipeline.py
```

Baixa o clima diário da NASA POWER (2010-01-01 a 2025-06-30), simula as safras, gera o dataset e treina e compara os modelos. Leva cerca de 3 minutos. Sem internet, use `python pipeline.py --clima-sintetico` (clima gerado artificialmente; o arquivo `data/fonte_clima.txt` registra qual fonte foi usada).

Saídas: `data/clima.csv`, `data/dataset.csv`, `models/modelo.joblib`, `models/metadata.json`, `reports/metricas.csv`, `reports/selecao.txt`.

## Abrir a aplicação

```
.venv\Scripts\python app.py
```

Acesse http://127.0.0.1:5000.

## Testes

```
.venv\Scripts\python -m pytest
```

## Resultados da comparação de modelos

Conteúdo de `reports/metricas.csv`, gerado com clima real da NASA POWER. Validação: 2020–2021; teste: 2022–2024. O modelo selecionado (XGBoost) foi retreinado em treino + validação antes de ser avaliado no teste; os demais foram ajustados só no treino.

| modelo | f1_macro_validacao | acuracia_balanceada_validacao | recall_classe2_validacao | f1_macro_teste | acuracia_balanceada_teste | recall_classe2_teste | selecionado |
|---|---|---|---|---|---|---|---|
| RegressaoLogistica | 0.6976 | 0.7237 | 0.9248 | 0.7412 | 0.7488 | 0.8186 | False |
| RandomForest | 0.7983 | 0.8042 | 0.9299 | 0.8501 | 0.8493 | 0.9154 | False |
| XGBoost | 0.8285 | 0.8338 | 0.9467 | 0.8708 | 0.864 | 0.9028 | True |
| MLP | 0.7817 | 0.7962 | 0.9401 | 0.8401 | 0.8324 | 0.8724 | False |
| Dummy | 0.2211 | 0.3333 | 0.0 | 0.2267 | 0.3333 | 0.0 | False |

## Limitações

- **Os rótulos são simulados.** Não existem dados reais rotulados de "precisa irrigar". Os rótulos vêm de um balanço hídrico do solo (método FAO-56) aplicado a clima real e a safras simuladas. O modelo aprende a reproduzir esse cálculo a partir de um resumo do clima recente, da cultura, do solo e da última irrigação.
- **Métrica alta não é validade agronômica.** F1 e acurácia medem a concordância com a simulação, não o acerto de uma decisão de irrigação em campo. Não foi feita validação em campo.
- **Parâmetros a conferir.** Os valores de Kc, estágios, profundidade de raiz, fator p e umidade do solo (spec.md, seção 5) são valores de referência do FAO-56 e precisam ser conferidos pela equipe. O limiar da classe "Atenção" (metade do RAW) é uma escolha de produto, não um valor agronômico.
- O balanço assume solo na capacidade de campo na semeadura, precipitação efetiva igual à total e sem ascensão capilar.
- Localidade única (Passo Fundo – RS) e três culturas (milho, soja, feijão).
