from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional, NumberRange
from datetime import date
import io
import random
import locale
from collections import defaultdict
import sys

# --- IMPORTAÇÕES PURAS PYTHON PARA PDF (ReportLab) ---
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas # Para desenhar no canvas diretamente
from reportlab.lib.utils import ImageReader # Para imagens se necessário (mas não usaremos por enquanto)

# --- CONFIGURAÇÃO E MODELAGEM DE DADOS (SIMULADO) ---

app = Flask(__name__)
app.config['SECRET_KEY'] = 'uma_chave_secreta_muito_forte_e_dificil' 

try:
    locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'Portuguese_Brazil.1252')
    except locale.Error:
        print("Aviso: Configuração de localidade em Português falhou.")

# --- DEFINIÇÃO GLOBAL DOS ESTILOS DO REPORTLAB ---
PDF_STYLES = getSampleStyleSheet()
PDF_STYLES.add(ParagraphStyle(name='CustomTitle', fontSize=18, alignment=1, spaceAfter=20, fontName='Helvetica-Bold', textColor=colors.navy))
PDF_STYLES.add(ParagraphStyle(name='CustomHeading2', fontSize=14, alignment=0, spaceBefore=15, spaceAfter=8, fontName='Helvetica-Bold', textColor=colors.darkblue))
PDF_STYLES.add(ParagraphStyle(name='CustomNormalSmall', fontSize=10, alignment=0, spaceAfter=5, textColor=colors.black))
PDF_STYLES.add(ParagraphStyle(name='CustomSummary', fontSize=16, alignment=0, spaceAfter=10, fontName='Helvetica-Bold', textColor=colors.black))
PDF_STYLES.add(ParagraphStyle(name='HeaderLogoText', fontSize=16, alignment=2, fontName='Helvetica-Bold', textColor=colors.yellow)) # Estilo para o texto do logo
PDF_STYLES.add(ParagraphStyle(name='FooterAddress', fontSize=9, alignment=0, fontName='Helvetica-Bold', textColor=colors.black)) # Estilo para o texto do rodapé


# SIMULAÇÃO DE BANCO DE DADOS
db_lojas = [
    {'id': 1, 'nome': 'Mega Loja Centro', 'responsavel': 'Ana Paula Silva'},
    {'id': 2, 'nome': 'Filial Zona Sul', 'responsavel': 'Carlos Eduardo Viera'},
    {'id': 3, 'nome': 'Loja Digital', 'responsavel': 'Beatriz Oliveira'}
]

def gerar_disparos_semanais_simulados():
    dias = ['segunda', 'terca', 'quarta', 'quinta', 'sexta', 'sabado', 'domingo']
    return {dia: random.randint(10, 80) for dia in dias}

db_vendedores = [
    {'id': 101, 'nome': 'Ricardo Gestor', 'loja_id': 1, 'loja': 'Mega Loja Centro', 'email': 'ricardo@megacentro.com', 'status': 'Conectado', 'base_tratada': True, 'disparos_dia': 120, 'disparos_semanais': gerar_disparos_semanais_simulados(), 'ultimo_status_tipo': 'Conectado', 'ultimo_status_data': '15/11/2025'},
    {'id': 102, 'nome': 'Mariana Vendas', 'loja_id': 1, 'loja': 'Mega Loja Centro', 'email': 'mariana@megacentro.com', 'status': 'Restrito', 'base_tratada': False, 'disparos_dia': 50, 'disparos_semanais': gerar_disparos_semanais_simulados(), 'ultimo_status_tipo': 'Restrito', 'ultimo_status_data': '14/11/2025'},
    {'id': 201, 'nome': 'Julio Cesar', 'loja_id': 2, 'loja': 'Filial Zona Sul', 'email': 'julio@zonasul.com', 'status': 'Bloqueado', 'base_tratada': True, 'disparos_dia': 10, 'disparos_semanais': gerar_disparos_semanais_simulados(), 'ultimo_status_tipo': 'Bloqueado', 'ultimo_status_data': '15/11/2025'},
    {'id': 301, 'nome': 'Patricia Tech', 'loja_id': 3, 'loja': 'Loja Digital', 'email': 'patricia@digital.com', 'status': 'Conectado', 'base_tratada': True, 'disparos_dia': 200, 'disparos_semanais': gerar_disparos_semanais_simulados(), 'ultimo_status_tipo': 'Conectado', 'ultimo_status_data': '16/11/2025'},
]

db_eventos = [
    {'nome': 'Reunião de Metas Mensais', 'data_evento': date(2025, 11, 20), 'loja': db_lojas[0]},
    {'nome': 'Treinamento de Base', 'data_evento': date(2025, 11, 22), 'loja': db_lojas[1]}
]

