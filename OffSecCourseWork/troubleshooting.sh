#!/bin/bash
# ============================================
## OffSec's troubleshooting script
## Last updated: September 02, 2025
# Version: 2.2.4
# ============================================

LOGFILE="troubleshoot.log"
> "$LOGFILE"

# --- Colors ---
RED="\e[31m"
GREEN="\e[32m"
YELLOW="\e[33m"
CYAN="\e[36m"
ORANGE="\e[38;5;208m"
RESET="\e[0m"

SUMMARY=()

log() {
    echo -e "$1" | tee -a "$LOGFILE"
}

add_summary() {
    SUMMARY+=("$1")
}

# good format for summary
format_summary() {
  local label="$1"
  local value="$2"

  local label_width=25
  local sep=' : '
  # indent width = label_width + length of separator
  local indent
  indent=$(printf '%*s' $((label_width + ${#sep})) '')

  # Expand backslash escapes (so "\n" becomes a real newline)
  local expanded
  expanded=$(printf '%b' "$value")

  local first=1
  while IFS= read -r line; do
    if [[ $first -eq 1 ]]; then
      printf "%-${label_width}s%s%s\n" "$label" "$sep" "$line"
      first=0
    else
      printf "%s%s\n" "$indent" "$line"
    fi
  done <<< "$expanded"
}


separator() {
    echo -e "\n----------------------------------------\n" | tee -a "$LOGFILE"
}

# Function: Spinner animation while a command is running
spinner() {
  local pid=$1
  local delay=0.15
  local spinstr='|/-\'
  while kill -0 $pid 2>/dev/null; do
    local temp=${spinstr#?}
    printf "[%c]" "$spinstr"
    spinstr=$temp${spinstr%"$temp"}
    sleep $delay
    printf "\b\b\b\b\b\b"
  done
  # Clear spinner after process finishes
  printf "     \b\b\b\b\b"
}




# ========== Flags ==========
SUMMARY=()
MTU_RESULT="Not tested"
echo "" > troubleshoot.log
echo "==== Troubleshooting Session ====" >> troubleshoot.log

# ---- DNS Resolve ----
if [[ "$1" == "--dns-resolve" ]]; then
    separator
    RESOLV_CONF="/etc/resolv.conf"
    BACKUP_FILE="/etc/resolv.conf.backup-$(date +%F_%T)"

    echo -e "${YELLOW}[i] Creating a backup of current DNS...${RESET}" | tee -a troubleshoot.log
    sudo cp "$RESOLV_CONF" "$BACKUP_FILE" 2>> troubleshoot.log
    if [[ $? -eq 0 ]]; then
        echo -e "${GREEN}[✓] Backup saved as $BACKUP_FILE${RESET}" | tee -a troubleshoot.log
    else
        echo -e "${RED}[x] Failed to backup DNS${RESET}" | tee -a troubleshoot.log
        exit 1
    fi

    # Ensure file is editable before updating
    if lsattr "$RESOLV_CONF" | grep -q 'i'; then
        echo -e "${YELLOW}[i] Removing immutable flag temporarily...${RESET}" | tee -a troubleshoot.log
        sudo chattr -i "$RESOLV_CONF"
    fi

    # Apply Google DNS
    echo -e "nameserver 8.8.8.8\nnameserver 8.8.4.4" | sudo tee "$RESOLV_CONF" > /dev/null

    # Make resolv.conf immutable again
    sudo chattr +i "$RESOLV_CONF"
    echo -e "${GREEN}[✓] DNS set to Google and file locked (immutable)${RESET}" | tee -a troubleshoot.log

    echo -e "${YELLOW}[i] Current DNS:${RESET}" | tee -a troubleshoot.log
    cat "$RESOLV_CONF" | tee -a troubleshoot.log

    # Flags list
    echo -e "\n${BLUE}=== Available Flags ===${RESET}"
    echo -e "${YELLOW}--dns-resolve${RESET}   : Set DNS to Google (8.8.8.8 / 8.8.4.4) and make it immutable"
    echo -e "${YELLOW}--dns-restore${RESET}   : Restore DNS from latest backup and make /etc/resolv.conf editable"
    echo -e "${YELLOW}--mtu${RESET}           : Perform MTU resolution to a target VM"
    echo -e "${YELLOW}--mtu-restore${RESET}   : Restore tun0 MTU to default (1500)"
    echo -e "${YELLOW}--setmtu${RESET}      : Interactively set MTU on tun0 (range 700–1500, adjust in steps of ±50"
    echo -e "${YELLOW}--killvpn${RESET}     : Kill all running OpenVPN processes"
    exit 0
fi

# ---- DNS Restore ----
if [[ "$1" == "--dns-restore" ]]; then
    separator
    RESOLV_CONF="/etc/resolv.conf"
    LATEST_BACKUP=$(ls -t /etc/resolv.conf.backup-* 2>/dev/null | head -1)

    if [[ -n "$LATEST_BACKUP" && -f "$LATEST_BACKUP" ]]; then
        echo -e "${YELLOW}[i] Restoring DNS from backup $LATEST_BACKUP${RESET}" | tee -a troubleshoot.log
        sudo chattr -i "$RESOLV_CONF" 2>> troubleshoot.log
        sudo cp "$LATEST_BACKUP" "$RESOLV_CONF" 2>> troubleshoot.log
        # keep file editable (do NOT lock with +i)
        echo -e "${GREEN}[✓] DNS restored successfully! File remains editable${RESET}" | tee -a troubleshoot.log
    else
        echo -e "${RED}[x] No DNS backup found! Run --dns-resolve first.${RESET}" | tee -a troubleshoot.log
    fi

    # Flags list
    echo -e "\n${BLUE}=== Available Flags ===${RESET}"
    echo -e "${YELLOW}--dns-resolve${RESET}   : Set DNS to Google (8.8.8.8 / 8.8.4.4) and make it immutable"
    echo -e "${YELLOW}--dns-restore${RESET}   : Restore DNS from latest backup and make /etc/resolv.conf editable"
    echo -e "${YELLOW}--mtu${RESET}           : Perform MTU resolution to a target VM"
    echo -e "${YELLOW}--mtu-restore${RESET}   : Restore tun0 MTU to default (1500)"
    echo -e "${YELLOW}--setmtu${RESET}      : Interactively set MTU on tun0 (range 700–1500, adjust in steps of ±50)"
    echo -e "${YELLOW}--killvpn${RESET}     : Kill all running OpenVPN processes"
    exit 0
fi

# ---- MTU Resolver ----
if [[ "$1" == "--mtu" ]]; then
    separator
    read -p "Machine's IP address: " TARGET_IP

    if [[ -z $TARGET_IP ]]; then
        echo "Please enter the target machine's IP address."
        exit 1
    fi

    echo -e "${CYAN}[i] Looking for the best MTU...${RESET}"
    echo -e "\n[i] MTU Discovery for $TARGET_IP" >> "$LOGFILE"

    (
        MTU=1500
        MIN_MTU=700

        # Step 1: Decrease until a working MTU is found or hit minimum
        while ! ping -M do -s $((MTU - 28)) -c 1 "$TARGET_IP" &>/dev/null; do
            MTU=$((MTU - 10))
            if (( MTU < MIN_MTU )); then
                echo "__FAIL__"
                exit 1
            fi
        done

        # Step 2: Fine-tune upwards until it fails
        while ping -M do -s $((MTU - 28)) -c 1 "$TARGET_IP" &>/dev/null; do
            MTU=$((MTU + 1))
        done
        MTU=$((MTU - 1))

        echo "$MTU" > /tmp/mtu_result.$$
    ) &

    pid=$!
    spinner $pid
    wait $pid
    echo -e "${GREEN}[✔] Done${RESET}"

    # Get result
    if [[ -f /tmp/mtu_result.$$ ]]; then
        BEST_MTU=$(cat /tmp/mtu_result.$$)
        rm -f /tmp/mtu_result.$$
        echo -e "\n${GREEN}[✓] Suitable MTU found: $BEST_MTU${RESET}"
        echo -e "${GREEN}[✓] Your tun0 MTU is now set to $BEST_MTU${RESET}" | tee -a "$LOGFILE"
        sudo ip link set dev tun0 mtu "$BEST_MTU"
    else
        echo -e "\n${RED}[x] No suitable MTU found. Host may be unreachable.${RESET}"
        echo -e "\N[x] No suitable MTU found. Host may be unreachable." | tee -a "$LOGFILE"
    fi
    echo -e "\n${BLUE}=== Available Flags ===${RESET}"
    echo -e "${YELLOW}--dns-resolve${RESET}   : Set DNS to Google (8.8.8.8 / 8.8.4.4) and make it immutable"
    echo -e "${YELLOW}--dns-restore${RESET}   : Restore DNS from latest backup and make /etc/resolv.conf editable"
    echo -e "${YELLOW}--mtu${RESET}           : Perform MTU resolution to a target VM"
    echo -e "${YELLOW}--mtu-restore${RESET}   : Restore tun0 MTU to default (1500)"
    echo -e "${YELLOW}--setmtu${RESET}      : Interactively set MTU on tun0 (range 700–1500, adjust in steps of ±50)"
    echo -e "${YELLOW}--killvpn${RESET}     : Kill all running OpenVPN processes"
    exit 0
fi




# ---- MTU Restore ----
if [[ "$1" == "--mtu-restore" ]]; then
    separator
    echo -e "${YELLOW}[i] Restoring tun0 MTU to default (1500)...${RESET}" | tee -a troubleshoot.log

    if ip link show tun0 &>/dev/null; then
        sudo ip link set dev tun0 mtu 1500
        if [[ $? -eq 0 ]]; then
            echo -e "${GREEN}[✓] tun0 MTU restored to 1500${RESET}" | tee -a troubleshoot.log
        else
            echo -e "${RED}[x] Failed to restore MTU for tun0${RESET}" | tee -a troubleshoot.log
        fi
    else
        echo -e "${RED}[x] tun0 interface not found!${RESET}" | tee -a troubleshoot.log
    fi

    echo -e "\n${BLUE}=== Available Flags ===${RESET}"
    echo -e "${YELLOW}--dns-resolve${RESET}   : Set DNS to Google (8.8.8.8 / 8.8.4.4) and make it immutable"
    echo -e "${YELLOW}--dns-restore${RESET}   : Restore DNS from latest backup and make /etc/resolv.conf editable"
    echo -e "${YELLOW}--mtu${RESET}           : Perform MTU resolution to a target VM"
    echo -e "${YELLOW}--mtu-restore${RESET}   : Restore tun0 MTU to default (1500)"
    echo -e "${YELLOW}--setmtu${RESET}      : Interactively set MTU on tun0 (range 700–1500, adjust in steps of ±50)"
    echo -e "${YELLOW}--killvpn${RESET}     : Kill all running OpenVPN processes"
    exit 0
fi

# ---- Interactive MTU Setter ----
if [[ "$1" == "--setmtu" ]]; then
    separator
    echo -e "${YELLOW}[i] Interactive MTU Setter (tun0)${RESET}" | tee -a troubleshoot.log

    # Ensure tun0 exists
    if ! ip link show tun0 &>/dev/null; then
        echo -e "${RED}[x] tun0 interface not found. Connect VPN first.${RESET}" | tee -a troubleshoot.log
        exit 1
    fi

    # Ask user for initial MTU
    while true; do
        read -rp "Enter initial MTU value (700-1500, must be divisible by 100): " INIT_MTU
        if [[ "$INIT_MTU" =~ ^[0-9]+$ ]] && (( INIT_MTU >= 700 && INIT_MTU <= 1500 )) && (( INIT_MTU % 100 == 0 )); then
            sudo ip link set dev tun0 mtu "$INIT_MTU"
            if [[ $? -eq 0 ]]; then
                echo -e "${GREEN}[✓] MTU set to $INIT_MTU on tun0${RESET}" | tee -a troubleshoot.log
                CURRENT_MTU=$INIT_MTU
                break
            else
                echo -e "${RED}[x] Failed to set MTU on tun0. Try again.${RESET}" | tee -a troubleshoot.log
            fi
        else
            echo -e "${RED}[x] Invalid MTU. Must be 700-1500 and divisible by 100.${RESET}"
        fi
    done

    # Adjustment loop
    while true; do
        echo -e "\n${YELLOW}[i] Current MTU on tun0: $CURRENT_MTU${RESET}"
        echo "Choose an option:"
        echo "1) Increase MTU by 50"
        echo "2) Decrease MTU by 50"
        echo "3) Done (apply and exit)"
        read -rp "Selection: " CHOICE

        case $CHOICE in
            1)
                NEW_MTU=$((CURRENT_MTU + 50))
                if (( NEW_MTU > 1500 )); then
                    echo -e "${RED}[x] Cannot increase above 1500.${RESET}"
                else
                    sudo ip link set dev tun0 mtu "$NEW_MTU"
                    if [[ $? -eq 0 ]]; then
                        echo -e "${GREEN}[✓] MTU increased to $NEW_MTU${RESET}" | tee -a troubleshoot.log
                        CURRENT_MTU=$NEW_MTU
                    else
                        echo -e "${RED}[x] Failed to update MTU.${RESET}" | tee -a troubleshoot.log
                    fi
                fi
                ;;
            2)
                NEW_MTU=$((CURRENT_MTU - 50))
                if (( NEW_MTU < 700 )); then
                    echo -e "${RED}[x] Cannot decrease below 700.${RESET}"
                else
                    sudo ip link set dev tun0 mtu "$NEW_MTU"
                    if [[ $? -eq 0 ]]; then
                        echo -e "${GREEN}[✓] MTU decreased to $NEW_MTU${RESET}" | tee -a troubleshoot.log
                        CURRENT_MTU=$NEW_MTU
                    else
                        echo -e "${RED}[x] Failed to update MTU.${RESET}" | tee -a troubleshoot.log
                    fi
                fi
                ;;
            3)
                echo -e "${YELLOW}[i] Final MTU on tun0: $CURRENT_MTU${RESET}" | tee -a troubleshoot.log
                echo -e "${GREEN}[✓] MTU finalized to $CURRENT_MTU${RESET}" | tee -a troubleshoot.log
                break
                ;;
            *)
                echo -e "${RED}[x] Invalid selection. Choose 1, 2, or 3.${RESET}"
                ;;
        esac
    done
    echo -e "\n${BLUE}=== Available Flags ===${RESET}"
    echo -e "${YELLOW}--dns-resolve${RESET}   : Set DNS to Google (8.8.8.8 / 8.8.4.4) and make it immutable"
    echo -e "${YELLOW}--dns-restore${RESET}   : Restore DNS from latest backup and make /etc/resolv.conf editable"
    echo -e "${YELLOW}--mtu${RESET}           : Perform MTU resolution to a target VM"
    echo -e "${YELLOW}--mtu-restore${RESET}   : Restore tun0 MTU to default (1500)"
    echo -e "${YELLOW}--setmtu${RESET}      : Interactively set MTU on tun0 (range 700–1500, adjust in steps of ±50)"
    echo -e "${YELLOW}--killvpn${RESET}     : Kill all running OpenVPN processes"
    exit 0
fi

# ---- Kill VPN ----
if [[ "$1" == "--killvpn" ]]; then
    separator
    echo -e "${YELLOW}[i] Kill VPN Processes${RESET}" | tee -a troubleshoot.log

    # Find all OpenVPN processes
    OVPN_PIDS=$(ps -eo pid,cmd | grep "[o]penvpn" | awk '{print $1}')

    if [[ -n "$OVPN_PIDS" ]]; then
        echo -e "${YELLOW}[i] Found OpenVPN processes: $OVPN_PIDS${RESET}" | tee -a troubleshoot.log
        for PID in $OVPN_PIDS; do
            echo -e "${YELLOW}[i] Killing OpenVPN process PID: $PID...${RESET}" | tee -a troubleshoot.log
            sudo kill -9 "$PID"
            if [[ $? -eq 0 ]]; then
                echo -e "${GREEN}[✓] Killed PID: $PID${RESET}" | tee -a troubleshoot.log
            else
                echo -e "${RED}[x] Failed to kill PID: $PID${RESET}" | tee -a troubleshoot.log
            fi
        done
        echo -e "${GREEN}[✓] All detected OpenVPN processes killed.${RESET}" | tee -a troubleshoot.log
    else
        echo -e "${RED}[x] No running OpenVPN processes found.${RESET}" | tee -a troubleshoot.log
    fi

    echo -e "\n${BLUE}=== Available Flags ===${RESET}"
    echo -e "${YELLOW}--dns-resolve${RESET}   : Set DNS to Google (8.8.8.8 / 8.8.4.4) and make it immutable"
    echo -e "${YELLOW}--dns-restore${RESET}   : Restore DNS from latest backup and make /etc/resolv.conf editable"
    echo -e "${YELLOW}--mtu${RESET}           : Perform MTU resolution to a target VM"
    echo -e "${YELLOW}--mtu-restore${RESET}   : Restore tun0 MTU to default (1500)"
    echo -e "${YELLOW}--setmtu${RESET}      : Interactively set MTU on tun0 (range 700–1500, adjust in steps of ±50)"
    echo -e "${YELLOW}--killvpn${RESET}     : Kill all running OpenVPN processes"
    exit 0
fi



# === Help Menu ===
function show_help() {
    echo -e "\n${BLUE}=== Available Flags ===${RESET}"
    echo -e "${YELLOW}--dns-resolve${RESET}   : Set DNS to Google (8.8.8.8 / 8.8.4.4) and make it immutable"
    echo -e "${YELLOW}--dns-restore${RESET}   : Restore DNS from latest backup and make /etc/resolv.conf editable"
    echo -e "${YELLOW}--mtu${RESET}           : Perform MTU resolution to a target VM"
    echo -e "${YELLOW}--mtu-restore${RESET}   : Restore tun0 MTU to default (1500)"
    echo -e "${YELLOW}--setmtu${RESET}      : Interactively set MTU on tun0 (range 700–1500, adjust in steps of ±50)"
    echo -e "${YELLOW}--killvpn${RESET}     : Kill all running OpenVPN processes"
    echo -e "\n${BLUE}=== Help Menu ===${RESET}"
    echo -e "${YELLOW}--help / -h ${RESET}, ${YELLOW}-h${RESET}, ${YELLOW}man${RESET} : Show this help menu"
    exit 0
}

for arg in "$@"; do
    case $arg in
        --help|-h|man)
            show_help
            ;;
        *)
            echo -e "${RED}[!] Unknown option: $arg${RESET}"
            echo -e "Use ${YELLOW}--help${RESET}, ${YELLOW}-h${RESET}, or ${YELLOW}man${RESET} to see available options."
            exit 1
            ;;
    esac
