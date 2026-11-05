import unittest
from bblia_work import memory_context, requests_web_lookup

class MemoryTests(unittest.TestCase):
    def test_opt_out_and_private_context(self):
        self.assertEqual(memory_context({'memory_enabled':False,'memories':['Rodrigo']}),'')
        self.assertEqual(memory_context({}),'')
        self.assertIn('Rodrigo',memory_context({'memories':['Rodrigo']}))
        self.assertNotIn('Rodrigo',memory_context({'memories':[]}))
    def test_invalid_notes_and_bounds(self):
        self.assertEqual(memory_context({'memories':'invalid'}),'')
        result=memory_context({'memories':[None,{},'x'*2000]*50})
        self.assertLess(len(result),12200)
    def test_current_questions_require_lookup(self):
        for q in ['Qual o preço hoje?', 'Quais as notícias recentes?', 'Pesquise sobre Android']:
            self.assertTrue(requests_web_lookup([{'content':q}]))
        self.assertFalse(requests_web_lookup([{'content':'Crie uma função de soma'}]))
