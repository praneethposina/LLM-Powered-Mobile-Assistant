from appium import webdriver
from appium.options.common import AppiumOptions
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions import interaction
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import xml.etree.ElementTree as ET
from groq import Groq
import json
import os
import time
import sys

os.environ["GROQ_API_KEY"] = "llama-3.1-70b-versatile"

def setup_appium():
    options = AppiumOptions()
    options.set_capability('platformName', 'Android')
    options.set_capability('deviceName', 'Pixel 7')
    options.set_capability('automationName', 'UiAutomator2')
    options.set_capability('platformVersion', '15')
    options.set_capability('appPackage', 'com.google.android.youtube')
    options.set_capability('appActivity', 'com.google.android.youtube.HomeActivity')
    options.set_capability('noReset', True)
    options.set_capability('newCommandTimeout', 3600)  # Set a long timeout (1 hour)
    
    driver = webdriver.Remote('http://localhost:4723', options=options)
    return driver

def capture_screen_xml(driver):
    return driver.page_source

def compress_xml(xml_string):
    root = ET.fromstring(xml_string)
    compressed_info = []

    def extract_info(elem):
        content_desc = elem.attrib.get('content-desc', '').strip()
        text = elem.attrib.get('text', '').strip()
        clickable = elem.attrib.get('clickable', 'false')
        bounds = elem.attrib.get('bounds', '')
        class_name = elem.attrib.get('class', '').split('.')[-1]
        
        if content_desc or (text and clickable == 'true'):
            info = f"{content_desc or text}|{bounds}|{class_name}"
            compressed_info.append(info)

        for child in elem:
            extract_info(child)

    extract_info(root)
    return '\n'.join(compressed_info)

def get_model_prediction(screen_info, command):
    client = Groq()

    prompt = f"""You are an AI assistant simulating a mobile phone user. Based on the given screen information and user command, provide the next single action to take. Focus on what to do in the current step to achieve the command as soon as possible. Output the action in JSON format without any preamble.

Current task: {command}

Screen information:
{screen_info}

Respond with a single JSON object representing the next action. The action should have the following properties:
- "action_type": The type of action (e.g., "CLICK", "TYPE", "SCROLL", "WAIT", "GOBACK")
- "element": The text after the colon (:) in the element information. This will be either the content description or the text of the element.
- "description": A brief description of the action
- "text": (Only for TYPE actions) The text to be typed
- "step_successful": A boolean indicating if the previous step was successful
- "task_complete": A boolean indicating if the entire task is complete based on the new screen available. if you are confident enough the task is complete, set it to true.
- "bounds": The bounds of the element in the format "[x1,y1][x2,y2]"
- "screen_awareness": A brief description of what's currently happening on the screen

Provide only the JSON object as your response, without any additional text."""

    print("\nGenerating AI Prediction...")
    try:
        completion = client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7,
            max_tokens=250,
            top_p=1,
            stream=True,
            stop=None,
        )

        prediction = ""
        for chunk in completion:
            content = chunk.choices[0].delta.content or ""
            print(content, end="", flush=True)
            prediction += content

        print("\n")  # New line after streaming completion
        
        try:
            json_prediction = json.loads(prediction)
            return json.dumps(json_prediction)
        except json.JSONDecodeError:
            print("Failed to parse JSON. Raw prediction:")
            print(prediction)
            return json.dumps({
                "action_type": "CLICK",
                "element": "Search",
                "description": "Click the Search button (fallback action due to parsing error)",
                "bounds": "",
                "step_successful": False,
                "task_complete": False,
                "screen_awareness": "Unable to determine screen state due to parsing error"
            })
    except Exception as e:
        print(f"Error in get_model_prediction: {str(e)}")
        return json.dumps({
            "action_type": "CLICK",
            "element": "Search",
            "description": "Click the Search button (fallback action due to error)",
            "bounds": "",
            "step_successful": False,
            "task_complete": False,
            "screen_awareness": "Unable to determine screen state due to error"
        })

def parse_actions(prediction):
    try:
        action = json.loads(prediction)
        parsed_action = {
            'action_type': action.get('action_type', '').upper(),
            'element_id': action.get('element', ''),
            'description': action.get('description', ''),
            'step_successful': action.get('step_successful', False),
            'task_complete': action.get('task_complete', False),
            'bounds': action.get('bounds', ''),
            'screen_awareness': action.get('screen_awareness', '')
        }
        if action.get('action_type', '').upper() == 'TYPE':
            parsed_action['text'] = action.get('text', '')
        return [parsed_action]
    except json.JSONDecodeError:
        print("Failed to parse JSON. Raw prediction:")
        print(prediction)
        return [{
            'action_type': 'CLICK',
            'element_id': 'Search',
            'description': 'Click the Search button (fallback action)',
            'step_successful': False,
            'task_complete': False,
            'bounds': '',
            'screen_awareness': 'Unable to determine screen state due to parsing error'
        }]
    except Exception as e:
        print(f"Error parsing actions: {str(e)}")
        return [{
            'action_type': 'CLICK',
            'element_id': 'Search',
            'description': 'Click the Search button (fallback action)',
            'step_successful': False,
            'task_complete': False,
            'bounds': '',
            'screen_awareness': 'Unable to determine screen state due to error'
        }]

