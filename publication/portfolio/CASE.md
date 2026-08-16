# Assistente de Conhecimento Estilo RAG — Kit de Demo Local-First

> Um serviço de respostas baseado em citações, pronto para reprodução, que roda com um único `docker compose up` e nunca precisa de cartão de crédito. Cada resposta é fundamentada no corpus do próprio operador, recusa-se honestamente quando a evidência é fraca e vem com uma suíte de testes determinística que comprova o contrato.

🇧🇷 **Esta é a documentação em português (Brasil).** [Read in English →](./CASE.en.md)

---

## 1. Problema

Equipes do lado do cliente adotam assistentes retrieval-augmented para consolidar documentação interna, mas o caminho de "demo interessante" para "produção auditável" é pavimentado com trade-offs não ditos:

- **Confiança.** Um modelo de linguagem que pode responder *qualquer coisa* com confiança plausível é um passivo em qualquer fluxo de trabalho regulado. O comprador precisa verificar a alegação lendo a fonte da qual a resposta veio.
- **Recusa.** Quando o corpus não contém a resposta, uma resposta alucinada é pior do que nenhuma resposta. O sistema deve recusar explicitamente e dizer *por que* recusou.
- **Auditoria.** Uma demo que produz uma resposta bonita não é suficiente. Operadores precisam ver o que o sistema realmente fez em cada requisição, com segredos redactados, em um log que possam grepar.
- **Reprodutibilidade.** A maioria das stacks RAG deriva entre execuções porque o modelo de embedding ou o índice vetorial muda por baixo. Uma demo para comprador deve produzir a mesma resposta sobre o mesmo corpus a cada vez.
- **Fricção de implantação.** Uma solução SaaS gerenciada exige contrato, conexão, relação de cobrança e revisão de segurança. Operadores que não têm nada disso pronto precisam de uma alternativa local que possa ser exercitada ponta a ponta em uma única máquina.

Este projeto demonstra uma resposta pequena e contida a essas restrições, montada com peças prontas e open-source e validada por uma suíte de testes reproduzível.

## 2. Público-alvo

O público-alvo são equipes de entrega pequenas e médias que já têm um corpus de documentação interna e querem expô-lo por uma superfície estilo chat, sem levantar um backend gerenciado:

- **Suporte interno** — uma única equipe que possui uma base de conhecimento curada e quer uma forma de baixo risco de pilotar "pergunte aos documentos" sem alterar a residência de dados.
- **Auditoria pré-vendas** — um comprador que precisa percorrer a trilha de evidências ponta a ponta antes de aprovar um piloto.
- **Estúdios de serviço** — uma equipe de entrega de preço fixo que precisa de uma arquitetura de referência que possa adaptar sem pagar a um fornecedor de embedding enquanto a proposta ainda está sendo escrita.

**Não** é um chatbot voltado ao consumidor. Não é um SaaS multi-tenant. Não é um serviço RAG hospedado. A promessa de binário único vale apenas para a história local com docker-compose.

## 3. Solução

Uma stack de quatro serviços que roda em uma única máquina e se recusa a responder quando o corpus não dá suporte:

- Uma **UI estática** (HTML / CSS / JS vanilla servidos por nginx) que dirige cada interação a partir do teclado ou de uma tela touch.
- Um serviço **FastAPI** que lida com identidade, coleções, consultas e citações. Modelos Pydantic impõem validação estrita de requisições.
- Um armazenamento **Postgres + pgvector** que guarda o corpus e os vetores de embedding.
- Uma imagem de teste **Playwright + pytest** que executa os testes ponta a ponta no navegador e a execução de aceitação determinística.

A UI é construída em torno de três estados honestos de resposta:

- `answered` — o texto da resposta mais uma lista numerada de citações. Cada citação carrega o arquivo fonte, localização, score de cosseno e um snippet curto. Marcadores `[N]` inline dentro do corpo da resposta são links clicáveis que pulam para o card de citação correspondente.
- `refused` — um banner amarelo que afirma *"O corpus não tem resposta para esta pergunta."* e expõe o `best_score` e `threshold` calculados para que o operador possa auditar por quê.
- `error` — um banner vermelho com a mensagem de erro (já redactada) e um botão de ação primária: *"Abrir configurações de token"* em um 401, *"Tentar novamente"* em um 5xx ou falha de rede. O detalhe técnico bruto vive dentro de um `<details>` colapsado para nunca atrapalhar o título amigável.

