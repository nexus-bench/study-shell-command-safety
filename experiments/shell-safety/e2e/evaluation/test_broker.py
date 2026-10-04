"""Dummy-key relay controls; upstream HTTP is mocked, no inference calls."""
import http.client
import json
import unittest
from unittest.mock import patch
from urllib.request import Request,build_opener
from urllib.error import HTTPError
from broker import start_broker


class FakeResponse:
    status=200
    done=False
    def getheader(self,*args): return 'application/json'
    def read1(self,size):
        if self.done:return b''
        self.done=True;return b'{"ok":true}'


class FakeConnection:
    debuglevel=0
    requests=[]
    def __init__(self,host,timeout):self.host=host
    def request(self,method,path,body,headers):
        self.requests.append((self.host,method,path,headers))
    def getresponse(self):return FakeResponse()
    def close(self):pass


class BrokerTests(unittest.TestCase):
    def test_route_and_secret_boundaries(self):
        urlopen=build_opener().open
        with patch.object(http.client,'HTTPSConnection',FakeConnection):
            server,counts=start_broker({'OPENAI_API_KEY':'dummy-controller-key'})
            try:
                request=Request('http://127.0.0.1:19001/codex/responses',data=b'{}',
                                headers={'Authorization':'Bearer untrusted-value','X-Api-Key':'untrusted-value'})
                with urlopen(request) as result: body=result.read()
                host,method,path,headers=FakeConnection.requests[-1]
                self.assertEqual((host,method,path),('api.openai.com','POST','/v1/responses'))
                self.assertEqual(headers['Authorization'],'Bearer dummy-controller-key')
                self.assertNotIn('X-Api-Key',headers)
                self.assertNotIn(b'dummy-controller-key',body)
                for path in ('codex/../../admin','unknown/responses','qwen/chat/completions'):
                    with self.assertRaises(HTTPError) as error:
                        urlopen(Request('http://127.0.0.1:19001/'+path,data=b'{}'))
                    self.assertIn(error.exception.code,(403,404))
                self.assertEqual(len(FakeConnection.requests),1)
            finally:server.shutdown();server.server_close()


if __name__=='__main__': unittest.main()
