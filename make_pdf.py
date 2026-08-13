import sys
import re
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, white, lightgrey
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, 
                                TableStyle, PageBreak, KeepTogether, XPreformatted)
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT

# --- CONFIGURATION DES COULEURS (Charte style Airbus / Corporate) ---
PRIMARY_COLOR = HexColor("#00205B") # Bleu foncé profond
SECONDARY_COLOR = HexColor("#009EE0") # Bleu clair
TEXT_COLOR = HexColor("#333333")
CODE_BG = HexColor("#F4F4F4")

def create_styles():
    """Définit la hiérarchie typographique du document."""
    styles = getSampleStyleSheet()
    
    # Style de base
    styles.add(ParagraphStyle(name='CorpNormal', parent=styles['Normal'],
                              fontName='Helvetica', fontSize=10, textColor=TEXT_COLOR,
                              spaceBefore=6, spaceAfter=6, alignment=TA_JUSTIFY, leading=14))
    
    # Titres
    styles.add(ParagraphStyle(name='CorpH1', parent=styles['Heading1'],
                              fontName='Helvetica-Bold', fontSize=18, textColor=PRIMARY_COLOR,
                              spaceBefore=20, spaceAfter=10, keepWithNext=True))
    
    styles.add(ParagraphStyle(name='CorpH2', parent=styles['Heading2'],
                              fontName='Helvetica-Bold', fontSize=14, textColor=SECONDARY_COLOR,
                              spaceBefore=15, spaceAfter=8, keepWithNext=True))
    
    styles.add(ParagraphStyle(name='CorpH3', parent=styles['Heading3'],
                              fontName='Helvetica-Bold', fontSize=12, textColor=PRIMARY_COLOR,
                              spaceBefore=12, spaceAfter=6, keepWithNext=True))
    
    # Résumé Exécutif / Blockquote
    styles.add(ParagraphStyle(name='ExecSummary', parent=styles['Normal'],
                              fontName='Helvetica-Oblique', fontSize=11, textColor=PRIMARY_COLOR,
                              spaceBefore=10, spaceAfter=10, leftIndent=20, rightIndent=20,
                              backColor=HexColor("#E6F2F8"), borderPadding=10, leading=15))
    
    # Code SQL (Monospace)
    styles.add(ParagraphStyle(name='CodeStyle', parent=styles['Normal'],
                              fontName='Courier', fontSize=9, textColor=HexColor("#D14"),
                              leading=12))
                              
    # Titre de la page de garde
    styles.add(ParagraphStyle(name='CoverTitle', parent=styles['Title'],
                              fontName='Helvetica-Bold', fontSize=28, textColor=PRIMARY_COLOR,
                              spaceBefore=100, spaceAfter=20, alignment=TA_CENTER))
    
    return styles

def add_header_footer(canvas, doc):
    """Génère l'en-tête (titre du doc) et le pied de page (numérotation) sur chaque page."""
    canvas.saveState()
    
    # Pied de page (Numéro de page)
    canvas.setFont('Helvetica', 9)
    canvas.setFillColor(HexColor("#888888"))
    page_num = canvas.getPageNumber()
    text = f"Page {page_num}"
    canvas.drawRightString(A4[0] - 2*cm, 1.5*cm, text)
    
    # En-tête (sur toutes les pages sauf la première)
    if page_num > 1:
        canvas.drawString(2*cm, A4[1] - 1.5*cm, "Projet BOM / Gross Needs - Documentation")
        canvas.setStrokeColor(HexColor("#CCCCCC"))
        canvas.line(2*cm, A4[1] - 1.7*cm, A4[0] - 2*cm, A4[1] - 1.7*cm)
        
    canvas.restoreState()

