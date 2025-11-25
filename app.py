# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional
from datetime import date
import io
import random
import locale
from collections import defaultdict
import sys
import os
from flask import render_template, send_file, flash
from xhtml2pdf import pisa
from flask import Flask, render_template, send_file
from io import BytesIO
from datetime import date

# reportlab
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from flask import redirect, url_for, request, flash


# local database helper
import database

app = Flask(__name__)
app.config['SECRET_KEY'] = 'uma_chave_secreta_muito_forte_e_dificil'

# locale
try:
    locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'Portuguese_Brazil.1252')
    except locale.Error:
        print("Aviso: Configuração de localidade em Português falhou.")

# ReportLab styles
PDF_STYLES = getSampleStyleSheet()
PDF_STYLES.add(ParagraphStyle(name='CustomTitle', fontSize=18, alignment=1, spaceAfter=20, fontName='Helvetica-Bold', textColor=colors.navy))
PDF_STYLES.add(ParagraphStyle(name='CustomHeading2', fontSize=14, alignment=0, spaceBefore=15, spaceAfter=8, fontName='Helvetica-Bold', textColor=colors.darkblue))
PDF_STYLES.add(ParagraphStyle(name='CustomNormalSmall', fontSize=10, alignment=0, spaceAfter=5, textColor=colors.black))
PDF_STYLES.add(ParagraphStyle(name='CustomSummary', fontSize=16, alignment=0, spaceAfter=10, fontName='Helvetica-Bold', textColor=colors.black))

# helpers
def gerar_disparos_semanais_simulados():
    dias = ['segunda', 'terca', 'quarta', 'quinta', 'sexta', 'sabado', 'domingo']
    return {dia: random.randint(10, 80) for dia in dias}

