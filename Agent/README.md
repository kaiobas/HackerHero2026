# HackerHero Guardian 🛡️

Sistema de **proteção de crianças em jogos online**, desenvolvido em Python.

Monitora a tela em tempo real, extrai texto com OCR, avalia risco com léxico especializado + IA e aciona proteções automáticas quando detecta assédio, grooming ou bullying.

---

## 🏗️ Arquitetura

```
main.py                        ← FastAPI + Orquestrador
├── app/
│   ├── capture/
│   │   └── screen_capture.py  ← Screenshots periódicos (mss)
│   ├── ocr/
│   │   └── text_extractor.py  ← Extração de texto (EasyOCR + OpenCV)
│   ├── risk/
│   │   └── risk_engine.py     ← Semáforo de risco (léxico categorizado)
│   ├── ai/
│   │   └── pattern_agent.py   ← Agente LLM (GPT-4o-mini via OpenAI)
│   ├── protection/
│   │   └── overlay.py         ← Overlay + blur + quarentena (Tkinter)
│   ├── api/
│   │   └── routes.py          ← Endpoints REST
│   └── guardian.py            ← Orquestrador central
├── models/
│   └── schemas.py             ← Schemas Pydantic
└── config.py                  ← Configurações centralizadas
```

---

## 🚦 Sistema de Risco (Semáforo)

| Nível | Score | Comportamento |
|-------|-------|---------------|
| 🟢 **GREEN** | 0–39 | Sem risco. Monitoramento normal. |
| 🟡 **YELLOW** | 40–69 | Alerta. Borda pulsante na tela. Log registrado. |
| 🔴 **RED** | 70–100 | Tela bloqueada + desfocada. Screenshot em quarentena. Responsável notificado. |

---

## 🤖 Agente de IA

- Modelo: **GPT-4o-mini** (configurável)
- Analisa uma janela das últimas **N capturas** de forma contextual
- Detecta padrões de **grooming**, **sextorsão**, **bullying** e coleta de dados pessoais
- Opera em paralelo ao motor léxico, combinando os scores (60% léxico + 40% IA)

---

## 📦 Instalação

### Requisitos
- Python 3.11+
- Windows 10/11 (para overlay nativo; outros OS funcionam sem overlay Win32)

### Setup

```bash
# 1. Clone o repositório
git clone https://github.com/kaiobas/HackerHero2026.git
cd HackerHero2026

# 2. Crie e ative o ambiente virtual
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Configure as variáveis de ambiente
copy .env.example .env          # Windows
# cp .env.example .env          # macOS/Linux
# Edite .env e adicione sua OPENAI_API_KEY

# 5. Execute
python main.py
```

---

## 🔌 API REST

Com o servidor rodando, acesse a documentação interativa:

- **Swagger UI:** http://127.0.0.1:8000/docs
- **ReDoc:** http://127.0.0.1:8000/redoc

### Endpoints principais

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/api/v1/status` | Estado atual do sistema |
| GET | `/api/v1/alerts` | Lista de alertas gerados |
| POST | `/api/v1/alerts/{id}/ack` | Marcar alerta como lido |
| GET | `/api/v1/risk/latest` | Última avaliação de risco |
| POST | `/api/v1/protection/release` | Liberar tela bloqueada (pais) |
| PATCH | `/api/v1/config` | Ajustar configurações em tempo real |
| GET | `/health` | Health-check |

---

## ⚙️ Configurações

Todas as configurações estão no arquivo `.env` (baseado em `.env.example`).

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `OPENAI_API_KEY` | — | Chave da API OpenAI (obrigatória para IA) |
| `CAPTURE_INTERVAL_SECONDS` | `5` | Intervalo entre capturas (segundos) |
| `AI_ANALYSIS_INTERVAL_SECONDS` | `30` | Intervalo da análise IA (segundos) |
| `RISK_YELLOW_THRESHOLD` | `40` | Score mínimo para alerta amarelo |
| `RISK_RED_THRESHOLD` | `70` | Score mínimo para bloqueio vermelho |
| `OCR_GPU` | `False` | Ativar GPU no EasyOCR |
| `BLUR_STRENGTH` | `20` | Intensidade do desfoque (pixels) |

---

## 🔐 Privacidade & Ética

- **Screenshots nunca são salvos em disco** — capturados em memória, processados e descartados imediatamente
- **Pais não têm acesso às imagens** — recebem apenas a notificação do nível de risco (verde/amarelo/vermelho)
- Ao receber um alerta, o responsável acessa presencialmente o computador para verificar o que aconteceu
- Todos os logs e alertas ficam **apenas no dispositivo local**
- O sistema deve ser instalado e configurado pelos **responsáveis legais**
- Recomenda-se transparência com a criança sobre o monitoramento

---

## 🗺️ Roadmap

- [ ] Dashboard web (React) para os pais
- [ ] Notificações por e-mail / WhatsApp
- [ ] Suporte a múltiplos monitores
- [ ] Modo silencioso (sem overlay, apenas log)
- [ ] Análise de imagem (não só texto) via Vision API
- [ ] Empacotamento como serviço Windows (`pywin32`)

---

## 📄 Licença

MIT – uso educacional e de proteção familiar.
