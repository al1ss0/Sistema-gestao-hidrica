# todo.md — Tarefas de execução

Siga as tarefas **na ordem**. Todos os valores, fórmulas e nomes estão em [spec.md](spec.md); não invente outros.

## Regras para quem executa

1. Execute uma tarefa por vez e só passe para a próxima quando a **Verificação** dela der certo.
2. Rode todos os comandos na raiz do repositório. O Python do projeto é `.venv/Scripts/python` (Windows).
3. Não altere `spec.md`, não apague `Pré - Projeto.pdf` e não faça commit.
4. Se uma verificação falhar, corrija o código da própria tarefa e rode-a de novo. Se continuar falhando depois de 3 tentativas, pare e informe o erro exato.
5. Marque `[x]` somente depois que a verificação passar.

---

## Fase 1 — Ambiente

- [ ] **1.1 Criar o ambiente virtual.**
  Rode `py -3.14 -m venv .venv`. Se der erro, rode `py -3.12 -m venv .venv`. Se ainda der erro, rode `uv venv --python 3.12 .venv`.
  *Verificação:* `.venv/Scripts/python --version` mostra 3.14 ou 3.12.

- [ ] **1.2 Criar o `requirements.txt` e instalar as dependências.**
  O arquivo deve ter uma linha para cada pacote: `pandas`, `numpy`, `scikit-learn`, `xgboost`, `joblib`, `matplotlib`, `flask`, `pytest`.
  Rode `.venv/Scripts/python -m pip install -r requirements.txt`. Se a instalação falhar no 3.14, apague `.venv` e repita a 1.1 com 3.12.
  Depois rode `.venv/Scripts/python -m pip freeze > requirements.txt` para fixar as versões.
  *Verificação:* `.venv/Scripts/python -c "import pandas, numpy, sklearn, xgboost, joblib, matplotlib, flask, pytest"` não mostra erro.

- [ ] **1.3 Criar as pastas e o `.gitignore`.**
  Crie as pastas `hidrica/`, `templates/`, `tests/`, `data/`, `models/` e `reports/`, cada uma com um arquivo `.gitkeep`.
  O `.gitignore` deve ter as linhas `.venv/`, `__pycache__/`, `.pytest_cache/`, `data/*.csv` e `models/*.joblib`.
  Crie `hidrica/__init__.py` vazio.
  *Verificação:* `git status` não lista `.venv`.

## Fase 2 — Configuração e cálculos agronômicos

- [ ] **2.1 Criar `config.py`** com as constantes do spec.md:
  - `LAT = -28.26`, `LON = -52.41`, `ALT = 687`.
  - `DATA_INICIO = "2010-01-01"`, `DATA_FIM = "2025-06-30"`.
  - `CULTURAS`: dicionário `{nome: {"kc_ini", "kc_mid", "kc_end", "estagios": (ini, dev, mid, late), "zr", "p"}}` com os valores da seção 5.
  - `SOLOS`: dicionário `{nome: {"fc", "wp"}}` com os valores da seção 5.
  - `ALPHA = 0.5`, `SEED = 42`, `CHUVA_MIN = 5.0`, `MAX_DIAS = 60`.
  - `DATAS_SEMEADURA = [(10, 1), (10, 15), (11, 1), (11, 15), (12, 1)]` e `ANOS_SEMEADURA = range(2010, 2025)`.
  - `ANOS_TREINO = range(2010, 2020)`, `ANOS_VALIDACAO = (2020, 2021)`, `ANOS_TESTE = (2022, 2023, 2024)`.
  - `RAIZ = Path(__file__).parent`, `DATA_DIR`, `MODELS_DIR` e `REPORTS_DIR` (todos com `pathlib`).
  - `NOMES_CLASSES = {0: "Sem necessidade de irrigação", 1: "Atenção: irrigação em breve", 2: "Irrigação recomendada"}`.
  - `AVISO` com o texto da seção 9, item 6.

  *Verificação:* `.venv/Scripts/python -c "import config; print(len(config.CULTURAS), len(config.SOLOS))"` imprime `3 3`.

- [ ] **2.2 Criar `hidrica/agro.py`** com estas funções:
  - `et0(tmax, tmin, ur, vento, rad, lat, alt, doy)`: fórmula da seção 6, usando `numpy`. Deve funcionar com números e com arrays ou Series.
  - `duracao_ciclo(cultura) -> int`: soma dos 4 estágios.
  - `kc(cultura, d) -> float`: curva da seção 6.
  - `taw(cultura, solo) -> float` e `raw(cultura, solo) -> float`.
  - `classificar(dr, raw_mm, alpha=config.ALPHA) -> int`.

