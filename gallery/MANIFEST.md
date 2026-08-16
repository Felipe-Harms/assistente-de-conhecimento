# Manifesto da Galeria — Assistente de Conhecimento

> Fonte: capturado por `scripts/run-demo.sh` (Playwright + Chromium 1148
> no container de teste). Determinístico contra o corpus embarcado e o
> adaptador de embedding stub determinístico. Regenere a qualquer momento
> com `./scripts/run-demo.sh`.

🇧🇷 **Esta é a documentação em português (Brasil).** [Read in English →](./MANIFEST.en.md)

Este manifesto é o inventário canônico da galeria pronta para revisão.
Cada arquivo PNG referenciado aqui é verificado por `scripts/verify-gallery.sh`
quanto à presença, cabeçalho PNG válido, dimensões razoáveis e tamanho não-zero.

## Estados exigidos

A demo comprova os quatro estados explícitos da UI que o comprador pode auditar:

- **idle** — UI carregada com a superfície de marca, nenhuma pergunta submetida.
- **answered** — pergunta on-topic, citações renderizadas com arquivo + score + snippet.
- **refused** — pergunta off-topic, banner `insufficient_evidence` com `reason` e `best_score` / `threshold`.
- **auth-error** — UI exibe um 401 (simulado via interceptação `page.route()` do Playwright; a API live é intencionalmente `AUTH_ENABLED=false` para a demo).

O corpus embarcado é pequeno e sintético; a pergunta on-topic
("vacinações para um cachorro adotado") é reproduzível. Re-executar
`scripts/run-demo.sh` produz capturas visualmente idênticas, byte-diferentes,
porque a UI não embute relógio nem seed aleatório.

## Inventário

| Estado | Arquivo | Dimensões (L×A) | Bytes | Query fonte |
|--------|---------|-----------------|-------|-------------|
| idle | `01-idle.png` | 1280 × 877 | 107,634 | (nenhuma) — UI inicial |
| answered | `02-answered.png` | 1280 × 1868 | 298,835 | "Que vacinações essenciais um cachorro recém-adotado precisa?" |
| refused | `03-refused.png` | 1280 × 878 | 113,283 | "Qual é a velocidade da luz no vácuo em metros por segundo?" |
| auth-error | `04-auth-error.png` | 1280 × 878 | 98,178 | "Esta UI vai exibir um 401?" (Playwright route 401) |

## Procedência

As capturas são produzidas dentro do container de teste em execução,
que roda o cliente Playwright Python contra o Chromium 1148. A UI é
carregada em `http://ui:80?workspace=<gallery-uuid>` para que cada captura
fique isolada. Nenhum dado real de cliente, nenhuma marca de terceiros
e nenhuma credencial embutida estão presentes em qualquer PNG; as
capturas são superfície de UI vazia sobre o stub local.

Os mesmos PNGs podem ser regenerados executando:

```bash
./scripts/run-demo.sh        # captura
./scripts/verify-gallery.sh   # valida contra este manifesto
```

`scripts/verify-gallery.sh` sai com código não-zero se:

- Um PNG listado aqui estiver faltando.
- Um PNG tiver cabeçalho corrompido ou não-PNG.
- As dimensões estiverem fora do intervalo de sanidade 800×600 / 4096×4096.
- O manifesto não referenciar todos os quatro estados.
- Qualquer conteúdo com formato de segredo aparecer em `scripts/_demo_*.py`
  ou `scripts/run-demo.sh` (varredura defensiva; a galeria em si não
  pode carregar segredos por construção).

## Variação conhecida de tamanho da UI

A captura `02-answered.png` é mais alta (1868 px) porque o card de
citações é renderizado abaixo da resposta e a página é capturada em
modo `full_page=True`. Os outros três estados cabem na viewport
(~878 px). Este é o comportamento esperado da UI estática e não uma
regressão.

## Limitações disclosed na copy

- **Sem dados reais de cliente.** O corpus é sintético / abertamente
  licenciado (cuidados com gatos, adoção de cachorros, fermentação,
  fitness, horta, licenciamento open-source, uma ferramenta Python fictícia).
  Compradores não podem usar esses PNGs como evidência de qualquer
  implantação real.
- **Embeddings stub.** Todos os quatro estados são produzidos contra o
  stub local determinístico. Trocar para um embedding de fornecedor
  mudará os scores de cosseno e pode deslocar uma resposta borderline
  para `refused` (o drift Q13 documentado é a exposição canônica).
- **Auth-error é simulado.** O `.env` embarcado vem com
  `AUTH_ENABLED=false` para que a stack live seja intencionalmente
  permissiva. O estado 401 é capturado via `page.route()` do Playwright,
  não pela troca do flag de auth da API. O gate de auth em si é
  exercitado ponta a ponta por `tests/e2e/test_ui_auth_gate.py`.

## Documentação bilíngue

- **Português (Brasil):** este arquivo.
- **Inglês:** [MANIFEST.en.md](./MANIFEST.en.md).

---

🇧🇷 **Esta é a documentação em português (Brasil).** [Read in English →](./MANIFEST.en.md)
