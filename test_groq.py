from groq import Groq
from dotenv import load_dotenv
import os

# Cargar .env
load_dotenv()

api_key = os.getenv("GROQ_API_KEY")

print("=" * 50)
print("PRUEBA DE GROQ")
print("=" * 50)

if not api_key:
    print("❌ No se encontró GROQ_API_KEY")
    exit()

print(f"✅ API KEY encontrada: {api_key[:10]}...")

try:
    client = Groq(api_key=api_key)

    response = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {
                "role": "user",
                "content": "Responde únicamente: AutoDocs funcionando"
            }
        ]
    )

    print("\n✅ CONEXIÓN EXITOSA")
    print("Respuesta:")
    print(response.choices[0].message.content)

except Exception as e:
    print("\n❌ ERROR")
    print(type(e).__name__)
    print(e)