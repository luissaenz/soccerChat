# ⚽ Soccer Chat Bot — DT Virtual con IA

Bot de Telegram que actúa como Director Técnico virtual de tu grupo de fútbol. Arma equipos balanceados por ELO, registra partidos y responde con humor ácido.

## Funcionalidades

- **Registro de jugadores** con sistema ELO automático
- **Armado de equipos equilibrados** basado en ELO
- **Registro de resultados** con actualización automática de ratings
- **Memoria persistente** de partidos y comentarios del grupo
- **Personalidad sarcástica** — responde como un amigo cargoso que sabe de fútbol
- **Modelos de IA via OpenRouter** (configurable)

## Comandos

| Comando | Descripción |
|---------|-------------|
| `/start` | Muestra ayuda |
| `/registrar Nombre` | Registra un jugador |
| `/jugadores` | Ranking ELO |
| `/resultado JugA,JugB 3 - JugC,JugD 2` | Carga resultado |
| `/equipos Juan, Pedro, Carlos, Luis` | Arma equipos balanceados |
| `/historial` | Últimos 10 partidos |

Además, si mencionás al bot en un mensaje, te responde con la IA.

## Setup Local

```bash
# Clonar y entrar al proyecto
cd soccerChat

# Crear entorno virtual
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env con tus tokens

# Ejecutar (modo polling para desarrollo)
python -m bot.main
```

## Deploy en Render

1. Crear un nuevo **Web Service** en [render.com](https://render.com)
2. Conectar tu repositorio
3. Configurar las variables de entorno:
   - `TELEGRAM_BOT_TOKEN` — Token de [@BotFather](https://t.me/BotFather)
   - `OPENROUTER_API_KEY` — API key de [OpenRouter](https://openrouter.ai)
   - `WEBHOOK_URL` — La URL pública de tu servicio (ej: `https://soccer-chat-bot.onrender.com`)
4. Agregar un **Disk** montado en `/data` (1 GB suficiente)
5. Build command: `pip install -r requirements.txt`
6. Start command: `python -m bot.main`

O usar el `render.yaml` incluido como Blueprint.

## Variables de Entorno

| Variable | Requerida | Default | Descripción |
|----------|-----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | — | Token del bot |
| `OPENROUTER_API_KEY` | ✅ | — | API key OpenRouter |
| `OPENROUTER_MODEL` | ❌ | `openai/gpt-4o-mini` | Modelo a usar |
| `WEBHOOK_URL` | ❌ | — | Si vacío usa polling |
| `PORT` | ❌ | `8080` | Puerto del webhook |
| `DB_PATH` | ❌ | `./data/soccer.db` | Ruta a la base SQLite |

## Estructura

```
soccerChat/
├── bot/
│   ├── __init__.py
│   ├── main.py        # Entry point
│   ├── handlers.py    # Comandos de Telegram
│   ├── ai.py          # Integración OpenRouter
│   ├── db.py          # SQLite CRUD
│   ├── elo.py         # Sistema ELO
│   └── prompts.py     # Personalidad del bot
├── requirements.txt
├── render.yaml
├── .env.example
└── README.md
```
