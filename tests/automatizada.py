from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time

driver = webdriver.Chrome()
driver.get("https://www.google.com")
time.sleep(100)  

# ---------- 1) Buscar por ID ----------
element_by_id = driver.find_element(By.ID, "APjFqb")
element_by_id.send_keys("javascript find element by id")
time.sleep(30)

# Limpiar el campo antes de la siguiente prueba
element_by_id.clear()

# ---------- 2) Buscar por CSS Selector ----------
element_by_css = driver.find_element(By.CSS_SELECTOR, "textarea[name='q']")
element_by_css.send_keys("javascript find element by css selector")
time.sleep(30)

# Limpiar el campo
element_by_css.clear()

# ---------- 3) Buscar por NAME ----------
element_by_name = driver.find_element(By.NAME, "q")
element_by_name.send_keys("javascript find element by name" + Keys.ENTER)

time.sleep(30)
driver.quit()