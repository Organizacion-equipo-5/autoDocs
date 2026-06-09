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

# Si hay múltiples keys separadas por comas, usar solo la primera
if ',' in api_key:
    api_key = api_key.split(',')[0].strip()
    print(f"ℹ️  Usando primera API key de múltiples keys")

print(f"✅ API KEY encontrada: {api_key[:10]}...")

try:
    client = Groq(api_key=api_key)

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "Eres un asistente útil."},
            {"role": "user", "content": "Di 'Hola' en una sola palabra."}
        ],
        max_tokens=10
    )

    print(f"✅ EXITO: {response.choices[0].message.content}")

except Exception as e:
    print(f"❌ ERROR")
    print(f"{type(e).__name__}")
    print(f"{e}")
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