# --- FORMULÁRIOS WTFORMS (Sem alterações) ---

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
    # Definido dentro do init para carregar as opções dinamicamente
    loja_id_relatorio = SelectField('Selecione a Loja', coerce=int, validators=[DataRequired()])
    ligacoes_realizadas = TextAreaField(' SCRIPT DISPAROS DE LIGAÇÕES', validators=[Optional(), Length(max=500)], render_kw={"rows": 5})
    submit = SubmitField('Gerar PDF')

    def __init__(self, *args, **kwargs):
        super(RelatorioForm, self).__init__(*args, **kwargs)
        self.loja_id_relatorio.choices = [(l['id'], l['nome']) for l in db_lojas]

# --- FUNÇÕES AUXILIARES DE PROCESSAMENTO DE DADOS (Sem alterações) ---

def processar_dados_painel():
    """Calcula KPIs e organiza dados para o Painel de Controle."""
    total_disparos = sum(sum(v['disparos_semanais'].values()) for v in db_vendedores)
    
    status_kpis = defaultdict(int)
    vendedores_por_status = defaultdict(list)
    bloqueados_hoje = []
    bases_pendentes_count = 0
    
    dia_bloqueio_count = defaultdict(int)

    for v in db_vendedores:
        status_kpis[v['status']] += 1
        
        # Cria uma view simplificada para a tabela de alerta
        vendedores_por_status[v['status']].append({
            'nome': v['nome'],
            'loja_nome': v['loja'],
            'ultimo_status_tipo': v['ultimo_status_tipo'],
            'ultimo_status_data': v['ultimo_status_data'],
        })

        if v['status'] == 'Bloqueado':
            # Simula a contagem de bloqueios por dia (usando o último status para simular o dia)
            try:
                dia_semana = date.today().strftime('%A')
                dia_bloqueio_count[dia_semana] += 1
            except:
                pass # Ignora se a formatação falhar
        
        if not v['base_tratada']:
            bases_pendentes_count += 1

    # Encontra o dia com mais bloqueios
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
    """Filtra vendedores para uma loja específica."""
    return [v for v in db_vendedores if v['loja_id'] == loja_id]

# --- FUNÇÃO PARA DESENHAR CABEÇALHO E RODAPÉ EM CADA PÁGINA (PAGE TEMPLATE) ---
def myPageTemplate(canvas, doc):
    canvas.saveState()
    
    # Dimensões da página
    page_width, page_height = A4
    
    # --- CABEÇALHO ---
    # Faixa preta superior
    canvas.setFillColor(colors.black)
    canvas.rect(0, page_height - 60, page_width, 60, fill=1) # x, y, width, height
    
    # Texto "SUPER MEGA VENDAS" (simulando logo)
    canvas.setFont('Helvetica-Bold', 16)
    canvas.setFillColor(colors.yellow)
    canvas.drawRightString(page_width - doc.rightMargin - 5, page_height - 35, "SUPER MEGA VENDAS") # Ajuste a posição X e Y
    
    # Faixa amarela abaixo do texto
    canvas.setFillColor(colors.yellow)
    # A largura da faixa amarela pode ser ajustada para simular o "corte" da imagem original
    # Aqui farei uma faixa completa para simplificar
    canvas.rect(0, page_height - 65, page_width, 5, fill=1) # x, y, width, height


    # --- MARCA D'ÁGUA "SMV" ---
    canvas.setFillColor(colors.lightgrey) # Cor cinza claro para a marca d'água
    canvas.setFont('Helvetica-Bold', 150) # Tamanho da fonte grande
    canvas.drawCentredString(page_width / 2, page_height / 2 - 50, "SMV") # Centraliza na página

    # --- RODAPÉ ---
    # Faixa amarela do rodapé
    canvas.setFillColor(colors.yellow)
    canvas.rect(0, 0, page_width, 40, fill=1) # x, y, width, height (ajustar altura se necessário)
    
    # Texto do endereço no rodapé
    address_text = "Manhattan Business Office, Av. Campos Sales, 901. Sala 1008 - Tirol, Natal/RN"
    canvas.setFont('Helvetica-Bold', 9)
    canvas.setFillColor(colors.black)
    
    # Posiciona o texto do endereço (alinhado à esquerda no exemplo, com margem)
    canvas.drawString(doc.leftMargin + 20, 15, address_text) # x, y

    canvas.restoreState()


# --- FUNÇÃO CENTRAL PARA GERAÇÃO DE PDF (ReportLab) ---