def parse_markdown(filepath, styles):
    """Lit le fichier Markdown et le convertit en éléments ReportLab."""
    story = []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    in_code_block = False
    code_content = []
    
    in_table = False
    table_data = []
    
    for line in lines:
        raw_line = line.rstrip('\n')
        clean_line = raw_line.strip()
        
        # --- GESTION DU CODE SQL ---
        if clean_line.startswith('```'):
            if in_code_block:
                # Fin du bloc de code
                in_code_block = False
                code_text = '\n'.join(code_content)
                code_flowable = XPreformatted(code_text, styles['CodeStyle'])
                
                # Encadrer le code dans un tableau pour le fond gris et KeepTogether
                code_table = Table([[code_flowable]], colWidths=[A4[0] - 4*cm])
                code_table.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), CODE_BG),
                    ('BOX', (0,0), (-1,-1), 0.5, HexColor("#CCCCCC")),
                    ('TOPPADDING', (0,0), (-1,-1), 10),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 10),
                    ('LEFTPADDING', (0,0), (-1,-1), 10),
                    ('RIGHTPADDING', (0,0), (-1,-1), 10),
                ]))
                story.append(KeepTogether(code_table))
                story.append(Spacer(1, 0.5*cm))
                code_content = []
            else:
                # Début du bloc de code
                in_code_block = True
            continue
            
        if in_code_block:
            code_content.append(raw_line)
            continue
            
        # --- GESTION DES TABLEAUX ---
        if clean_line.startswith('|') and clean_line.endswith('|'):
            # Ignorer la ligne de séparation markdown |---|---|
            if set(clean_line.replace('|', '').replace('-', '').replace(':', '').replace(' ', '')) == set():
                continue
                
            in_table = True
            # Extraire les cellules
            cells = [cell.strip() for cell in clean_line.split('|')[1:-1]]
            
            # Convertir les cellules en Paragraph pour gérer le retour à la ligne automatique
            paragraph_cells = [Paragraph(cell, styles['CorpNormal']) for cell in cells]
            table_data.append(paragraph_cells)
            continue
        elif in_table:
            # Fin du tableau
            in_table = False
            if table_data:
                # Calculer la largeur de chaque colonne pour remplir la page
                num_cols = len(table_data[0])
                col_width = (A4[0] - 4*cm) / num_cols
                
                t = Table(table_data, colWidths=[col_width] * num_cols)
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), PRIMARY_COLOR), # En-tête bleu
                    ('TEXTCOLOR', (0, 0), (-1, 0), white),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('INNERGRID', (0, 0), (-1, -1), 0.5, HexColor("#CCCCCC")),
                    ('BOX', (0, 0), (-1, -1), 1, PRIMARY_COLOR),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, HexColor("#F9F9F9")]),
                ]))
                story.append(KeepTogether(t)) # Évite que le tableau soit coupé
                story.append(Spacer(1, 0.5*cm))
                table_data = []

        # --- GESTION DES TEXTES ET TITRES ---
        if not clean_line:
            story.append(Spacer(1, 0.2*cm))
        elif clean_line.startswith('# '):
            story.append(Paragraph(clean_line[2:], styles['CorpH1']))
        elif clean_line.startswith('## '):
            story.append(Paragraph(clean_line[3:], styles['CorpH2']))
        elif clean_line.startswith('### '):
            story.append(Paragraph(clean_line[4:], styles['CorpH3']))
        elif clean_line.startswith('> '):
            # Utilisé pour le résumé exécutif (Blockquote markdown)
            story.append(Paragraph(clean_line[2:], styles['ExecSummary']))
        elif clean_line.startswith('- ') or clean_line.startswith('* '):
            # Listes à puces simples
            story.append(Paragraph(f"• {clean_line[2:]}", styles['CorpNormal']))
        else:
            # Remplacement basique du gras markdown **texte** en balises ReportLab <b>texte</b>
            formatted_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', clean_line)
            story.append(Paragraph(formatted_text, styles['CorpNormal']))

    return story

def generate_pdf(markdown_file, output_pdf):
    """Construit le PDF final."""
    doc = SimpleDocTemplate(
        output_pdf,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2.5*cm,
        bottomMargin=2.5*cm
    )
    
    styles = create_styles()
    story = []
    
    # 1. PAGE DE GARDE
    story.append(Paragraph("Documentation Technique", styles['CorpH2']))
    story.append(Paragraph("Projet BOM / Gross Needs", styles['CoverTitle']))
    story.append(Spacer(1, 4*cm))
    story.append(Paragraph("Généré automatiquement depuis Markdown", styles['CorpNormal']))
    story.append(PageBreak())
    
    # 2. CONTENU DU DOCUMENT
    markdown_content = parse_markdown(markdown_file, styles)
    story.extend(markdown_content)
    
    # 3. CRÉATION (avec ajout des en-têtes/pieds de page)
    doc.build(story, onFirstPage=add_header_footer, onLaterPages=add_header_footer)
    print(f"✅ PDF généré avec succès : {output_pdf}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python make_pdf.py <fichier.md> [sortie.pdf]")
        sys.exit(1)
        
    input_md = sys.argv[1]
    output_pdf = sys.argv[2] if len(sys.argv) > 2 else input_md.replace('.md', '.pdf')
    
    generate_pdf(input_md, output_pdf)
