🇧🇷 **Esta é a documentação em português (Brasil).** [Read in English →](./README.en.md)

# Assistente de Conhecimento

Um assistente de conhecimento local, com Docker Compose como ponto de partida, que fundamenta respostas em um corpus curado e se recusa a responder quando a evidência é insuficiente. Construído como um demonstrador de prova/produção sobre material sintético e abertamente licenciado.

> **UI ponta a ponta ativa.** Um bundle estático (nginx) consome uma superfície de marca configurável a partir de `GET /v1/identity`, permite ao operador escolher uma coleção + workspace, envia perguntas via `POST /v1/query` e renderiza um dos três estados honestos — *respondido* (com citações), *recusado* (`insufficient_evidence`) ou *erro*. A autenticação é configurável via `AUTH_ENABLED=true`; quando ativada, a UI exibe um campo de token bearer e encaminha `Authorization: Bearer …` em cada requisição. Cada requisição é auditada em JSON estruturado via `app.audit`.

---

## Visão Geral

- **Objetivo.** Uma stack local reproduzível: um serviço FastAPI, uma UI estática e um armazenamento PostgreSQL+pgvector, além de uma imagem `test` que executa `pytest` (com Playwright + Chromium dirigindo a UI ponta a ponta em `tests/e2e/`).
- **Não-objetivo.** Não é SaaS, não é implantação pública, não é pipeline de fine-tuning de modelo. Veja *Escopo & limites* abaixo.
- **Stack.** Python 3.12 (api/test), nginx (ui), PostgreSQL 16 com pgvector (db). `docker compose` é a única forma suportada de inicialização.

## Início Rápido

Requisitos: Docker Engine ≥ 29 e Docker Compose v2.

```bash
cp .env.example .env                     # valores placeholder; edite se necessário
docker compose config --quiet            # composição é válida
docker compose build --pull              # constrói todos os serviços
docker compose up -d --wait              # inicia e aguarda os healthchecks

curl -fsS http://127.0.0.1:8080/         # confirma que a UI está acessível
curl -fsS http://127.0.0.1:8080/healthz-ui  # probe interno da UI
                                       # `8080` é o que UI_PORT estiver definido
docker compose exec api curl -fsS \
   http://127.0.0.1:8000/healthz          # probe interno da API

# Executa os smoke tests de segurança:
docker compose run --rm test

# Executa o smoke E2E da UI — requer a stack ativa:
./scripts/smoke-ui.sh

# Executa a suíte completa: segurança + integração + aceitação + E2E + prova:
./scripts/test-all.sh
```

## Arquitetura

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│      ui      │    │      api     │    │      db      │
│  (nginx)     │◄──►│  (FastAPI)   │◄──►│  PostgreSQL  │
│  HTML/CSS/JS │    │  Python 3.12 │    │   +pgvector  │
└──────────────┘    └──────────────┘    └──────────────┘
                            ▲
                            │
                      ┌──────────────┐
                      │     test     │
                      │  pytest +    │
                      │  Playwright  │
                      └──────────────┘
```

- **ui/** — bundle estático servido por nginx. Configurável em tempo de execução via `GET /v1/identity`.
- **api/** — serviço FastAPI Python 3.12 com asyncpg + SQLAlchemy + Structured logs. Endpoints: `GET /v1/identity`, `GET /v1/collections`, `POST /v1/query`, `POST /v1/ingest`.
- **db/** — PostgreSQL 16 com pgvector. Schema e índice HNSW inicializados em `db/init.sql`.
- **test/** — imagem pytest com Playwright + Chromium para testes E2E da UI.

## API

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET`  | `/v1/identity` | Retorna configuração de marca, auth e identidade. |
| `GET`  | `/v1/collections?workspace=<id>` | Lista coleções disponíveis no workspace. |
| `POST` | `/v1/query` | Envia uma pergunta; retorna `answered` (com citações) ou `refused`. |
| `POST` | `/v1/ingest` | Ingere um documento (multipart) em uma coleção. |
| `GET`  | `/healthz` | Probe de saúde da API. |
| `GET`  | `/healthz-ui` | Probe de saúde da UI (via nginx). |

Todos os endpoints sob `/v1/*` requerem `Authorization: Bearer <token>` quando `AUTH_ENABLED=true`.

## Configuração

As variáveis de ambiente são lidas exclusivamente de `.env` (veja `.env.example`). Variáveis principais:

- `AUTH_ENABLED` — quando `true`, exige token bearer nas requisições.
- `AUTH_TOKEN` — token bearer pré-compartilhado.
- `EMBEDDING_STUB` — quando `true`, usa embedding determinístico local (padrão); quando `false`, usa a API OpenAI.
- `RETRIEVAL_MIN_SCORE` — limiar de similaridade do cosseno para aceitar uma resposta.
- `UI_PORT` — porta para a UI nginx (padrão `8080`).

## Segurança

- **Token bearer.** Quando `AUTH_ENABLED=true`, todas as requisições à API exigem `Authorization: Bearer <token>`.
- **Auditoria.** Cada requisição é registrada em JSON estruturado via `app.audit`.
- **Validação.** Entradas são validadas por Pydantic; payloads malformados retornam 422.
- **Segredos.** Nunca embutidos em código; sempre via env + `.env` (ignorado por git).

Veja `tests/security/` para a suíte de testes de segurança.

## Testes

```bash
# Segurança + integração + aceitação (dentro do container test):
docker compose run --rm test

# Smoke E2E da UI (requer stack ativa):
./scripts/smoke-ui.sh

# Suíte completa:
./scripts/test-all.sh
```

## Internacionalização

A UI possui i18n integrado:
- **Padrão:** português (Brasil) — `pt-BR`.
- **Alternar:** clique no botão "EN"/"PT" no cabeçalho para alternar.
- **Persistência:** a preferência é salva em `localStorage`.

## Licença

MIT — veja [LICENSE](./LICENSE). Copyright (c) 2026 Felipe Harms.

## Contribuindo

Issues e pull requests são bem-vindos. Para mudanças grandes, abra uma issue primeiro para discutir a abordagem.

---

🇧🇷 **Esta é a documentação em português (Brasil).** [Read in English →](./README.en.md)