O quarto estado — workspace vazio — é apresentado como um placeholder acionável em vez de um beco sem saída: o usuário é informado de que o workspace não tem coleções e recebe duas próximas etapas concretas (trocar de workspace pelo disclosure que abre automaticamente, ou ingerir via a API documentada).

## 4. Arquitetura e stack

```
                navegador host
                     │  :8080
                     ▼
             ┌───────────────┐
             │  ui (nginx)   │  HTML/CSS/JS estáticos
             └───────┬───────┘
                     │  /api/* →  api:8000
                     ▼
             ┌───────────────┐
             │  api (FastAPI)│  pydantic + audit + auth gate
             └───────┬───────┘
                     │  SQLAlchemy / asyncpg
                     ▼
             ┌───────────────┐
             │  db (pgvector)│  Postgres 16 + pgvector
             └───────────────┘

             ┌───────────────┐
             │  test         │  pytest + Playwright / Chromium
             │ (run --rm)    │  sob demanda; não faz parte de `up`
             └───────────────┘
```

| Componente | Escolha | Por quê |
|------------|---------|---------|
| Runtime da API | Python 3.12 + FastAPI + Pydantic | Validação estrita de requisições com `extra="forbid"`, limites de tamanho, rejeição de bytes NUL. |
| Armazenamento vetorial | PostgreSQL 16 + pgvector | Um binário, um alvo de backup, uma história real de `pg_dump`. Sem DB vetorial separado para operar. |
| UI | nginx + JS vanilla | Sem build step, sem lock-in de framework, sem supply chain. O bundle inteiro tem < 50 KB. |
| Auth | Gate configurável de Bearer-token | Comparação via `secrets.compare_digest`, falha fechado. `/healthz` e `/readyz` são sempre públicos. |
| Embeddings | Stub local determinístico | Faz hash de cada entrada para um vetor unitário de 1536 dimensões. A suíte de testes é reproduzível e sem credenciais pagas. Um adaptador de fornecedor é plugável (`EMBEDDING_STUB=false`). |
| Runner de teste | pytest + Playwright/Chromium | Dirige o navegador real ponta a ponta. Cada teste recebe um contexto fresh para que o localStorage não vaze entre casos de auth. |
| Observabilidade | Log de auditoria JSON estruturado | Uma linha por requisição com `rid`, `principal`, `method`, `path`, `status`, `latency_ms` e `extra` redactado. Padrões Bearer/skey/JWT/PEM são saneados. |

## 5. Decisões-chave

- **Três estados honestos, sem falhas silenciosas.** A UI nunca mostra um "carregando…" que nunca resolve. A API ou responde, recusa, ou levanta um erro — e a UI renderiza cada um explicitamente.
- **Citações são de primeira classe, não um afterthought.** Cada resposta carrega o arquivo fonte, localização, score e um snippet. Os marcadores `[N]` inline são links clicáveis que pulam para o card correspondente.
- **Recusa é um recurso.** O corpus é deliberadamente estreito para que a execução de aceitação possa exercitar o caminho de recusa. O limiar de recuperação (padrão `0.20`) é exposto na resposta de recusa para que o operador possa auditar por que o sistema recusou.
- **Sem lock-in de fornecedor para embeddings.** O adaptador stub é determinístico e usado pela suíte de testes. Trocar para um provedor real é uma mudança de configuração, não de código.
- **Aceitação reproduzível.** A execução de aceitação de 16 perguntas está fixada ao corpus embarcado e ao stub determinístico. O mesmo commit produz o mesmo `results.json` e `results.md`.
- **Retenção manual, não cron.** O pacote embarcado não roda nenhuma limpeza agendada. O procedimento de retenção é documentado e exige backup, preview de contagem de linhas, dry-run, a palavra literal de confirmação `DELETE`, e um backup pós-delete.
- **Sem hospedagem pública.** A história local com docker-compose é toda a história de implantação. Não há modo gerenciado, console admin hospedado, nem monitoramento 24/7.

## 6. Segurança e isolamento

