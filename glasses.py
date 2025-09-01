# Libraries Used
import csv
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# Step 1 - Configuration and Data Fetching
# Setup Selenium and WebDriver
print("Setting up webdriver...")
chrome_option = Options()
chrome_option.add_argument('--headless')
chrome_option.add_argument('--disable-gpu')
chrome_option.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.265 Safari/537.36"
)
print("done setting up..")

# Install the chrome driver (This is a one time thing)
print("Installing Chrome WD")
service = Service(ChromeDriverManager().install())
print("Final Setup")
driver = webdriver.Chrome(service=service, options=chrome_option)
print("Done")

# Make connection and get URL content
url = "https://www.glasses.com/gl-us/eyeglasses"
print(f"Visting {url} page")
driver.get(url)

# Further instruction: wait for JS to load the files
try:
    print("Waiting for product tiles to load")
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CLASS_NAME, 'catalog-page'))
    )
    print("Done...Proceed to parse the data")
except (TimeoutError, Exception) as e:
    print(f"Error waiting for {url}: {e}")
    driver.quit()
    print("Closed")

# Step 2 - Data Parsing and Extraction
# Get page source and parse using BeautifulSoup
content = driver.page_source
page = BeautifulSoup(content, 'html.parser')

# Temporary storage for the extracted data
glasses_data = []

# Locate all product tiles and extract the data for each product.
product_tiles = page.find_all("a", class_='product-tile')
print(f"Found {len(product_tiles)} products")

for tile in product_tiles:
    product_info = tile.find('div', class_='product-info')

    if product_info:
        brand_tag = product_info.find('div', class_='product-brand')
        brand = brand_tag.text if brand_tag else None # product brand

        name_tag = product_info.find('div', class_='product-code')
        name = name_tag.text if name_tag else None

        # for price
        price_cnt = product_info.find('div', class_='product-prices')
        if price_cnt:
            # Former Price
            former_price_tag = price_cnt.find('div', class_='product-list-price')
            former_price = former_price_tag.text if former_price_tag else None
            # Current Price
            current_price_tag = price_cnt.find('div', class_='product-offer-price')
            current_price = current_price_tag.text if current_price_tag else None
        else:
            former_price = current_price = None
    else:
        brand = name = former_price = current_price = None 
        # Automatically applies missing value, if the product info is not available.
    
    discount_tag = tile.find('div', class_='product-badge discount-badge thirty')
    discount = discount_tag.text if discount_tag else None

    # Assignment: Add the category
            
    data = {
        'Brand': brand,
        'Product_Name': name,
        'Former_Price': former_price,
        'Current_Price': current_price,
        'Discount': discount
    }
    # Append data to the list
    glasses_data.append(data)

# Step 3 - Data Storage and Finalization
# Save to CSV file
column_name = glasses_data[0].keys() # get the column names
with open('glassesdotcom_data.csv', mode='w', newline='', encoding='utf-8') as csv_file: # open up the file with context manager
    dict_writer = csv.DictWriter(csv_file, fieldnames=column_name)
    dict_writer.writeheader()
    dict_writer.writerows(glasses_data)
print(f"Saved {len(glasses_data)} records to CSV")

# Save to JSON file
with open("glassesdotcom.json", mode='w') as json_file:
    json.dump(glasses_data, json_file, indent=4)
print(f"Saved {len(glasses_data)} records to JSON")

# close the browser
driver.quit()
print("End of Web Extraction")

