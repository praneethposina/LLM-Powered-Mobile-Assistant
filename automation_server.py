from flask import Flask, request, jsonify
from appium import webdriver
from appium.options.common import AppiumOptions
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions import interaction
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.keys import Keys
import threading
import json
import uuid
import os
import time
import xml.etree.ElementTree as ET
from groq import Groq
from functools import lru_cache

app = Flask(__name__)
sessions = {}
session_lock = threading.Lock()

def setup_appium():
    options = AppiumOptions()
    options.set_capability('platformName', 'Android')
    options.set_capability('deviceName', 'Pixel 7')  # Update this to match your device
    options.set_capability('automationName', 'UiAutomator2')
    options.set_capability('platformVersion', '15')  # Update this to match your Android version
    options.set_capability('noReset', True)
    options.set_capability('newCommandTimeout', 300)
    options.set_capability('adbExecTimeout', 60000)
    
    driver = webdriver.Remote('http://localhost:4723', options=options)
    return driver
os.environ["GROQ_API_KEY"] = "GROQ_API_KEY"
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
            info = f"{content_desc or text}|Bounds:{bounds}|{class_name}"
            compressed_info.append(info)

        for child in elem:
            extract_info(child)

    extract_info(root)
    return '\n'.join(compressed_info)

def get_model_prediction(verification_prompt, command):
    client = Groq()

    prompt = f"""You are an advanced AI assistant simulating a mobile phone user. Your task is to predict the next **single action** to take based on the given screen information and user command. Follow these steps to provide the most accurate and efficient action:


{verification_prompt}

Respond with a single JSON object representing the next action. The action should have the following properties:
- "action_type": The type of action (e.g., "CLICK", "TYPE", "SCROLL", "WAIT", "GOBACK", "ENTER"). Actively use the "ENTER" action whenever required. Actively use "SCROLL" action when you dontfind what you are supposed to find.
- "element": The text after the colon (:) in the element information. This will be either the content description or the text of the element.
- "description": A brief description of the action
- "text": (Only for TYPE actions) The text to be typed
- "previous_step_successful": A boolean indicating if the previous step was successful
- "task_complete": A boolean indicating if the entire task is complete based on the new screen available. if you are confident enough the task is complete, set it to true.
- "bounds": The bounds of the element in the format "[x1,y1][x2,y2]"
- "screen_awareness": A brief description of what's currently happening on the screen

if your command is : "Open youtube"
Example:
{{
    "action_type": "CLICK",
    "element": "Google Search",
    "description": "Click Google search to search for youtube",
    "bounds": "[100,200][200,300]",
    "previous_step_successful": true,
    "task_complete": false,
    "screen_awareness": "The home screen is displayed with various apps and the Google search bar at the bottom."
}}

{{
    "action_type": "TYPE",
    "element": "Search",
    "description": "Type 'YouTube' in the search bar",
    "text": "YouTube",
    "bounds": "[100,200][200,300]",
    "previous_step_successful": true,
    "task_complete": false,
    "screen_awareness": "A search bar is active, waiting for input."
}}

{{
    "action_type": "ENTER",
    "element": "Search",
    "description": "Press the Enter key to submit the search",
    "bounds": "[100,200][200,300]",
    "previous_step_successful": true,
    "task_complete": false,
    "screen_awareness": "The search query has been entered, ready to be submitted."
}}

{{
    "action_type": " ",
    "element": " ",
    "description": "Do nothing since task is complete",
    "bounds": "[ , ][ , ]",
    "previous_step_successful": true,
    "task_complete": true,
    "screen_awareness": "Youtube home page is displayed."
}}
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
            stream=False
        )

        prediction = completion.choices[0].message.content
        print(f"\nAI Response: {prediction}")
        
        try:
            json_prediction = json.loads(prediction)
            return json.dumps(json_prediction)
        except json.JSONDecodeError:
            print("Failed to parse JSON. Raw prediction:")
            print(prediction)
            return json.dumps({
                "action_type": "CLICK",
                "element": "Camera",
                "description": "Click the Camera app icon (fallback action due to parsing error)",
                "bounds": "",
                "previous_step_successful": False,
                "task_complete": False,
                "screen_awareness": "Unable to determine screen state due to parsing error"
            })
    except Exception as e:
        print(f"Error in get_model_prediction: {str(e)}")
        return json.dumps({
            "action_type": "CLICK",
            "element": "Camera",
            "description": "Click the Camera app icon (fallback action due to error)",
            "bounds": "",
            "previous_step_successful": False,
            "task_complete": False,
            "screen_awareness": "Unable to determine screen state due to error"
        })

def parse_actions(prediction):
    if isinstance(prediction, str):
        try:
            prediction = json.loads(prediction)
        except json.JSONDecodeError:
            print("Error parsing prediction JSON")
            return [{"previous_step_successful": False, "task_complete": False}]
    return [prediction]

def execute_action(driver, action):
    action_type = action['action_type']
    element = action.get('element', '')
    bounds = action.get('bounds', '')

    print(f"Executing: {action_type} on {element}")

    try:
        if bounds:
            bounds = bounds.replace('Bounds:', '').strip()
            x, y = parse_bounds(bounds)
            if x is None or y is None:
                print("Invalid bounds detected")
                return
            
            actions = ActionChains(driver)
            actions.w3c_actions = ActionBuilder(driver, mouse=PointerInput(interaction.POINTER_TOUCH, "touch"))
            actions.w3c_actions.pointer_action.move_to_location(x, y)

            if action_type == 'CLICK':
                actions.w3c_actions.pointer_action.click()
                actions.perform() 
            elif action_type == 'TYPE':
                actions.w3c_actions.pointer_action.click()
                actions.perform()
                el = driver.find_element(AppiumBy.XPATH, f"//*[@bounds='{bounds}']")
                el.send_keys(action.get('text', ''))
                driver.press_keycode(66)  # Enter key
            elif action_type == 'ENTER':
                actions.w3c_actions.pointer_action.click()
                actions.perform()
                driver.press_keycode(66)  # Enter key
        elif action_type == 'SCROLL':
            size = driver.get_window_size()
            start_x = size['width'] * 0.5
            start_y = size['height'] * 0.4
            end_x = size['width'] * 0.5
            end_y = size['height'] * 0.1
            
            actions = ActionChains(driver)
            actions.w3c_actions = ActionBuilder(driver, mouse=PointerInput(interaction.POINTER_TOUCH, "touch"))
            actions.w3c_actions.pointer_action.move_to_location(start_x, start_y)
            actions.w3c_actions.pointer_action.pointer_down()
            actions.w3c_actions.pointer_action.move_to_location(end_x, end_y)
            actions.w3c_actions.pointer_action.release()
            actions.perform()
        elif action_type == 'WAIT':
            time.sleep(action.get('duration', 5))
        elif action_type == 'GOBACK':
            driver.back()
        else:
            print(f"Unknown action type: {action_type}")
    except Exception as e:
        print(f"Error executing action: {str(e)}")
        if action_type in ['CLICK', 'TYPE', 'ENTER']:
            print("Attempting to find element without bounds...")
            try:
                el = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((AppiumBy.XPATH, f"//*[@content-desc='{element}' or @text='{element}']"))
                )
                if action_type == 'CLICK':
                    el.click()
                elif action_type == 'TYPE':
                    el.send_keys(action.get('text', ''))
                elif action_type == 'ENTER':
                    driver.press_keycode(66)  # Enter key
            except Exception as inner_e:
                print(f"Failed to find element: {str(inner_e)}")

def parse_bounds(bounds_str):
    try:
        coords = bounds_str.replace('][', ',').strip('[]').split(',')
        x1, y1, x2, y2 = map(int, coords)
        return (x1 + x2) // 2, (y1 + y2) // 2
    except ValueError:
        print(f"Invalid bounds format: {bounds_str}")
        return None, None

# Add a root route for testing
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "success",
        "message": "Automation server is running"
    })

@app.route('/start_session', methods=['POST'])
def start_session():
    try:
        print("Attempting to start Appium session...")
        driver = setup_appium()
        session_id = str(uuid.uuid4())
        
        with session_lock:
            sessions[session_id] = {
                'driver': driver,
                'last_activity': time.time()
            }
        
        print(f"Session started successfully: {session_id}")
        return jsonify({
            "status": "success",
            "message": "Session started",
            "session_id": session_id
        })
    except Exception as e:
        print(f"Error starting session: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return jsonify({
            "status": "error",
            "message": str(e)
        })

@app.route('/execute_command', methods=['POST'])
def execute_command():
    print("\n=== Execute Command Request Received ===")
    data = request.json
    session_id = data.get('session_id')
    command = data.get('command')
    
    print(f"Session ID: {session_id}")
    print(f"Command: {command}")
    
    if not session_id or session_id not in sessions:
        print("Error: Invalid or expired session")
        return jsonify({
            "status": "error",
            "message": "Invalid or expired session",
            "session_expired": True
        })
    
    try:
        session = sessions[session_id]
        driver = session['driver']
        session['last_activity'] = time.time()
        
        # Always start from home screen
        print("Going to home screen...")
        driver.press_keycode(3)  # 3 is the keycode for HOME button
        time.sleep(1)  # Wait for home screen to load
        
        step_number = 1
        max_steps = 15
        
        print(f"\nStarting command execution with {max_steps} max steps")
        
        while step_number <= max_steps:
            print(f"\nStep {step_number}/{max_steps}")
            
            # Get current screen info
            xml = capture_screen_xml(driver)
            compressed_info = compress_xml(xml)
            print(f"Current Screen Information:")
            print(compressed_info)
            
            # Create verification prompt
            verification_prompt = f"""Your command is: {command}