- **Gate de auth.** Quando `AUTH_ENABLED=true`, cada requisição `/v1/*` deve carregar `Authorization: Bearer <token>` correspondente a `AUTH_TOKEN`. A comparação usa `secrets.compare_digest`. `/healthz` e `/readyz` são sempre públicos para que os probes não precisem de token.
- **Validação de entrada.** Cada corpo de requisição flui por modelos Pydantic com `extra="forbid"`, limites de tamanho e rejeição de bytes NUL. Veja `tests/security/test_validation.py`.
- **Log de auditoria estruturado.** `app/audit.py` emite uma linha JSON por requisição para STDOUT com `rid`, `principal`, `method`, `path`, `status`, `latency_ms` e `extra` redactado. Um saneador conservador (`scrub`, `scrub_mapping`) remove padrões Bearer/skey/JWT e zera chaves de header sensíveis.
- **Varredura de segredos.** `tests/security/test_secrets.py` percorre cada arquivo de texto no repositório e falha se qualquer conteúdo com formato de segredo (sk-…, JWT, Bearer …, bloco PEM, AWS access key id) vazar.
- **Isolamento de rede.** A porta do DB não é exposta no host. A UI é o único serviço com porta publicada; apenas a UI fala com a API através do reverse proxy.
- **Token em localStorage do navegador** é uma escolha deliberada para o gate de token estático sobre `localhost`. Uma implantação em produção com um IdP real deve trocar `api/app/auth.py` por OIDC / OAuth2 e mover o token para fora do `localStorage` (cookie `HttpOnly` + token CSRF). O gate está isolado em um único módulo, de modo que a troca é mecânica.

## 7. Resultados verificáveis

O contrato de reprodução é pequeno e concreto:

| Suíte | Contagem | Comando |
|-------|----------|---------|
| Segurança | 70 | `docker compose run --rm test pytest -q tests/security` |
| Integração | 20 | `docker compose run --rm test pytest -q tests/integration` |
| Aceitação | 8 | `docker compose run --rm test pytest -q tests/acceptance` |
| Ponta a ponta UI | 24 | `./scripts/smoke-ui.sh` |

Mais a cadeia canônica de fechamento em `scripts/test-publication.sh`, que executa cada verificador de costas para uma stack fresca.

**De 16 perguntas de aceitação, a execução de demonstração resolve 15 de forma limpa e expõe 1 drift conhecido**:

- **Q13 ("Quem venceu a final da Copa América de 2024?")** inesperadamente retornou `status=answered` com `best_score=0.2977` acima do limiar de recuperação de `0.20`. O corpus não contém conteúdo de esportes; a correspondência mais próxima foi um chunk em `indoor-herb-garden.md` cuja seção "Light Requirements" compartilha sobreposição incidental de tokens com a pergunta. O drift é uma limitação conhecida do embedding stub determinístico (ele faz hash de cada entrada para um vetor unitário, o que pode elevar fragmentos borderline acima do limiar). O verificador aceita o drift de 1/16 (6,25 %) dentro do orçamento de aceitação de 20 %. Limiares mais restritos recusariam Q13 mas também recusariam consultas legítimas on-topic — o limiar atual é o equilíbrio calibrado.

A discussão completa do gap está em the repository gap report e é preservada literalmente no repositório.

## 8. Limitações honestas

- **Sem conhecimento do mundo real.** O corpus embarcado é sintético e abertamente licenciado. O assistente não pode responder perguntas fora do seu corpus, e o corpus é estreito por design (cuidados com gatos, adoção de cachorros, fermentação, fitness, horta, licenciamento open-source, uma ferramenta Python fictícia).
- **Sem OCR, sem tabelas complexas, sem gráficos.** Apenas Markdown, texto plano e PDFs textuais são ingeridos. Imagens escaneadas, notas manuscritas e figuras multimodais estão fora do escopo.
- **Sem promessa de precisão perfeita.** Embeddings são com perdas. O assistente pode recusar corretamente e ainda assim errar uma resposta parcialmente suportada. Cada resposta carrega as citações nas quais foi fundamentada — leia-as.
- **Sem serviços externos vivos.** O adaptador de embedding é o stub local determinístico por padrão. Uma integração de fornecedor está disponível via configuração, mas não é exercitada pela suíte de testes (sem rede em CI).
- **Auth off por padrão.** O `.env` embarcado define `AUTH_ENABLED=false` para que a stack de demo seja permissiva. O gate de auth é ativado por uma única troca de configuração e é verificado ponta a ponta por `tests/e2e/test_ui_auth_gate.py`.
- **Token em localStorage.** O token persiste no `localStorage` do navegador para que um refresh em uma única aba mantenha o estado autenticado. Este é o trade-off certo para um gate de token estático sobre `localhost`; uma implantação real deve trocar o gate por um IdP adequado. O gate está isolado em um único módulo, de modo que a troca é mecânica.
- **Stub embedding.** O stub determinístico faz hash de cada entrada para um vetor unitário de 1536 dimensões. A suíte de testes é reproduzível porque o hashing é estável. Trocar para um embedding de fornecedor mudará os scores de cosseno e pode deslocar respostas borderline — o drift Q13 é o exemplo canônico dessa exposição.
- **Sem modo hospedado.** Sem URL pública, sem terminação TLS, sem multi-tenancy SaaS, sem billing. A inicialização é exclusivamente local (`docker compose up`).
- **Sem SLA, sem monitoramento 24/7.** Esta é uma demonstração reproduzível, não um serviço de produção.
- **Sem camada de raciocínio avançada.** A extensão "Intelligence" (recuperação multi-hop, uso de ferramentas agentic, cache semântico) está intencionalmente fora do escopo. A geração atual responde perguntas single-hop; multi-hop é uma linha de pesquisa separada.