done


############################System check#############

# ============================================
# 0. Get Username
# ============================================

LDAP="No active VPN"

# Run the logic in the background and redirect all output explicitly
(
  RUNNING_VPN=$(ps -eo cmd | grep "[o]penvpn" | grep -oE '[^ ]+\.ovpn' | head -n 1)

  if [ -n "$RUNNING_VPN" ]; then
      LATEST_FILE=$(find / -type f -iname "$RUNNING_VPN" -printf '%T@ %p\n' 2>/dev/null \
                    | sort -n | tail -1 | cut -d' ' -f2-)

      if [ -n "$LATEST_FILE" ] && ip a show tun0 &>/dev/null; then
          sed -n '/<cert>/,/<\/cert>/p' "$LATEST_FILE" | sed '1d;$d' \
          | openssl x509 -noout -subject 2>/dev/null \
          | sed 's/.*CN=\([^,]*\).*/\1/' > /tmp/ldap_result.txt
      else
          echo "No certificate found." > /tmp/ldap_result.txt
      fi
  else
      echo "No active VPN" > /tmp/ldap_result.txt
  fi
) &
pid=$!

spinner $pid
wait $pid

LDAP=$(< /tmp/ldap_result.txt)
rm -f /tmp/ldap_result.txt
##LDAP
echo -e "LDAP Username: $LDAP" >> "$LOGFILE"

