import requests

r = requests.get("http://localhost:11434/api/tags", timeout=3)
models = [m['name'] for m in r.json().get('models', [])]
print("Modelos:", models)
print("Mistral:", any('mistral' in m for m in models))