- [ ] **2.3 Criar `tests/test_agro.py`** com estes testes:
  - O `et0` do exemplo da seção 6 (tmax 21,5; tmin 12,3; ur 70,56; vento 2,78; rad 22,07; lat 50,8; alt 100; doy 187) fica entre 3,8 e 4,0.
  - Para o milho: `kc("milho", 0) == 0.30`; `kc("milho", 70) == 1.20`; `kc("milho", 50)` está entre 0,30 e 1,20 (valor esperado: 0,75); `kc("milho", 149)` está próximo de 0,60 (tolerância 0,05).
  - `taw("milho", "médio") == 130.0` (com tolerância de 1e-6).
  - `classificar`: com `raw_mm = 10`, Dr = 4,9 → 0; Dr = 5 → 1; Dr = 9,99 → 1; Dr = 10 → 2.

  *Verificação:* `.venv/Scripts/python -m pytest tests/test_agro.py` passa.

## Fase 3 — Clima

- [ ] **3.1 Criar `hidrica/clima.py`** com estas funções:
  - `baixar_nasa_power() -> pd.DataFrame`: faz um GET na URL da seção 4 com `urllib.request`, com timeout de 120 s, e lê `["properties"]["parameter"]`. Monta as colunas da seção 4, troca −999 por NaN, interpola as colunas numéricas (a chuva com NaN vira 0) e lança uma exceção se vier vazio.
  - `gerar_clima_sintetico(inicio=config.DATA_INICIO, fim=config.DATA_FIM, seed=config.SEED) -> pd.DataFrame`: fórmulas da seção 4, com as mesmas colunas.
  - `adicionar_et0(df) -> pd.DataFrame`: cria a coluna `et0` usando `agro.et0` com `config.LAT`, `config.ALT` e o `doy` da data.
  - `preparar_clima(sintetico=False) -> pd.DataFrame`: baixa os dados (ou gera os sintéticos se `sintetico=True` ou se o download falhar, imprimindo `"AVISO: usando clima sintético"`), adiciona o `et0`, salva `data/clima.csv` e grava em `data/fonte_clima.txt` a palavra `nasa_power` ou `sintetico`.
  - `carregar_clima() -> pd.DataFrame`: lê `data/clima.csv`, com `data` como datetime e índice.

- [ ] **3.2 Criar `tests/conftest.py`** com uma fixture `clima` (escopo `session`) que retorna `adicionar_et0(gerar_clima_sintetico())` indexado por `data`. Nenhum teste pode depender da internet.

- [ ] **3.3 Criar `tests/test_clima.py`** com estes testes:
  - O clima sintético tem as 7 colunas da seção 4 e nenhum NaN.
  - `ur` fica entre 30 e 100, e `chuva` é sempre ≥ 0.
  - O `et0` é > 0 em todas as linhas.
  - Duas chamadas com a mesma seed geram DataFrames iguais.

  *Verificação:* `.venv/Scripts/python -m pytest tests/test_clima.py` passa.

## Fase 4 — Simulação e dataset

- [ ] **4.1 Criar `hidrica/dataset.py`** com:
  - Constantes:
    - `CATEGORICAS = ["cultura", "solo"]`;
    - `NUMERICAS` = as features numéricas da seção 7;
    - `FEATURES = CATEGORICAS + NUMERICAS`;
    - `PROIBIDAS = ["dr", "taw", "raw"]`.
  - `simular_cenario(clima, cultura, solo, semeadura, politica, rng=None, irrigacoes=None, data_fim=None) -> pd.DataFrame`:
    - Percorre os dias de `semeadura` até o fim do ciclo, ou até `data_fim` se for informado.
    - `politica` pode ser `"sequeiro"`, `"irrigado"` (regra da seção 7, usando `rng.random() < 0.5`) ou `"manual"` (usa `irrigacoes`, um dict `{data: mm}`).
    - Aplica o balanço da seção 6.
    - Retorna uma linha por dia com as colunas `data, d, cultura, solo, kc, et0, etc, chuva, irrigacao, tmax, ur, vento, rad, dr, taw, raw, classe`.
  - `adicionar_features(df) -> pd.DataFrame`: cria as features da seção 7 para **um** cenário, usando apenas o dia e os anteriores (`rolling(window, min_periods=1)`).
  - `gerar_dataset(clima) -> pd.DataFrame`:
    - Percorre os 1.350 cenários da seção 7, com `rng = np.random.default_rng(config.SEED)` criado uma única vez.
    - Adiciona as colunas `cenario_id` e `ano` (ano de semeadura).
    - Aplica as features e o filtro de linhas da seção 7.
    - Salva `data/dataset.csv` e retorna o DataFrame.
  - `dividir(df) -> (treino, validacao, teste)`: separa por `ano`, conforme a seção 7.

