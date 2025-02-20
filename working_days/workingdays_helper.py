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

# Helper function to clean string
def clean_string(text):
    patterns = [r',', r'"', r"\'", r'\[', r'\]',r'\n']
    for pattern in patterns:
        text = re.sub(pattern, "", text)
    text = ' '.join(text.split())
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

# Main function to calculate working days
def workingdays(start="01/01/2022", end=None,file_name="working_days_cache.csv"):    
    datestart = datetime.strptime(start, '%m/%d/%Y').date()

    if end is None:
        dateend = datetime.now().date()       
    else:
        dateend = datetime.strptime(end, '%m/%d/%Y').date()

    rows = []  # Use a list to accumulate rows
    chambers = ["Senate", "House"]

    while datestart <= dateend:
        datestart, url, tree = web_test(datestart, dateend)

        # next valid webpage may be past dateend, break if so
        if datestart > dateend:
            break
        
        # for each chamber (House and Senate)
        for chamber in chambers:
            date = datestart.strftime("%m/%d/%Y")

            # Initialize values for the day
            day_data = {
                "House or Senate": chamber,
                "Date": date,
                "Time Convened": None,
                "Time Adjourned": None,
                "Time in Session": None,
                "Working Day?": "INPUT BY HAND",
                "Scraped adjournment string":None,
                "url":url
            }

            xpaths = [
                f"//center[h2[contains(text(), '{chamber}')]]//following-sibling::p[strong='Adjournment:'][contains(text(),{chamber})]//text()",
                f"//center[h2[contains(text(), '{chamber}')]]//following-sibling::p[strong='Recess:'][contains(text(),{chamber})]//text()",
                f"//center[h2[contains(text(), '{chamber}')]]//following-sibling::p/text()",
                f"//center[h2[contains(text(), '{chamber}')]]//following-sibling::p[contains(translate(text(), 'ADJOURN', 'adjourn'), 'adjourn')]//text()",
                f"//center[h2[contains(text(), '{chamber}')]]//following-sibling::p[contains(text(),'in session')]//text()",
                #pre-styled structure
                f"//pre[@class='styled' and contains(., '{chamber}') and (contains(., 'met at') or contains(., 'adjourned at'))]//text()"

            ]
            
            for xp in range(len(xpaths)):
                try:
                    # if pre-styled text box (lots of misc text) do some extra processing to select correct element
                    if xp == (len(xpaths) - 1): #get last xpath
                        for s in tree.xpath(xpaths[xp]):
                            s = clean_string(s)
                            strg = ""
                            
                            if "met at" in s:
                                strg = s
                            elif "adjourn" in s:
                                strg = s
                            elif "convened" in s:
                                strg = s
                            elif "in session" in s:
                                strg = s
                            elif "recessed at" in s:
                                strg = s
                            else:
                                strg += s #save each result                                
                    else: # most cases
                        strg = clean_string("".join(tree.xpath(xpaths[xp])[0:2]))
                except Exception as e:
                    print("Error with xpath: ",e)
                        
                day_data["Scraped adjournment string"] = strg

                # Not in session
                if "not in session" in strg:
                    day_data["Time Convened"] = None
                    day_data["Time Adjourned"] = None
                    day_data["Working Day?"] = "NS"

                # Pro forma
                elif "pro forma" in strg:
                        day_data["Time Convened"] = None
                        day_data["Time Adjourned"] = None
                        day_data["Working Day?"] = "pf"
                        
                # try and extrac times
                else:
                    try:
                        day_data = return_times_from_string(strg,day_data)
                         
                        if day_data["Time Convened"] and day_data["Time Adjourned"]:

                            #minutes
                            timein = (day_data["Time Adjourned"] - day_data["Time Convened"]).total_seconds() / 60
                            day_data["Time in Session"] = timein

                            if timein >= 60:
                                day_data["Working Day?"] = "x"
                            elif timein > 0:
                                day_data["Working Day?"] = "pf"

                            day_data["Time Convened"] = day_data["Time Convened"].strftime("%H:%M%p")
                            day_data["Time Adjourned"] = day_data["Time Adjourned"].strftime("%H:%M%p")

                    except Exception as e:
                        print("Issue exracting times, string: ",strg,"\nError:",e)
                                
                if day_data["Working Day?"] !=  "INPUT BY HAND":
                    break

            # Append daily results as a dictionary to the rows list
            rows.append(day_data)
            df = pd.DataFrame(rows, columns=day_data.keys())
            df.to_csv(file_name)
            
        # Add one day to the loop
        datestart += timedelta(days=1)

    # Convert the accumulated rows (list of dictionaries) into a DataFrame
    df = pd.DataFrame(rows, columns=day_data.keys())
    df.to_csv(file_name)
    
    return df

# # Main function to calculate working days
# def workingdays(start="01/01/2022", end=None,file_name="working_days_cache.csv"):    
#     datestart = datetime.strptime(start, '%m/%d/%Y').date()

#     if end is None:
#         dateend = datetime.now().date()       
#     else:
#         dateend = datetime.strptime(end, '%m/%d/%Y').date()