# ============================================
# 1. User Info
# ============================================

echo -e "Username: $(whoami)" >> "$LOGFILE"
add_summary "${CYAN}$(format_summary "User" "$(whoami)")${RESET}"

# ============================================
# 2. Date
# ============================================
echo -e "\nDate: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOGFILE"
add_summary "${CYAN}$(format_summary "Date" "$(date '+%B %d, %Y %H:%M:%S')")${RESET}"

# ============================================
# 3. Virtual Machine Check
# ============================================
echo -e "\n\n==== Virtual Machine Check ====" >> "$LOGFILE"

if (dmidecode | grep -iq vmware); then
    echo -e "\nVM Check: VMware" >> "$LOGFILE"
    add_summary "${GREEN}$(format_summary "VM Check" "VMware")${RESET}"
elif (dmidecode | grep -iq virtualbox); then
    echo -e "\nVM Check: Virtualbox! We highly recommend you use Kali VM within the VMware. Check our guide: https://help.offensive-security.com/hc/en-us/articles/360049796792-Kali-Linux-Virtual-Machine" >> "$LOGFILE"
    add_summary "${ORANGE}$(format_summary "VM Check" "Virtualbox! We highly recommend you use Kali VM within the VMware. Check our guide: https://help.offensive-security.com/hc/en-us/articles/360049796792-Kali-Linux-Virtual-Machine")${RESET}"
