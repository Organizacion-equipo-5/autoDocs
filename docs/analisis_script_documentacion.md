# Documentación del script de análisis de datos

## 1. ¿Qué script se usa para analizar el proyecto?

El análisis principal se realiza en [backend/services/analyzer.py](backend/services/analyzer.py).

Ese script se ejecuta desde el endpoint de análisis en [backend/routes/analysis.py](backend/routes/analysis.py), que:

1. recibe el `project_id` del proyecto
2. toma la ruta física del proyecto (`file_path`)
3. lanza el análisis en un hilo en segundo plano
4. guarda los resultados en la colección `analysis_results`
5. actualiza el estado del proyecto a `completed` o `error`

> Importante: el análisis no se hace en [backend/services/doc_generator.py](backend/services/doc_generator.py). Ese archivo **solo genera documentación** a partir de los resultados ya analizados.

---

## 2. Flujo completo del análisis

### Paso 1: entrada del proyecto

El endpoint [backend/routes/analysis.py](backend/routes/analysis.py) llama a `ProjectAnalyzer(project_path)` con la ruta del proyecto que el usuario subió o que se resolvió desde la URL.

### Paso 2: recorrido del árbol de archivos

El método `analyze()` de [backend/services/analyzer.py](backend/services/analyzer.py) ejecuta esta secuencia:

1. `_scan_structure()`
2. `_detect_primary_language()`
3. `_analyze_code_files()`
4. `_calculate_quality_score()`

### Paso 3: almacenamiento de resultados

Una vez el análisis está listo, [backend/routes/analysis.py](backend/routes/analysis.py) crea un objeto con:

- `project_id`
- `results`
- `documentation`
- `created_at`

y lo guarda con `replace_one(..., upsert=True)` en la base de datos.

---

## 3. Qué extrae el script

El resultado final contiene estas secciones:

- `total_files`
- `primary_language`
- `languages`
- `structure`
- `functions`
- `classes`
- `endpoints`
- `imports`
- `quality_score`
- `complexity`
- `issues`

### 3.1 `languages`

Cuenta cuántos archivos existen por lenguaje detectado.

Se usan mapas de extensiones como:

- `.py` → Python
- `.js` → JavaScript
- `.ts` → TypeScript
- `.java` → Java
- `.php` → PHP
- `.rb` → Ruby
- `.go` → Go
- `.cs` → C#

Si no hay extensión conocida, el script intenta detectar el lenguaje con shebang (`#!`) para casos como scripts ejecutables.

### 3.2 `structure`

Lista la estructura de archivos detectados con:

- `path`
- `name`
- `type`
- `language`
- `size`
- `extension`

Se guarda un máximo de 300 elementos.

### 3.3 `functions`

Extrae funciones y guarda información como:

- `name`
- `file`
- `line`
- `params`
- `docstring`
- `is_async`
- `complexity`

Para Python usa `ast` para analizar el árbol del código.
Para otros lenguajes usa expresiones regulares para detectar firmas.

### 3.4 `classes`

Extrae clases y información como:

- `name`
- `file`
- `line`
- `methods`
- `bases`
- `docstring`

### 3.5 `endpoints`

Detecta rutas expuestas por frameworks comunes.

Ejemplos soportados:

