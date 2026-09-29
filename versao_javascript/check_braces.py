import sys
import re

def check_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    scripts = re.findall(r'<script.*?</script>', text, flags=re.DOTALL)
    print(f"--- {path} ---")
    for i, s in enumerate(scripts):
        print(f"Script {i+1}: {{ {s.count('{')} }} {s.count('}')}")

check_file(r'c:\Users\f201503\Documents\Resumo para audiência\versao_javascript\index.html')
check_file(r'c:\Users\f201503\Documents\Resumo para audiência\versao_javascript\ABRIR_APLICATIVO_DIRETO.html')
