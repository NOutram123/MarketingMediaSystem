"""Build the printable guide from EASY_SETUP.md; run with ReportLab installed."""
import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/pdf/easy-setup.pdf'


def markup(text):
    text = escape(text.replace('\u2019', "'").replace('\u201c', '"').replace('\u201d', '"').replace('\u2014', '-'))
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'`(.*?)`', r'<font name="Courier">\1</font>', text)
    return text


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='BodyGuide', fontName='Helvetica', fontSize=10, leading=15, spaceAfter=9, textColor=colors.HexColor('#223746')))
    styles.add(ParagraphStyle(name='StepGuide', fontName='Helvetica-Bold', fontSize=11, leading=15, alignment=TA_CENTER, textColor=colors.white))
    styles.add(ParagraphStyle(name='CodeGuide', fontName='Courier', fontSize=8, leading=12, spaceAfter=10, backColor=colors.HexColor('#edf3f4'), borderPadding=10, splitLongWords=True))
    styles['Heading1'].textColor = colors.HexColor('#153e49')
    styles['Heading1'].fontSize = 24
    styles['Heading1'].leading = 29
    styles['Heading2'].textColor = colors.HexColor('#176d73')
    styles['Heading2'].spaceBefore = 15
    styles['Heading2'].spaceAfter = 10
    story = [Paragraph('MARKETING MEDIA SYSTEM', styles['Heading1']),
             Paragraph('Easy Setup | Windows 11 + NVIDIA CUDA', styles['Heading2']),
             Paragraph('From source folder to a tested local studio. Keep this guide beside the setup wizard.', styles['BodyGuide'])]
    flow = Table([[Paragraph(label, styles['StepGuide']) for label in ['1<br/>Install studio', '2<br/>Local foundation', '3<br/>Test computer', '4<br/>API connections']]], colWidths=[43*mm]*4)
    flow.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#176d73')),('BOX',(0,0),(-1,-1),0.5,colors.white),('INNERGRID',(0,0),(-1,-1),2,colors.white),('TOPPADDING',(0,0),(-1,-1),12),('BOTTOMPADDING',(0,0),(-1,-1),12)]))
    story += [Spacer(1, 5*mm), flow, Spacer(1, 6*mm)]
    paragraph, code = [], None
    def flush():
        if paragraph:
            story.append(Paragraph(markup(' '.join(paragraph)), styles['BodyGuide']))
            paragraph.clear()
    for line in (ROOT / 'EASY_SETUP.md').read_text(encoding='utf-8').splitlines():
        if line.startswith('# '):
            continue
        if line.startswith('```'):
            flush()
            if code is None:
                code = []
            else:
                story.append(Paragraph('<br/>'.join(escape(item) for item in code), styles['CodeGuide']))
                code = None
            continue
        if code is not None:
            code.append(line)
        elif line.startswith('## '):
            flush()
            story.append(Paragraph(markup(line[3:]), styles['Heading2']))
        elif line.startswith('|'):
            flush()
            cells = [item.strip() for item in line.strip('|').split('|')]
            if cells[0] in ('Problem', '---'):
                continue
            story.append(KeepTogether([Paragraph(markup('**' + cells[0] + '**'), styles['BodyGuide']), Paragraph(markup(cells[1]), styles['BodyGuide'])]))
        elif not line.strip():
            flush()
        elif re.match(r'^\d+\. ', line):
            flush()
            story.append(Paragraph(markup(line), styles['BodyGuide']))
        else:
            paragraph.append(line)
    flush()
    def footer(canvas, doc):
        canvas.setStrokeColor(colors.HexColor('#c9dadd'))
        canvas.line(20*mm, 17*mm, 190*mm, 17*mm)
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#58717c'))
        canvas.drawString(20*mm, 12*mm, 'Marketing Media System | Easy Setup | 29 September 2026')
        canvas.drawRightString(190*mm, 12*mm, str(doc.page))
    SimpleDocTemplate(str(OUT), pagesize=A4, rightMargin=19*mm, leftMargin=19*mm, topMargin=18*mm, bottomMargin=24*mm,
                      title='Marketing Media System - Easy Setup', author='Marketing Media System').build(story, onFirstPage=footer, onLaterPages=footer)
    print(OUT)


if __name__ == '__main__':
    main()
