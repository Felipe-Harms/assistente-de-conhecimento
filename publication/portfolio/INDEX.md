# Índice — Seções do Estudo de Caso

> Um índice navegável de cada seção em [CASE.md](CASE.md). Cada linha aponta para o cabeçalho e oferece um resumo de uma linha para que você possa escanear o documento sem rolar.

🇧🇷 **Esta é a documentação em português (Brasil).** [Read in English →](./INDEX.en.md)

## Seções

| # | Seção | Resumo de uma linha |
|---|-------|---------------------|
| 1 | [Problema](CASE.md#1-problem) | Confiança, recusa, auditoria, reprodutibilidade e fricção de implantação — os trade-offs não ditos que separam uma demo de uma entrega. |
| 2 | [Público-alvo](CASE.md#2-target-public) | Equipes de entrega pequenas e médias com corpus curado e sem backend gerenciado disponível. |
| 3 | [Solução](CASE.md#3-solution) | Uma stack local de quatro serviços que apresenta três estados honestos de resposta (`answered`, `refused`, `error`) e um estado vazio acionável. |
| 4 | [Arquitetura e stack](CASE.md#4-architecture-and-stack) | nginx + FastAPI + Postgres/pgvector + Playwright, com uma justificativa de uma linha para cada escolha. |
| 5 | [Decisões-chave](CASE.md#5-key-decisions) | Três estados honestos, citações como primeira classe, recusa como recurso, sem lock-in de fornecedor, aceitação reproduzível, retenção manual. |
| 6 | [Segurança e isolamento](CASE.md#6-security-and-isolation) | Gate de auth, validação Pydantic, log de auditoria estruturado, varredura de segredos, isolamento de rede e o trade-off do localStorage. |
| 7 | [Resultados verificáveis](CASE.md#7-verifiable-results) | 70 + 20 + 8 + 24 = 122 testes verdes em um clone fresco, mais o drift Q13 documentado (1/16 dentro do orçamento de 20 %). |
| 8 | [Limitações honestas](CASE.md#8-honest-limitations) | Sem conhecimento do mundo real, sem OCR, sem precisão perfeita, sem serviços vivos, auth off por padrão, localStorage, stub embedding, sem modo hospedado, sem SLA, sem raciocínio avançado. |
| 9 | [Como rodar a demo](CASE.md#9-how-to-run-the-demo) | `git clone → cp .env.example .env → docker compose up -d --wait → curl` e a cadeia canônica de fechamento. |
| 10 | [Refresh de stack e troca de embedding](CASE.md#10-stack-refresh-and-embedding-switch) | Troque o stub por um provedor OpenAI-compatível real via configuração, não código. |
| 11 | [Ponteiros para a fonte da verdade](CASE.md#11-source-of-truth-pointers) | Onde olhar no repositório para cada afirmação feita no estudo de caso. |

## Short copy reutilizável

| Bloco | Onde usar |
|-------|-----------|
| [Resumo de um parágrafo](SHORT-COPY.md#1-o-resumo-de-um-parágrafo) | Página de destino do portfólio, parágrafo "sobre o projeto". |
| [Pitch de três frases](SHORT-COPY.md#2-o-pitch-de-três-frases) | Prospecção a frio, headline de currículo, bio de conferência. |
| [Bloco de confiança e trade-offs](SHORT-COPY.md#3-o-bloco-de-confiança-e-trade-offs) | Revisão de segurança para o comprador, questionário de due-diligence. |
| [Bloco de resultados específicos](SHORT-COPY.md#4-o-bloco-de-resultados-específicos) | Deck pré-vendas, anexo de proposta, pergunta "o que a suíte de testes realmente comprova?". |
| [Parágrafo "para quem é isso"](SHORT-COPY.md#5-o-parágrafo-para-quem-é-isso) | Seção de escopo de público, narrativa de escopo de trabalho. |

## Arquivos companheiros

| Arquivo | Propósito |
|---------|-----------|
| [README.md](README.md) | Ponto de entrada — o que é este diretório, como lê-lo, como o caso se mantém honesto. |
| [CASE.md](CASE.md) | O estudo de caso completo. |
| [SHORT-COPY.md](SHORT-COPY.md) | Parágrafos curtos reutilizáveis. |
| [INDEX.md](INDEX.md) | Este arquivo — índice navegável. |
| [assets/](assets/) | Capturas de tela prontas para revisão da galeria. |

---

🇧🇷 **Esta é a documentação em português (Brasil).** [Read in English →](./INDEX.en.md)
