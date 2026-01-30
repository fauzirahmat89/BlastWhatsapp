
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options

try:
    print("Setting up options...")
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--remote-debugging-port=9222") # Fixed port sometimes helps
    
    print("Installing driver...")
    service = Service(ChromeDriverManager().install())
    
    print("Starting Chrome...")
    driver = webdriver.Chrome(service=service, options=options)
    
    print("Visiting Google...")
    driver.get("https://www.google.com")
    print("Success!")
    driver.quit()
except Exception as e:
    print(f"FAILED: {e}")
