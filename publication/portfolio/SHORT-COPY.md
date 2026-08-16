# Short Copy — Parágrafos Reutilizáveis

> Três blocos autocontidos que você pode colar em uma proposta, um bullet de currículo, um site de portfólio ou uma conversa de vendas. Cada bloco se sustenta sozinho; concatene conforme necessário.

🇧🇷 **Esta é a documentação em português (Brasil).** [Read in English →](./SHORT-COPY.en.md)

---

## 1. O resumo de um parágrafo

Um serviço de respostas baseado em citações, local-first, que roda com um único `docker compose up` e se recusa a responder quando o corpus não dá suporte. A stack tem quatro containers: uma UI estática servida por nginx, um serviço FastAPI com validação estrita de requisições via Pydantic, um armazenamento Postgres + pgvector, e uma imagem de teste Playwright + pytest que dirige os testes ponta a ponta no navegador. A UI apresenta três estados honestos de resposta — `answered` com citações inline clicáveis, `refused` com o score e limiar calculados, e `error` com um banner amigável e um botão de ação primária. A suíte é reproduzível: 70 testes de segurança + 20 de integração + 8 de aceitação + 24 ponta a ponta de UI, todos verdes em um clone fresco.

---

## 2. O pitch de três frases

Um assistente de retrieval-augmented pequeno e contido, que transforma uma pasta local de documentos Markdown, texto plano e PDFs textuais em uma superfície estilo chat, com citações, recusas e um log de auditoria estruturado. Roda em uma única máquina, não exige cartão de crédito nem backend hospedado, e vem com uma suíte de testes determinística que comprova o contrato. A versão atual adota cinco melhorias independentes de UX identificadas por uma auditoria externa — citações clicáveis, mensagens de erro humanas, estados vazios acionáveis, alvos de toque amigáveis em mobile, e foco de teclado visível — e as agrupa com um estudo de caso de portfólio sanitizado que visitantes públicos podem ler junto com o código.

---

## 3. O bloco de confiança e trade-offs

Os quatro trade-offs honestos que tornam o sistema auditável: o limiar de recuperação é exposto em cada recusa para que o operador veja por que o sistema recusou, cada requisição flui por um logger de auditoria JSON estruturado com redação de payloads com formato de segredo, o token bearer é comparado via `secrets.compare_digest` e falha fechado, e a suíte de testes roda os mesmos comandos em cada clone — não há estado oculto entre a suíte e os números verificáveis. O sistema é intencionalmente estreito: sem OCR, sem tabelas complexas, sem serviços externos vivos por padrão, sem modo hospedado, sem monitoramento 24/7, sem SLA gerenciado. Trocar para um provedor de embedding real é uma mudança de configuração, não de código.

---

## 4. O bloco de resultados específicos

Resultados de testes ponta a ponta a partir de um clone fresco: 70 testes de segurança, 20 testes de integração, 8 testes de aceitação e 24 testes ponta a ponta de UI (dez dos quais dedicados às melhorias de UX adotadas nesta versão). A execução de aceitação de 16 perguntas resolve 15 de forma limpa e expõe 1 drift conhecido do stub de embedding (Q13, "Quem venceu a final da Copa América de 2024?", respondida com `best_score=0.2977` acima do limiar `0.20` porque a correspondência mais próxima compartilha sobreposição incidental de tokens com a pergunta). O drift é documentado no relatório de gaps do repositório e está dentro do orçamento de 20 % de aceitação.

---

## 5. O parágrafo "para quem é isso"

O público-alvo são equipes de entrega pequenas e médias que já têm uma base de conhecimento curada e querem expô-la por uma superfície estilo chat sem levantar um backend gerenciado. Não é um chatbot voltado ao consumidor, não é um SaaS multi-tenant, não é um serviço RAG hospedado. A promessa de binário único vale apenas para a história local com docker-compose; uma implantação em produção troca o gate de token estático por um IdP real e move o token para fora do `localStorage`. O gate está isolado em um único módulo, de modo que a troca é mecânica.

---

## Documentação bilíngue

- **Português (Brasil):** este arquivo.
- **Inglês:** [SHORT-COPY.en.md](./SHORT-COPY.en.md).

---

🇧🇷 **Esta é a documentação em português (Brasil).** [Read in English →](./SHORT-COPY.en.md)
