# Test which includedData values cause the denial.
# Run on the USER's machine: py -3.11 test_included.py
import json, urllib.request, urllib.parse, urllib.error
from pathlib import Path
c=json.load(open('config.json',encoding='utf-8'))
a=[x for x in c['accounts'] if x.get('id')=='sheelady_us'][0]
cid=a['lwa_client_id']; csec=a['lwa_client_secret']; rt=a['refresh_token']
mid='ATVPDKIKX0DER'; endpoint='https://sellingpartnerapi-na.amazon.com'; asin='B09SD3W56K'

# get token
body=urllib.parse.urlencode({'grant_type':'refresh_token','refresh_token':rt,'client_id':cid,'client_secret':csec}).encode()
req=urllib.request.Request('https://api.amazon.com/auth/o2/token',data=body,headers={'Content-Type':'application/x-www-form-urlencoded'})
access=json.loads(urllib.request.urlopen(req,timeout=30).read())['access_token']
print('token OK')

def call(included):
    url=f'{endpoint}/catalog/2022-04-01/items/{asin}?'+urllib.parse.urlencode({'marketplaceIds':mid,'includedData':included})
    r=urllib.request.Request(url,headers={'x-amz-access-token':access,'Accept':'application/json'})
    try:
        urllib.request.urlopen(r,timeout=30).read()
        return 'PASS'
    except urllib.error.HTTPError as e:
        return f'FAIL {e.code}: '+e.read().decode()[:120]

# test each field alone, then the full generator set
for f in ['summaries','productTypes','attributes','dimensions','salesRanks','identifiers','images']:
    print(f'{f:14} -> {call(f)}')
print()
print('FULL generator set ->', call('attributes,dimensions,summaries,productTypes,salesRanks,identifiers,images'))
