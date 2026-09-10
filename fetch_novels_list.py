# -*- coding: utf-8 -*-
import sys
import json
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')

url = 'https://docs.google.com/spreadsheets/d/1s-yf1gRHagPIeikEC9_aVIAst7oDaiwoNzLH-hd0Q24/gviz/tq?tqx=out:json'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
res = urllib.request.urlopen(req)
text = res.read().decode('utf-8')
if 'google.visualization.Query.setResponse(' in text:
    text = text.split('google.visualization.Query.setResponse(')[1].rsplit(');', 1)[0]
data = json.loads(text)
novels = []
for r in data.get('table', {}).get('rows', []):
    c = r.get('c', [])
    name = str(c[0].get('v', '') if len(c) > 0 and c[0] else '').strip()
    link = str(c[2].get('v', '') if len(c) > 2 and c[2] else '').strip()
    orig = str(c[7].get('v', '') if len(c) > 7 and c[7] else '').strip()
    if name and name != 'الاسم' and name != 'الإسم ':
        novels.append({'name': name, 'link': link, 'orig': orig})
        print(f"• Name: {name} | Link: {link}")
