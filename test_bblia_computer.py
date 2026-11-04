import json
import os
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import bblia_computer as pc
import bblia_agent as agent


class ComputerTests(unittest.TestCase):
    def test_oauth_uses_fixed_callback_pkce_and_resource(self):
        metadata={'authorization_endpoint':'https://auth.desktopcommander.app/authorize',
                  'token_endpoint':'https://auth.desktopcommander.app/token',
                  'registration_endpoint':'https://auth.desktopcommander.app/register',
                  'resource':pc.MCP_URL,'scopes_supported':['offline_access']}
        with patch.object(pc,'oauth_metadata',return_value=metadata),patch.object(pc,'json_request',return_value={'client_id':'bblia-public-client'}) as request:
            result=pc.oauth_start({'state':'s'*43,'code_challenge':'c'*43})
        params=parse_qs(urlsplit(result['authorization_url']).query)
        self.assertEqual(params['code_challenge_method'],['S256'])
        self.assertEqual(params['redirect_uri'],[pc.REDIRECT_URI])
        self.assertEqual(params['resource'],[pc.MCP_URL])
        self.assertEqual(request.call_args.args[1]['token_endpoint_auth_method'],'none')
        self.assertNotIn('client_secret',result)

    def test_untrusted_endpoints_and_cross_origin_redirects_rejected(self):
        for url in ('http://mcp.desktopcommander.app/mcp','https://evil.test/token',
                    'https://mcp.desktopcommander.app.evil.test/token','https://user:pass@mcp.desktopcommander.app/mcp'):
            with self.assertRaises(pc.ComputerError):pc.trusted_url(url)
        self.assertIsNone(pc.NoRedirect().redirect_request(None,None,302,'',{},'https://evil.test'))

    def test_device_is_pinned_and_foreign_async_calls_rejected(self):
        client=pc.CommanderClient({'access_token':'private-access','device_id':'selected-device'})
        client.definitions={'start_process':{'inputSchema':{'type':'object','properties':{'deviceId':{'type':'string'},'command':{'type':'string'}},'required':['command','deviceId']}},
                            'get_tool_result':{'inputSchema':{'type':'object','properties':{'call_id':{'type':'string'}}}}}
        definitions=client.model_tools()
        self.assertNotIn('deviceId',definitions[0]['parameters']['properties'])
        with patch.object(client,'rpc',return_value={'content':[{'type':'text','text':'started'}],
                                                   'structuredContent':{'call_id':'call-1234567890123456'}}) as rpc:
            client.call('start_process',{'command':'hostname','deviceId':'other-device'})
            self.assertEqual(rpc.call_args.args[1]['arguments']['deviceId'],'selected-device')
            client.call('get_tool_result',{'call_id':'call-1234567890123456'})
            with self.assertRaises(pc.ComputerError):client.call('get_tool_result',{'call_id':'foreign-call'})
        self.assertNotIn('private-access',json.dumps(definitions))

    def test_agent_credentials_are_not_in_prompt_or_public_result(self):
        class FakeComputer:
            def __init__(self,connection):
                self.actions=[]
                assert connection['access_token']=='private-access'
            def initialize(self):return self
            def model_tools(self):return [{'type':'function','name':'pc_start_process','description':'Run','parameters':{'type':'object','properties':{}}}]
            def call(self,name,args):
                self.actions.append({'tool':name,'confirmed':True})
                return {'content':[{'type':'text','text':'exit 0: COMPUTER-TEST'}]}
        replies=[{'id':'one','output':[{'type':'function_call','name':'pc_start_process','call_id':'a','arguments':'{}'}]},
                 {'id':'two','output':[{'type':'function_call','name':'finalizar_trabalho','call_id':'b',
                   'arguments':json.dumps({'tipo':'computador','resumo':'Computador respondeu COMPUTER-TEST.','limitacoes':[]})}]}]
        seen=[]
        def model(payload,key):seen.append(payload);return replies.pop(0)
        with patch.dict(os.environ,{'OPENAI_API_KEY':'server-key'}),patch.object(agent,'CommanderClient',FakeComputer),patch.object(agent,'request_model',side_effect=model):
            job=agent.start_work({'messages':[{'role':'user','content':'Confira meu computador'}],
                                 'use_computer':True,'computer_connection':{'access_token':'private-access','device_id':'selected-device'}})
            for _ in range(200):
                result=agent.get_work(job['id'])
                if result['status']!='processing':break
                time.sleep(.005)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['kind'],'computador')
        self.assertEqual(result['artifacts'],[])
        self.assertNotIn('private-access',json.dumps(seen))
        self.assertNotIn('private-access',json.dumps(result))


if __name__=='__main__':unittest.main()