def gerar_pdf_reportlab(loja_data, vendedores_data, ligacoes_realizadas):
    """
    Gera um PDF usando ReportLab (Puro Python) com template fixo de cabeçalho/rodapé e marca d'água.
    """
    
    buffer = io.BytesIO()
    
    # Usamos o pageTemplate para aplicar o cabeçalho e rodapé em todas as páginas
    doc = SimpleDocTemplate(buffer, pagesize=A4, 
                            rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
    
    # Define as margens superiores e inferiores para o CONTEÚDO
    # Deixa espaço para o cabeçalho (aprox. 70pt do topo) e rodapé (aprox. 40pt de baixo)
    doc.topMargin = 70
    doc.bottomMargin = 40
    
    Story = []
    styles = PDF_STYLES
    
    # Título Principal do Relatório (será abaixo do cabeçalho fixo)
    Story.append(Paragraph("Relatório Gerencial de Desempenho de Disparos", styles['CustomTitle']))
    Story.append(Spacer(1, 0.5 * cm))

    # Informações da Loja e Período
    Story.append(Paragraph("Informações da Loja e Período", styles['CustomHeading2']))
    Story.append(Paragraph(f"<b>Loja:</b> {loja_data.get('nome', 'N/A')}", styles['CustomNormalSmall']))
    Story.append(Paragraph(f"<b>Responsável:</b> {loja_data.get('responsavel', 'N/A')}", styles['CustomNormalSmall']))
    Story.append(Paragraph(f"<b>Data de Geração:</b> {date.today().strftime('%d de %B de %Y')}", styles['CustomNormalSmall']))
    Story.append(Spacer(1, 0.7 * cm))

    # Total de Convites (Sem título "KPIs")
    total_convites = sum(sum(v['disparos_semanais'].values()) for v in vendedores_data)
    Story.append(Paragraph(f"Total de Convites Enviados (Estimado na Semana): <u>{total_convites}</u>", styles['CustomSummary']))
    Story.append(Paragraph("Este total é a soma dos disparos semanais registrados por todos os vendedores ativos desta loja.", styles['CustomNormalSmall']))
    Story.append(Spacer(1, 0.7 * cm))
    
    # Relato Manual
    Story.append(Paragraph("Relato Manual (Ações de Follow-up)", styles['CustomHeading2']))
    relato = ligacoes_realizadas if ligacoes_realizadas else "Nenhum relato manual fornecido no momento da geração do relatório."
    Story.append(Paragraph(relato, styles['CustomNormalSmall']))
    Story.append(Spacer(1, 0.7 * cm))
    
    # Tabela de Desempenho Individual
    Story.append(Paragraph("Desempenho Individual dos Vendedores", styles['CustomHeading2']))
    
    table_data = [
        ["Vendedor", "Disparos (Semana)", "Disparos (Hoje)", "Status Atual", "Base Tratada?"]
    ]
    
    for vendedor in vendedores_data:
        total_semana = sum(vendedor['disparos_semanais'].values())
        status_text = vendedor['status']
        base_tratada_text = 'Sim' if vendedor['base_tratada'] else 'Não'
        
        row = [
            Paragraph(vendedor['nome'], styles['CustomNormalSmall']),
            Paragraph(str(total_semana), styles['CustomNormalSmall']),
            Paragraph(str(vendedor['disparos_dia']), styles['CustomNormalSmall']),
            Paragraph(status_text, styles['CustomNormalSmall']),
            Paragraph(base_tratada_text, styles['CustomNormalSmall']),
        ]
        table_data.append(row)

    if len(table_data) > 1:
        table = Table(table_data, colWidths=[3.5*cm, 2.5*cm, 2.5*cm, 3*cm, 2.5*cm])
        
        table_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.navy),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ])
        
        table.setStyle(table_style)
        Story.append(table)
    else:
         Story.append(Paragraph("Nenhum vendedor encontrado para esta loja.", styles['CustomNormalSmall']))


    # Construção do Documento, aplicando o template de página
    doc.build(Story, onFirstPage=myPageTemplate, onLaterPages=myPageTemplate)
    
    buffer.seek(0)
    return buffer

# --- ROTAS DA APLICAÇÃO (sem alterações, exceto pela chamada da função de PDF) ---

@app.route('/')
def index():
    return redirect(url_for('painel'))

