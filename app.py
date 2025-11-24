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

# reportlab
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm

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

def gerar_pdf_reportlab(loja_data, vendedores_data, ligacoes_realizadas):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
    Story = []
    styles = PDF_STYLES
    Story.append(Paragraph("Relatório Gerencial de Desempenho de Disparos", styles['CustomTitle']))
    Story.append(Spacer(1, 0.5 * cm))
    Story.append(Paragraph("Informações da Loja e Período", styles['CustomHeading2']))
    Story.append(Paragraph(f"<b>Loja:</b> {loja_data.get('nome','N/A')}", styles['CustomNormalSmall']))
    Story.append(Paragraph(f"<b>Responsável:</b> {loja_data.get('responsavel','N/A')}", styles['CustomNormalSmall']))
    Story.append(Paragraph(f"<b>Data de Geração:</b> {date.today().strftime('%d de %B de %Y')}", styles['CustomNormalSmall']))
    Story.append(Spacer(1, 0.7 * cm))
    total_convites = sum(sum(v['disparos_semanais'].values()) for v in vendedores_data)
    Story.append(Paragraph(f"Total de Convites Enviados (Estimado na Semana): <u>{total_convites}</u>", styles['CustomSummary']))
    Story.append(Paragraph("Este total é a soma dos disparos semanais registrados por todos os vendedores ativos desta loja.", styles['CustomNormalSmall']))
    Story.append(Spacer(1, 0.7 * cm))
    Story.append(Paragraph("Relato Manual (Ações de Follow-up)", styles['CustomHeading2']))
    relato = ligacoes_realizadas if ligacoes_realizadas else "Nenhum relato manual fornecido no momento da geração do relatório."
    Story.append(Paragraph(relato, styles['CustomNormalSmall']))
    Story.append(Spacer(1, 0.7 * cm))
    Story.append(Paragraph("Desempenho Individual dos Vendedores", styles['CustomHeading2']))
    table_data = [["Vendedor", "Disparos (Semana)", "Disparos (Hoje)", "Status Atual", "Base Tratada?"]]
    for vendedor in vendedores_data:
        total_semana = sum(vendedor['disparos_semanais'].values())
        status_text = vendedor.get('status', '')
        base_tratada_text = 'Sim' if vendedor.get('base_tratada') else 'Não'
        row = [
            Paragraph(vendedor.get('nome',''), styles['CustomNormalSmall']),
            Paragraph(str(total_semana), styles['CustomNormalSmall']),
            Paragraph(str(vendedor.get('disparos_dia',0)), styles['CustomNormalSmall']),
            Paragraph(status_text, styles['CustomNormalSmall']),
            Paragraph(base_tratada_text, styles['CustomNormalSmall'])
        ]
        table_data.append(row)
    if len(table_data) > 1:
        table = Table(table_data, colWidths=[3.5*cm,2.5*cm,2.5*cm,3*cm,2.5*cm])
        table_style = TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.navy),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
            ('GRID',(0,0),(-1,-1),0.5,colors.lightgrey),
            ('BACKGROUND',(0,1),(-1,-1),colors.white),
        ])
        table.setStyle(table_style)
        Story.append(table)
    else:
        Story.append(Paragraph("Nenhum vendedor encontrado para esta loja.", styles['CustomNormalSmall']))
    doc.build(Story, onFirstPage=myPageTemplate, onLaterPages=myPageTemplate)
    buffer.seek(0)
    folder_base = os.path.join('static', 'pdfs', sanitize_filename(loja_data.get('nome','loja')))
    os.makedirs(folder_base, exist_ok=True)
    filename_base = f"Relatorio_{sanitize_filename(loja_data.get('nome','loja'))}_{date.today().strftime('%Y%m%d')}.pdf"
    disk_path = os.path.join(folder_base, filename_base)
    with open(disk_path, 'wb') as f:
        f.write(buffer.getbuffer())
    buffer.seek(0)
    return buffer, disk_path

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

@app.route('/vendedores/<int:vendedor_id>/alternar_base', methods=['POST'])
def alternar_base_tratada(vendedor_id):
    from database import toggle_base_tratada
    toggle_base_tratada(vendedor_id)
    flash("Status de base tratada alterado!", "success")
    return redirect(request.referrer or url_for('vendedores'))

# ---------------------- ROTAS DE PDF ----------------------
@app.route('/gerar_relatorio_pdf', methods=['POST'])
def gerar_relatorio_pdf():
    form = RelatorioForm(request.form)
    lojas = database.listar_lojas()
    form.loja_id_relatorio.choices = [(l['id'], l['nome']) for l in lojas]
    if form.validate_on_submit():
        loja_id = form.loja_id_relatorio.data
        ligacoes_realizadas = form.ligacoes_realizadas.data
        loja_data = database.get_loja_by_id(loja_id)
        vendedores_loja = get_vendedores_by_loja_id(loja_id)
        if not loja_data:
            flash(f"Erro: Loja com ID {loja_id} não encontrada.", 'danger')
            return redirect(url_for('painel'))
        try:
            pdf_buffer, disk_path = gerar_pdf_reportlab(loja_data, vendedores_loja, ligacoes_realizadas)
            filename = os.path.basename(disk_path)
            return send_file(pdf_buffer, as_attachment=True, download_name=filename)
        except Exception as e:
            flash(f"Erro ao gerar PDF: {str(e)}", 'danger')
            return redirect(url_for('painel'))
    flash("Formulário inválido!", "warning")
    return redirect(url_for('painel'))

if __name__ == '__main__':
    app.run(debug=True)