else
    echo -e "\nVM Check: VM not detected! We highly recommend you use Kali VM within the VMware. Check our guide: https://help.offensive-security.com/hc/en-us/articles/360049796792-Kali-Linux-Virtual-Machine" >> "$LOGFILE"
    add_summary "${RED}$(format_summary "VM Check" "VM not detected! We highly recommend you use Kali VM within the VMware. Check our guide: https://help.offensive-security.com/hc/en-us/articles/360049796792-Kali-Linux-Virtual-Machine")${RESET}"
fi

# ============================================
# 4. VPN Status (Interfaces + OpenVPN Command)
# ============================================

# --- Check VPN Interfaces ---
TUN0_COUNT=$(ip -o link show | grep -Eo 'tun[0-9]+' | sort -u | wc -l)

echo -e "\n\n==== VPN Status ====" >> "$LOGFILE"

if [[ $TUN0_COUNT -eq 0 ]]; then
    echo -e "\nVPN Check: No VPN detected!" >> "$LOGFILE"
    add_summary "${ORANGE}$(format_summary "VPN Check" "No VPN detected!")${RESET}"
elif [[ $TUN0_COUNT -gt 1 ]]; then
    echo -e "\nVPN Check: Multiple VPNs connected!" >> "$LOGFILE"
    add_summary "${RED}$(format_summary "VPN Check" "Multiple VPNs connected!")${RESET}"