- [ ] **4.2 Criar `tests/test_dataset.py`** usando a fixture `clima`:
  - Em um cenário `milho/arenoso/2015-10-01/irrigado`, `dr` fica sempre entre 0 e `taw`.
  - Um cenário `sequeiro` tem `irrigacao == 0` em todas as linhas.
  - O número de linhas de um cenário é igual a `duracao_ciclo`.
  - Teste anti-vazamento: alterar a chuva de um dia futuro (`d = 100`) não muda nenhuma feature em `d = 50`.
  - Nenhuma coluna de `PROIBIDAS` está em `FEATURES`.
  - Em `dividir`, os conjuntos de anos de treino, validação e teste não se sobrepõem.

  *Verificação:* `.venv/Scripts/python -m pytest tests/test_dataset.py` passa.

## Fase 5 — Modelos

- [ ] **5.1 Criar `hidrica/modelo.py`** com:
  - `criar_pipeline(estimador) -> Pipeline`: monta o pré-processamento da seção 8.
  - `treinar_e_avaliar(df, pasta_saida=config.RAIZ, rapido=False) -> dict`:
    1. Divide os dados com `dividir`.
    2. Roda o `GridSearchCV` das 4 grades da seção 8 (RegressaoLogistica, RandomForest, XGBoost, MLP) no treino, com `groups = treino["ano"]`. Fixe `random_state=42` em todos os modelos que aceitam esse parâmetro.
    3. Ajusta o Dummy.
    4. Calcula, na validação, o F1-macro, a acurácia balanceada e o recall da classe 2 de cada modelo.
    5. Escolhe o vencedor pela regra da seção 8.
    6. Usa como modelo final o vencedor ajustado **só no treino**, sem retreinar com a validação, porque os anos de validação calibram a predição conformal (`hidrica/conformal.py`). Avalia no teste todos os modelos (os outros só para a tabela).
    7. Calibra a predição conformal na validação e avalia a cobertura no teste.
    8. Salva `reports/metricas.csv`, `reports/selecao.txt`, `reports/conformal.csv`, `models/modelo.joblib` e `models/metadata.json` dentro de `pasta_saida`.

    Com `rapido=True`, usa 3.000 linhas amostradas do treino (seed 42) e só o primeiro valor de cada grade (para os testes). A amostra deve ser estratificada por `classe` (por exemplo, com `train_test_split(..., train_size=3000, stratify=treino["classe"], random_state=42)`), porque o XGBoost falha se faltar alguma das classes 0, 1 ou 2.
  - `carregar_modelo(pasta=config.RAIZ) -> (pipeline, metadata)`.

- [ ] **5.2 Criar `tests/test_modelo.py`**, com uma fixture de escopo `session` que roda `gerar_dataset(clima)` e `treinar_e_avaliar(df, tmp_path_factory.mktemp("saida"), rapido=True)`:
  - `metricas.csv` tem 5 linhas (RegressaoLogistica, RandomForest, XGBoost, MLP, Dummy).
  - `metadata.json` tem as chaves `modelo`, `hiperparametros`, `features`, `metricas` e `data`.
  - O modelo carregado retorna em `predict_proba` 3 probabilidades por linha, que somam 1 (tolerância 1e-6).
  - Rodar duas vezes com `rapido=True` gera o mesmo `metricas.csv`.

  *Verificação:* `.venv/Scripts/python -m pytest tests/test_modelo.py` passa.

  `gerar_dataset` está em `dataset.py`, mas é chamado aqui pela fixture. Se ele demorar mais de 5 minutos, otimize-o com listas Python em vez de `df.loc` dentro do laço.

## Fase 6 — Pipeline completo

- [ ] **6.1 Criar `pipeline.py`**, que aceita o argumento opcional `--clima-sintetico` e executa: `preparar_clima(sintetico)` → `gerar_dataset` → `treinar_e_avaliar`. Ao final, imprime `reports/selecao.txt`.

- [ ] **6.2 Rodar `.venv/Scripts/python pipeline.py`.**
  *Verificação:* existem `data/clima.csv`, `data/dataset.csv`, `models/modelo.joblib`, `models/metadata.json`, `reports/metricas.csv` e `reports/selecao.txt`. Leia `data/fonte_clima.txt` e informe se o clima é `nasa_power` ou `sintetico`. Copie o conteúdo de `reports/metricas.csv` para o relatório final da execução, **sem** alterar os números.

## Fase 7 — Serviço de recomendação

