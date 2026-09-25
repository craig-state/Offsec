import pyperclip  # pip install pyperclip

ZW = '\u200C' 

def zero_widthify(text):
    return ZW.join(text)

original = ".secrets" 
zw_string = zero_widthify(original)
pyperclip.copy(zw_string)
