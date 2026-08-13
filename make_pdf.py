import sys
import re
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, white, lightgrey
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, 
                                TableStyle, PageBreak, KeepTogether, XPreformatted)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT

# --- CONFIGURATION DES COULEURS (Charte style Airbus / Corporate) ---
PRIMARY_COLOR = HexColor("#00205B") # Bleu foncé profond
SECONDARY_COLOR = HexColor("#009EE0") # Bleu clair
TEXT_COLOR = HexColor("#333333")
CODE_BG = HexColor("#F4F4F4")

class AirbusDocTemplate(SimpleDocTemplate):
    """Classe personnalisée pour intercepter les titres et construire le sommaire + les signets PDF."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bookmark_id = 0
        self.last_level = -1 # <--- On garde en mémoire le niveau du dernier signet

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph):
            style_name = flowable.style.name
            
            # Si c'est un titre (H1, H2, H3), on l'ajoute au sommaire
            if style_name in ['CorpH1', 'CorpH2', 'CorpH3']:
                text = flowable.getPlainText()
                
                # On évite d'ajouter le "Sommaire" et le sous-titre de la page de garde
                if text in ["Sommaire", "Documentation Technique"]:
                    return

                if style_name == 'CorpH1': level = 0
                elif style_name == 'CorpH2': level = 1
                else: level = 2
                
                # --- LE CORRECTIF EST ICI ---
                # ReportLab interdit de sauter d'un niveau (ex: passer de rien à H2)
                # Si le niveau est trop "profond" par rapport au précédent, on l'ajuste.
                if level > self.last_level + 1:
                    level = self.last_level + 1
                
                # 1. Notifier la Table des Matières
                self.notify('TOCEntry', (level, text, self.page))
                
                # 2. Créer le signet de navigation dans le PDF
                self.bookmark_id += 1
                b_name = f"bm_{self.bookmark_id}"
                self.canv.bookmarkPage(b_name)
                self.canv.addOutlineEntry(text, b_name, level, closed=False)
                
                # 3. Mettre à jour le dernier niveau utilisé
                self.last_level = level

def create_styles():
    """Définit la hiérarchie typographique du document."""
    styles = getSampleStyleSheet()
    
    styles.add(ParagraphStyle(name='CorpNormal', parent=styles['Normal'],
                              fontName='Helvetica', fontSize=10, textColor=TEXT_COLOR,
                              spaceBefore=6, spaceAfter=6, alignment=TA_JUSTIFY, leading=14))
    
    styles.add(ParagraphStyle(name='CorpH1', parent=styles['Heading1'],
                              fontName='Helvetica-Bold', fontSize=18, textColor=PRIMARY_COLOR,
                              spaceBefore=20, spaceAfter=10, keepWithNext=True))
    
    styles.add(ParagraphStyle(name='CorpH2', parent=styles['Heading2'],
                              fontName='Helvetica-Bold', fontSize=14, textColor=SECONDARY_COLOR,
                              spaceBefore=15, spaceAfter=8, keepWithNext=True))
    
    styles.add(ParagraphStyle(name='CorpH3', parent=styles['Heading3'],
                              fontName='Helvetica-Bold', fontSize=12, textColor=PRIMARY_COLOR,
                              spaceBefore=12, spaceAfter=6, keepWithNext=True))
    
    styles.add(ParagraphStyle(name='ExecSummary', parent=styles['Normal'],
                              fontName='Helvetica-Oblique', fontSize=11, textColor=PRIMARY_COLOR,
                              spaceBefore=10, spaceAfter=10, leftIndent=20, rightIndent=20,
                              backColor=HexColor("#E6F2F8"), borderPadding=10, leading=15))
    
    styles.add(ParagraphStyle(name='CodeStyle', parent=styles['Normal'],
                              fontName='Courier', fontSize=9, textColor=HexColor("#D14"),
                              leading=12))
                              
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
                in_code_block = False
                code_text = '\n'.join(code_content)
                code_flowable = XPreformatted(code_text, styles['CodeStyle'])
                
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
                in_code_block = True
            continue
            
        if in_code_block:
            code_content.append(raw_line)
            continue
            
        # --- GESTION DES TABLEAUX ---
        if clean_line.startswith('|') and clean_line.endswith('|'):
            if set(clean_line.replace('|', '').replace('-', '').replace(':', '').replace(' ', '')) == set():
                continue
                
            in_table = True
            cells = [cell.strip() for cell in clean_line.split('|')[1:-1]]
            paragraph_cells = [Paragraph(cell, styles['CorpNormal']) for cell in cells]
            table_data.append(paragraph_cells)
            continue
        elif in_table:
            in_table = False
            if table_data:
                # Calcul de la largeur des colonnes pour le tableau
                num_cols = len(table_data[0])
                col_width = (A4[0] - 4*cm) / num_cols
                
                t = Table(table_data, colWidths=[col_width] * num_cols)
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), PRIMARY_COLOR),
                    ('TEXTCOLOR', (0, 0), (-1, 0), white),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('INNERGRID', (0, 0), (-1, -1), 0.5, HexColor("#CCCCCC")),
                    ('BOX', (0, 0), (-1, -1), 1, PRIMARY_COLOR),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, HexColor("#F9F9F9")]),
                ]))
                story.append(KeepTogether(t))
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
            story.append(Paragraph(clean_line[2:], styles['ExecSummary']))
        elif clean_line.startswith('- ') or clean_line.startswith('* '):
            story.append(Paragraph(f"• {clean_line[2:]}", styles['CorpNormal']))
        else:
            formatted_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', clean_line)
            story.append(Paragraph(formatted_text, styles['CorpNormal']))

    return story

def generate_pdf(markdown_file, output_pdf):
    """Construit le PDF final avec le sommaire dynamique."""
    # On utilise notre classe personnalisée au lieu de SimpleDocTemplate
    doc = AirbusDocTemplate(
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
    
    # 2. SOMMAIRE AUTOMATIQUE
    story.append(Paragraph("Sommaire", styles['CorpH1']))
    toc = TableOfContents()
    
    # Esthétique des différents niveaux de titre dans le sommaire
    toc.levelStyles = [
        ParagraphStyle(fontName='Helvetica-Bold', fontSize=11, name='TOC1', leftIndent=20, firstLineIndent=-20, spaceBefore=10, leading=14),
        ParagraphStyle(fontName='Helvetica', fontSize=10, name='TOC2', leftIndent=40, firstLineIndent=-20, spaceBefore=3, leading=12),
        ParagraphStyle(fontName='Helvetica', fontSize=10, name='TOC3', leftIndent=60, firstLineIndent=-20, spaceBefore=3, leading=12),
    ]
    story.append(toc)
    story.append(PageBreak())
    
    # 3. CONTENU DU DOCUMENT
    markdown_content = parse_markdown(markdown_file, styles)
    story.extend(markdown_content)
    
    # 4. CRÉATION DU PDF EN DEUX PASSES (MultiBuild)
    # Requis pour que le sommaire puisse calculer les numéros de page exacts !
    doc.multiBuild(story, onFirstPage=add_header_footer, onLaterPages=add_header_footer)
    print(f"✅ PDF généré avec succès : {output_pdf}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python make_pdf.py <fichier.md> [sortie.pdf]")
        sys.exit(1)
        
    input_md = sys.argv[1]
    output_pdf = sys.argv[2] if len(sys.argv) > 2 else input_md.replace('.md', '.pdf')
    
    generate_pdf(input_md, output_pdf)