@app.route('/painel')
def painel():
    """Rota para o Painel de Controle Principal."""
    dados_painel = processar_dados_painel()
    
    # Inicializa formulários para modais que podem ser abertos aqui
    vendedor_form = VendedorForm()
    vendedor_form.loja_id.choices = [(l['id'], l['nome']) for l in db_lojas]
    
    loja_form = LojaForm()
    loja_edit_form = LojaEditForm()
    relatorio_form = RelatorioForm()
    
    return render_template('dashboard.html', 
        pagina='painel', 
        today_date=date.today(),
        db_vendedores=db_vendedores, # Passa todos os vendedores para o cálculo do gráfico
        eventos=db_eventos,
        
        # Dados do painel
        **dados_painel,
        
        # Formulários para modais
        vendedor_form=vendedor_form,
        loja_form=loja_form,
        loja_edit_form=loja_edit_form,
        relatorio_form=relatorio_form
    )

@app.route('/gerar_relatorio_pdf', methods=['POST'])
def gerar_relatorio_pdf():
    """
    Gera o PDF usando ReportLab.
    """
    form = RelatorioForm(request.form)
    form.loja_id_relatorio.choices = [(l['id'], l['nome']) for l in db_lojas] 

    if form.validate_on_submit():
        loja_id = form.loja_id_relatorio.data
        ligacoes_realizadas = form.ligacoes_realizadas.data
        
        loja_data = next((l for l in db_lojas if l['id'] == loja_id), None)
        vendedores_loja = get_vendedores_by_loja_id(loja_id)

        if not loja_data:
            flash(f"Erro: Loja com ID {loja_id} não encontrada.", 'danger')
            return redirect(url_for('painel'))

        try:
            pdf_buffer = gerar_pdf_reportlab(loja_data, vendedores_loja, ligacoes_realizadas)
            
            filename = f"Relatorio_Desempenho_{loja_data['nome']}_{date.today().strftime('%Y%m%d')}.pdf"
            return send_file(pdf_buffer, as_attachment=True, 
                             download_name=filename, 
                             mimetype='application/pdf')

        except Exception as e:
            print(f"Erro detalhado na geração do PDF (ReportLab): {e}", file=sys.stderr)
            flash(f"Erro ao gerar PDF: {e}. Verifique se a biblioteca 'reportlab' está instalada e se os estilos estão corretos.", 'danger')
            return redirect(url_for('painel'))

    else:
        flash("Erro de validação no formulário de relatório. Por favor, selecione uma loja.", 'warning')
        return redirect(url_for('painel'))

# --- Rotas de CRUD para Lojas, Vendedores, etc ---

@app.route('/vendedores', methods=['GET', 'POST'])
def vendedores():
    vendedor_form = VendedorForm()
    vendedor_form.loja_id.choices = [(l['id'], l['nome']) for l in db_lojas]
    relatorio_form = RelatorioForm()
    
    if vendedor_form.validate_on_submit():
        novo_id = max(v['id'] for v in db_vendedores) + 1 if db_vendedores else 101
        novo_vendedor = {
            'id': novo_id,
            'nome': vendedor_form.nome.data,
            'email': vendedor_form.email.data,
            'loja_id': vendedor_form.loja_id.data,
            'loja': next(l['nome'] for l in db_lojas if l['id'] == vendedor_form.loja_id.data),
            'status': vendedor_form.status.data,
            'base_tratada': True, 
            'disparos_dia': 0, 
            'disparos_semanais': gerar_disparos_semanais_simulados(),
            'ultimo_status_tipo': vendedor_form.status.data, 
            'ultimo_status_data': date.today().strftime('%d/%m/%Y')
        }
        db_vendedores.append(novo_vendedor)
        flash(f'Vendedor {novo_vendedor["nome"]} adicionado com sucesso!', 'success')
        return redirect(url_for('vendedores'))

    return render_template('dashboard.html', 
        pagina='vendedores', 
        vendedores=db_vendedores,
        vendedor_form=vendedor_form,
        loja_form=LojaForm(),
        loja_edit_form=LojaEditForm(),
        relatorio_form=relatorio_form,
        today_date=date.today() 
    )

@app.route('/mudar_status_vendedor/<int:vendedor_id>/<string:novo_status>', methods=['POST'])
def mudar_status_vendedor(vendedor_id, novo_status):
    vendedor = next((v for v in db_vendedores if v['id'] == vendedor_id), None)
    if vendedor:
        vendedor['status'] = novo_status
        vendedor['ultimo_status_tipo'] = novo_status
        vendedor['ultimo_status_data'] = date.today().strftime('%d/%m/%Y')
        flash(f'Status de {vendedor["nome"]} alterado para "{novo_status}".', 'success')
    return redirect(url_for('vendedores'))

