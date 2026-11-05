import sys,json,base64,io,zipfile
from pathlib import Path
from xml.sax.saxutils import escape

def main():
 try:
  import resource
  resource.setrlimit(resource.RLIMIT_AS,(320*1024*1024,320*1024*1024));resource.setrlimit(resource.RLIMIT_CPU,(12,12));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
 except (ImportError,ValueError):pass
 sys.path.insert(0,sys.argv[1])
 import docx,openpyxl,pptx,reportlab
 if any(not Path(m.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve()) for m in (docx,openpyxl,pptx,reportlab)):raise RuntimeError('Bibliotecas dedicadas não instaladas')
 payload=json.loads(sys.stdin.read(1000001))
 if payload.get('probe'):print('{"ready":true}');return
 d=payload['data'];kind=payload['kind'];out=io.BytesIO()
 def text(v,limit=12000):
  if not isinstance(v,str) or len(v)>limit:raise ValueError('Campo textual inválido ou muito longo.')
  return ''.join(c for c in v if c in '\n\r\t' or ord(c)>=32)
 title=text(d.get('titulo','Documento BBLIA'),200)
 sections=d.get('secoes',[])
 if not isinstance(sections,list) or len(sections)>80:raise ValueError('Use até 80 seções.')
 if kind in ('docx','pdf'):
  parts=[]
  for section in sections:
   if not isinstance(section,dict):raise ValueError('Seção inválida.')
   parts.append((text(section.get('titulo',''),200),text(section.get('texto',''))))
  if kind=='docx':
   from docx.shared import Pt,Inches
   document=docx.Document();document.core_properties.title=title
   document.styles['Normal'].font.name='Calibri';document.styles['Normal'].font.size=Pt(11)
   document.add_heading(title,0)
   for heading,body in parts:
    if heading:document.add_heading(heading,1)
    for line in body.split('\n'):document.add_paragraph(line)
   document.save(out);verified=docx.Document(io.BytesIO(out.getvalue()))
   validation={'format_opened':True,'paragraphs':len(verified.paragraphs),'visual_reviewed':False}
  else:
   from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer
   from reportlab.lib.styles import getSampleStyleSheet
   from reportlab.lib.pagesizes import A4
   styles=getSampleStyleSheet();story=[Paragraph(escape(title),styles['Title']),Spacer(1,12)]
   for heading,body in parts:
    if heading:story.append(Paragraph(escape(heading),styles['Heading2']))
    for line in body.split('\n'):
     story.append(Paragraph(escape(line) or ' ',styles['BodyText']));story.append(Spacer(1,5))
   SimpleDocTemplate(out,pagesize=A4,title=title,author='BBLIA',leftMargin=45,rightMargin=45,topMargin=45,bottomMargin=45).build(story)
   if not out.getvalue().startswith(b'%PDF-') or b'%%EOF' not in out.getvalue()[-100:]:raise ValueError('PDF não confirmado.')
   validation={'pdf_structure':True,'visual_reviewed':False,'note':'Fonte padrão para texto latino; não inclui renderização visual automática.'}
 elif kind=='xlsx':
  headers=d.get('cabecalhos',[]);rows=d.get('linhas',[])
  if not isinstance(headers,list) or not 1<=len(headers)<=30 or not all(isinstance(x,str) and len(x)<=200 for x in headers) or not isinstance(rows,list) or len(rows)>2000:raise ValueError('Planilha: até 30 colunas e 2000 linhas.')
  from openpyxl.styles import Font,PatternFill,Alignment
  book=openpyxl.Workbook();sheet=book.active;sheet.title='Dados';sheet.freeze_panes='A2';sheet.append(headers)
  for row in rows:
   if not isinstance(row,list) or len(row)>len(headers):raise ValueError('Linha de planilha inválida.')
   for value in row:
    if value is not None and not isinstance(value,(str,int,float,bool)):raise ValueError('Célula inválida.')
    if isinstance(value,str) and len(value)>12000:raise ValueError('Célula muito longa.')
   sheet.append(row)
  for row in sheet:
   for cell in row:
    # Untrusted content is text, never executable spreadsheet formulas.
    if isinstance(cell.value,str):cell.data_type='s'
  for cell in sheet[1]:cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='263B65');cell.alignment=Alignment(wrap_text=True)
  for col in sheet.columns:
   width=min(48,max(12,max(len(str(c.value or '')) for c in col)+2));sheet.column_dimensions[col[0].column_letter].width=width
  sheet.auto_filter.ref=sheet.dimensions;book.save(out);verified=openpyxl.load_workbook(io.BytesIO(out.getvalue()))
  validation={'format_opened':True,'rows':verified.active.max_row,'columns':verified.active.max_column,'formulas':False,'visual_reviewed':False}
 elif kind=='pptx':
  slides=d.get('slides',[])
  if not isinstance(slides,list) or not 1<=len(slides)<=30:raise ValueError('Apresentação: de 1 a 30 slides.')
  from pptx.util import Inches,Pt
  from pptx.dml.color import RGBColor
  deck=pptx.Presentation();deck.slide_width=Inches(13.333);deck.slide_height=Inches(7.5)
  for item in slides:
   if not isinstance(item,dict):raise ValueError('Slide inválido.')
   heading=text(item.get('titulo',''),80);body=text(item.get('texto',''),700)
   if len(body.split('\n'))>8:raise ValueError('Use até oito parágrafos por slide.')
   slide=deck.slides.add_slide(deck.slide_layouts[6]);slide.background.fill.solid();slide.background.fill.fore_color.rgb=RGBColor.from_string('101B31')
   box=slide.shapes.add_textbox(Inches(.7),Inches(.55),Inches(12),Inches(1.1));p=box.text_frame.paragraphs[0];p.text=heading;p.font.size=Pt(30);p.font.bold=True;p.font.color.rgb=RGBColor.from_string('F4CF78')
   box=slide.shapes.add_textbox(Inches(.8),Inches(1.9),Inches(11.7),Inches(4.9));box.text_frame.word_wrap=True
   for i,line in enumerate(body.split('\n')):
    p=box.text_frame.paragraphs[0] if i==0 else box.text_frame.add_paragraph();p.text=line;p.font.size=Pt(20);p.font.color.rgb=RGBColor.from_string('FFFFFF');p.space_after=Pt(12)
  deck.core_properties.title=title;deck.save(out);verified=pptx.Presentation(io.BytesIO(out.getvalue()))
  validation={'format_opened':True,'slides':len(verified.slides),'visual_reviewed':False}
 else:raise ValueError('Formato inválido.')
 raw=out.getvalue()
 if len(raw)>4*1024*1024:raise ValueError('Arquivo maior que 4 MB.')
 if kind!='pdf':
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   if z.testzip() is not None:raise ValueError('Arquivo inválido.')
 print(json.dumps({'ok':True,'base64':base64.b64encode(raw).decode(),'validation':validation},ensure_ascii=False))

if __name__=='__main__':
 try:main()
 except Exception as e:print(json.dumps({'ok':False,'error':str(e)[:500]},ensure_ascii=False))
