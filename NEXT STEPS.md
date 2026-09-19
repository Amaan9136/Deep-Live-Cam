Since Deep-Live-Cam runs locally, you can easily disable its built-in safety check by editing one line of its Python code.
Locate the File: Go to your Deep-Live-Cam installation folder. Navigate into the core logic folder (usually named modules or processors). Look for a file related to frame processing, typically named frame_processor.py or core.py.
Open the Code: Open the .py file in a text editor like Notepad or Visual Studio Code.
Find the Filter: Press Ctrl + F and search for keywords like nsfw, check_nsfw, or has_nsfw. You will find a conditional check that looks similar to this:
python
if check_nsfw(frame):
    print("NSFW content detected!")
    return None
Disable it: Comment out the block by adding a # in front of each line, or change the condition to always be false:
python
if False: # check_nsfw(frame):
    print("NSFW content detected!")