else
    echo -e "\nVPN Check: Connected!" >> "$LOGFILE"
    add_summary "${GREEN}$(format_summary "VPN Check" "Connected!")${RESET}"
fi

# ============================================
# 5. Network Interfaces
# ============================================
echo -e "\n\n==== Network Interface ====" >> "$LOGFILE"
ifconfig -a >> "$LOGFILE"
sleep 1.5 &
pid=$!
spinner $pid
wait $pid
echo -e "${GREEN}[✔] Network interfaces checked ${RESET}"

# ============================================
# 6. Network Routes
# ============================================
echo -e "\n\n==== Network Routes ====" >> "$LOGFILE"
ip route show >> "$LOGFILE"
sleep 1.5 &
pid=$!
spinner $pid
wait $pid
echo -e "${GREEN}[✔] Network routes checked ${RESET}"


# Find duplicate routes based on Destination|Genmask|Gateway|Iface
DUPLICATE_ROUTE=$(route -n \
  | awk 'NR>2 {print $1 "|" $3 "|" $2 "|" $8}' \
  | sort \
  | uniq -d)

if [ -n "$DUPLICATE_ROUTE" ]; then
    echo -e "\nDuplicate routes found:" >> "$LOGFILE"
    # print the duplicate entries (one per line)
    echo "$DUPLICATE_ROUTE" | while IFS= read -r line; do
        # replace '|' back to spaces for readability
        echo "  $line" | tr '|' ' ' >> "$LOGFILE"
    done
else
    echo -e "\nNo duplicate routes found :)" >> "$LOGFILE"
fi

# Find default route interface (skip headers)
IFACE=$(route -n | awk 'NR>2 && $1 == "0.0.0.0" && $4 ~ /G/ {print $8}')

if [ -z "$IFACE" ]; then
    echo "No default gateway/interface found" >> "$LOGFILE"
else
    # Check interface state safely
    if ip link show "$IFACE" 2>/dev/null | grep -q "state UP"; then
        echo -e "\nInterface $IFACE is up" >> "$LOGFILE"
    else
        echo -e "\nInterface $IFACE is down" >> "$LOGFILE"
    fi
fi

# ============================================
# 7. UDP Port Test (VPN 1194)
# ============================================
echo -e "\n\n==== UDP Port Test ====" >> "$LOGFILE"

VPN_SERVER="192.168.45.1"

if sudo nmap -sU -p 1194 "$VPN_SERVER" | grep -q "1194/udp open\|1194/udp open|filtered"; then
    echo -e "\nUDP 1194: Reachable" >> "$LOGFILE"
    add_summary "${GREEN}$(format_summary "UDP 1194" "Reachable")${RESET}"
