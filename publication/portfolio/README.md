# Estudo de Caso — Assistente de Conhecimento Local-First

> Um serviço de respostas baseado em citações, pronto para reprodução, que roda com um único `docker compose up` e nunca precisa de cartão de crédito. Cada resposta é fundamentada no corpus do próprio operador, recusa-se honestamente quando a evidência é fraca e vem com uma suíte de testes determinística que comprova o contrato.

🇧🇷 **Esta é a documentação em português (Brasil).** [Read in English →](./README.en.md)

## Comece aqui

- **[CASE.md](CASE.md)** — o estudo de caso completo: problema, público-alvo, solução, arquitetura, stack, decisões, segurança, resultados verificados, limitações honestas e como rodar a demo.
- **[SHORT-COPY.md](SHORT-COPY.md)** — três parágrafos reutilizáveis que você pode colar em uma proposta, um bullet de currículo ou um site de portfólio.
- **[INDEX.md](INDEX.md)** — um índice navegável de cada seção do estudo de caso, com o cabeçalho da seção e um resumo de uma linha.
- **[assets/](assets/)** — capturas de tela prontas para revisão da galeria: idle, answered, refused e o banner de erro amigável.

## O que este caso não é

- **Não** é a fonte do código. O código vive na raiz do repositório e em `ui/`, `api/`, `db/`, `tests/` e `scripts/`.
- **Não** é uma página de marketing. Os resultados verificados e as limitações honestas são seções obrigatórias, não opcionais.
- **Não** é uma publicação externa. Nada aqui é postado em uma plataforma de terceiros; este é um artefato local que visitantes podem navegar junto com o código.

## Como o caso se mantém honesto

- O estudo de caso cita as contagens de testes (`70 segurança + 20 integração + 8 aceitação + 24 ponta a ponta = 122`) literalmente das suítes reproduzíveis.
- O drift Q13 ("Quem venceu a final da Copa América de 2024?") é declarado como uma limitação conhecida, porque o embedding stub determinístico eleva um fragmento borderline acima do limiar de recuperação. O drift é documentado em `proof/gaps.md` e é preservado literalmente no repositório.
- A postura exclusivamente local é declarada explicitamente: sem modo hospedado, sem SLA, sem monitoramento 24/7, sem endpoint público.
- A troca de trade-off do token em localStorage é declarada como uma escolha deliberada do gate de token estático, não como um padrão recomendado para implantação em produção.

## Como reproduzir os resultados

Os números verificáveis do estudo de caso vêm destes comandos:

```bash
# Levanta a stack
docker compose up -d --wait

# Executa a suíte completa de testes
docker compose run --rm test pytest -q tests/security
docker compose run --rm test pytest -q tests/integration
docker compose run --rm test pytest -q tests/acceptance
./scripts/smoke-ui.sh

# Cadeia canônica de fechamento
./scripts/test-publication.sh
```

A mesma cadeia roda em CI e em um clone fresco. Não há nenhum passo manual entre os comandos e os números verificáveis citados neste estudo de caso.

## Documentação bilíngue

Este portfólio é publicado em português (Brasil) como apresentação principal, com inglês claramente acessível:

- **Português (Brasil):** `README.md`, `CASE.md`, `INDEX.md`, `SHORT-COPY.md`.
- **Inglês:** `README.en.md`, `CASE.en.md`, `INDEX.en.md`, `SHORT-COPY.en.md`.

Os identificadores técnicos (nomes de env, endpoints de API, nomes de funções/classes, SQL, serviços Docker, identificadores JS) permanecem em inglês para preservar os contratos.

---

🇧🇷 **Esta é a documentação em português (Brasil).** [Read in English →](./README.en.md)