- Flask / FastAPI / Django (Python)
- Express / NestJS (JavaScript / TypeScript)
- Spring (Java)
- Laravel (PHP)
- Rails / Sinatra (Ruby)
- Go HTTP (Gin / Echo / Fiber)
- ASP.NET Core (C#)
- Ktor / Spring (Kotlin)
- Phoenix (Elixir)
- Actix / Axum (Rust)

Cada endpoint guarda:

- `method`
- `path`
- `file`
- `framework`

### 3.6 `quality_score`

Se calcula con `_calculate_quality_score()`.

La fórmula actual es:

- parte base: `100`
- se reduce si hay funciones sin docstring
- se reduce si hay funciones con complejidad alta
- se reduce si existen errores capturados en `issues`
- se incrementa si la base tiene tests (`test` en el nombre)

### 3.7 `complexity`

Guarda métricas globales:

- `avg`
- `max`
- `high_complexity_funcs`

### 3.8 `issues`

Guarda errores de parsing o excepciones al analizar un archivo.

Es útil para detectar archivos que no pudieron analizarse.

---

## 4. Cómo analiza cada lenguaje

### 4.1 Python

La lectura de Python usa el módulo `ast`.

Se extraen:

- funciones
- clases
- caminos de endpoints con patrones como:
  - `@app.get(...)`
  - `@app.post(...)`
  - `@app.route(...)`
  - `path(...)`

También se calcula la complejidad con un estimador basado en nodos del AST.

### 4.2 JavaScript y TypeScript

Se detectan:

- funciones con `function`
- funciones flecha
- clases
- endpoints Express y NestJS

### 4.3 Java

Se detectan:

- endpoints con anotaciones como `@GetMapping`
- métodos `public/private/protected`
- clases

### 4.4 PHP

Se detectan:

- rutas con `Route::get(...)`
- funciones `function`
- clases

### 4.5 Ruby

Se detectan:

- rutas como `get '/ruta'`
- métodos `def`
- clases

### 4.6 Go

Se detectan:

- handlers HTTP con `router.GET(...)` o `HandleFunc(...)`
- funciones `func`
- structs como clases de dominio

### 4.7 C#

Se detectan:

- atributos `HttpGet`, `HttpPost`, etc.
- métodos `public/private/protected/internal`
- clases

### 4.8 Kotlin

Se detectan:

- `@GetMapping`, `@PostMapping`, etc.
- funciones `fun`
- clases

### 4.9 Rust

Se detectan:

- atributos `#[get("...")]`
- funciones `fn`
- structs

### 4.10 Swift

Se detectan:

- funciones `func`
- clases

### 4.11 C / C++

Se detectan:

- funciones con firma estilo C/C++
- clases

### 4.12 Scala

Se detectan:

- funciones `def`
- clases, objetos y traits

### 4.13 Elixir

Se detectan:

- rutas tipo `get "/ruta"`
- funciones `def`
- `defmodule`

---

## 5. Ejemplo de estructura de salida

```json
{
  "total_files": 42,
  "primary_language": "Python",
  "languages": {
    "Python": 18,
    "JavaScript": 8,
    "HTML": 5
  },
  "structure": [
    {
      "path": "app.py",
      "name": "app.py",
      "type": "file",
      "language": "Python",
      "size": 2048,
      "extension": ".py"
    }
  ],
  "functions": [
    {
      "name": "create_app",
      "file": "app.py",
      "line": 12,
      "params": ["config"],
      "docstring": "Crea la app principal",
      "is_async": false,
      "complexity": 3
    }
  ],
  "classes": [
    {
      "name": "UserService",
      "file": "services/user_service.py",
      "line": 1,
      "methods": ["create", "delete"],
      "bases": [],
      "docstring": ""
    }
  ],
  "endpoints": [
    {
      "method": "GET",
      "path": "/users",
      "file": "routes/user.py",
      "framework": "Flask/FastAPI"
    }
  ],
  "quality_score": 78,
  "complexity": {
    "avg": 2.1,
    "max": 10,
    "high_complexity_funcs": 1
  },
  "issues": []
}
```

---

## 6. Cómo se usa este análisis en el proyecto

El análisis se ejecuta con el endpoint:

- `POST /api/analysis/<project_id>/start`

Luego se consulta el estado con:

- `GET /api/analysis/<project_id>/status`

Y se obtiene el resultado con:

- `GET /api/analysis/<project_id>/results`

El flujo completo es:

1. Inicio del análisis
2. Guardado en base de datos
3. Generación de documentación con [backend/services/doc_generator.py](backend/services/doc_generator.py)
4. Exposición del resultado en la UI

---

## 7. Limitaciones del script

Algunas limitaciones importantes:

- El análisis de funciones en lenguajes no Python se basa en expresiones regulares, por lo que puede fallar en casos complejos.
- No hace análisis semántico profundo del código.
- No resuelve dependencias ni arquitectura real del proyecto.
- La detección de endpoints depende del estilo del código y puede omitir patrones no contemplados.

---

## 8. Resumen corto

El script de análisis de datos es [backend/services/analyzer.py](backend/services/analyzer.py).

Su trabajo es:

1. recorrer el proyecto
2. identificar lenguaje, archivos, funciones, clases y endpoints
3. calcular una puntuación de calidad
4. devolver un JSON estructurado con métricas útiles

Luego [backend/services/doc_generator.py](backend/services/doc_generator.py) consume esos resultados para producir documentación técnica.
