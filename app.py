# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional
from datetime import date
import locale
from collections import defaultdict
import os
from io import BytesIO
from xhtml2pdf import pisa

# ReportLab
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

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
PDF_STYLES.add(ParagraphStyle(name='CustomSummary', fontSize=16, alignment=0, spaceAfter=10, fontName='Helvetica-Bold', textColor=colors.black'))

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
    vendedores = database.listar_vendedores_com_disparos()
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
        v['disparos_semanais'] = ds if ds else {
            'segunda': 0, 'terca': 0, 'quarta': 0, 'quinta': 0,
            'sexta': 0, 'sabado': 0, 'domingo': 0
        }
    return vendedores

# ---------------------- ROUTES ----------------------

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
        novo_vendedor_db = database.insert_vendedor(novo_vendedor)

        # Cria disparos semanais zerados
        database.update_disparos_semanais(novo_vendedor_db['id'], {
            'segunda': 0, 'terca': 0, 'quarta': 0, 'quinta': 0,
            'sexta': 0, 'sabado': 0, 'domingo': 0
        })

        flash(f'Vendedor {novo_vendedor["nome"]} adicionado com sucesso!', 'success')
        return redirect(url_for('vendedores'))

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

@app.route("/editar_disparos_dia", methods=["POST"])
def editar_disparos_dia():
    vendedor_id = request.form.get("vendedor_id")
    disparos_hoje = request.form.get("disparos_hoje")

    if not vendedor_id or disparos_hoje is None:
        flash("Erro ao salvar disparos. Dados incompletos.", "danger")
        return redirect(url_for("vendedores"))

    try:
        database.atualizar_disparos_dia(vendedor_id, int(disparos_hoje))
        flash("Disparos de hoje atualizados com sucesso!", "success")
    except Exception as e:
        flash(f"Erro ao atualizar: {e}", "danger")

    return redirect(url_for("vendedores"))

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
        novo_vendedor_db = database.insert_vendedor(novo_vendedor)

        # Cria disparos semanais zerados
        database.update_disparos_semanais(novo_vendedor_db['id'], {
            'segunda': 0, 'terca': 0, 'quarta': 0, 'quinta': 0,
            'sexta': 0, 'sabado': 0, 'domingo': 0
        })

        flash(f"Loja '{nova_loja['nome']}' e Gestor cadastrados com sucesso!", 'success')
        return redirect(url_for('lojas'))

    lojas_com_vendedores = []
    for loja in database.listar_lojas():
        loja_copy = loja.copy()
        loja_copy['vendedores'] = get_vendedores_by_loja_id(loja['id'])
        lojas_com_vendedores.append(loja_copy)
    return render_template('dashboard.html',
                           pagina='lojas',
                           lojas=lojas_com_vendedores,
                           vendedor_form=VendedorForm(),
                           loja_form=loja_form,
                           loja_edit_form=loja_edit_form,
                           relatorio_form=relatorio_form,
                           today_date=date.today())

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