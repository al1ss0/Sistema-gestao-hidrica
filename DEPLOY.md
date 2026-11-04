# Publicação: GitHub e hospedagem

## Como o projeto é publicado

O sistema é **uma única aplicação Flask** que serve a interface (HTML, CSS e JavaScript) e a API (`/analise`, `/api/municipios`, `/saude`). Por isso ele precisa de uma hospedagem que execute Python, e **o GitHub Pages não serve**: ele só entrega páginas estáticas.

| Papel | Onde |
|---|---|
| Código, histórico e revisão | **GitHub** |
| Testes automáticos a cada push | **GitHub Actions** (`.github/workflows/ci.yml`) |
| Aplicação no ar (interface + backend) | **Render**, usando o `Dockerfile` (ou qualquer hospedagem que rode contêineres) |

Manter interface e backend juntos é a opção mais simples e barata para este protótipo: um serviço, um endereço, sem CORS. Se um dia a interface precisar de outro time ou de uma CDN, o backend já expõe as rotas de dados em JSON (`/api/municipios`) e pode ser separado.

## O que já está pronto no repositório

| Arquivo | Função |
|---|---|
| `wsgi.py` | Entrada de produção: `gunicorn wsgi:app` |
| `Dockerfile` / `.dockerignore` | Imagem de produção (Python 3.14, gunicorn, usuário sem privilégios, `HEALTHCHECK`) |
| `render.yaml` | Blueprint do Render: serviço web, variáveis de ambiente e verificação de saúde em `/saude` |
| `requirements.txt` / `requirements-dev.txt` | Dependências de execução (versões fixas) e de desenvolvimento |
| `.github/workflows/ci.yml` | Roda os testes no GitHub a cada push e pull request |
| `models/modelo.joblib` | Modelo treinado. **Precisa estar no git**, porque a hospedagem não treina |

## Passo 1: enviar o código ao GitHub

1. Crie um repositório vazio em https://github.com/new (sem README, sem `.gitignore`, sem licença, para não conflitar com o histórico local).
2. Na pasta do projeto:

```
git add -A
git commit -m "Seleção de localidade e preparação para hospedagem"
git remote add origin https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git
git push -u origin main
```

3. Abra a aba **Actions** do repositório e confirme que o workflow **CI** ficou verde.

Antes do primeiro `push`, confira que `git status` lista `models/modelo.joblib`, `models/metadata.json` e `reports/metricas.csv` (são os arquivos que a hospedagem usa).

## Passo 2: colocar no ar no Render

1. Crie uma conta em https://render.com e conecte-a ao seu GitHub.
2. **New → Blueprint** e escolha o repositório. O Render lê o `render.yaml` e cria o serviço `hidrodecisao`.
3. Aguarde o build (alguns minutos). Quando o serviço estiver **Live**, o endereço aparece no painel (algo como `https://hidrodecisao.onrender.com`). O HTTPS já vem configurado.
4. Teste: abra o endereço, acesse `/saude` (deve mostrar `{"modelo":true,"status":"ok"}`) e faça uma análise escolhendo um município.

A partir daí, **cada `git push` na branch principal faz um novo deploy** (`autoDeploy: true`).

### Variáveis de ambiente

| Variável | Valor no `render.yaml` | Para que serve |
|---|---|---|
| `PORT` | definida pelo Render | Porta em que o gunicorn escuta |
| `HIDRO_PROXY` | `1` | Atrás do proxy do Render, lê o IP real do visitante (necessário ao limite de consultas). **Não ligue fora de um proxy**, senão o cabeçalho pode ser forjado |
| `HIDRO_ATUALIZAR` | `0` | Sem arquivo de clima salvo, não há o que atualizar na inicialização |
| `HIDRO_LIMITE_POR_MIN` | `30` | Consultas por minuto por visitante que acionam serviços externos (`0` desliga o limite) |

## Testar a imagem antes de publicar

```
docker build -t hidrodecisao .
docker run --rm -p 8000:8000 hidrodecisao
```

Abra http://127.0.0.1:8000.

## Funcionamento em produção

- **Clima sob demanda.** Não há `data/clima.csv` na imagem: para cada análise o sistema busca na NASA POWER só o período necessário e guarda em cache na memória (6 h, no máximo 128 entradas).
- **Nada é gravado em disco** e não há banco de dados; reiniciar o serviço não perde nada.
- **Memória.** Um processo (`--workers 1 --threads 4`) mantém o modelo carregado uma só vez, o que cabe nos 512 MB do plano gratuito. Para mais tráfego, aumente `--threads` ou o plano antes de aumentar os processos.
- **Plano gratuito do Render.** O serviço "dorme" após um período sem acessos e a primeira visita seguinte demora para responder (o contêiner precisa subir). Confira os limites e preços atuais em https://render.com/pricing, pois mudam.