@app.route('/alternar_base_tratada/<int:vendedor_id>', methods=['POST'])
def alternar_base_tratada(vendedor_id):
    vendedor = next((v for v in db_vendedores if v['id'] == vendedor_id), None)
    if vendedor:
        vendedor['base_tratada'] = not vendedor['base_tratada']
        status = 'Tratada' if vendedor['base_tratada'] else 'Pendente'
        flash(f'Base de {vendedor["nome"]} alterada para {status}.', 'success')
    return redirect(url_for('vendedores'))

@app.route('/editar_disparos_dia', methods=['POST'])
def editar_disparos_dia():
    vendedor_id = int(request.form.get('vendedor_id'))
    disparos_hoje = int(request.form.get('disparos_hoje'))
    
    vendedor = next((v for v in db_vendedores if v['id'] == vendedor_id), None)
    if vendedor:
        vendedor['disparos_dia'] = disparos_hoje
        flash(f'Disparos do dia de {vendedor["nome"]} atualizados para {disparos_hoje}.', 'success')
    return redirect(url_for('vendedores'))

@app.route('/editar_disparos_semana', methods=['POST'])
def editar_disparos_semana():
    vendedor_id = int(request.form.get('vendedor_id'))
    vendedor = next((v for v in db_vendedores if v['id'] == vendedor_id), None)

    if vendedor:
        disparos_semanais = {}
        dias = ['segunda', 'terca', 'quarta', 'quinta', 'sexta', 'sabado', 'domingo']
        for dia in dias:
            disparos_semanais[dia] = int(request.form.get(f'disparo_{dia}', 0))
        
        vendedor['disparos_semanais'] = disparos_semanais
        flash(f'Disparos semanais de {vendedor["nome"]} atualizados com sucesso.', 'success')
    return redirect(url_for('vendedores'))


@app.route('/lojas', methods=['GET', 'POST'])
def lojas():
    loja_form = LojaForm()
    loja_edit_form = LojaEditForm()
    relatorio_form = RelatorioForm()

    if loja_form.validate_on_submit():
        novo_loja_id = max(l['id'] for l in db_lojas) + 1 if db_lojas else 1
        
        nova_loja = {
            'id': novo_loja_id,
            'nome': loja_form.nome_loja.data,
            'responsavel': loja_form.responsavel.data
        }
        db_lojas.append(nova_loja)
        
        novo_vendedor_id = max(v['id'] for v in db_vendedores) + 1 if db_vendedores else 101
        novo_vendedor = {
            'id': novo_vendedor_id,
            'nome': loja_form.nome_vendedor.data,
            'email': loja_form.email_vendedor.data,
            'loja_id': novo_loja_id,
            'loja': nova_loja['nome'],
            'status': 'Conectado',
            'base_tratada': True, 
            'disparos_dia': 0, 
            'disparos_semanais': gerar_disparos_semanais_simulados(),
            'ultimo_status_tipo': 'Conectado', 
            'ultimo_status_data': date.today().strftime('%d/%m/%Y')
        }
        db_vendedores.append(novo_vendedor)
        
        flash(f'Loja "{nova_loja["nome"]}" e Gestor cadastrados com sucesso!', 'success')
        return redirect(url_for('lojas'))

    lojas_com_vendedores = []
    for loja in db_lojas:
        loja_copy = loja.copy()
        loja_copy['vendedores'] = [v for v in db_vendedores if v['loja_id'] == loja['id']]
        lojas_com_vendedores.append(loja_copy)

    return render_template('dashboard.html', 
        pagina='lojas', 
        lojas=lojas_com_vendedores,
        vendedor_form=VendedorForm(),
        loja_form=loja_form,
        loja_edit_form=LojaEditForm(),
        relatorio_form=relatorio_form,
        today_date=date.today() 
    )

@app.route('/editar_loja', methods=['POST'])
def editar_loja():
    form = LojaEditForm(request.form)
    
    loja_id = int(request.form.get('loja_id'))

    if form.validate_on_submit():
        loja_encontrada = next((l for l in db_lojas if l['id'] == loja_id), None)
        if loja_encontrada:
            nome_antigo = loja_encontrada['nome']
            loja_encontrada['nome'] = form.nome.data
            loja_encontrada['responsavel'] = form.responsavel.data
            
            for v in db_vendedores:
                if v['loja_id'] == loja_id:
                    v['loja'] = form.nome.data
                    
            flash(f'Loja "{nome_antigo}" atualizada para "{loja_encontrada["nome"]}" com sucesso!', 'success')
            return redirect(url_for('lojas'))
        else:
            flash(f'Erro: Loja com ID {loja_id} não encontrada.', 'danger')
            
    else:
        flash("Erro de validação ao editar a loja.", 'warning')

    return redirect(url_for('lojas'))


if __name__ == '__main__':
    app.run(debug=True)