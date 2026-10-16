from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time

driver = webdriver.Chrome()
driver.get("http://localhost:8080/")
time.sleep(3)

# ---------- 1) Buscar por ID ----------
# Buscar el enlace "CREAR TEST" que tiene un ID o buscar elementos con ID disponibles
try:
    # Intentar encontrar el enlace de crear test por su texto y luego buscar elementos con ID
    crear_test_link = driver.find_element(By.LINK_TEXT, "CREAR TEST")
    print("Enlace CREAR TEST encontrado por texto")
    
    # Buscar elementos con ID en la página
    elements_with_id = driver.find_elements(By.XPATH, "//*[@id]")
    print(f"Elementos con ID encontrados: {len(elements_with_id)}")
    
    # Usar el primer elemento con ID si existe
    if elements_with_id:
        element_by_id = elements_with_id[0]
        element_id = element_by_id.get_attribute("id")
        print(f"Usando elemento con ID: {element_id}")
        # Si es un input o textarea, escribir texto
        if element_by_id.tag_name in ['input', 'textarea']:
            element_by_id.send_keys("prueba por id")
            time.sleep(2)
            element_by_id.clear()
except Exception as e:
    print(f"Error en búsqueda por ID: {e}")

# ---------- 2) Buscar por CSS Selector ----------
try:
    # Buscar el enlace "CREAR TEST" por CSS selector
    element_by_css = driver.find_element(By.CSS_SELECTOR, "a[href='crear.html']")
    print("Enlace CREAR TEST encontrado por CSS selector: a[href='crear.html']")
    element_by_css.click()
    time.sleep(2)
    driver.back()
    time.sleep(2)
except Exception as e:
    print(f"Error en búsqueda por CSS selector: {e}")

# ---------- 3) Buscar por NAME ----------
try:
    # Buscar elementos con atributo name
    elements_with_name = driver.find_elements(By.XPATH, "//*[@name]")
    print(f"Elementos con NAME encontrados: {len(elements_with_name)}")
    
    if elements_with_name:
        element_by_name = elements_with_name[0]
        element_name = element_by_name.get_attribute("name")
        print(f"Usando elemento con NAME: {element_name}")
        # Si es un input o textarea, escribir texto
        if element_by_name.tag_name in ['input', 'textarea']:
            element_by_name.send_keys("prueba por name" + Keys.ENTER)
            time.sleep(2)
except Exception as e:
    print(f"Error en búsqueda por NAME: {e}")

time.sleep(2)
driver.quit()