## Serviços de terceiros e limites

| Serviço | Uso | Observação |
|---|---|---|
| **NASA POWER** | Clima diário | Gratuito. Cada análise de outra localidade faz uma consulta (cerca de 1 a 3 s) |
| **Open-Meteo** (geocodificação e altitude) | Achar o município e a altitude | API gratuita **de uso não comercial**, com limite diário de consultas. Para uso comercial ou tráfego alto é preciso contratar um plano ou trocar de provedor. Os dados de geocodificação vêm do GeoNames (CC BY 4.0), e a atribuição está na página "Sobre" |

O limite por IP e o cache existem para que um uso excessivo, ou um abuso, não esgote essas cotas.

## Segurança já aplicada

- Servidor de produção (gunicorn), `debug` desligado, contêiner executado por usuário sem privilégios.
- Entradas validadas (datas, números, coordenadas dentro do Brasil, tamanho dos textos); saídas escapadas pelo Jinja2.
- Cabeçalhos: `Content-Security-Policy` (só scripts e estilos do próprio site), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff` e `Referrer-Policy`.
- Limite de consultas por IP nas rotas que chamam serviços externos.
- Não há cadastro, login nem armazenamento de dados do usuário. A localização informada é enviada à NASA POWER e ao Open-Meteo para obter o clima e a altitude; isso está descrito na página "Sobre".

## Atualizar o modelo ou os dados

1. Localmente: `python pipeline.py` (retreina com o clima mais recente).
2. Confira `reports/metricas.csv` e `reports/selecao.txt`.
3. Faça commit de `models/modelo.joblib`, `models/metadata.json` e `reports/metricas.csv` e dê `push`: a hospedagem faz o deploy sozinha.

O modelo só precisa ser retreinado para mudar o que ele sabe (novas safras, outras regiões). O clima das análises é sempre buscado na hora.

## Outras hospedagens

O mesmo `Dockerfile` funciona em Fly.io, Railway, Google Cloud Run e Hugging Face Spaces (tipo Docker). Basta apontar o serviço para o repositório, definir `HIDRO_PROXY=1` e usar `/saude` como verificação de saúde. A porta vem da variável `PORT`, que essas plataformas definem.

## O que foi e o que não foi verificado

Estado em 03/11/2026, durante o desenvolvimento:

| Item | Situação |
|---|---|
| 137 testes automatizados (Windows, Python 3.14) | Passam |
| Aplicação em execução com NASA POWER e Open-Meteo reais (município, coordenadas, outras regiões, erros) | Verificado |
| Todas as dependências fixadas têm pacote pronto para **Linux x86_64 com Python 3.14** (sem compilar), incluindo `xgboost-cpu` | Verificado no PyPI |
| Sintaxe de `.github/workflows/ci.yml` e `render.yaml` | Verificada (arquivos YAML válidos) |
| **Build e execução da imagem Docker** | **Não verificado.** O ambiente de desenvolvimento não tinha rede dentro dos contêineres (o `apt` e o `pip` não conseguiram baixar nada), então a imagem não foi construída. A imagem base `python:3.14-slim` existe. Rode `docker build` e `docker run` (seção acima) na sua máquina antes de confiar nela |
| Execução do workflow no GitHub Actions | Não verificado (depende de o repositório existir no GitHub) |
| Deploy no Render | Não verificado (depende da conta de vocês). O formato de `render.yaml` segue a documentação do Render, mas vale conferir no painel se o Blueprint foi aceito sem avisos |

Se o `docker build` falhar, o ponto mais provável é a instalação do `libgomp1` (necessário ao XGBoost no Linux) ou alguma diferença do Render; a mensagem de erro aponta o passo.

## Lista antes de divulgar o endereço

- [ ] CI verde no GitHub.
- [ ] `/saude` responde `ok` no endereço público.
- [ ] Uma análise por município e uma por coordenadas funcionam no endereço público.
- [ ] Os parâmetros agronômicos (Kc, estágios, raízes, fator p, umidades do solo) foram conferidos pela equipe: são valores de referência do FAO-56 e ainda não foram validados.
- [ ] Todos sabem que o modelo só vale no local de treino e que, nas demais localidades, o resultado principal é o cálculo de referência.
