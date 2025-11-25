# database.py
import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
import sys
from datetime import date

load_dotenv()

# ==============================
# CONFIGURAÇÃO DO DATABASE + SSL
# ==============================
raw_url = os.getenv("DATABASE_URL")

if not raw_url:
    print("ERRO: DATABASE_URL não configurado nas variáveis de ambiente.", file=sys.stderr)
else:
    if "sslmode" not in raw_url:
        raw_url += "?sslmode=require"

DATABASE_URL = raw_url


# ==============================
# FUNÇÃO DE CONEXÃO
# ==============================
def get_conn():
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print("Erro ao conectar ao banco:", e, file=sys.stderr)
        raise


# ==============================
# CRIAÇÃO DE TABELAS
# ==============================
def ensure_tables():
    sql = """
    CREATE TABLE IF NOT EXISTS lojas (
        id SERIAL PRIMARY KEY,
        nome TEXT NOT NULL,
        responsavel TEXT
    );

    CREATE TABLE IF NOT EXISTS vendedores (
        id SERIAL PRIMARY KEY,
        nome TEXT NOT NULL,
        email TEXT,
        loja_id INTEGER REFERENCES lojas(id) ON DELETE SET NULL,
        status TEXT,
        base_tratada BOOLEAN DEFAULT FALSE,
        disparos_dia INTEGER DEFAULT 0,
        ultimo_status_tipo TEXT,
        ultimo_status_data TEXT
    );

    CREATE TABLE IF NOT EXISTS disparos_semanais (
        id SERIAL PRIMARY KEY,
        vendedor_id INTEGER REFERENCES vendedores(id) ON DELETE CASCADE,
        segunda INTEGER DEFAULT 0,
        terca INTEGER DEFAULT 0,
        quarta INTEGER DEFAULT 0,
        quinta INTEGER DEFAULT 0,
        sexta INTEGER DEFAULT 0,
        sabado INTEGER DEFAULT 0,
        domingo INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS eventos (
        id SERIAL PRIMARY KEY,
        nome TEXT,
        data_evento DATE,
        loja_id INTEGER REFERENCES lojas(id) ON DELETE SET NULL
    );
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(sql)
    conn.commit()
    cur.close()
    conn.close()

# Garante as tabelas
try:
    ensure_tables()
except Exception as e:
    print("Aviso: ensure_tables erro (pode ser ignorado):", e)


# ==============================
# FUNÇÕES CRUD
# ==============================

def listar_lojas():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM lojas ORDER BY id;")
    data = cur.fetchall()
    cur.close(); conn.close()
    return [dict(r) for r in data]


def get_loja_by_id(loja_id):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM lojas WHERE id = %s;", (loja_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return dict(row) if row else None


def insert_loja(nome, responsavel):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("INSERT INTO lojas (nome, responsavel) VALUES (%s, %s) RETURNING *;", (nome, responsavel))
    row = cur.fetchone()
    conn.commit()
    cur.close(); conn.close()
    return dict(row)


def update_loja(loja_id, nome, responsavel):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE lojas SET nome=%s, responsavel=%s WHERE id=%s;", (nome, responsavel, loja_id))
    conn.commit()
    cur.close(); conn.close()


# ---------- VENDEDORES ----------

def listar_vendedores():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM vendedores ORDER BY id;")
    data = cur.fetchall()
    cur.close(); conn.close()
    return [dict(r) for r in data]


def get_vendedores_by_loja(loja_id):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM vendedores WHERE loja_id = %s ORDER BY id;", (loja_id,))
    data = cur.fetchall()
    cur.close(); conn.close()
    return [dict(r) for r in data]


def insert_vendedor(v):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        INSERT INTO vendedores (nome, email, loja_id, status, base_tratada, disparos_dia, ultimo_status_tipo, ultimo_status_data)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *;
    """, (v.get('nome'), v.get('email'), v.get('loja_id'), v.get('status'),
          v.get('base_tratada', False), v.get('disparos_dia',0),
          v.get('ultimo_status_tipo'), v.get('ultimo_status_data')))
    row = cur.fetchone()
    conn.commit()
    cur.close(); conn.close()
    return dict(row)


def update_status_vendedor(vendedor_id, novo_status):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE vendedores
        SET status = %s,
            ultimo_status_tipo = %s,
            ultimo_status_data = TO_CHAR(CURRENT_DATE, 'DD/MM/YYYY')
        WHERE id = %s;
    """, (novo_status, novo_status, vendedor_id))
    conn.commit()
    cur.close(); conn.close()


def deletar_vendedor(vendedor_id):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM vendedores WHERE id = %s", (vendedor_id,))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Erro ao deletar vendedor: {e}")
        return False
    finally:
        cur.close()
        conn.close()


# --------- DISPAROS ---------

def update_disparos_semanais(vendedor_id, d):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM disparos_semanais WHERE vendedor_id=%s;", (vendedor_id,))
    exists = cur.fetchone()

    valores = (
        d.get('segunda',0), d.get('terca',0), d.get('quarta',0),
        d.get('quinta',0), d.get('sexta',0), d.get('sabado',0),
        d.get('domingo',0)
    )

    if exists:
        cur.execute("""
            UPDATE disparos_semanais SET segunda=%s, terca=%s, quarta=%s, quinta=%s,
            sexta=%s, sabado=%s, domingo=%s WHERE vendedor_id=%s;
        """, valores + (vendedor_id,))
    else:
        cur.execute("""
            INSERT INTO disparos_semanais (vendedor_id, segunda, terca, quarta, quinta, sexta, sabado, domingo)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s);
        """, (vendedor_id,) + valores)

    conn.commit()
    cur.close(); conn.close()


def get_disparos_semanais(vendedor_id):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM disparos_semanais WHERE vendedor_id=%s;", (vendedor_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return dict(row) if row else None


def update_disparos_dia(vendedor_id, valor):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE vendedores SET disparos_dia=%s WHERE id=%s;", (valor, vendedor_id))
    conn.commit()
    cur.close(); conn.close()