else
    echo -e "\nUDP 1194: Unreachable" >> "$LOGFILE"
    add_summary "${RED}$(format_summary "UDP 1194" "Unreachable")${RESET}"
fi
sleep 1.5 &
pid=$!
spinner $pid
wait $pid
echo -e "${GREEN}[✔] Testing UDP Port ${RESET}"
# ============================================
# 8. Kernel Version
# ============================================
echo -e "\n\n==== Kernel Version ====" >> "$LOGFILE"
echo -e "\nKernel: $(uname -r)" >> "$LOGFILE"
add_summary "${CYAN}$(format_summary "Kernel" "$(uname -r)")${RESET}"

# ============================================
# 9. Operating System
# ============================================

echo -e "\n\n==== Operating System ====" >> "$LOGFILE"
lsb_release -a 2>/dev/null >> "$LOGFILE"
add_summary "${CYAN}$(format_summary "Operating System" "$(lsb_release -d | cut -f2)")${RESET}"

# ============================================
# 10. DNS Information
# ============================================
echo -e "\n\n==== DNS Information ====" >> "$LOGFILE"

if grep -q "8.8.8.8" /etc/resolv.conf; then
    echo -e "\nDNS Check: 8.8.8.8 configured" >> "$LOGFILE"
    add_summary "${GREEN}$(format_summary "DNS check" "8.8.8.8 DNS is set properly")${RESET}"
else
    echo -e "\n[x] Google DNS not set" >> "$LOGFILE"
    cat /etc/resolv.conf >> "$LOGFILE"
    
    add_summary "\n${ORANGE}$(format_summary "DNS check" "Not configured. We always recommend to use the Google DNS as your default DNS server.\nFor more information, please refer to the URL below.\nURL: https://help.offsec.com/hc/en-us/articles/360046293832#general-vpn-tips")\n${RESET}"
fi

# ============================================
# 11. Ping Test 8.8.8.8 and Google
# ============================================
echo -e "\n\n==== Ping Test 8.8.8.8 and Google ====" >> "$LOGFILE"
# Ping 8.8.8.8
echo -e "${CYAN}\n\n[i] Ping Test (External: 8.8.8.8)${RESET}"
echo -e "\n\n[i] Ping Test (External: 8.8.8.8)" >> "$LOGFILE"
ping -c 20 8.8.8.8 2>&1 | tee -a "$LOGFILE" > ping_tmp.log &
pid=$!
spinner $pid
wait $pid
echo -e "${GREEN}[✔] Done${RESET}"

PING_OUTPUT=$(cat ping_tmp.log)

if [[ $? -ne 0 ]]; then
    echo -e "\nPinging 8.8.8.8: Failed" >> "$LOGFILE"
    add_summary "${RED}$(format_summary "Pinging 8.8.8.8" "Failed!")${RESET}"
