import os
import time
import pandas as pd
import PySimpleGUI as sg
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException,TimeoutException
from typing import List
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support import expected_conditions as EC
import logging
import coloredlogs
import requests
from urllib.parse import parse_qs, urlparse
import datetime
logger = logging.getLogger('scraper')
coloredlogs.install(level='INFO', logger=logger, fmt='%(asctime)s,%(msecs)03d %(hostname)s %(name)s %(levelname)s %(message)s')


class AuctionScraper():
    def __init__(self):
        self.BASE_URL = 'https://miamidade.realforeclose.com/index.cfm'
        self.data:List[dict] = []
        self.AREA_LIST = ['W', 'R', 'C']
        self.save_path = './Output'

    @staticmethod
    def get_domain(site_id):
        url = requests.post('https://brevard.realforeclose.com/index.cfm', data={
            'ZACTION': 'AJAX',
            'ZMETHOD': 'LOGIN',
            'func': 'SWITCH',
            'VENDOR': site_id
        }).json()['URL']
        return urlparse(url).netloc

    @staticmethod
    def wait_for_selector(driver, selector):
        try:
            WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.XPATH, f"{selector}")))
        except (StaleElementReferenceException, NoSuchElementException, TimeoutException):
            return None
        else:
            return True

    @staticmethod
    def wait_for_click(element):
        try:
            element.click()
        except (StaleElementReferenceException, NoSuchElementException, TimeoutException):
            return None
        else:
            return True

    @staticmethod
    def add_dollor(text):
        text = "$" + text
        return text

    def get_auctions(self, driver):
        current_url = driver.current_url
        all_auctions = []
        self.wait_for_selector(driver, "//div[@isset='1']")
        parsed = parse_qs(urlparse(current_url).query)
        current_date = parsed.get("AUCTIONDATE")
        if current_date is None:
            current_date = parsed.get("AuctionDate")[0]
        else:
            current_date = current_date[0]
        for area in self.AREA_LIST:
            try:
                max_pages = int(driver.find_element(By.XPATH, f'//div[@class="Head_{area}"]//span[@id="max{area}A"]').text)
            except:
                logger.debug(f'can not get AREA_LIST: {area}')
                continue
            logger.debug(f'{area} {max_pages} //div[@class="Head_{area}"]//span[@id="maxCA"]')
            for i in range(max_pages):
                logger.info(f'Scraping page no: {i+1} from website ({current_date})')
                collected_auctions_status = driver.find_elements(By.XPATH, f'//div[@id="Area_{area}"]//div[@isset="1"]//div[@class="AUCTION_STATS"]')
                collected_auctions_details = driver.find_elements(By.XPATH, f'//div[@id="Area_{area}"]//div[@isset="1"]//table[@class="ad_tab"]')

                if collected_auctions_status and collected_auctions_details:
                    for status, detail in zip(collected_auctions_status, collected_auctions_details):
                        all_auctions.append((status.text, detail.text))

                    driver.find_element(By.XPATH, f'//div[@class="Head_{area}"]//div[@class="PageFrame"]//span[@class="PageRight"]/img').click()
                    time.sleep(2)
        try:
            self.save_auctions(all_auctions, current_date, current_url)
        except Exception as e:
            pass

    def save_auctions(self, all_auctions,current_date, current_url):
        for status, detail in all_auctions:
            details = {
                "Auction Sold": None,
                "Amount": None,
                "Sold To": None,
                "Auction Type": None,
                "Case #": None,
                "Certificate #": None,
                "Opening Bid": None,
                "Parcel ID": None,
                "Property Address": None,
                "Assessed Value": None,
                "Auction Status": None,
            }
            for key, value in zip(status.split('\n')[::2], status.split('\n')[1::2]):
                details[key.strip()] = value.strip()
            prev = ""
            for key_value in detail.split('\n'):
                if ":" in key_value:
                    # if "Property Address".lower() in key_value.lower() and "Parcel size".lower() in key_value.lower():
                    if len(key_value.split(':')) == 3:
                        key, val1, val2 = key_value.split(':')
                        details[key.strip()] = val1.strip() + ' ' + val2.strip()
                        prev = key
                    else:
                        key, value = key_value.split(':')
                        details[key.strip()] = value.strip()
                        prev = key
                else:
                    details[prev] += " \n" + key_value.strip()
            website_name = urlparse(current_url).netloc.rsplit('.')[0].replace('.','_')
            details['source'] = website_name
            self.data.append(details)

    def save(self):
        out_name = f'{self.save_path}/{self.selected_county.replace(" ","_").replace(".","")}.xlsx'
        if self.data:
            df = pd.DataFrame(self.data)
            df = df[df['Sold To'] == '3rd Party Bidder']
            if 'Amount' in df.columns:
                df['Amount'] = df['Amount'].replace("[\$\,]",'', regex=True).astype(float)
                df = df.sort_values(by=['Amount'], ascending=False)
                df['Amount'] = df['Amount'].astype(str).apply(self.add_dollor)
            else:
                pass
            df.to_excel(out_name, index=False)

    def init_GUI(self, driver):
        THEME = 'DarkBlack'
        sg.theme(THEME)   # Add a touch of color
        driver.get(self.BASE_URL)
        website_list = []
        base_select_website = driver.find_element(By.XPATH, '//select[@id="JMP_MENU_SEL"]')
        for website in base_select_website.text.split('\n')[1:]:
            if webdriver and website.strip():
                website_list.append(website.strip())
        # All the stuff inside your window.
        layout = [[sg.Text('Select any of the following website:')],
                  [sg.Text('Miami-dade is default selected press Ok if you want to select default.')],
                  [sg.Combo(values=website_list, key='WEBSITE', size=(75, 6))],
                  [sg.Button('Ok'), sg.Button('Cancel')]]
        # Create the Window
        window = sg.Window('Select Website', layout)
        # Event Loop to process "events" and get the "values" of the inputs
        today = datetime.datetime.today()
        current_date = datetime.datetime.strftime(today, "%m/%d/%Y")
        while True:
            event, values = window.read()
            if event == 'Ok':
                break
            elif event == sg.WIN_CLOSED or event == 'Cancel':  # if user closes window or clicks cancel
                driver.close()
                exit(0)
        window.close()
        if values["WEBSITE"]:
            self.selected_county = values["WEBSITE"]
        # Check whether the specified path exists or not
        isExist = os.path.exists(self.save_path)
        if not isExist:
            # Create a new directory because it does not exist
            os.makedirs(self.save_path)
            logger.info("The new directory is created!")

    def init_driver(self):
        HEADLESS = False
        # Create a new instance of the Chrome driver
        chrome_options = webdriver.ChromeOptions()
        if HEADLESS:
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--ignore-certificate-errors-spki-list')
            chrome_options.add_argument('--ignore-ssl-errors')
        driver = webdriver.Chrome(ChromeDriverManager().install(), chrome_options= chrome_options)
        return driver

    def init_scraper(self, driver, domain):
        driver.get(f"https://{domain}/index.cfm?zaction=USER&zmethod=CALENDAR")
        previous = "//div[@class='CALNAV' and @tabindex='0'][1]/a"
        try:
            while True:
                calender = [e.get_attribute('dayid') for e in driver.find_elements(By.XPATH,"//div[@dayid and @role='link']") if e]
                for date_ in calender:
                    driver.get(f"https://{domain}/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE={date_}")
                    self.wait_for_selector(driver, "//div[contains(@id, 'AITEM')][1]")
                    self.get_auctions(driver)
                    driver.back()
                if self.wait_for_selector(driver, previous):
                    previous_url = driver.find_element(By.XPATH, previous).get_attribute("href")
                    driver.get(previous_url)
                    continue
                else:
                    break
        except KeyboardInterrupt:
            pass
        finally:
            self.save()

    def start(self):
        driver = self.init_driver()
        self.init_GUI(driver)
        site_ids = [elem.get_attribute('value') for elem in driver.find_elements(By.XPATH, f"//option[text()='{self.selected_county}']")]
        site_id = site_ids.pop(0)
        domain = self.get_domain(site_id)
        self.init_scraper(driver, domain)
        driver.quit()

auction_scraper = AuctionScraper()
auction_scraper.start()