## 9. Como rodar a demo

Requisitos: Docker Engine ≥ 29 e Docker Compose v2.

```bash
# 1. Clone o repositório
git clone <este-repo> assistente-de-conhecimento
cd assistente-de-conhecimento

# 2. Inicialize a configuração
cp .env.example .env                     # valores placeholder; edite se necessário

# 3. Construa, levante e verifique a stack
docker compose config --quiet            # a composição é válida
docker compose build --pull              # constrói todos os serviços
docker compose up -d --wait              # inicia e aguarda os healthchecks

# 4. Abra a demo
xdg-open http://127.0.0.1:8080/          # ou visite a URL no seu navegador
xdg-open http://127.0.0.1:8080/gallery/  # a galeria pronta para revisão

# 5. Execute a varredura completa de testes
docker compose run --rm test pytest -q tests/security
docker compose run --rm test pytest -q tests/integration
docker compose run --rm test pytest -q tests/acceptance
./scripts/smoke-ui.sh                    # testes de UI ponta a ponta
./scripts/test-publication.sh            # cadeia canônica de fechamento

# 6. Desmonte tudo (DESTRUTIVO: descarta o volume pgvector)
docker compose down -v
```

O serviço `test` está oculto por uma configuração `profiles: ["never"]`, então `docker compose up` não o inicia. Ele roda apenas sob demanda via `docker compose run --rm test …`.

### Onboarding com seu próprio corpus

1. Coloque arquivos Markdown, texto plano ou PDF textual em `data/corpus/`.
2. Reconstrua e levante a stack novamente:
   `docker compose build --pull api && docker compose up -d --wait`.
3. Reexecute a prova para atualizar `proof/results.json` e `proof/results.md`: `./scripts/run-proof.sh`.
4. Revise the repository gap report e atualize-o se os novos documentos cobrirem qualquer tópico de recusa em aberto — `enforces that every corpus document appears in the source map` exige que cada documento do corpus apareça no source map.

## 10. Refresh de stack e troca de embedding

O provedor é desacoplado pelo adaptador de embedding. O stub (`EMBEDDING_STUB=true`) é o adaptador local determinístico de hash para vetor usado para testes e execuções offline. Para trocar para um provedor OpenAI-compatível real:

```bash
# .env
EMBEDDING_STUB=false
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_API_KEY=<definido pelo secret manager — nunca comite>
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536
```

Em seguida, reconstrua a imagem da API:
`docker compose build --pull api && docker compose up -d --wait`.
A coluna de dimensão no armazenamento vetorial é criada por `ensure_schema()` com base em `EMBEDDING_DIM`, então mudar o valor sem um volume fresco levanta um erro de inicialização — isso é intencional.

---

## 11. Ponteiros para a fonte da verdade

- `README.md` — página de destino do repositório, início rápido.
- `publication/HANDOFF.md` — handoff único para o comprador.
- `publication/RETENTION.md` — procedimento de retenção manual.
- `publication/COPY.md` — copy comercial (promessa, entregáveis, limites, aceitação).
- `publication/UX-REVIEW.md` — auditoria independente de usabilidade que conduziu as melhorias de UX aplicadas nesta versão.
- the repository gap report — lista explícita de tópicos de recusa e o drift Q13.
- `scripts/test-publication.sh` — cadeia canônica de fechamento.
- `gallery/SHA256SUMS.reference` — hash de conteúdo dos quatro estados de revisão.

---

🇧🇷 **Esta é a documentação em português (Brasil).** [Read in English →](./CASE.en.md)