else
  PACKET_LOSS=$(echo "$PING_OUTPUT" | grep -oP '\d+(?=% packet loss)')
  AVG_PING=$(echo "$PING_OUTPUT" | grep "rtt min/avg" | awk -F'/' '{print $5}')

  [[ -z "$PACKET_LOSS" ]] && PACKET_LOSS=100
  [[ -z "$AVG_PING" ]] && AVG_PING=9999

  ## Round off ping
  AVG_PING_INT=$(printf "%.0f" "$AVG_PING")

  if [[ $AVG_PING_INT -lt 99 ]]; then
    add_summary "${GREEN}$(format_summary "Pinging 8.8.8.8" "(Avg ${AVG_PING} ms, ${PACKET_LOSS}% loss")${RESET}"
  elif [[ $AVG_PING_INT -ge 100 && $AVG_PING_INT -lt 200 ]]; then
    add_summary "${ORANGE}\n$(format_summary "Pinging 8.8.8.8" "$(printf '%b' "(Avg ${AVG_PING} ms, ${PACKET_LOSS}%% loss)\nYour latency may cause issues when using the VPN.\nPlease consider using Kali-in-Browser.\nURL: https://help.offsec.com/hc/en-us/articles/9550819362964-Connectivity-Guide#h_01J4S77TGKA3EFJNXG66MDA4ZS${RESET}")")\n"

  else
    add_summary "${RED}\n$(format_summary "Pinging 8.8.8.8" "$(printf '%b' "(Avg ${AVG_PING} ms, ${PACKET_LOSS}%% loss)\nYour latency may cause issues when using the VPN.\nPlease consider using Kali-in-Browser.\nURL: https://help.offsec.com/hc/en-us/articles/9550819362964-Connectivity-Guide#h_01J4S77TGKA3EFJNXG66MDA4ZS${RESET}")")\n"
  fi
fi

# Ping google.com
echo -e "${CYAN}\n\n[i] Ping Test (External: www.google.com${RESET}"
echo -e "\n\n[i] Ping Test (External: www.google.com)" >> "$LOGFILE"
ping -c 20 google.com 2>&1 | tee -a "$LOGFILE" > ping_tmp.log &
pid=$!
spinner $pid
wait $pid
echo -e "${GREEN}[✔] Done${RESET}"

PING_OUTPUT=$(cat ping_tmp.log)

if [[ $? -ne 0 ]]; then
    echo -e "\nPinging google.com: Failed" >> "$LOGFILE"
    add_summary "${RED}$(format_summary "Pinging google.com" "Failed")${RESET}"
else
  PACKET_LOSS=$(echo "$PING_OUTPUT" | grep -oP '\d+(?=% packet loss)')
  AVG_PING=$(echo "$PING_OUTPUT" | grep "rtt min/avg" | awk -F'/' '{print $5}')

  [[ -z "$PACKET_LOSS" ]] && PACKET_LOSS=100
  [[ -z "$AVG_PING" ]] && AVG_PING=9999

  ## Round off ping
  AVG_PING_INT=$(printf "%.0f" "$AVG_PING")

  if [[ $AVG_PING_INT -lt 100 ]]; then
    add_summary "${GREEN}$(format_summary "Pinging google.com" "(Avg ${AVG_PING} ms, ${PACKET_LOSS}% loss")${RESET}"
  elif [[ $AVG_PING_INT -ge 100 && $AVG_PING_INT -lt 200 ]]; then
    add_summary "${ORANGE}\n$(format_summary "Pinging google.com" "$(printf '%b' "(Avg ${AVG_PING} ms, ${PACKET_LOSS}%% loss)\nYour latency may cause issues when using the VPN.\nPlease consider using Kali-in-Browser.\nURL: https://help.offsec.com/hc/en-us/articles/360055974671-What-is-in-browser-Kali-Linux${RESET}")")\n"
  else
    add_summary "${RED}\n$(format_summary "Pinging google.com" "$(printf '%b' "(Avg ${AVG_PING} ms, ${PACKET_LOSS}%% loss)\nYour latency may cause issues when using the VPN.\nPlease consider using Kali-in-Browser.\nURL: https://help.offsec.com/hc/en-us/articles/360055974671-What-is-in-browser-Kali-Linux${RESET}")")\n"
  fi
fi

# ============================================
# 12. External IP & Location
# ============================================
echo -e "\n\n==== External IP & Location ====" >> "$LOGFILE"

echo -e "\n\n${CYAN}[i] Fetching external IP${RESET}"

# Run curl in background and capture to temp file
curl -sS -m 20 http://ipinfo.io/ip > external_ip.tmp &
pid=$!
spinner $pid
wait $pid
echo -e "${GREEN}[✔] Done${RESET}"

EXTERNAL_IP=$(cat external_ip.tmp)
rm -f external_ip.tmp

if [[ -z "$EXTERNAL_IP" ]]; then
    echo -e "\n${RED}[x] Failed to retrieve external IP. Check your connection.${RESET}"
    echo -e "\n[!] Failed to retrieve external IP. Check your connection." >> "$LOGFILE"
    add_summary "${RED}$(format_summary "External IP" "Not found!")${RESET}"
else
    sleep 1.5s

    # === Fetch IP security info ===
    RESPONSE=$(curl -s "https://proxycheck.io/v3/$EXTERNAL_IP")
    
    PROXY=$(echo "$RESPONSE" | grep -o '"proxy":[^,]*' | head -1 | sed 's/"proxy"://;s/[[:space:]]//g')
    VPN=$(echo "$RESPONSE" | grep -o '"vpn":[^,]*' | head -1 | sed 's/"vpn"://;s/[[:space:]]//g')
    COUNTRY=$(printf '%s\n' "$RESPONSE" | awk -F'"' '/"country_name"/{print $4; exit}')
    REGION=$(printf '%s\n' "$RESPONSE" | awk -F'"' '/"region_name":/ {print $4; exit}')
    HOSTING=$(echo "$RESPONSE" | grep -o '"hosting":[^,]*' | head -1 | sed 's/"hosting"://;s/[[:space:]]//g')

    # Find line number where "operator" first appears
    start_line=$(printf '%s\n' "$RESPONSE" | grep -n '"operator"' | head -n1 | cut -d: -f1)

    if [ -n "$start_line" ]; then
        # Grab a chunk of lines starting at start_line (200 lines should be plenty)
        OPERATOR_BLOCK=$(printf '%s\n' "$RESPONSE" | tail -n +"$start_line" | head -n 200)

        # Extract name (last "name" inside block) and url (first "url" inside block)
        OPERATOR_NAME=$(printf '%s\n' "$OPERATOR_BLOCK" \
            | grep -oE '"name"[[:space:]]*:[[:space:]]*"[^"]*"' \
            | tail -n1 \
            | sed -E 's/.*:[[:space:]]*"([^"]*)".*/\1/')

        # Defensive defaults
        OPERATOR_NAME=${OPERATOR_NAME:-N/A}
    else
        # operator not found
        OPERATOR_NAME="No thrid-party VPN detected!"
    fi

    add_summary "${CYAN}$(format_summary "IP Address" "$EXTERNAL_IP")${RESET}"
    add_summary "${CYAN}$(format_summary "Country" "$COUNTRY")${RESET}"

    if [ -z "$REGION" ]; then
        add_summary "${RED}$(format_summary "Region" "N/A")${RESET}"
    else
        add_summary "${CYAN}$(format_summary "Region" "$REGION")${RESET}"
    fi 
    
fi
# Extract additional info

# === Safeguard for Firewall Countries ===
FIREWALL_COUNTRIES=("Singapore", "Egypt" "Russia" "China" "Iran" "UAE" "Turkey" "North Korea" "Turkmenistan" "Uzbekistan" "Saudi Arabia" "United Arab Emirates" "United Arab Emirates (UAE)" "Ethiopia" "Belarus" "Myanmar" "Oman" "Qatar" "Pakistan")

if [[ " ${FIREWALL_COUNTRIES[@]} " =~ " ${COUNTRY} " ]]; then
    add_summary "${RED}\n$(format_summary "Firewall check" "Your country has blocks in place that may cause issues when using the VPN. \nPlease note that many of our students have experienced connectivity difficulty when connecting from $(printf '%b' "${COUNTRY}\ndue to the country-wide firewalls in place as warned during the registration process.${RESET}")")\n"
else
    add_summary "${GREEN}$(format_summary "Firewall check" "All good. Your VPN connection should work normally.")${RESET}"
fi

# Display Region & Flags
if [[ -z "$RESPONSE" ]]; then
    echo -e "\n${RED}[!] Failed to retrieve region. Check your connection.${RESET}"
    echo -e "\n[!] Failed to retrieve region. Check your connection." >> "$LOGFILE"
else
    # Third-party VPN
    if [[ "$VPN" == "true" ]]; then
        {
            echo -e "\nThird-party VPN: Detected!" >> "$LOGFILE"
            echo -e "\VPN Application: $OPERATOR_NAME" >> "$LOGFILE"
            add_summary "${RED}$(format_summary "Third-party VPN" "Detected!")${RESET}"
            add_summary "${RED}$(format_summary "VPN Application" "$OPERATOR_NAME")${RESET}"
        }
    else
        {
            echo -e "\nThird-party VPN: None" >> "$LOGFILE"
            add_summary "${GREEN}$(format_summary "Third-party VPN" "None")${RESET}"
        }
    fi

    # VPS/Cloud
    if [[ "$HOSTING" == "true" ]]; then
        {
            echo -e "\nVPS/Cloud: Detected!" >> "$LOGFILE"
            add_summary "${RED}$(format_summary "VPS/Cloud" "Detected!")${RESET}"
        }
    else
        {
            echo -e "\nVPS/Cloud: None" >> "$LOGFILE"
            add_summary "${GREEN}$(format_summary "VPS/Cloud" "None")${RESET}"
        }
    fi

fi

# Check proxy
if [[ -z "$RESPONSE" ]]; then
    echo -e "\n${RED}[!] Failed to check proxy. Check your connection.${RESET}"
    echo -e "\n[!] Failed to check proxy. Check your connection." >> "$LOGFILE"
    add_summary "${RED}$(format_summary "Check proxy" "Failed to check proxy. Check your internet connection.")${RESET}"
elif [[ $IS_PROXY == "true" ]]; then
    echo -e "\nProxy check: Your connection is using a proxy which may cause issues when using the VPN." >> "$LOGFILE"
    add_summary "${RED}$(format_summary "Proxy check" "Your connection is using a proxy which may cause issues when using the VPN.")${RESET}"
else
    echo -e "\nProxy check: No proxies detected" >> "$LOGFILE"
    add_summary "${GREEN}$(format_summary "Proxy check" "No proxies detected")${RESET}"
fi


# ============================================
# Final Summary
# ============================================
echo -e "\n\n==== Informative summary ====" >> "$LOGFILE"
echo -e "${CYAN}\n\n==== Informative summary ====${RESET}\n"

BAD_FOUND=0

for entry in "${SUMMARY[@]}"; do
    if [[ "$entry" == *"$GREEN"* ]]; then
        log "$entry"
    elif [[ "$entry" == *"$RED"* ]]; then
        log "$entry"
        BAD_FOUND=1
    else
        log "$entry"
    fi
done

echo -e "\n\n==== Final result ====" >> "$LOGFILE"
echo -e "${CYAN}\n\n==== Final result ====${RESET}\n"
# Final banner
if [[ $BAD_FOUND -eq 0 ]]; then
    echo -e "\n\n[✓] All checks passed – system looks good!" >> "$LOGFILE"
    echo -e "${GREEN}[✓] All checks passed – system looks good!${RESET}"
else
    echo -e "[x] Issues detected – please review the summary above." >> "$LOGFILE"
    echo -e "${RED}\n[x] Issues detected – please review the summary above.${RESET}"
fi

echo -e "${CYAN}\nYou may run troubleshooting script with -h or --help to check for more feature.${RESET}"

## remove those temporary files ##
rm -rf response.json
rm -rf vpn_check.json
rm -rf ping_tmp.log
rm -rf LOGFILE
## Notice
echo -e "\n\n${CYAN}[+] Scan completed.${RESET}\n\n"
echo -e "${CYAN}[+] Should you experience any connectivity issues, please provided us with the following:\n${RESET}"
echo -e "    - ${BOLD}${CYAN}troubleshoot.log ${RESET}"
echo -e "    - ${BOLD}${CYAN}OpenVPN connection window ${RESET}"
echo -e "    - ${BOLD}${CYAN}OSID ${RESET}"

