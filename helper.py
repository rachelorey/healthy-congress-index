from lxml import html
import requests
import re
import pandas as pd
from datetime import datetime, timedelta
from lxml import html
import requests
import time

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options


def scrape_w_selenium(url):

    """
    uses selenium to get page_content and return tree
    """

    ##set up selenium scraper
    options = Options()
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    #since there is no more chromedriver.exe, Selenium should auto-detect the integrated driver
    driver = webdriver.Chrome(options=options)
    driver.get(url)
    time.sleep(2)

    # Parse the HTML content with lxml
    page_content = driver.page_source
    tree = html.fromstring(page_content)
    driver.quit()

    return tree

def web_test(datestart,dateend):
    """
    checks whether url for given date is valid
    if it's not, moves on to next day
    """
    url =f"https://www.congress.gov/congressional-record/{datestart.year}/{datestart.month}/{datestart.day}/daily-digest"
    tree = scrape_w_selenium(url)
    print(url)

    while "We couldn't find that page" in "".join(tree.xpath("//h1//text()")):
        
        #if page invalid, add another date and rescrape
        datestart = datestart + timedelta(days=1)
        url = f"https://www.congress.gov/congressional-record/{datestart.year}/{datestart.month}/{datestart.day}/daily-digest"

        #scrape new url
        tree = scrape_w_selenium(url)
              
        #stop if pass end date
        if datestart > dateend:
            break
        
    return(datestart,url,tree)

# Helper function to clean string (moved for reuse)
def clean_string(text):
    patterns = [r',', r'"', r"\'", r'\[', r'\]']
    for pattern in patterns:
        text = re.sub(pattern, "", text)
    return text

def extract_between(text, start_key, end_key=None):
    try:
        # Split once by the start_key and take the second part (after the start_key)
        after_start = text.split(start_key, 1)[1]
        
        # If end_key is provided, split by it; otherwise, return everything after start_key
        if end_key:
            between = after_start.split(end_key, 1)[0]
        else:
            between = after_start  # No end_key, take everything after start_key
        
        return between.strip()  # Strip whitespace from the result
    except IndexError:
        return None  # Return None if start_key is not found

# # Helper function to calculate time in session
# def calculate_time_in_session(conv, adj):
#     try:
#         return (datetime.combine(datetime(1, 1, 1), adj) - datetime.combine(datetime(1, 1, 1), conv)).seconds // 60
#     except:
#         return 0

def time_str_to_datetime(time_str):
    """Convert time string to datetime object."""
    # Try to convert the extracted time into a datetime object
    try:
        return datetime.strptime(time_str, '%I:%M:%S %p')
    except ValueError:
        try:
            return datetime.strptime(time_str, '%I:%M %p')  # Handle times without seconds
        except ValueError:
            try:
                return datetime.strptime(time_str, '%I %p')  # Handle times without minutes
            except ValueError:
                return None  # If the time string format is not recognized

def process_time_string(time_string):
    if type(time_string) == str:
        time_string = time_string.replace("12 noon","12:00pm").replace("noon","12:00pm").replace("midnight","12:00am").replace(".","").strip()
    else:
        return None
    
    # Regular expression to capture all time patterns
    time_pattern = r'\d{1,2}:\d{2}(?::\d{2})?\s*[aApP]\s*[mM]' # w periods: r'\d{1,2}:\d{2}(?::\d{2})?\s*[aApP]\.?[mM]\.?'

    # Find all time patterns in the string
    matches = re.findall(time_pattern, time_string)

    # other time formarts
    if not matches:

        # Regular expression to capture times like "9am", "9 am", "5pm", etc.
        time_pattern = r'\b\d{1,2}\s*[aApP]\s*[mM]\b' # w periods: r'\b\d{1,2}\s*[aApP]\s*\.?\s*[mM]\s*\.?\b'

        # Find all time patterns in the string
        matches = re.findall(time_pattern, time_string)

    if matches:
        return time_str_to_datetime(matches[0])
    else:
        return None

def return_times_from_string(strg,day_data):

    chamber = day_data["House or Senate"]
    
    if chamber == "Senate":
        strg = strg[:strg.find("House")]
    else: 
        strg = strg[strg.find("House"):]


    convened_terms = ["met at","convened at"]
    adjourned_terms = ["adjourned at","and","recessed at"]

    for convened_term in convened_terms:
        for adjourned_term in adjourned_terms: 

            #extract string containing time convened
            if day_data["Time Convened"] is None:
                day_data["Time Convened"] = extract_between(strg, convened_term, adjourned_term)

                if day_data["Time Convened"]:
                    day_data["Time Convened"] = process_time_string(day_data["Time Convened"])

            #extract string containing time adjourned
            if day_data["Time Adjourned"] is None:

                # if "until" in input string, stop looking there (sometimes there's start time next day, ie "adjourns at X until tomorrow")
                end_str = "until" if "until" in strg else None
                
                #extract text
                day_data["Time Adjourned"] = extract_between(strg, adjourned_term,end_str)

                #extract times
                if day_data["Time Adjourned"]:
                    day_data["Time Adjourned"] = process_time_string(day_data["Time Adjourned"])

    return(day_data)

# Helper function to handle exceptions
# def handle_exceptions(strg, conv, adj, insession, chamber, conv_, adj_):
#     try:
#         conv.append(extract_between(strg, conv_, "on"))
#         adj.append(extract_between(strg, adj_, "on"))
#         timein = calculate_time_in_session(conv[-1], adj[-1])
#         insession.append("x" if timein >= 60 else "NS")
#     except:
#         insession.append("INPUT BY HAND")
#         conv.append(f"Error: {strg}")
#         adj.append(f"Error: {strg}")
