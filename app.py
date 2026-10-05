# -*- coding: utf-8 -*-
"""
===============================================================
 FEIRA NUZZI — BACK-END FLASK + SQLITE [VERSÃO SEGURA]
===============================================================
 Serve o front + API REST. Persistência garantida.
 
 MELHORIAS DE SEGURANÇA:
 - Endpoints de debug removidos
 - Mensagens de erro genéricas
 - Email de vendedor protegido
 - Logs sensíveis removidos
 - CORS configurado
 - Credenciais em .env

 Rodar:
     pip install flask flask-cors python-dotenv
     python app.py

 Acessar:
     http://localhost:5000            → catálogo (cliente)
     http://localhost:5000/parceiro.html → portal do vendedor
     http://localhost:5000/admin.html    → painel admin
===============================================================
"""
import os
import json
import sqlite3
import secrets
import logging
from datetime import datetime
from functools import wraps
from pathlib import Path
import socket
import re
import ipaddress
import subprocess

from flask import (
    Flask, request, jsonify, g, session,
    send_from_directory, abort,
)
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

# =====================================================================
# LOGGING - Estruturado, sem dados sensíveis
# =====================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# =====================================================================
# CONFIG
# =====================================================================
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "feira.db"

app = Flask(__name__, static_folder=None)

# 🔒 SEGURANÇA: Secret key é OBRIGATÓRIA em produção
FEIRA_SECRET = os.environ.get("FEIRA_SECRET")
if not FEIRA_SECRET:
    # Gera chave aleatória APENAS para desenvolvimento local
    FEIRA_SECRET = secrets.token_hex(32)
    logger.warning("⚠️  FEIRA_SECRET não definida. Usando chave aleatória para esta execução.")
    logger.warning("⚠️  Sessões serão invalidadas quando o servidor reiniciar!")
    logger.warning("⚠️  Para produção, defina a variável de ambiente FEIRA_SECRET")

app.secret_key = FEIRA_SECRET

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    JSON_AS_ASCII=False,
)

# 🔒 SEGURANÇA: CORS restrito (ajuste conforme necessário)
# Para rede local, permite localhost e IPs locais
CORS_ORIGINS = [
    "http://localhost:5000",
    "http://localhost:3000",
    "http://127.0.0.1:5000",
]

# Adiciona IPs locais dinamicamente
try:
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    if local_ip and local_ip != "127.0.0.1":
        CORS_ORIGINS.append(f"http://{local_ip}:5000")
        CORS_ORIGINS.append(f"http://{local_ip}:3000")
except:
    pass

CORS(
    app,
    resources={r"/api/*": {"origins": CORS_ORIGINS, "supports_credentials": True}},
    supports_credentials=True
)

logger.info(f"CORS permitido para: {CORS_ORIGINS}")

# =====================================================================
# BANCO
# =====================================================================
def _raw_conn():
    conn = sqlite3.connect(
        DB_PATH,
        timeout=30.0,
        isolation_level="DEFERRED",
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def get_conn():
    if "db" not in g:
        g.db = _raw_conn()
    return g.db


@app.teardown_appcontext
def _close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        try:
            if exc is None:
                db.commit()
            else:
                db.rollback()
        finally:
            db.close()


def commit(conn):
    conn.commit()


# =====================================================================
# SCHEMA
# =====================================================================
SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nome        TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    senha_hash  TEXT NOT NULL,
    tipo        TEXT NOT NULL CHECK (tipo IN ('cliente','vendedor','adm')),
    criado_em   TEXT NOT NULL DEFAULT (datetime('now')),
    ip_acesso       TEXT,
    mac_address     TEXT,
    so_text         TEXT,
    dispositivo_tipo TEXT
);