- [ ] **7.1 Criar `hidrica/recomendacao.py`** com:
  - `validar(form: dict, clima) -> (entrada: dict | None, erros: list[str])`: aplica as regras da seção 9, com mensagens em português, por exemplo `"A data da análise deve ser posterior à semeadura."`.
  - `recomendar(entrada, clima, modelo, metadata) -> dict`:
    1. Roda `simular_cenario(..., politica="manual", irrigacoes={data_irrigacao: lamina} ou {}, data_fim=data_analise)` e depois `adicionar_features`. Pega a última linha.
    2. Faz `modelo.predict_proba(linha[metadata["features"]])`.
    3. Retorna `classe_modelo`, `texto_modelo`, `probabilidades` (dict texto → %), `classe_referencia`, `texto_referencia`, `divergente`, `dr`, `raw`, `lamina` (`None` na classe 0), `grafico` (PNG em base64, gerado com matplotlib usando o backend `"Agg"`, conforme a seção 9, item 4) e `aviso = config.AVISO`.

- [ ] **7.2 Criar `tests/test_recomendacao.py`** (usando o modelo da fixture de `test_modelo.py`; se preciso, mova a fixture para `conftest.py`):
  - Um formulário sem data de semeadura gera um erro.
  - Uma data de análise anterior à semeadura gera um erro.
  - Uma data de irrigação informada sem lâmina gera um erro.
  - Um formulário válido (milho, médio, semeadura 2016-10-15, análise 2017-01-10) retorna um dict com todas as chaves, as probabilidades somando ~100 e `grafico` como uma string não vazia.

  *Verificação:* `.venv/Scripts/python -m pytest tests/test_recomendacao.py` passa.

## Fase 8 — Interface Flask

- [ ] **8.1 Criar `app.py`** com `create_app(pasta=config.RAIZ, clima=None)`:
  - Carrega o clima (de `carregar_clima()`, se não for passado) e o modelo uma única vez.
  - Rota `/` (GET e POST): chama `validar` e, se não houver erros, `recomendar`, e renderiza `index.html`.
  - Se o modelo não existir, a página mostra `"Modelo não encontrado. Execute: python pipeline.py"`.
  - Ao final do arquivo: `if __name__ == "__main__": create_app().run(host="127.0.0.1", port=5000, debug=False)`.
  - Nenhum cálculo pode ser feito dentro de `app.py`; ele só chama `hidrica.recomendacao`.

- [ ] **8.2 Criar `templates/index.html`**:
  - Formulário com os campos da seção 9, mantendo os valores digitados depois do envio.
  - Lista de erros em vermelho.
  - Bloco de resultado com os itens 1 a 6 da seção 9, nessa ordem.
  - Gráfico como `<img src="data:image/png;base64,...">`.
  - CSS simples dentro de `<style>`, sem bibliotecas externas e sem JavaScript.

- [ ] **8.3 Criar `tests/test_app.py`** (com o Flask test client, o modelo da fixture e o clima sintético):
  - GET `/` → status 200 e contém `<form`.
  - POST inválido (sem datas) → 200 e contém a mensagem de erro.
  - POST válido (o caso da 7.2) → 200 e contém `"Recomendação de suporte à decisão"`, `data:image/png;base64` e um dos 3 textos de classe.
  - Uma pasta sem modelo → a página contém `"Modelo não encontrado"`.

  *Verificação:* `.venv/Scripts/python -m pytest tests/test_app.py` passa.

- [ ] **8.4 Teste manual da aplicação real.**
  1. Rode `.venv/Scripts/python app.py` em segundo plano.
  2. Com `curl`, faça um GET em `http://127.0.0.1:5000/` e confirme o status 200.
  3. Faça um POST com o caso da 7.2 e confirme que a resposta contém um texto de classe.
  4. Encerre o servidor.

## Fase 9 — Documentação e verificação final

- [ ] **9.1 Escrever o `README.md`** com:
  - o título do projeto;
  - o que o sistema faz (resumo da seção 1 do spec);
  - a instalação (comandos da fase 1);
  - como gerar o modelo (`python pipeline.py` e a opção `--clima-sintetico`);
  - como abrir a aplicação (`python app.py` → http://127.0.0.1:5000);
  - como rodar os testes (`python -m pytest`);
  - a tabela de `reports/metricas.csv` copiada sem alterar os números;
  - as **Limitações**: o texto da seção 3 do spec, mais o aviso de que os parâmetros da seção 5 precisam ser conferidos pela equipe.

- [ ] **9.2 Verificação final.**
  1. Rode `.venv/Scripts/python -m pytest` e confirme que 100% dos testes passam.
  2. Confira cada item da seção 11 do spec.md.
  3. Informe como resultado:
     - a lista dos arquivos criados;
     - a saída do pytest;
     - a fonte do clima usada;
     - o conteúdo de `reports/metricas.csv` e `reports/selecao.txt`;
     - qualquer item da seção 11 que não tenha sido atendido.

---

## Fora do escopo do executor (tarefas da equipe)

Veja [proximos_passos.md](proximos_passos.md).