#     # Load existing cache if it exists
#     if os.path.exists(file_name):
#         rows = pd.read_csv(file_name, dtype=str)
#     else:
#         rows = pd.DataFrame(columns=["House or Senate", "Date", "Time Convened", "Time Adjourned", "Time in Session", "Working Day?", "Scraped adjournment string", "url"])

#     chambers = ["Senate", "House"]

#     while datestart <= dateend:

#         filtered_cache = rows[rows["Date"] == datestart.strftime("%m/%d/%Y")]

#         if not filtered_cache.empty and set(filtered_cache["House or Senate"]) >= set(chambers):
#             print(f"Skipping {datestart.strftime('%m/%d/%Y')}, already in cache.")
#             datestart += timedelta(days=1)
#             continue  # Skip this date if already present
        
#         datestart, url, tree = web_test(datestart, dateend)

#         # next valid webpage may be past dateend, break if so
#         if datestart > dateend:
#             break

#         # for each chamber (House and Senate)
#         for chamber in chambers:
#             date = datestart.strftime("%m/%d/%Y")

#             # Initialize values for the day
#             day_data = {
#                 "House or Senate": chamber,
#                 "Date": date,
#                 "Time Convened": None,
#                 "Time Adjourned": None,
#                 "Time in Session": None,
#                 "Working Day?": "INPUT BY HAND",
#                 "Scraped adjournment string":None,
#                 "url":url
#             }
        
#             xpaths = [
#                 f"//center[h2[contains(text(), '{chamber}')]]//following-sibling::p[strong='Adjournment:'][contains(text(),{chamber})]//text()",
#                 f"//center[h2[contains(text(), '{chamber}')]]//following-sibling::p/text()",
#                 f"//center[h2[contains(text(), '{chamber}')]]//following-sibling::p[contains(translate(text(), 'ADJOURN', 'adjourn'), 'adjourn')]//text()",
#                 f"//center[h2[contains(text(), '{chamber}')]]//following-sibling::p[contains(text(),'in session')]//text()",
#                 f"//center[h2[contains(text(), '{chamber}')]]/following-sibling::p[contains(text(), 'met at') or contains(text(), 'adjourned') or contains(text(), 'in session') or contains(text(), 'recessed at')]//text()",
#                 f"//center[h2[contains(text(), '{chamber}')]]/following-sibling::p//text()",
#                 f"//pre[contains(., '{chamber}') and (contains(., 'met at') or contains(., 'adjourned at'))]//text()"
#                 #pre-styled structure
#                 f"//pre[@class='styled' and contains(., '{chamber}') and (contains(., 'met at') or contains(., 'adjourned at'))]//text()"

#             ]
            
#             strg = ""
#             for xp in xpaths:
#                 try:
#                     for s in tree.xpath(xp):
#                         s = clean_string(s)
#                         # Ensure strg gets assigned
#                         if any(keyword in s for keyword in ["met at", "adjourn", "convened", "in session", "recessed at"]):
#                             strg = s
#                             break
#                         else:
#                             strg += s  # Save result
#                     # print(f"Extracted text for XPath {xp}: {strg}")
#                 except Exception as e:
#                     print(f"Error with XPath {xp}: {e}")

#             # Ensure strg has a valid value even if XPath fails
#             if not strg:
#                 strg = "No data found"

#             day_data["Scraped adjournment string"] = strg  # Now strg is always defined

#             # Not in session
#             if "not in session" in strg:
#                 day_data["Time Convened"] = None
#                 day_data["Time Adjourned"] = None
#                 day_data["Working Day?"] = "NS"

#             # Pro forma
#             elif "pro forma" in strg:
#                     day_data["Time Convened"] = None
#                     day_data["Time Adjourned"] = None
#                     day_data["Working Day?"] = "pf"
                    
#             # try and extrac times
#             else:
#                 try:
#                     day_data = return_times_from_string(strg,day_data)
                        
#                     if day_data["Time Convened"] and day_data["Time Adjourned"]:

#                         #minutes
#                         timein = (day_data["Time Adjourned"] - day_data["Time Convened"]).total_seconds() / 60
#                         day_data["Time in Session"] = timein

#                         if timein >= 60:
#                             day_data["Working Day?"] = "x"
#                         elif timein > 0:
#                             day_data["Working Day?"] = "pf"

#                         day_data["Time Convened"] = day_data["Time Convened"].strftime("%H:%M%p")
#                         day_data["Time Adjourned"] = day_data["Time Adjourned"].strftime("%H:%M%p")

#                 except Exception as e:
#                     print("Issue exracting times, string: ",strg,"\nError:",e)
                                
#                 if day_data["Working Day?"] !=  "INPUT BY HAND":
#                     break

#             # Convert day_data to a DataFrame with one row
#             new_row = pd.DataFrame([day_data])

#             # Append the new row to the existing DataFrame
#             rows = pd.concat([rows, new_row], ignore_index=True)

#             # Save the updated DataFrame
#             rows.to_csv(file_name, index=False)
                        
#         # Add one day to the loop
#         datestart += timedelta(days=1)

#     # Convert the accumulated rows (list of dictionaries) into a DataFrame
#     df = pd.DataFrame(rows, columns=day_data.keys())
#     df.to_csv(file_name)
    
#     return df