# Forms
class VendedorForm(FlaskForm):
    nome = StringField('Nome', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    loja_id = SelectField('Loja', coerce=int, validators=[DataRequired()])
    status = SelectField('Status Inicial', choices=[
        ('Conectado', 'Conectado'),
        ('Restrito', 'Restrito'),
        ('Bloqueado', 'Bloqueado'),
        ('Desconectado', 'Desconectado')
    ], validators=[DataRequired()])
    submit = SubmitField('Adicionar Vendedor')

class LojaForm(FlaskForm):
    nome_loja = StringField('Nome da Loja', validators=[DataRequired(), Length(min=3)])
    responsavel = StringField('Responsável', validators=[DataRequired(), Length(min=3)])
    nome_vendedor = StringField('Nome do Gestor (Vendedor)', validators=[DataRequired(), Length(min=2)])
    email_vendedor = StringField('Email do Gestor (Vendedor)', validators=[DataRequired(), Email()])
    submit = SubmitField('Criar Loja')

class LojaEditForm(FlaskForm):
    nome = StringField('Nome da Loja', validators=[DataRequired(), Length(min=3)])
    responsavel = StringField('Responsável', validators=[DataRequired(), Length(min=3)])
    submit = SubmitField('Salvar Alterações')

class RelatorioForm(FlaskForm):
    loja_id_relatorio = SelectField('Selecione a Loja', coerce=int, validators=[DataRequired()])
    ligacoes_realizadas = TextAreaField(' SCRIPT DISPAROS DE LIGAÇÕES', validators=[Optional(), Length(max=500)], render_kw={"rows": 5})
    submit = SubmitField('Gerar PDF')
    def __init__(self, *args, **kwargs):
        super(RelatorioForm, self).__init__(*args, **kwargs)
        lojas = database.listar_lojas()
        self.loja_id_relatorio.choices = [(l['id'], l['nome']) for l in lojas]

# Helpers
def processar_dados_painel():
    vendedores = database.listar_vendedores()
    for v in vendedores:
        ds = database.get_disparos_semanais(v['id'])
        v['disparos_semanais'] = ds if ds else gerar_disparos_semanais_simulados()
    total_disparos = sum(sum(v['disparos_semanais'].values()) for v in vendedores)
    status_kpis = defaultdict(int)
    vendedores_por_status = defaultdict(list)
    bloqueados_hoje = []
    bases_pendentes_count = 0
    dia_bloqueio_count = defaultdict(int)
    for v in vendedores:
        status_kpis[v.get('status','Desconhecido')] += 1
        vendedores_por_status[v.get('status','Desconhecido')].append({
            'nome': v.get('nome'),
            'loja_nome': None,
            'ultimo_status_tipo': v.get('ultimo_status_tipo'),
            'ultimo_status_data': v.get('ultimo_status_data'),
        })
        if v.get('status') == 'Bloqueado':
            try:
                dia_semana = date.today().strftime('%A')
                dia_bloqueio_count[dia_semana] += 1
            except:
                pass
        if not v.get('base_tratada', False):
            bases_pendentes_count += 1
    dia_mais_bloqueio = max(dia_bloqueio_count, key=dia_bloqueio_count.get, default='N/A')
    return {
        'total_disparos': total_disparos,
        'status_kpis': status_kpis,
        'vendedores_por_status': vendedores_por_status,
        'bloqueados_hoje': bloqueados_hoje,
        'bases_pendentes_count': bases_pendentes_count,
        'dia_mais_bloqueio': dia_mais_bloqueio,
    }

def get_vendedores_by_loja_id(loja_id):
    vendedores = database.get_vendedores_by_loja(loja_id)
    for v in vendedores:
        ds = database.get_disparos_semanais(v['id'])
        v['disparos_semanais'] = ds if ds else gerar_disparos_semanais_simulados()
    return vendedores

def sanitize_filename(s: str):
    if not s:
        return "file"
    allowed = "-_.() abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    cleaned = "".join(c for c in s if c in allowed)
    return cleaned.replace(" ", "_")

# PDF helpers
def myPageTemplate(canvas, doc):
    canvas.saveState()
    page_width, page_height = A4
    canvas.setFillColor(colors.black)
    canvas.rect(0, page_height - 60, page_width, 60, fill=1)
    canvas.setFont('Helvetica-Bold', 16)
    canvas.setFillColor(colors.yellow)
    canvas.drawRightString(page_width - doc.rightMargin - 5, page_height - 35, "SUPER MEGA VENDAS")
    canvas.setFillColor(colors.yellow)
    canvas.rect(0, page_height - 65, page_width, 5, fill=1)
    canvas.setFillColor(colors.lightgrey)
    canvas.setFont('Helvetica-Bold', 150)
    canvas.drawCentredString(page_width / 2, page_height / 2 - 50, "SMV")
    canvas.setFillColor(colors.yellow)
    canvas.rect(0, 0, page_width, 40, fill=1)
    address_text = "Manhattan Business Office, Av. Campos Sales, 901. Sala 1008 - Tirol, Natal/RN"
    canvas.setFont('Helvetica-Bold', 9)
    canvas.setFillColor(colors.black)
    canvas.drawString(doc.leftMargin + 20, 15, address_text)
    canvas.restoreState()

from flask import render_template, send_file, flash
from xhtml2pdf import pisa
import io
import os
from datetime import date

def gerar_pdf_xhtml2pdf(loja_data, vendedores_loja, ligacoes_realizadas):
    # Garantir que dados existam
    loja_data = loja_data or {'nome':'N/A','responsavel':'N/A'}
    vendedores_loja = vendedores_loja or []

    for v in vendedores_loja:
        if 'disparos_semanais' not in v or not v['disparos_semanais']:
            v['disparos_semanais'] = {d:0 for d in ['segunda','terca','quarta','quinta','sexta','sabado','domingo']}
        status_classes = {
            'Conectado': 'status-connected',
            'Bloqueado': 'status-blocked',
            'Restrito': 'status-restricted',
            'Desconectado': 'status-disconnected'
        }
        v['status_class'] = status_classes.get(v.get('status','Desconectado'), 'status-disconnected')

    total_convites = sum(sum(v['disparos_semanais'].values()) for v in vendedores_loja)
    
    # Renderiza HTML
    html = render_template(
        'relatorio_template_html.html',
        loja=loja_data,
        vendedores_loja=vendedores_loja,
        data_hoje=date.today().strftime('%d/%m/%Y'),
        total_convites_enviados=total_convites,
        ligacoes_realizadas=ligacoes_realizadas
    )

    # Gerar PDF
    pdf = io.BytesIO()
    pisa_status = pisa.CreatePDF(io.StringIO(html), dest=pdf)
    
    if pisa_status.err:
        raise Exception("Erro ao gerar PDF")

    pdf.seek(0)

    # Criar pasta para salvar PDF
    folder_base = os.path.join('static', 'pdfs', loja_data.get('nome','loja'))
    os.makedirs(folder_base, exist_ok=True)
    filename = f"Relatorio_{loja_data.get('nome','loja')}_{date.today().strftime('%Y%m%d')}.pdf"
    disk_path = os.path.join(folder_base, filename)
    
    with open(disk_path, 'wb') as f:
        f.write(pdf.getbuffer())

    pdf.seek(0)
    return pdf, disk_path


# ---------------------- ROUTES ----------------------

@app.route('/')
def index():
    return redirect(url_for('painel'))

@app.route('/painel')
def painel():
    dados_painel = processar_dados_painel()
    vendedor_form = VendedorForm()
    lojas = database.listar_lojas()
    vendedor_form.loja_id.choices = [(l['id'], l['nome']) for l in lojas]
    loja_form = LojaForm()
    loja_edit_form = LojaEditForm()
    relatorio_form = RelatorioForm()
    vendedores = database.listar_vendedores()
    for v in vendedores:
        ds = database.get_disparos_semanais(v['id'])
        v['disparos_semanais'] = ds if ds else gerar_disparos_semanais_simulados()
    eventos_raw = []
    return render_template('dashboard.html',
                           pagina='painel',
                           today_date=date.today(),
                           db_vendedores=vendedores,
                           eventos=eventos_raw,
                           **dados_painel,
                           vendedor_form=vendedor_form,
                           loja_form=loja_form,
                           loja_edit_form=loja_edit_form,
                           relatorio_form=relatorio_form)

@app.route("/editar_disparos_semana", methods=["POST"])
def editar_disparos_semana():
    from database import atualizar_disparos_hoje, atualizar_disparos_semana
    vendedor_id = request.form.get("vendedor_id")

    if not vendedor_id:
        flash("Erro: Vendedor não identificado.", "danger")
        return redirect(request.referrer or url_for("vendedores"))

    # CASO 1 → Atualização de disparos DIÁRIOS
    disparos_hoje = request.form.get("disparos_hoje")
    if disparos_hoje is not None:
        try:
            atualizar_disparos_hoje(vendedor_id, int(disparos_hoje))
            flash("Disparos do dia atualizados com sucesso!", "success")
        except Exception as e:
            flash(f"Erro ao atualizar disparos diários: {e}", "danger")

        return redirect(url_for("vendedores"))

    # CASO 2 → Atualização de disparos SEMANAIS
    dias = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
    disparos_semana = {}

    try:
        for dia in dias:
            valor = request.form.get(f"disparo_{dia}")
            disparos_semana[dia] = int(valor) if valor is not None else 0

        atualizar_disparos_semana(vendedor_id, disparos_semana)
        flash("Disparos semanais atualizados com sucesso!", "success")

    except Exception as e:
        flash(f"Erro ao atualizar disparos da semana: {e}", "danger")

    return redirect(url_for("vendedores"))


# ---------------------- ROTAS DE VENDEDORES ----------------------
@app.route('/vendedores', methods=['GET', 'POST'])
def vendedores():
    vendedor_form = VendedorForm()
    lojas = database.listar_lojas()
    vendedor_form.loja_id.choices = [(l['id'], l['nome']) for l in lojas]
    relatorio_form = RelatorioForm()

    if vendedor_form.validate_on_submit():
        novo_vendedor = {
            'nome': vendedor_form.nome.data,
            'email': vendedor_form.email.data,
            'loja_id': vendedor_form.loja_id.data,
            'status': vendedor_form.status.data,
            'base_tratada': True,
            'disparos_dia': 0,
            'ultimo_status_tipo': vendedor_form.status.data,
            'ultimo_status_data': date.today().strftime('%d/%m/%Y')
        }
        database.insert_vendedor(novo_vendedor)
        flash(f'Vendedor {novo_vendedor["nome"]} adicionado com sucesso!', 'success')
        return redirect(url_for('vendedores'))

    # Usa a nova função que inclui os disparos semanais
    vendedores = database.listar_vendedores_com_disparos()

    return render_template(
        'dashboard.html',
        pagina='vendedores',
        vendedores=vendedores,
        vendedor_form=vendedor_form,
        loja_form=LojaForm(),
        loja_edit_form=LojaEditForm(),
        relatorio_form=relatorio_form,
        today_date=date.today()
    )

@app.route('/mudar_status_vendedor/<int:vendedor_id>/<novo_status>', methods=['POST'])
def mudar_status_vendedor(vendedor_id, novo_status):
    sucesso = database.update_status_vendedor(vendedor_id, novo_status)

    if not sucesso:
        flash("Erro ao alterar status")
    return redirect(url_for('vendedores'))

# Apagar um vendedor
@app.route('/deletar_vendedor/<int:vendedor_id>', methods=['POST'])
def deletar_vendedor(vendedor_id):
    database.deletar_vendedor(vendedor_id)
    flash('Vendedor removido com sucesso!', 'success')
    return redirect(url_for('vendedores'))

# ---------------------- ROTAS DE LOJAS ----------------------
@app.route('/lojas', methods=['GET','POST'])
def lojas():
    loja_form = LojaForm()
    loja_edit_form = LojaEditForm()
    relatorio_form = RelatorioForm()
    if loja_form.validate_on_submit():
        nova_loja = database.insert_loja(loja_form.nome_loja.data, loja_form.responsavel.data)
        novo_vendedor = {
            'nome': loja_form.nome_vendedor.data,
            'email': loja_form.email_vendedor.data,
            'loja_id': nova_loja['id'],
            'status': 'Conectado',
            'base_tratada': True,
            'disparos_dia': 0,
            'ultimo_status_tipo': 'Conectado',
            'ultimo_status_data': date.today().strftime('%d/%m/%Y')
        }
        database.insert_vendedor(novo_vendedor)
        flash(f"Loja '{nova_loja['nome']}' e Gestor cadastrados com sucesso!", 'success')
        return redirect(url_for('lojas'))
    lojas_com_vendedores = []
    for loja in database.listar_lojas():
        loja_copy = loja.copy()
        loja_copy['vendedores'] = database.get_vendedores_by_loja(loja['id'])
        lojas_com_vendedores.append(loja_copy)
    return render_template('dashboard.html',
                           pagina='lojas',
                           lojas=lojas_com_vendedores,
                           vendedor_form=VendedorForm(),
                           loja_form=loja_form,
                           loja_edit_form=loja_edit_form,
                           relatorio_form=relatorio_form,
                           today_date=date.today())

@app.route('/editar_loja', methods=['POST'])
def editar_loja():
    form = LojaEditForm(request.form)
    loja_id = int(request.form.get('loja_id'))
    if form.validate_on_submit():
        database.update_loja(loja_id, form.nome.data, form.responsavel.data)
        flash('Loja atualizada com sucesso!', 'success')
    else:
        flash('Erro de validação ao editar a loja.', 'warning')
    return redirect(url_for('lojas'))


# ---------------------- ROTAS DE PDF ----------------------
@app.route('/gerar_relatorio_pdf')
def gerar_relatorio_pdf():
    # Dados do relatório
    loja = {'nome': 'Loja Teste', 'responsavel': 'João'}
    data_hoje = date.today().strftime('%d/%m/%Y')
    total_convites_enviados = 120
    ligacoes_realizadas = "Exemplo de relato manual."
    vendedores_loja = [
        {'nome': 'Vendedor 1', 'disparos_semanais': {1:10, 2:12}, 'disparos_dia': 5, 'status':'Connected', 'base_tratada': True},
        {'nome': 'Vendedor 2', 'disparos_semanais': {1:8, 2:9}, 'disparos_dia': 4, 'status':'Blocked', 'base_tratada': False},
    ]

    # Renderiza HTML do template
    html = render_template('relatorio_template_html.html',
                           loja=loja,
                           data_hoje=data_hoje,
                           total_convites_enviados=total_convites_enviados,
                           ligacoes_realizadas=ligacoes_realizadas,
                           vendedores_loja=vendedores_loja)

    # PDF em memória
    pdf = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=pdf)

    if pisa_status.err:
        return "Erro ao gerar PDF", 500

    pdf.seek(0)
    return send_file(pdf, as_attachment=True, download_name="relatorio.pdf", mimetype='application/pdf')

if __name__ == "__main__":
    app.run(debug=True)