CREATE TABLE IF NOT EXISTS lojas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id   INTEGER UNIQUE NOT NULL,
    nome         TEXT NOT NULL DEFAULT '',
    categoria    TEXT NOT NULL DEFAULT '',
    descricao    TEXT NOT NULL DEFAULT '',
    tempo        TEXT NOT NULL DEFAULT '',
    horario      TEXT NOT NULL DEFAULT '',
    logo         TEXT NOT NULL DEFAULT '',
    banner       TEXT NOT NULL DEFAULT '',
    aberta       INTEGER NOT NULL DEFAULT 0,
    atualizado_em TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS produtos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    loja_id      INTEGER NOT NULL,
    nome         TEXT NOT NULL,
    descricao    TEXT NOT NULL DEFAULT '',
    preco        TEXT NOT NULL DEFAULT 'R$ 0,00',
    categoria    TEXT NOT NULL DEFAULT '',
    imagem       TEXT NOT NULL DEFAULT '',
    disponivel   INTEGER NOT NULL DEFAULT 1,
    estoque      INTEGER,
    criado_em    TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (loja_id) REFERENCES lojas(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pedidos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    loja_id         INTEGER NOT NULL,
    cliente_id      INTEGER,
    cliente_nome    TEXT NOT NULL,
    reserva_id      TEXT,
    itens           TEXT NOT NULL,
    valor           TEXT NOT NULL,
    valor_numerico  REAL NOT NULL DEFAULT 0,
    hora            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pendente'
                    CHECK (status IN ('pendente','preparo','pronto','concluido','cancelado')),
    criado_em       TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (loja_id)    REFERENCES lojas(id)    ON DELETE CASCADE,
    FOREIGN KEY (cliente_id) REFERENCES usuarios(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS pedido_itens (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id    INTEGER NOT NULL,
    produto_id   INTEGER NOT NULL,
    quantidade   INTEGER NOT NULL,
    FOREIGN KEY (pedido_id)  REFERENCES pedidos(id)  ON DELETE CASCADE,
    FOREIGN KEY (produto_id) REFERENCES produtos(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS visitas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    stall_id     INTEGER NOT NULL,
    visitado_em  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Produtos configuráveis (ex.: milk-shake): opções de cada produto.
-- Só são usadas quando produtos.configuravel = 1; produtos comuns não tocam nelas.
CREATE TABLE IF NOT EXISTS produto_sabores (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    produto_id INTEGER NOT NULL,
    nome       TEXT NOT NULL,
    ordem      INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (produto_id) REFERENCES produtos(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS produto_tamanhos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    produto_id INTEGER NOT NULL,
    nome       TEXT NOT NULL,
    acrescimo  REAL NOT NULL DEFAULT 0,
    ordem      INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (produto_id) REFERENCES produtos(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS produto_adicionais (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    produto_id INTEGER NOT NULL,
    nome       TEXT NOT NULL,
    preco      REAL NOT NULL DEFAULT 0,
    ordem      INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (produto_id) REFERENCES produtos(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_psab_prod   ON produto_sabores(produto_id);
CREATE INDEX IF NOT EXISTS idx_ptam_prod   ON produto_tamanhos(produto_id);
CREATE INDEX IF NOT EXISTS idx_pad_prod    ON produto_adicionais(produto_id);

CREATE INDEX IF NOT EXISTS idx_prod_loja   ON produtos(loja_id);
CREATE INDEX IF NOT EXISTS idx_ped_loja    ON pedidos(loja_id);
CREATE INDEX IF NOT EXISTS idx_ped_cliente ON pedidos(cliente_id);
CREATE INDEX IF NOT EXISTS idx_ped_status  ON pedidos(status);
CREATE INDEX IF NOT EXISTS idx_pi_pedido   ON pedido_itens(pedido_id);
CREATE INDEX IF NOT EXISTS idx_pi_produto  ON pedido_itens(produto_id);
"""


COLUNAS_ACESSO = ("ip_acesso", "mac_address", "so_text", "dispositivo_tipo")


def _migrar_colunas_acesso(conn):
    """Garante as colunas de acesso em bancos criados antes delas existirem.
    No feira.db atual elas já existem, então nada é alterado."""
    existentes = {r["name"] for r in conn.execute("PRAGMA table_info(usuarios)")}
    for col in COLUNAS_ACESSO:
        if col not in existentes:
            conn.execute(f"ALTER TABLE usuarios ADD COLUMN {col} TEXT")
            logger.info(f"✓ Coluna usuarios.{col} adicionada")


def _migrar_produtos_configuraveis(conn):
    """Adiciona, sem mexer nos dados existentes, as colunas do recurso de
    produtos configuráveis. Em bancos que já têm as colunas, nada é alterado.
    - produtos.configuravel: 0 (padrão) = produto comum
    - pedido_itens.configuracao: JSON com a escolha feita (sabor/tamanho/adicionais)
    - pedido_itens.preco_unitario: preço unitário calculado no servidor"""
    cols_prod = {r["name"] for r in conn.execute("PRAGMA table_info(produtos)")}
    if "configuravel" not in cols_prod:
        conn.execute("ALTER TABLE produtos ADD COLUMN configuravel INTEGER NOT NULL DEFAULT 0")
        logger.info("✓ Coluna produtos.configuravel adicionada")
    cols_pi = {r["name"] for r in conn.execute("PRAGMA table_info(pedido_itens)")}
    if "configuracao" not in cols_pi:
        conn.execute("ALTER TABLE pedido_itens ADD COLUMN configuracao TEXT")
        logger.info("✓ Coluna pedido_itens.configuracao adicionada")
    if "preco_unitario" not in cols_pi:
        conn.execute("ALTER TABLE pedido_itens ADD COLUMN preco_unitario REAL")
        logger.info("✓ Coluna pedido_itens.preco_unitario adicionada")


def init_db():
    conn = _raw_conn()
    try:
        conn.executescript(SCHEMA)
        _migrar_colunas_acesso(conn)
        _migrar_produtos_configuraveis(conn)
        conn.commit()
    finally:
        conn.close()


def seed_demo():
    """🔒 Credenciais de teste - carregadas de variáveis de ambiente"""
    conn = _raw_conn()
    try:
        # Carrega credenciais do .env ou usa padrões seguros para demo
        demo_credentials = [
            (
                "Cliente Demo",
                os.environ.get("DEMO_CLIENTE_EMAIL", "cliente@feiranuzzi.com"),
                os.environ.get("DEMO_CLIENTE_PASS", "compras123"),
                "cliente"
            ),
            (
                "Seu Nino",
                os.environ.get("DEMO_VENDEDOR_EMAIL", "nino@feiranuzzi.com"),
                os.environ.get("DEMO_VENDEDOR_PASS", "colheita2024"),
                "vendedor"
            ),
            (
                "Administrador",
                os.environ.get("DEMO_ADMIN_EMAIL", "admin@feiranuzzi.com"),
                os.environ.get("DEMO_ADMIN_PASS", "admin123"),
                "adm"
            ),
        ]

        for nome, email, senha, tipo in demo_credentials:
            if not conn.execute("SELECT 1 FROM usuarios WHERE email=?", (email,)).fetchone():
                conn.execute(
                    "INSERT INTO usuarios (nome,email,senha_hash,tipo) VALUES (?,?,?,?)",
                    (nome, email, generate_password_hash(senha), tipo),
                )
                logger.info(f"✓ Usuário demo criado: {email} ({tipo})")

        row = conn.execute("SELECT id FROM usuarios WHERE email=?",
                           (os.environ.get("DEMO_VENDEDOR_EMAIL", "nino@feiranuzzi.com"),)).fetchone()
        if row:
            uid = row["id"]
            if not conn.execute("SELECT 1 FROM lojas WHERE usuario_id=?", (uid,)).fetchone():
                conn.execute("""
                    INSERT INTO lojas (usuario_id, nome, categoria, descricao,
                                       horario, aberta)
                    VALUES (?,?,?,?,?,1)
                """, (uid, "Barraca do Seu Nino", "Frutas & Verduras",
                      "Produtos direto da roça.", "Sáb e Dom, 6h às 13h"))

            # Produtos iniciais
            loja = conn.execute("SELECT id FROM lojas WHERE usuario_id=?", (uid,)).fetchone()
            if loja and not conn.execute("SELECT 1 FROM produtos WHERE loja_id=?",
                                          (loja["id"],)).fetchone():
                seed_prod = [
                    ("Manga Tommy", "Doce e firme, colhida na semana.",
                     "R$ 6,90/kg", "Frutas & Verduras",
                     "https://images.unsplash.com/photo-1553279768-865429fa0078?w=400&q=80", 30),
                    ("Alface crespa", "Orgânica, sem agrotóxico.",
                     "R$ 3,50 un", "Frutas & Verduras",
                     "https://images.unsplash.com/photo-1622206151226-18ca2c9d680f?w=400&q=80", 20),
                    ("Tomate italiano", "Ideal para molhos caseiros.",
                     "R$ 7,00/kg", "Frutas & Verduras",
                     "https://images.unsplash.com/photo-1546094096-0df4bcaaa337?w=400&q=80", 15),
                ]
                for nome_p, desc, preco, cat, img, est in seed_prod:
                    conn.execute("""
                        INSERT INTO produtos (loja_id, nome, descricao, preco,
                                              categoria, imagem, disponivel, estoque)
                        VALUES (?,?,?,?,?,?,1,?)
                    """, (loja["id"], nome_p, desc, preco, cat, img, est))

        conn.commit()
        logger.info("✓ Base de dados de demonstração pronta")
    finally:
        conn.close()


# =====================================================================
# HELPERS
# =====================================================================
def rows_to_list(rows):
    return [dict(r) for r in rows]


def autenticar(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        uid = session.get("uid")
        if not uid:
            logger.debug("Acesso negado: sem sessão")
            return jsonify({"erro": "Não autenticado"}), 401
        u = get_conn().execute("SELECT * FROM usuarios WHERE id=?", (uid,)).fetchone()
        if not u:
            session.clear()
            logger.debug(f"Acesso negado: sessão inválida uid={uid}")
            return jsonify({"erro": "Sessão inválida"}), 401
        g.usuario = dict(u)
        return f(*args, **kwargs)
    return wrapper


def exigir_tipo(*tipos):
    def deco(f):
        @wraps(f)
        @autenticar
        def wrapper(*args, **kwargs):
            if g.usuario["tipo"] not in tipos:
                logger.warning(f"Acesso negado: usuário {g.usuario['id']} tipo {g.usuario['tipo']} tentou acessar rota admin")
                return jsonify({"erro": "Acesso negado"}), 403
            return f(*args, **kwargs)
        return wrapper
    return deco


# =====================================================================
# ACESSO DO USUÁRIO — IP, MAC, sistema e tipo de dispositivo
# =====================================================================
def _ip_cliente() -> str:
    # remote_addr é o IP real da conexão. X-Forwarded-For não é usado de
    # propósito: qualquer cliente consegue forjar esse header.
    return request.remote_addr or ""


def _obter_mac(ip: str):
    """Descobre o MAC via tabela ARP do servidor. Só funciona para
    aparelhos na MESMA rede local (Wi-Fi da feira); fora dela, ou em
    localhost, devolve None — o MAC não viaja numa requisição HTTP."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if addr.version != 4 or addr.is_loopback or not addr.is_private:
        return None

    try:
        if os.path.exists("/proc/net/arp"):          # Linux
            with open("/proc/net/arp", encoding="utf-8") as f:
                next(f, None)
                for linha in f:
                    c = linha.split()
                    if len(c) >= 4 and c[0] == ip and c[3] != "00:00:00:00:00:00":
                        return c[3].upper()
            return None
        # Windows / macOS
        saida = subprocess.run(
            ["arp", "-a", ip], capture_output=True, text=True, timeout=2
        ).stdout
    except (OSError, subprocess.SubprocessError, StopIteration):
        return None

    m = re.search(r"((?:[0-9a-fA-F]{1,2}[:-]){5}[0-9a-fA-F]{1,2})", saida)
    if not m:
        return None
    partes = [p.zfill(2) for p in re.split(r"[:-]", m.group(1))]
    mac = ":".join(partes).upper()
    return None if mac in ("00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF") else mac


def _analisar_user_agent(ua: str):
    """Devolve (so_text, dispositivo_tipo) a partir do User-Agent."""
    ua = (ua or "")[:300]
    baixo = ua.lower()
    if not ua:
        return None, None

    if "android" in baixo:
        m = re.search(r"android[ /]?([\d.]+)", ua, re.I)
        so = "Android" + (f" {m.group(1)}" if m else "")
    elif any(k in baixo for k in ("iphone", "ipad", "ipod")):
        m = re.search(r"OS (\d+)[_.](\d+)", ua)
        so = "iOS" + (f" {m.group(1)}.{m.group(2)}" if m else "")
    elif "windows" in baixo:
        so = "Windows"
    elif "cros" in baixo:
        so = "ChromeOS"
    elif "mac os x" in baixo or "macintosh" in baixo:
        so = "macOS"
    elif "linux" in baixo:
        so = "Linux"
    else:
        so = "Desconhecido"

    if "ipad" in baixo or "tablet" in baixo or ("android" in baixo and "mobile" not in baixo):
        tipo = "tablet"
    elif "mobi" in baixo or "iphone" in baixo or "android" in baixo:
        tipo = "celular"
    else:
        tipo = "desktop"
    return so, tipo


def registrar_acesso(conn, usuario_id: int):
    """Grava no usuário os dados do último acesso. Nunca derruba o
    login/cadastro: se algo falhar, apenas registra no log."""
    try:
        ip = _ip_cliente()
        so, tipo = _analisar_user_agent(request.headers.get("User-Agent", ""))
        conn.execute(
            "UPDATE usuarios SET ip_acesso=?, mac_address=?, so_text=?, "
            "dispositivo_tipo=? WHERE id=?",
            (ip or None, _obter_mac(ip), so, tipo, usuario_id),
        )
        commit(conn)
    except Exception as e:
        conn.rollback()
        logger.warning(f"Não foi possível registrar o acesso do usuário {usuario_id}: {str(e)[:80]}")


# =====================================================================
# AUTH
# =====================================================================
@app.post("/api/auth/register")
def register():
    data = request.get_json() or {}
    nome  = (data.get("nome") or "").strip()
    email = (data.get("email") or "").strip().lower()
    senha = data.get("senha") or ""
    
    if not nome or not email or len(senha) < 6:
        return jsonify({"erro": "Dados inválidos (senha mín. 6 caracteres)"}), 400

    conn = get_conn()
    try:
        if conn.execute("SELECT 1 FROM usuarios WHERE email=?", (email,)).fetchone():
            # 🔒 SEGURANÇA: Não revelar se email já existe
            return jsonify({"erro": "Não foi possível criar a conta"}), 400
        
        cur = conn.execute(
            "INSERT INTO usuarios (nome,email,senha_hash,tipo) VALUES (?,?,?,?)",
            (nome, email, generate_password_hash(senha), "cliente"),
        )
        commit(conn)
        uid = cur.lastrowid
        registrar_acesso(conn, uid)
        logger.info(f"✓ Novo usuário cliente registrado: {email}")
    except sqlite3.IntegrityError as e:
        conn.rollback()
        logger.warning(f"Erro ao registrar usuário {email}: {str(e)[:50]}")
        # 🔒 SEGURANÇA: Mensagem genérica, sem detalhes de banco
        return jsonify({"erro": "Não foi possível criar a conta"}), 400

    if not conn.execute("SELECT 1 FROM usuarios WHERE id=?", (uid,)).fetchone():
        logger.error(f"Usuário criado mas não encontrado: {uid}")
        return jsonify({"erro": "Erro ao gravar dados"}), 500

    session["uid"] = uid
    return jsonify({"email": email, "type": "cliente", "name": nome}), 201


@app.post("/api/auth/login")
def login():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    senha = data.get("senha") or ""

    u = get_conn().execute("SELECT * FROM usuarios WHERE email=?", (email,)).fetchone()
    if not u or not check_password_hash(u["senha_hash"], senha):
        # 🔒 SEGURANÇA: Mensagem genérica, sem enumeration
        logger.info(f"Tentativa de login falhada: {email}")
        return jsonify({"erro": "E-mail ou senha incorretos"}), 401

    session["uid"] = u["id"]
    session.permanent = True
    registrar_acesso(get_conn(), u["id"])
    logger.info(f"✓ Login bem-sucedido: {u['email']} ({u['tipo']})")
    return jsonify({"email": u["email"], "type": u["tipo"], "name": u["nome"]})


@app.post("/api/auth/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/auth/session")
def get_session():
    uid = session.get("uid")
    if not uid:
        return jsonify(None)
    u = get_conn().execute("SELECT * FROM usuarios WHERE id=?", (uid,)).fetchone()
    if not u:
        session.clear()
        return jsonify(None)
    return jsonify({"email": u["email"], "type": u["tipo"], "name": u["nome"]})


# =====================================================================
# VISITAS
# =====================================================================
@app.post("/api/visits")
def registrar_visita():
    data = request.get_json() or {}
    stall_id = data.get("stallId")
    if not stall_id:
        return jsonify({"erro": "stallId obrigatório"}), 400
    conn = get_conn()
    conn.execute("INSERT INTO visitas (stall_id) VALUES (?)", (int(stall_id),))
    commit(conn)
    return jsonify({"ok": True})


# =====================================================================
# CATÁLOGO — barracas
# =====================================================================
FALLBACK_IMG = "https://images.unsplash.com/photo-1542838132-92c53300491e?w=800&q=80"


def _hash_stall_id(email: str) -> int:
    h = 0
    for c in email:
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
        if h >= 0x80000000:
            h -= 0x100000000
    return 900000000 + abs(h)


# =====================================================================
# PRODUTOS CONFIGURÁVEIS (ex.: milk-shake) — helpers
# =====================================================================
MAX_OPCOES = 30          # limite por grupo (sabores/tamanhos/adicionais)
MAX_NOME_OPCAO = 60


def parse_preco(txt) -> float:
    """'R$ 12,50' -> 12.5 (mesma regra do front: ponto = milhar, vírgula = decimal)."""
    m = re.search(r"[\d.,]+", str(txt or ""))
    if not m:
        return 0.0
    try:
        return float(m.group(0).replace(".", "").replace(",", "."))
    except ValueError:
        return 0.0


def fmt_brl(v) -> str:
    return "R$ " + f"{float(v):.2f}".replace(".", ",")


def _valor_opcao(v) -> float:
    """Aceita número (3, 3.5) ou texto ('3,50', 'R$ 3,50'). Nunca negativo."""
    if v is None or v == "":
        return 0.0
    if isinstance(v, bool):
        raise ValueError("Valor inválido")
    if isinstance(v, (int, float)):
        n = float(v)
    else:
        n = parse_preco(v)
    if n < 0 or n != n or n > 100000:
        raise ValueError("Valor inválido")
    return round(n, 2)


def _nome_opcao(v) -> str:
    nome = str(v or "").strip()
    if not nome:
        raise ValueError("Toda opção precisa de um nome.")
    if len(nome) > MAX_NOME_OPCAO:
        raise ValueError(f"Nome de opção muito longo (máx. {MAX_NOME_OPCAO} caracteres).")
    return nome


def _parse_opcoes(data):
    """Valida as listas vindas do formulário do vendedor.
    Retorna (sabores, tamanhos, adicionais) já normalizados.
    Levanta ValueError com mensagem pronta para o usuário."""
    def lista(chave):
        v = data.get(chave) or []
        if not isinstance(v, list):
            raise ValueError("Formato inválido nas opções do produto.")
        if len(v) > MAX_OPCOES:
            raise ValueError(f"Máximo de {MAX_OPCOES} opções por grupo.")
        return v

    def sem_duplicados(nomes, rotulo):
        vistos = set()
        for n in nomes:
            k = n.casefold()
            if k in vistos:
                raise ValueError(f"{rotulo} repetido: {n}")
            vistos.add(k)

    sabores = []
    for it in lista("sabores"):
        sabores.append(_nome_opcao(it.get("nome") if isinstance(it, dict) else it))
    sem_duplicados(sabores, "Sabor")

    tamanhos = []
    for it in lista("tamanhos"):
        if not isinstance(it, dict):
            raise ValueError("Formato inválido nos tamanhos.")
        tamanhos.append((_nome_opcao(it.get("nome")), _valor_opcao(it.get("acrescimo"))))
    sem_duplicados([t[0] for t in tamanhos], "Tamanho")

    adicionais = []
    for it in lista("adicionais"):
        if not isinstance(it, dict):
            raise ValueError("Formato inválido nos adicionais.")
        adicionais.append((_nome_opcao(it.get("nome")), _valor_opcao(it.get("preco"))))
    sem_duplicados([a[0] for a in adicionais], "Adicional")

    return sabores, tamanhos, adicionais


def _salvar_opcoes(conn, produto_id, sabores, tamanhos, adicionais):
    """Substitui as opções do produto. Pedidos antigos não são afetados, pois
    guardam uma cópia (nome/preço) da escolha em pedido_itens.configuracao."""
    for tabela in ("produto_sabores", "produto_tamanhos", "produto_adicionais"):
        conn.execute(f"DELETE FROM {tabela} WHERE produto_id=?", (produto_id,))
    for i, nome in enumerate(sabores):
        conn.execute("INSERT INTO produto_sabores (produto_id, nome, ordem) VALUES (?,?,?)",
                     (produto_id, nome, i))
    for i, (nome, acr) in enumerate(tamanhos):
        conn.execute("INSERT INTO produto_tamanhos (produto_id, nome, acrescimo, ordem) VALUES (?,?,?,?)",
                     (produto_id, nome, acr, i))
    for i, (nome, preco) in enumerate(adicionais):
        conn.execute("INSERT INTO produto_adicionais (produto_id, nome, preco, ordem) VALUES (?,?,?,?)",
                     (produto_id, nome, preco, i))


def _contar_opcoes(conn, produto_id):
    n_sab = conn.execute("SELECT COUNT(*) AS n FROM produto_sabores WHERE produto_id=?",
                         (produto_id,)).fetchone()["n"]
    n_tam = conn.execute("SELECT COUNT(*) AS n FROM produto_tamanhos WHERE produto_id=?",
                         (produto_id,)).fetchone()["n"]
    return n_sab, n_tam


def _opcoes_do_produto(conn, produto_id) -> dict:
    return {
        "sabores": [{"id": r["id"], "nome": r["nome"]} for r in conn.execute(
            "SELECT id, nome FROM produto_sabores WHERE produto_id=? ORDER BY ordem, id",
            (produto_id,))],
        "tamanhos": [{"id": r["id"], "nome": r["nome"], "acrescimo": r["acrescimo"]} for r in conn.execute(
            "SELECT id, nome, acrescimo FROM produto_tamanhos WHERE produto_id=? ORDER BY ordem, id",
            (produto_id,))],
        "adicionais": [{"id": r["id"], "nome": r["nome"], "preco": r["preco"]} for r in conn.execute(
            "SELECT id, nome, preco FROM produto_adicionais WHERE produto_id=? ORDER BY ordem, id",
            (produto_id,))],
    }


def _resolver_configuracao(conn, produto, cfg) -> dict:
    """Valida a escolha do cliente contra as opções do produto NO BANCO e
    calcula o preço unitário no servidor (nunca confia no valor do navegador).
    preço = preço base + acréscimo do tamanho + soma dos adicionais."""
    nome = produto["nome"]
    if not isinstance(cfg, dict):
        raise ValueError(f"Escolha o sabor e o tamanho de {nome}.")
    try:
        sabor_id = int(cfg.get("saborId"))
        tamanho_id = int(cfg.get("tamanhoId"))
        ad_ids = [int(x) for x in (cfg.get("adicionaisIds") or [])]
    except (TypeError, ValueError):
        raise ValueError(f"Configuração inválida para {nome}.")

    sabor = conn.execute(
        "SELECT id, nome FROM produto_sabores WHERE id=? AND produto_id=?",
        (sabor_id, produto["id"])).fetchone()
    if not sabor:
        raise ValueError(f"Sabor inválido para {nome}.")
    tamanho = conn.execute(
        "SELECT id, nome, acrescimo FROM produto_tamanhos WHERE id=? AND produto_id=?",
        (tamanho_id, produto["id"])).fetchone()
    if not tamanho:
        raise ValueError(f"Tamanho inválido para {nome}.")

    adicionais = []
    for aid in dict.fromkeys(ad_ids):          # remove repetidos, mantém ordem
        ad = conn.execute(
            "SELECT id, nome, preco FROM produto_adicionais WHERE id=? AND produto_id=?",
            (aid, produto["id"])).fetchone()
        if not ad:
            raise ValueError(f"Adicional inválido para {nome}.")
        adicionais.append(ad)

    base = parse_preco(produto["preco"])
    unit = round(base + tamanho["acrescimo"] + sum(a["preco"] for a in adicionais), 2)

    descricao = f"{nome} ({sabor['nome']}, {tamanho['nome']}"
    if adicionais:
        descricao += ", com " + ", ".join(a["nome"] for a in adicionais)
    descricao += ")"

    return {
        "descricao": descricao,
        "preco_unitario": unit,
        "snapshot": {
            "produto": nome,
            "sabor": {"id": sabor["id"], "nome": sabor["nome"]},
            "tamanho": {"id": tamanho["id"], "nome": tamanho["nome"],
                        "acrescimo": tamanho["acrescimo"]},
            "adicionais": [{"id": a["id"], "nome": a["nome"], "preco": a["preco"]}
                           for a in adicionais],
            "preco_base": base,
            "preco_unitario": unit,
        },
    }


def _produto_publico(conn, p) -> dict:
    d = {
        "id": p["id"],
        "name": p["nome"],
        "price": p["preco"],
        "desc": p["descricao"] or "",
        "img": p["imagem"] or FALLBACK_IMG,
        "estoque": p["estoque"],
    }
    if p["configuravel"]:
        d["configuravel"] = True
        d["opcoes"] = _opcoes_do_produto(conn, p["id"])
    return d


@app.get("/api/stalls")
def listar_stalls():
    """🔒 SEGURANÇA: Não retorna email do vendedor"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT u.email, u.nome AS owner_nome, l.*
        FROM usuarios u
        JOIN lojas l ON l.usuario_id = u.id
        WHERE u.tipo='vendedor' AND l.aberta=1
          AND EXISTS (SELECT 1 FROM produtos p
                      WHERE p.loja_id=l.id AND p.disponivel=1)
        ORDER BY l.nome
    """).fetchall()

    result = []
    for r in rows:
        prods = conn.execute("""
            SELECT * FROM produtos
            WHERE loja_id=? AND disponivel=1
            ORDER BY criado_em DESC
        """, (r["id"],)).fetchall()

        cover = r["banner"] or r["logo"] or FALLBACK_IMG
        result.append({
            "id": _hash_stall_id(r["email"]),
            # ✅ REMOVIDO: "_vendorEmail" - não retorna mais o email
            "name": r["nome"] or r["owner_nome"] or "Barraca",
            "category": r["categoria"] or "Outros",
            "owner": r["owner_nome"] or "",
            "desc": r["descricao"] or "Loja parceira da feira.",
            "about": r["descricao"] or "Loja parceira da feira.",
            "cover": cover,
            "gallery": [cover, r["logo"] or FALLBACK_IMG, FALLBACK_IMG],
            "address": "Vitrine da loja na Feira Nuzzi",
            "hours": r["horario"] or "Consulte o horário na loja",
            "products": [_produto_publico(conn, p) for p in prods],
        })
    return jsonify(result)


# =====================================================================
# VENDEDOR
# =====================================================================
def _produto_vendor(conn, p) -> dict:
    d = {
        "id": p["id"], "nome": p["nome"], "descricao": p["descricao"],
        "preco": p["preco"], "categoria": p["categoria"],
        "imagem": p["imagem"], "disponivel": bool(p["disponivel"]),
        "estoque": p["estoque"],
        "configuravel": bool(p["configuravel"]),
    }
    if p["configuravel"]:
        d["opcoes"] = _opcoes_do_produto(conn, p["id"])
    return d


def _vendor_payload(conn, usuario_id: int) -> dict:
    loja = conn.execute("SELECT * FROM lojas WHERE usuario_id=?", (usuario_id,)).fetchone()
    if not loja:
        return {
            "loja": {"nome": "", "categoria": "", "descricao": "",
                     "tempo": "", "horario": "", "logo": "", "banner": "",
                     "aberta": False},
            "produtos": [], "pedidos": [],
        }

    produtos = conn.execute(
        "SELECT * FROM produtos WHERE loja_id=? ORDER BY criado_em DESC",
        (loja["id"],)
    ).fetchall()
    pedidos = conn.execute(
        "SELECT * FROM pedidos WHERE loja_id=? ORDER BY criado_em DESC",
        (loja["id"],)
    ).fetchall()

    return {
        "loja": {
            "nome": loja["nome"], "categoria": loja["categoria"],
            "descricao": loja["descricao"], "tempo": loja["tempo"],
            "horario": loja["horario"], "logo": loja["logo"],
            "banner": loja["banner"], "aberta": bool(loja["aberta"]),
        },
        "produtos": [_produto_vendor(conn, p) for p in produtos],
        "pedidos": [{
            "id": p["id"], "cliente": p["cliente_nome"], "itens": p["itens"],
            "valor": p["valor"], "valorNumerico": p["valor_numerico"],
            "hora": p["hora"], "status": p["status"], "reservaId": p["reserva_id"],
        } for p in pedidos],
    }


@app.get("/api/vendor/data")
@exigir_tipo("vendedor")
def vendor_data():
    return jsonify(_vendor_payload(get_conn(), g.usuario["id"]))


@app.put("/api/vendor/loja")
@exigir_tipo("vendedor")
def vendor_update_loja():
    data = request.get_json() or {}
    campos = ("nome", "categoria", "descricao", "tempo", "horario", "logo", "banner")
    conn = get_conn()
    uid = g.usuario["id"]

    loja = conn.execute("SELECT * FROM lojas WHERE usuario_id=?", (uid,)).fetchone()

    if not loja:
        valores = {
            "nome":      data.get("nome")      or g.usuario["nome"],
            "categoria": data.get("categoria") or "",
            "descricao": data.get("descricao") or "",
            "tempo":     data.get("tempo")     or "",
            "horario":   data.get("horario")   or "",
            "logo":      data.get("logo")      or "",
            "banner":    data.get("banner")    or "",
            "aberta":    1 if data.get("aberta") else 0,
        }
        conn.execute("""
            INSERT INTO lojas (usuario_id, nome, categoria, descricao,
                               tempo, horario, logo, banner, aberta)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (uid, valores["nome"], valores["categoria"], valores["descricao"],
              valores["tempo"], valores["horario"], valores["logo"],
              valores["banner"], valores["aberta"]))
    else:
        sets, vals = [], []
        for c in campos:
            if c in data:
                sets.append(f"{c}=?")
                vals.append(data[c] or "")
        if "aberta" in data:
            sets.append("aberta=?")
            vals.append(1 if data["aberta"] else 0)
        if sets:
            sets.append("atualizado_em=datetime('now')")
            vals.append(uid)
            conn.execute(f"UPDATE lojas SET {', '.join(sets)} WHERE usuario_id=?", vals)

    commit(conn)
    check = conn.execute("SELECT id FROM lojas WHERE usuario_id=?", (uid,)).fetchone()
    if not check:
        logger.error(f"Falha ao gravar loja para usuário {uid}")
        return jsonify({"erro": "Erro ao atualizar loja"}), 500
    return jsonify({"ok": True, "loja_id": check["id"]})


def _parse_estoque(valor):
    """Converte o campo 'estoque' vindo do form: '' ou None => sem controle
    de estoque (NULL); número inteiro >= 0 => estoque controlado.
    Levanta ValueError se vier algo inválido (ex: texto, negativo)."""
    if valor is None or valor == "":
        return None
    n = int(valor)
    if n < 0:
        raise ValueError("estoque não pode ser negativo")
    return n


@app.post("/api/vendor/produtos")
@exigir_tipo("vendedor")
def vendor_criar_produto():
    data = request.get_json() or {}
    nome = (data.get("nome") or "").strip()
    if not nome:
        return jsonify({"erro": "Nome obrigatório"}), 400

    try:
        estoque = _parse_estoque(data.get("estoque"))
    except (TypeError, ValueError):
        return jsonify({"erro": "Estoque deve ser um número inteiro (0 ou mais), ou vazio para não controlar."}), 400

    # Produto configurável (opcional): valida as opções antes de gravar qualquer coisa
    configuravel = bool(data.get("configuravel"))
    opcoes = None
    if configuravel:
        try:
            opcoes = _parse_opcoes(data)
        except ValueError as e:
            return jsonify({"erro": str(e)}), 400
        if not opcoes[0] or not opcoes[1]:
            return jsonify({"erro": "Produto configurável precisa de pelo menos 1 sabor e 1 tamanho."}), 400

    conn = get_conn()
    uid = g.usuario["id"]

    loja = conn.execute("SELECT id FROM lojas WHERE usuario_id=?", (uid,)).fetchone()
    if not loja:
        cur = conn.execute(
            "INSERT INTO lojas (usuario_id, nome) VALUES (?,?)",
            (uid, g.usuario["nome"])
        )
        commit(conn)
        loja_id = cur.lastrowid
    else:
        loja_id = loja["id"]

    cur = conn.execute("""
        INSERT INTO produtos (loja_id, nome, descricao, preco, categoria,
                              imagem, disponivel, estoque, configuravel)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        loja_id, nome,
        data.get("descricao", ""),
        data.get("preco", "R$ 0,00"),
        data.get("categoria", ""),
        data.get("imagem", ""),
        1 if data.get("disponivel", True) else 0,
        estoque,
        1 if configuravel else 0,
    ))
    new_id = cur.lastrowid
    if configuravel:
        _salvar_opcoes(conn, new_id, *opcoes)
    commit(conn)

    if not conn.execute("SELECT 1 FROM produtos WHERE id=?", (new_id,)).fetchone():
        logger.error(f"Produto criado mas não encontrado: {new_id}")
        return jsonify({"erro": "Erro ao criar produto"}), 500

    return jsonify({"id": new_id, "ok": True}), 201


@app.put("/api/vendor/produtos/<int:pid>")
@exigir_tipo("vendedor")
def vendor_editar_produto(pid):
    data = request.get_json() or {}
    campos = ("nome", "descricao", "preco", "categoria",
              "imagem", "disponivel", "estoque")
    conn = get_conn()

    p = conn.execute("""
        SELECT p.id FROM produtos p
        JOIN lojas l ON l.id = p.loja_id
        WHERE p.id=? AND l.usuario_id=?
    """, (pid, g.usuario["id"])).fetchone()
    if not p:
        return jsonify({"erro": "Produto não encontrado"}), 404

    if "estoque" in data:
        try:
            data["estoque"] = _parse_estoque(data.get("estoque"))
        except (TypeError, ValueError):
            return jsonify({"erro": "Estoque deve ser um número inteiro (0 ou mais), ou vazio para não controlar."}), 400

    # Produto configurável: só mexe nas opções se o front enviou "configuravel".
    # Chamadas antigas (pausar, repor estoque, editar preço...) não passam por aqui.
    opcoes = None
    if "configuravel" in data:
        if data.get("configuravel"):
            if any(k in data for k in ("sabores", "tamanhos", "adicionais")):
                try:
                    opcoes = _parse_opcoes(data)
                except ValueError as e:
                    return jsonify({"erro": str(e)}), 400
                n_sab, n_tam = len(opcoes[0]), len(opcoes[1])
            else:
                n_sab, n_tam = _contar_opcoes(conn, pid)
            if n_sab < 1 or n_tam < 1:
                return jsonify({"erro": "Produto configurável precisa de pelo menos 1 sabor e 1 tamanho."}), 400

    sets, vals = [], []
    for c in campos:
        if c in data:
            sets.append(f"{c}=?")
            if c == "disponivel":
                vals.append(1 if data[c] else 0)
            else:
                vals.append(data[c])
    if "configuravel" in data:
        sets.append("configuravel=?")
        vals.append(1 if data.get("configuravel") else 0)
    if not sets:
        return jsonify({"ok": True, "msg": "Nada para atualizar"})

    vals.append(pid)
    conn.execute(f"UPDATE produtos SET {', '.join(sets)} WHERE id=?", vals)
    if opcoes is not None:
        _salvar_opcoes(conn, pid, *opcoes)
    commit(conn)
    return jsonify({"ok": True})


@app.delete("/api/vendor/produtos/<int:pid>")
@exigir_tipo("vendedor")
def vendor_excluir_produto(pid):
    conn = get_conn()
    cur = conn.execute("""
        DELETE FROM produtos WHERE id=? AND loja_id IN
            (SELECT id FROM lojas WHERE usuario_id=?)
    """, (pid, g.usuario["id"]))
    commit(conn)
    if cur.rowcount == 0:
        return jsonify({"erro": "Produto não encontrado"}), 404
    return jsonify({"ok": True})


@app.put("/api/vendor/pedidos/<int:pid>/status")
@exigir_tipo("vendedor", "adm")
def vendor_update_pedido(pid):
    data = request.get_json() or {}
    status = data.get("status")
    if status not in ("pendente", "preparo", "pronto", "concluido", "cancelado"):
        return jsonify({"erro": "Status inválido"}), 400

    conn = get_conn()
    pedido = conn.execute("SELECT * FROM pedidos WHERE id=?", (pid,)).fetchone()
    if not pedido:
        return jsonify({"erro": "Pedido não encontrado"}), 404

    # vendedor só pode mexer nos pedidos da própria loja; admin pode em qualquer um
    if g.usuario["tipo"] == "vendedor":
        loja = conn.execute("SELECT id FROM lojas WHERE usuario_id=?",
                            (g.usuario["id"],)).fetchone()
        if not loja or pedido["loja_id"] != loja["id"]:
            return jsonify({"erro": "Pedido não encontrado"}), 404

    status_anterior = pedido["status"]

    # 🔒 SEGURANÇA: para o VENDEDOR confirmar a retirada (status "concluido"),
    # é obrigatório informar o código de retirada do cliente (reserva_id).
    # Isso evita que um pedido seja marcado como entregue sem o cliente
    # apresentar sua senha. O admin pode fazer isso sem o código.
    if (status == "concluido" and status_anterior != "concluido"
            and g.usuario["tipo"] == "vendedor"):
        codigo = (data.get("codigo") or "").strip().upper()
        codigo_esperado = (pedido["reserva_id"] or "").strip().upper()
        if not codigo:
            return jsonify({"erro": "Informe o código do cliente para confirmar a retirada."}), 400
        if not codigo_esperado or codigo != codigo_esperado:
            return jsonify({"erro": "Código do cliente incorreto."}), 400
    conn.execute("UPDATE pedidos SET status=? WHERE id=?", (status, pid))

    # devolve o estoque reservado se o pedido está sendo cancelado agora
    if status == "cancelado" and status_anterior != "cancelado":
        itens = conn.execute(
            "SELECT produto_id, quantidade FROM pedido_itens WHERE pedido_id=?",
            (pid,)
        ).fetchall()
        for it in itens:
            conn.execute(
                "UPDATE produtos SET estoque = estoque + ? "
                "WHERE id=? AND estoque IS NOT NULL",
                (it["quantidade"], it["produto_id"])
            )

    commit(conn)
    logger.info(f"Pedido #{pid} status alterado: {status_anterior} → {status}")
    return jsonify({"ok": True, "status": status})


# =====================================================================
# PEDIDOS (cliente)
# =====================================================================
_CODIGO_ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def gerar_senha_pedido(conn):
    """Gera código de retirada único"""
    for _ in range(20):
        codigo = "NZ-" + "".join(secrets.choice(_CODIGO_ALFABETO) for _ in range(5))
        existe = conn.execute(
            "SELECT 1 FROM pedidos WHERE reserva_id=?", (codigo,)
        ).fetchone()
        if not existe:
            return codigo
    return "NZ-" + secrets.token_hex(4).upper()


@app.post("/api/orders")
def criar_pedidos():
    uid = session.get("uid")
    if not uid:
        logger.debug("Tentativa de criar pedido sem sessão")
        return jsonify({
            "erro": "Não autenticado",
            "dica": "Faça login novamente na mesma origem (localhost:5000)."
        }), 401

    conn = get_conn()
    u = conn.execute("SELECT * FROM usuarios WHERE id=?", (uid,)).fetchone()
    if not u:
        session.clear()
        logger.debug(f"Tentativa com uid inválido: {uid}")
        return jsonify({"erro": "Sessão inválida"}), 401

    if u["tipo"] != "cliente":
        logger.warning(f"Usuário {u['email']} ({u['tipo']}) tentou criar pedido como cliente")
        return jsonify({
            "erro": "Apenas clientes podem fazer pedidos"
        }), 403

    data = request.get_json(silent=True) or {}
    reserva_id = gerar_senha_pedido(conn)
    stalls = data.get("stalls") or []
    
    if not stalls:
        return jsonify({"erro": "Sem itens"}), 400

    # ---- 1ª passada: valida vendedor/loja/produtos ----
    pendentes = []
    ignorados = []

    lojas_disponiveis = conn.execute("""
        SELECT u.email, l.id AS loja_id
        FROM usuarios u
        JOIN lojas l ON l.usuario_id = u.id
        WHERE u.tipo='vendedor' AND l.aberta=1
    """).fetchall()

    lojas_por_stall = {
        str(_hash_stall_id(row["email"])): row["loja_id"]
        for row in lojas_disponiveis
    }

    for s in stalls:
        stall_id = str(s.get("stallId") or "").strip()

        if not stall_id:
            ignorados.append({"motivo": "sem stallId"})
            continue

        loja_id = lojas_por_stall.get(stall_id)

        if not loja_id:
            ignorados.append({"motivo": "barraca não encontrada"})
            continue

        itens_validados = []

        for i in (s.get("items") or []):
            qty = int(i.get("qty", 1))
            if qty < 1:
                return jsonify({"erro": "Quantidade inválida."}), 400
            produto = None
            produto_id = i.get("id")

            if produto_id:
                produto = conn.execute(
                    "SELECT id, nome, estoque, preco, configuravel "
                    "FROM produtos WHERE id=? AND loja_id=?",
                    (produto_id, loja_id)
                ).fetchone()

            nome_item = i.get("name", "?")
            config_snapshot = None
            preco_unit = None
            if produto and produto["configuravel"]:
                # Produto configurável: valida a escolha e calcula o preço no servidor
                try:
                    cfg = _resolver_configuracao(conn, produto, i.get("config"))
                except ValueError as e:
                    return jsonify({"erro": str(e)}), 400
                nome_item = cfg["descricao"]
                preco_unit = cfg["preco_unitario"]
                config_snapshot = cfg["snapshot"]

            itens_validados.append({
                "produto_id": produto["id"] if produto else None,
                "qty": qty,
                "nome": nome_item,
                "config": config_snapshot,
                "preco_unit": preco_unit,
                "preco_db": parse_preco(produto["preco"]) if produto else None,
                "preco_cliente": i.get("price"),
            })

        itens_desc = ", ".join(
            f"{it['qty']}x {it['nome']}"
            for it in itens_validados
        )

        valor = s.get("valor", "R$ 0,00")
        valor_numerico = float(s.get("valorNumerico") or 0)

        # Se a barraca tem algum item configurável, o total é recalculado aqui
        # no servidor (preço configurado + preço cadastrado dos demais itens).
        # Pedidos só com produtos comuns seguem exatamente como antes.
        if any(it["config"] for it in itens_validados):
            total = 0.0
            for it in itens_validados:
                if it["preco_unit"] is not None:
                    unit = it["preco_unit"]
                elif it["preco_db"] is not None:
                    unit = it["preco_db"]
                else:
                    unit = parse_preco(it["preco_cliente"])
                total += unit * it["qty"]
            valor_numerico = round(total, 2)
            valor = fmt_brl(valor_numerico)

        pendentes.append({
            "loja_id": loja_id,
            "itens": itens_validados,
            "itens_desc": itens_desc,
            "valor": valor,
            "valor_numerico": valor_numerico,
        })

    # ---- 2ª passada: desconta o estoque de forma atômica (tudo ou nada) ----
    # A condição "estoque >= qty" no próprio UPDATE evita a corrida de duas
    # pessoas comprando a última unidade ao mesmo tempo: só uma consegue.
    criados = []
    erros_estoque = []
    try:
        for p in pendentes:
            for it in p["itens"]:
                if not it["produto_id"]:
                    continue
                cur = conn.execute(
                    "UPDATE produtos SET estoque = estoque - ? "
                    "WHERE id=? AND estoque IS NOT NULL AND estoque >= ?",
                    (it["qty"], it["produto_id"], it["qty"])
                )
                if cur.rowcount == 0:
                    # ou o produto não controla estoque (não precisa bloquear),
                    # ou controla e não há quantidade suficiente — descobre qual.
                    prod = conn.execute(
                        "SELECT nome, estoque FROM produtos WHERE id=?",
                        (it["produto_id"],)
                    ).fetchone()
                    if prod and prod["estoque"] is not None:
                        erros_estoque.append(
                            f"{prod['nome']}: restam só {prod['estoque']} "
                            f"unidade(s), pedido pede {it['qty']}"
                        )

        if erros_estoque:
            conn.rollback()
            return jsonify({
                "erro": "Estoque insuficiente para finalizar a reserva.",
                "detalhes": erros_estoque,
            }), 409

        for p in pendentes:
            cur = conn.execute("""
                INSERT INTO pedidos (loja_id, cliente_id, cliente_nome,
                                     reserva_id, itens, valor, valor_numerico,
                                     hora, status)
                VALUES (?,?,?,?,?,?,?,?, 'pendente')
            """, (
                p["loja_id"], uid, u["nome"],
                reserva_id, p["itens_desc"],
                p["valor"], p["valor_numerico"],
                datetime.now().strftime("%H:%M"),
            ))
            pedido_id = cur.lastrowid
            criados.append(pedido_id)

            for it in p["itens"]:
                if not it["produto_id"]:
                    continue
                conn.execute(
                    "INSERT INTO pedido_itens (pedido_id, produto_id, quantidade, "
                    "configuracao, preco_unitario) VALUES (?,?,?,?,?)",
                    (pedido_id, it["produto_id"], it["qty"],
                     json.dumps(it["config"], ensure_ascii=False) if it["config"] else None,
                     it["preco_unit"])
                )

        commit(conn)
    except sqlite3.Error as e:
        conn.rollback()
        logger.error(f"Erro ao gravar pedidos: {str(e)[:100]}")
        # 🔒 SEGURANÇA: Mensagem genérica
        return jsonify({"erro": "Erro ao processar pedido"}), 500

    if criados:
        placeholders = ",".join("?" * len(criados))
        n = conn.execute(
            f"SELECT COUNT(*) AS n FROM pedidos WHERE id IN ({placeholders})",
            criados
        ).fetchone()["n"]
        
        if n != len(criados):
            logger.error(f"Pedidos não persistiram: esperava {len(criados)}, salvou {n}")
            return jsonify({"erro": "Erro ao processar pedido"}), 500
        
        logger.info(f"✓ Pedidos criados: {len(criados)} para cliente {u['email']}")
    else:
        logger.info(f"Nenhum pedido válido para cliente {u['email']}")

    return jsonify({
        "ok": True,
        "pedidos": criados,
        "reservaId": reserva_id,
        "ignorados": ignorados,
    }), 201


@app.get("/api/orders/minhas")
@exigir_tipo("cliente")
def minhas_reservas():
    conn = get_conn()
    rows = conn.execute("""
        SELECT p.*, l.nome AS loja_nome
        FROM pedidos p
        JOIN lojas l ON l.id = p.loja_id
        WHERE p.cliente_id = ?
        ORDER BY p.criado_em DESC
    """, (g.usuario["id"],)).fetchall()
    return jsonify(rows_to_list(rows))


# =====================================================================
# ADMIN
# =====================================================================
@app.get("/api/admin/usuarios")
@exigir_tipo("adm")
def admin_usuarios():
    conn = get_conn()
    us = conn.execute("""
        SELECT id, nome, email, tipo, criado_em,
               ip_acesso, mac_address, so_text, dispositivo_tipo
        FROM usuarios ORDER BY id
    """).fetchall()
    return jsonify(rows_to_list(us))


@app.post("/api/admin/usuarios")
@exigir_tipo("adm")
def admin_criar_usuario():
    data = request.get_json() or {}
    tipo = data.get("tipo")
    if tipo not in ("cliente", "vendedor", "adm"):
        return jsonify({"erro": "Tipo inválido"}), 400
    nome  = (data.get("nome") or "").strip()
    email = (data.get("email") or "").strip().lower()
    senha = data.get("senha") or ""
    if not nome or not email or len(senha) < 6:
        return jsonify({"erro": "Dados inválidos"}), 400

    conn = get_conn()
    try:
        if conn.execute("SELECT 1 FROM usuarios WHERE email=?", (email,)).fetchone():
            # 🔒 SEGURANÇA: Mensagem genérica
            return jsonify({"erro": "Não foi possível criar usuário"}), 400
        cur = conn.execute(
            "INSERT INTO usuarios (nome,email,senha_hash,tipo) VALUES (?,?,?,?)",
            (nome, email, generate_password_hash(senha), tipo),
        )
        uid = cur.lastrowid
        if tipo == "vendedor":
            conn.execute("INSERT INTO lojas (usuario_id, nome) VALUES (?,?)",
                         (uid, nome))
        commit(conn)
        logger.info(f"✓ Usuário criado via admin: {email} ({tipo})")
    except sqlite3.IntegrityError as e:
        conn.rollback()
        logger.warning(f"Erro IntegrityError ao criar usuário: {str(e)[:50]}")
        # 🔒 SEGURANÇA: Mensagem genérica
        return jsonify({"erro": "Não foi possível criar usuário"}), 400

    return jsonify({"id": uid, "ok": True}), 201


@app.get("/api/admin/reservas")
@exigir_tipo("adm")
def admin_reservas():
    conn = get_conn()
    rows = conn.execute("""
        SELECT p.*, l.nome AS loja_nome
        FROM pedidos p JOIN lojas l ON l.id = p.loja_id
        ORDER BY p.criado_em DESC
    """).fetchall()
    return jsonify(rows_to_list(rows))


@app.get("/api/admin/dashboard")
@exigir_tipo("adm")
def admin_dashboard():
    conn = get_conn()
    hoje = "date('now')"

    total_reservas = conn.execute(
        "SELECT COUNT(*) AS n FROM pedidos"
    ).fetchone()["n"]

    reservas_hoje = conn.execute(
        f"SELECT COUNT(*) AS n FROM pedidos WHERE date(criado_em) = {hoje}"
    ).fetchone()["n"]

    pendentes = conn.execute(
        "SELECT COUNT(*) AS n FROM pedidos WHERE status='pendente'"
    ).fetchone()["n"]

    lojas_ativas = conn.execute(
        "SELECT COUNT(*) AS n FROM lojas WHERE aberta=1"
    ).fetchone()["n"]

    estoque_baixo = conn.execute(
        "SELECT COUNT(*) AS n FROM produtos "
        "WHERE estoque IS NOT NULL AND estoque <= 3"
    ).fetchone()["n"]

    ultimas = conn.execute("""
        SELECT p.id, p.cliente_nome AS cliente, p.itens, p.valor,
               p.status, p.criado_em, l.nome AS loja
        FROM pedidos p JOIN lojas l ON l.id = p.loja_id
        ORDER BY p.criado_em DESC LIMIT 8
    """).fetchall()

    ranking = conn.execute("""
        SELECT l.nome AS loja, COUNT(p.id) AS reservas
        FROM lojas l
        LEFT JOIN pedidos p ON p.loja_id = l.id
        GROUP BY l.id
        ORDER BY reservas DESC
        LIMIT 6
    """).fetchall()

    return jsonify({
        "reservas_total": total_reservas,
        "reservas_hoje": reservas_hoje,
        "pendentes": pendentes,
        "lojas_ativas": lojas_ativas,
        "estoque_baixo": estoque_baixo,
        "ultimas": rows_to_list(ultimas),
        "ranking": rows_to_list(ranking),
    })


@app.get("/api/admin/lojas")
@exigir_tipo("adm")
def admin_lojas():
    conn = get_conn()
    rows = conn.execute("""
        SELECT l.*, u.nome AS dono_nome, u.email AS dono_email,
               (SELECT COUNT(*) FROM produtos WHERE loja_id=l.id) AS total_produtos,
               (SELECT COUNT(*) FROM pedidos  WHERE loja_id=l.id) AS total_reservas
        FROM lojas l JOIN usuarios u ON u.id = l.usuario_id
        ORDER BY l.nome
    """).fetchall()
    return jsonify(rows_to_list(rows))


@app.put("/api/admin/lojas/<int:lid>/foto")
@exigir_tipo("adm")
def admin_atualizar_foto_loja(lid):
    # Usa a coluna "logo" que já existe na tabela lojas — nenhuma
    # alteração de schema/banco de dados é feita aqui.
    data = request.get_json() or {}
    foto = (data.get("logo") or "").strip()
    conn = get_conn()
    loja = conn.execute("SELECT id FROM lojas WHERE id=?", (lid,)).fetchone()
    if not loja:
        return jsonify({"erro": "Loja não encontrada"}), 404
    conn.execute(
        "UPDATE lojas SET logo=?, atualizado_em=datetime('now') WHERE id=?",
        (foto, lid),
    )
    conn.commit()
    return jsonify({"ok": True, "logo": foto})


@app.get("/api/admin/produtos")
@exigir_tipo("adm")
def admin_produtos():
    conn = get_conn()
    rows = conn.execute("""
        SELECT p.*, l.nome AS loja_nome,
               (SELECT COUNT(*) FROM pedidos WHERE loja_id=p.loja_id) AS reservas
        FROM produtos p JOIN lojas l ON l.id = p.loja_id
        ORDER BY l.nome, p.nome
    """).fetchall()
    return jsonify(rows_to_list(rows))


# =====================================================================
# ERROS
# =====================================================================
@app.errorhandler(404)
def nf(_):
    return jsonify({"erro": "Rota não encontrada"}), 404


@app.errorhandler(500)
def se(e):
    # 🔒 SEGURANÇA: Mensagem genérica, sem detalhes do erro
    logger.error(f"Erro 500: {str(e)[:100]}")
    return jsonify({"erro": "Erro interno"}), 500


@app.errorhandler(sqlite3.Error)
def sqlerr(e):
    # 🔒 SEGURANÇA: Mensagem genérica para erros SQL
    logger.error(f"Erro SQLite: {str(e)[:100]}")
    return jsonify({"erro": "Erro ao processar"}), 500


# =====================================================================
# ESTÁTICOS
# =====================================================================
ALLOWED_STATIC = {
    "index.html", "style.css", "script.js",
    "parceiro.html", "parceiro.css", "parceiro.js",
    "admin.html", "admin.css", "admin.js",
}


@app.route("/")
def serve_index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/parceiro.html")
def serve_parceiro():
    return send_from_directory(BASE_DIR, "parceiro.html")


@app.route("/admin.html")
def serve_admin():
    return send_from_directory(BASE_DIR, "admin.html")


@app.route("/<path:filename>")
def serve_static(filename):
    if filename in ALLOWED_STATIC:
        return send_from_directory(BASE_DIR, filename)
    abort(404)


# =====================================================================
# HELPERS - Descobrir IP Local
# =====================================================================
def get_local_ip():
    """Tenta descobrir o IP local da máquina"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        try:
            return socket.gethostbyname(socket.gethostname())
        except:
            return "127.0.0.1"


# =====================================================================
# START
# =====================================================================
init_db()
seed_demo()


if __name__ == "__main__":
    local_ip = get_local_ip()
    
    print("=" * 70)
    print("  🎪 FEIRA NUZZI — Servidor iniciado")
    print("=" * 70)
    print()
    print("  📍 Acesso LOCAL:")
    print(f"     http://localhost:5000")
    print()
    print("  📍 Acesso REDE LOCAL (de outro computador/celular):")
    print(f"     http://{local_ip}:5000")
    print(f"     → Gere um QR Code apontando para: http://{local_ip}:5000")
    print()
    print("  📄 Portal do Parceiro:")
    print(f"     http://localhost:5000/parceiro.html")
    print(f"     http://{local_ip}:5000/parceiro.html")
    print()
    print("  🔐 Painel Admin:")
    print(f"     http://localhost:5000/admin.html")
    print(f"     http://{local_ip}:5000/admin.html")
    print()
    print("  💾 Banco SQLite:")
    print(f"     {str(DB_PATH)}")
    print()
    print("=" * 70)
    print("  ⏸️  Pressione CTRL+C para encerrar")
    print("=" * 70)
    
    app.run(host="0.0.0.0", port=5000, debug=False)