Current screen information:
{compressed_info}

Is step {step_number} successful? If yes, predict the next step. If no, predict a corrective action. If the entire task is complete (command is executed) acetively check if the command is executed, set "task_complete" to true. Respond in JSON format as before."""

            print("\nGetting AI prediction...")
            prediction = get_model_prediction(verification_prompt, command)
            print(f"AI Prediction: {prediction}")
            
            try:
                action = parse_actions(prediction)[0]
                print(f"\nParsed Action: {action}")
                
                previous_step_successful = action['previous_step_successful']
                task_complete = action['task_complete']
                
                print(f"Previous step successful: {previous_step_successful}")
                print(f"Task complete: {task_complete}")
                
                if task_complete:
                    print("Command execution completed successfully")
                    return jsonify({
                        "status": "success",
                        "message": "Command execution completed",
                        "action": action,
                        "screen_info": compressed_info,
                        "task_complete": True
                    })
                
                # Execute the action
                print(f"\nExecuting action: {action['action_type']} on {action.get('element', '')}")
                execute_action(driver, action)
                
                # Log the interaction
                with open("ai_interaction_log.txt", "a", encoding="utf-8") as f:
                    f.write(f"\nStep {step_number}/{max_steps}:\n")
                    f.write(f"Command: {command}\n")
                    f.write(f"Screen Information:\n{compressed_info}\n\n")
                    f.write(f"Action:\n")
                    f.write(f"Type: {action['action_type']}, Element: {action.get('element', '')}, Bounds: {action.get('bounds', '')}, Description: {action['description']}\n")
                    f.write(f"Screen Awareness: {action['screen_awareness']}\n")
                    if 'text' in action:
                        f.write(f"Text: {action['text']}\n")
                    f.write(f"Previous step successful: {previous_step_successful}\n")
                    f.write(f"Task complete: {task_complete}\n")
                
                step_number += 1
                
            except Exception as e:
                print(f"Error in action execution: {str(e)}")
                return jsonify({
                    "status": "error",
                    "message": str(e)
                })
        
        print(f"Maximum steps ({max_steps}) reached")
        return jsonify({
            "status": "warning",
            "message": f"Maximum steps ({max_steps}) reached"
        })
            
    except Exception as e:
        print(f"Error in command execution: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return jsonify({
            "status": "error",
            "message": str(e)
        })

@app.route('/end_session', methods=['POST'])
def end_session():
    data = request.json
    session_id = data.get('session_id')
    
    if session_id and session_id in sessions:
        try:
            with session_lock:
                sessions[session_id]['driver'].quit()
                del sessions[session_id]
            return jsonify({"status": "success", "message": "Session ended"})
        except Exception as e:
            print(f"Error ending session: {str(e)}")
            return jsonify({"status": "error", "message": str(e)})
    return jsonify({"status": "success", "message": "Session not found"})

# Cleanup old sessions periodically
def cleanup_old_sessions():
    while True:
        time.sleep(300)  # Check every 5 minutes
        current_time = time.time()
        with session_lock:
            for session_id in list(sessions.keys()):
                if current_time - sessions[session_id]['last_activity'] > 1800:  # 30 minutes
                    try:
                        sessions[session_id]['driver'].quit()
                    except:
                        pass
                    del sessions[session_id]

@lru_cache(maxsize=100)
def get_cached_prediction(prompt_hash):
    # Convert the prompt to a string hash for caching
    return get_model_prediction(prompt_hash)

if __name__ == '__main__':
    cleanup_thread = threading.Thread(target=cleanup_old_sessions, daemon=True)
    cleanup_thread.start()
    
    print("Starting automation server on http://0.0.0.0:5001")
    app.run(host='0.0.0.0', port=5001, debug=True)