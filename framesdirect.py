import re
import json
import csv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# Setup Selenium and WebDriver
print("Setting up WebDriver...")
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.265 Safari/537.36"
)

# Use webdriver_manager to handle the driver automatically
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

# Get URL Content and Wait for Page to Load JS
url = "https://www.framesdirect.com/eyeglasses/"
print(f"Visiting URL: {url}")
driver.get(url)

try:
    print("Waiting for initial product tiles to load...")
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.ID, "ctl00_mp_body"))
    )
except Exception as e:
    print(f"Error waiting for page to load: {e} or could not find the elemnet")
    driver.quit()
    exit()

# Main data storage list
glasses_data = []

# Getting and parsing the page source
page = driver.page_source
parsed_page = BeautifulSoup(page, "html.parser")


# Data Extraction logic
product_holders = parsed_page.find('div', id='product-list-container')
all_products = product_holders.find_all('div', class_="prod-holder")
print(f"Found {len(all_products)} glasswares.")

# Data Quality Implementation
def price_in_float(price: str|None) -> float:
    """
    Convert the prices to float, also change empty strings to None
    """
    if not(price) or price.strip() == "":
        return None
    else:
        float_price = re.sub(r"[^\d.]", "", price)
        return float(float_price)

# Navigating through all products
for product in all_products:
    glasses_names = product.find('div', class_='prod-title prod-model')
    glasses_price_discount = product.find('div', class_="prod-bot")

    if glasses_names and glasses_price_discount:
        # Glass names and brands
        name_tag = glasses_names.find('div', class_='product_name')
        name = name_tag.text if name_tag else None

        brand_tag = glasses_names.find('div', class_='catalog-name')
        brand = brand_tag.text if brand_tag else None

        # Glass prices and brands
        former_pr_tag = glasses_price_discount.find('div', class_='prod-catalog-retail-price')
        former_price = former_pr_tag.text if former_pr_tag else None
        former_price = price_in_float(former_price)

        current_pr_tag = glasses_price_discount.find('div', class_='prod-aslowas')
        current_price = current_pr_tag.text if current_pr_tag else None
        current_price = price_in_float(current_price)

        discount_tag = glasses_price_discount.find('div', class_='frame-discount size-11')
        discount = discount_tag.text if discount_tag else None
        discount = None if not discount or discount.strip() == "" else discount.strip()
        discount = discount.replace(" off", "") if discount is not None else None
    else:
        continue
    
    data = {
            'brand': brand,
            'name': name,
            'former_price': former_price,
            'current_price': current_price,
            'discount': discount
            }
    # Append data to the list
    glasses_data.append(data)

# Save Data to Files
print("Saving data to files...")

# Save to JSON
with open('./extracted_data/framesdirect_data.json', 'w') as json_file:
    json.dump(glasses_data, json_file, indent=4)
print(f"{len(glasses_data)} records successfully saved to the extracted data folder.")

# Save to CSV
if glasses_data:
    keys = glasses_data[0].keys()
    with open('./extracted_data/framesdirect_data.csv', 'w', newline='', encoding='utf-8') as csv_file:
        dict_writer = csv.DictWriter(csv_file, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(glasses_data)
    print(f"{len(glasses_data)} records successfully saved to the extracted data folder.")

# End the session
driver.quit()
print("\nScraping complete. WebDriver closed.")