def execute_action(driver, action):
    action_type = action['action_type']
    element = action['element_id']
    description = action['description']
    bounds = action['bounds']

    print(f"Executing: {action_type} on {element} - {description}")

    try:
        if bounds:
            x, y = parse_bounds(bounds)
            actions = ActionChains(driver)
            actions.w3c_actions = ActionBuilder(driver, mouse=PointerInput(interaction.POINTER_TOUCH, "touch"))
            actions.w3c_actions.pointer_action.move_to_location(x, y)

            if action_type == 'CLICK':
                print("Clicking on element")
                actions.w3c_actions.pointer_action.click()
                actions.perform() 
            elif action_type == 'TYPE':
                actions.w3c_actions.pointer_action.click()
                actions.perform()
                driver.set_value(None, action.get('text', ''))
            else:
                print(f"Unsupported action type for bounds: {action_type}")
        elif action_type == 'SCROLL':
            size = driver.get_window_size()
            start_x = size['width'] * 0.5
            start_y = size['height'] * 0.8
            end_x = size['width'] * 0.5
            end_y = size['height'] * 0.2
            
            actions = ActionChains(driver)
            actions.w3c_actions = ActionBuilder(driver, mouse=PointerInput(interaction.POINTER_TOUCH, "touch"))
            actions.w3c_actions.pointer_action.move_to_location(start_x, start_y)
            actions.w3c_actions.pointer_action.pointer_down()
            actions.w3c_actions.pointer_action.move_to_location(end_x, end_y)
            actions.w3c_actions.pointer_action.release()
            actions.perform()
        elif action_type == 'WAIT':
            time.sleep(int(element.split('_')[-1]))
        elif action_type == 'GOBACK':
            driver.back()
        else:
            print(f"Unknown action type: {action_type}")
    except Exception as e:
        print(f"Error executing action: {str(e)}")
        if action_type in ['CLICK', 'TYPE'] and not bounds:
            print("Attempting to find element without bounds...")
            try:
                el = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((AppiumBy.XPATH, f"//*[@content-desc='{element}' or @text='{element}']"))
                )
                if action_type == 'CLICK':
                    el.click()
                elif action_type == 'TYPE':
                    el.send_keys(action.get('text', ''))
            except Exception as inner_e:
                print(f"Failed to find element without bounds: {str(inner_e)}")

def parse_bounds(bounds_str):
    coords = bounds_str.replace('][', ',').strip('[]').split(',')
    x1, y1, x2, y2 = map(int, coords)
    return (x1 + x2) // 2, (y1 + y2) // 2

def keep_session_alive(driver):
    try:
        driver.get_window_size()  # Perform a simple action to keep the session alive
    except Exception as e:
        print(f"Error keeping session alive: {str(e)}")

def generate_dataset(num_samples):
    dataset = []
    for _ in range(num_samples):
        scenario = random.choice(SCENARIOS)
        num_steps = random.randint(3, 7)
        
        steps = []
        pre_step_successful = True  # Initialize as True for the first step
        
        for i in range(num_steps):
            action = random.choice(ACTIONS)
            element = random.choice(ELEMENTS)
            
            step = {
                "action": action,
                "element": element,
                "pre_step_successful": pre_step_successful
            }
            
            steps.append(step)
            
            # Randomly determine if this step was successful for the next iteration
            pre_step_successful = random.choice([True, False])
        
        sample = {
            "scenario": scenario,
            "steps": steps
        }
        
        dataset.append(sample)
    
    return dataset

def save_dataset(dataset, filename):
    with open(filename, 'w') as f:
        json.dump(dataset, f, indent=2)

if __name__ == "__main__":
    driver = setup_appium()
    try:
        dataset = generate_dataset(100)  # Example usage with 100 samples
        save_dataset(dataset, "youtube_interaction_dataset.json")
        print(f"\nDataset with {len(dataset)} scenarios generated and saved to youtube_interaction_dataset.json")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
    finally:
        driver.quit()
        print("Exiting the script.")
        sys.exit(0)