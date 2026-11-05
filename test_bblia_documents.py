import unittest,json,base64,io,zipfile
import bblia_documents as d
from unittest.mock import patch
class DocumentTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  d.prepare()
  if d.status()['state']!='ready':raise RuntimeError('Document dependencies unavailable: tests must generate real files')
 def create(self,kind,data):return d.create({'nome':'BBLIA-teste','formato':kind,'dados':json.dumps(data,ensure_ascii=False)})
 def test_word_roundtrip(self):
  from docx import Document
  f=self.create('docx',{'titulo':'Relatório BBLIA','secoes':[{'titulo':'Resumo','texto':'Ação concluída com revisão.'}]})
  doc=Document(io.BytesIO(base64.b64decode(f['data_base64'])))
  self.assertIn('Ação concluída', '\n'.join(p.text for p in doc.paragraphs));self.assertTrue(f['validation']['format_opened'])
 def test_spreadsheet_preserves_numbers_and_neutralizes_formulas(self):
  from openpyxl import load_workbook
  f=self.create('xlsx',{'cabecalhos':['Produto','Valor'],'linhas':[['BBL',35],['=HYPERLINK("https://invalid")',10]]})
  sheet=load_workbook(io.BytesIO(base64.b64decode(f['data_base64']))).active
  self.assertEqual(sheet['B2'].value,35);self.assertEqual(sheet['A3'].data_type,'s');self.assertEqual(sheet.freeze_panes,'A2')
 def test_presentation_roundtrip(self):
  from pptx import Presentation
  f=self.create('pptx',{'titulo':'BBLIA','slides':[{'titulo':'Bem-vindo','texto':'Primeira etapa\nSegunda etapa'}]})
  deck=Presentation(io.BytesIO(base64.b64decode(f['data_base64'])));self.assertEqual(len(deck.slides),1)
  self.assertIn('Bem-vindo','\n'.join(s.text for s in deck.slides[0].shapes if s.has_text_frame))
 def test_pdf_text(self):
  import fitz
  f=self.create('pdf',{'titulo':'Documento BBLIA','secoes':[{'titulo':'Resumo','texto':'Teste de texto com acentuação.'}]})
  doc=fitz.open(stream=base64.b64decode(f['data_base64']),filetype='pdf');text=''.join(page.get_text() for page in doc)
  self.assertIn('Documento BBLIA',text);self.assertIn('acentuação',text);self.assertFalse(f['validation']['visual_reviewed'])
 def test_limits_and_path(self):
  with self.assertRaises(ValueError):d.create({'nome':'../secret','formato':'pdf','dados':'{}'})
  with self.assertRaises(ValueError):self.create('pptx',{'slides':[{'titulo':'a','texto':'x'*701}]})
  with self.assertRaises(ValueError):self.create('xlsx',{'cabecalhos':[],'linhas':[]})
 def test_tool_delivers_binary_not_text_renamed(self):
  from bblia_work import execute_work_tool
  artifacts=[];result=execute_work_tool('criar_documento',{'nome':'Relatorio','formato':'docx','dados':'{"titulo":"BBLIA"}'},artifacts)
  self.assertEqual(result['status'],'created');self.assertTrue(zipfile.is_zipfile(io.BytesIO(base64.b64decode(artifacts[0]['data_base64']))))
 def test_unavailable_never_claims_created(self):
  from bblia_work import execute_work_tool
  with patch.dict(d.STATE,{'state':'unavailable'}):
   artifacts=[];result=execute_work_tool('criar_documento',{'nome':'r','formato':'pdf','dados':'{}'},artifacts)
  self.assertIn('error',result);self.assertEqual(artifacts,[])
if __name__=='__main__':unittest.main()
