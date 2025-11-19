#!/bin/bash

# ==============================================================================
# SahraBot Setup & Management Script
# Author: Gemini & BiMaghz
# ==============================================================================

PROJECT_NAME="sahrabot"
PROJECT_DIR="/opt/$PROJECT_NAME"
COMMAND_NAME="${PROJECT_NAME}"
REPO_URL="https://github.com/BiMaghz/SahraBot.git"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

strip_quotes() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  s="${s%\"}"
  s="${s#\"}"
  s="${s%\'}"
  s="${s#\'}"
  echo "$s"
}

_check_docker() {
    if ! command -v docker &>/dev/null; then
        echo -e "${YELLOW}Docker not found. Installing Docker...${NC}"
        sudo curl -fsSL https://get.docker.com | sh
        echo -e "${GREEN}Docker installed successfully.${NC}"
    else
        echo -e "${GREEN}Docker is already installed.${NC}"
    fi
}

_set_env_var() {
    local key="$1"
    local val="$2"
    mkdir -p "$PROJECT_DIR"
    if [ ! -f "$PROJECT_DIR/.env" ]; then
        echo "$key=\"$val\"" > "$PROJECT_DIR/.env"
        sudo chown "${SUDO_USER:-$USER}":"${SUDO_USER:-$USER}" "$PROJECT_DIR/.env"
    else
        if grep -qE "^${key}=" "$PROJECT_DIR/.env"; then
            sudo sed -i "s|^${key}=.*|${key}=\"${val}\"|" "$PROJECT_DIR/.env"
        else
            echo "${key}=\"${val}\"" | sudo tee -a "$PROJECT_DIR/.env" >/dev/null
        fi
    fi
}

_prompt_for_env() {
    echo -e "\n--- Core Configuration (.env) ---"
    read -p "Enter your Bot Token: " BOT_TOKEN

    while true; do
        read -p "Enter your Marzneshin Panel URL (e.g., https://panel.example.com): " PANEL_URL

        PANEL_URL=$(echo "$PANEL_URL" | sed -E 's#(https?://[^/]+).*#\1#')
        PANEL_URL=$(echo "$PANEL_URL" | sed 's#/$##')

        if [[ $PANEL_URL =~ ^https?:// ]]; then
            break
        else
            echo -e "${RED}Invalid URL. Please include http:// or https://${NC}"
        fi
    done

    echo -e "\n--- Webhook Configuration ---"
    read -p "Do you want to enable webhook notifications? (y/N): " ENABLE_WEBHOOK
    
    local webhook_address="0.0.0.0"
    local webhook_port="9090"
    local webhook_secret="please_change_this_secret"
    local enable_webhook_flag=False

    if [[ $ENABLE_WEBHOOK =~ ^[Yy]$ ]]; then
        enable_webhook_flag=True
        read -p "Enter Webhook Listen Address (default: 0.0.0.0): " webhook_address_input
        if [ ! -z "$webhook_address_input" ]; then
            webhook_address=$webhook_address_input
        fi
        
        read -p "Enter Webhook Listen Port: " webhook_port_input
        if [ ! -z "$webhook_port_input" ]; then
            webhook_port=$webhook_port_input
        fi
        
        read -p "Enter Webhook Secret Token: " webhook_secret
    fi

    {
        echo "BOT_TOKEN=\"$BOT_TOKEN\""
        echo "PANEL_URL=\"$PANEL_URL\""
        echo ""
        echo "# --- Optional Webhook Settings ---"
        echo "ENABLE_WEBHOOK=$enable_webhook_flag"
        echo "WEBHOOK_ADDRESS=\"$webhook_address\""
        echo "WEBHOOK_PORT=\"$webhook_port\""
        echo "WEBHOOK_SECRET=\"$webhook_secret\""
    } > "$PROJECT_DIR/.env"
    
    echo -e "${GREEN}.env file created/updated successfully.${NC}"
}

_load_admins() {
    usernames=()
    passwords=()
    chatids=()
    if [ ! -f "$PROJECT_DIR/config.yml" ]; then
        return
    fi
    local idx=-1
    while IFS= read -r line || [ -n "$line" ]; do
        if [[ $line =~ ^[[:space:]]*-\ panel_username:[[:space:]]*(.*) ]]; then
            val="${BASH_REMATCH[1]}"
            val=$(strip_quotes "$val")
            usernames+=("$val")
            passwords+=("")
            chatids+=("")
            idx=$(( ${#usernames[@]} - 1 ))
        elif [[ $line =~ ^[[:space:]]*panel_password:[[:space:]]*(.*) ]]; then
            val="${BASH_REMATCH[1]}"
            val=$(strip_quotes "$val")
            if [ "$idx" -ge 0 ]; then
                passwords[$idx]="$val"
            fi
        elif [[ $line =~ ^[[:space:]]*chat_ids:[[:space:]]*(.*) ]]; then
            val="${BASH_REMATCH[1]}"
            val=$(strip_quotes "$val")
            if [ "$idx" -ge 0 ]; then
                chatids[$idx]="$val"
            fi
        fi
    done < "$PROJECT_DIR/config.yml"
}

_save_admins() {
    mkdir -p "$PROJECT_DIR"
    {
        echo "# Admin configurations"
        echo "admin_config:"
        for i in "${!usernames[@]}"; do
            u="${usernames[$i]}"
            p="${passwords[$i]}"
            c="${chatids[$i]}"
            if [[ -z "$c" ]]; then
                c="[]"
            else
                if [[ ! "$c" =~ ^\[[[:space:]]*.*\]$ ]]; then
                    c=$(echo "$c" | sed 's/[[:space:]]//g')
                    c="[$c]"
                fi
            fi
            echo "  - panel_username: \"$u\""
            echo "    panel_password: \"$p\""
            echo "    chat_ids: $c"
        done
    } > "$PROJECT_DIR/config.yml"
    sudo chown "${SUDO_USER:-$USER}":"${SUDO_USER:-$USER}" "$PROJECT_DIR/config.yml"
}

_prompt_for_yml() {
    echo -e "\n--- Admin Configuration (config.yml) ---"
    while true; do
        read -p "How many admin groups do you want to configure? " ADMIN_COUNT
        if [[ $ADMIN_COUNT =~ ^[0-9]+$ ]] && [ "$ADMIN_COUNT" -ge 0 ]; then
            break
        else
            echo -e "${RED}Please enter a valid number (0 or greater).${NC}"
        fi
    done
    usernames=()
    passwords=()
    chatids=()
    for i in $(seq 1 $ADMIN_COUNT); do
        echo "--- Configuring Admin Group #$i ---"
        read -p "  Panel Username for this group: " PANEL_USERNAME
        read -s -p "  Panel Password for this group: " PANEL_PASSWORD
        echo
        read -p "  Telegram Chat ID(s) for this group (comma-separated): " CHAT_IDS
        usernames+=("$PANEL_USERNAME")
        passwords+=("$PANEL_PASSWORD")
        chatids+=("$CHAT_IDS")
    done
    _save_admins
    echo -e "${GREEN}config.yml created/updated successfully.${NC}"
}

_start_bot() {
    echo -e "${YELLOW}Building and starting bot containers...${NC}"
    sudo docker compose -f "$PROJECT_DIR/docker-compose.yml" up --build -d
    sudo docker image prune -f
    echo -e "${GREEN}Bot is running in the background! Use '${COMMAND_NAME}' then 'View Logs' to see logs.${NC}"
}

install_bot() {
    echo -e "${GREEN}Welcome to SahraBot Installer!${NC}"
    _check_docker
    echo -e "${YELLOW}Creating project directory at '$PROJECT_DIR'...${NC}"
    sudo mkdir -p "$PROJECT_DIR"
    sudo chown -R "${SUDO_USER:-$USER}":"${SUDO_USER:-$USER}" "$PROJECT_DIR"
    if [ ! -d "$PROJECT_DIR/.git" ]; then
        echo -e "${YELLOW}Cloning project repository...${NC}"
        git clone "$REPO_URL" "$PROJECT_DIR"
    else
        echo -e "${YELLOW}Repository exists. Pulling latest changes...${NC}"
        cd "$PROJECT_DIR" && git pull
    fi

    sudo rm -f "$PROJECT_DIR/.env.example" "$PROJECT_DIR/config.yml.example" "$PROJECT_DIR/LICENSE" "$PROJECT_DIR/README.md"

    cd "$PROJECT_DIR" || exit 1
    _prompt_for_env
    _prompt_for_yml
    _start_bot
    echo -e "${YELLOW}Installing management command to /usr/local/bin/${COMMAND_NAME}...${NC}"
    sudo mv "$PROJECT_DIR/setup.sh" "/usr/local/bin/${COMMAND_NAME}"
    sudo chmod +x "/usr/local/bin/${COMMAND_NAME}"
    echo -e "\n${GREEN}Installation Complete!${NC}"
    echo -e "Manage your bot with: ${YELLOW}${COMMAND_NAME}${NC}"
}

_manage_admins() {
    while true; do
        clear
        echo -e "${GREEN}--- Current Admin Groups ---${NC}"
        _load_admins
        if [ "${#usernames[@]}" -eq 0 ]; then
            echo "No admin groups configured."
        else
            for i in "${!usernames[@]}"; do
                idx=$((i+1))
                u="${usernames[$i]}"
                c="${chatids[$i]}"
                if [[ -z "$c" ]]; then
                    c="[]"
                fi
                printf "%d) Username: %s, ChatIDs: %s\n" "$idx" "$u" "$c"
            done
        fi
        echo
        echo "Options:"
        echo "1) Add Admin Group"
        echo "2) Edit Admin Group"
        echo "3) Delete Admin Group"
        echo "4) Back"
        read -p "Choose an option [1-4]: " choice
        case "$choice" in
            1)
                read -p "Panel Username: " PANEL_USERNAME
                read -s -p "Panel Password: " PANEL_PASSWORD
                echo
                read -p "Telegram Chat ID(s) (comma-separated): " CHAT_IDS
                usernames+=("$PANEL_USERNAME")
                passwords+=("$PANEL_PASSWORD")
                chatids+=("$CHAT_IDS")
                _save_admins
                echo -e "${GREEN}Admin group added.${NC}"
                sudo docker compose down
                sudo docker compose up --build -d
                sudo docker image prune -f
                sleep 1
                ;;
            2)
                if [ "${#usernames[@]}" -eq 0 ]; then
                    echo -e "${YELLOW}No admin groups to edit.${NC}"
                    sleep 1
                    continue
                fi
                read -p "Enter admin number to edit: " num
                if ! [[ "$num" =~ ^[0-9]+$ ]]; then
                    echo -e "${RED}Invalid number.${NC}"
                    sleep 1
                    continue
                fi
                if [ "$num" -lt 1 ] || [ "$num" -gt "${#usernames[@]}" ]; then
                    echo -e "${RED}Number out of range.${NC}"
                    sleep 1
                    continue
                fi
                idx=$((num-1))
                cur_u="${usernames[$idx]}"
                cur_p="${passwords[$idx]}"
                cur_c="${chatids[$idx]}"
                if [[ -z "$cur_c" ]]; then cur_c="[]"; fi
                read -p "New Panel Username (leave empty to keep '$cur_u'): " newu
                read -s -p "New Panel Password (leave empty to keep current): " newp
                echo
                read -p "New Telegram Chat ID(s) (comma-separated) (leave empty to keep '$cur_c'): " newc
                if [[ -n "$newu" ]]; then usernames[$idx]="$newu"; fi
                if [[ -n "$newp" ]]; then passwords[$idx]="$newp"; fi
                if [[ -n "$newc" ]]; then chatids[$idx]="$newc"; fi
                _save_admins
                echo -e "${GREEN}Admin group updated.${NC}"
                sudo docker compose down
                sudo docker compose up --build -d
                sudo docker image prune -f
                sleep 1
                ;;
            3)
                if [ "${#usernames[@]}" -eq 0 ]; then
                    echo -e "${YELLOW}No admin groups to delete.${NC}"
                    sleep 1
                    continue
                fi
                read -p "Enter admin number to delete: " numdel
                if ! [[ "$numdel" =~ ^[0-9]+$ ]]; then
                    echo -e "${RED}Invalid number.${NC}"
                    sleep 1
                    continue
                fi
                if [ "$numdel" -lt 1 ] || [ "$numdel" -gt "${#usernames[@]}" ]; then
                    echo -e "${RED}Number out of range.${NC}"
                    sleep 1
                    continue
                fi
                idxdel=$((numdel-1))
                read -p "Are you sure you want to delete admin #$numdel (${usernames[$idxdel]})? [y/N]: " confirm
                if [[ $confirm =~ ^[Yy]$ ]]; then
                    unset 'usernames[idxdel]'
                    unset 'passwords[idxdel]'
                    unset 'chatids[idxdel]'
                    usernames=("${usernames[@]}")
                    passwords=("${passwords[@]}")
                    chatids=("${chatids[@]}")
                    _save_admins
                    echo -e "${GREEN}Admin group deleted.${NC}"
                    sudo docker compose down
                    sudo docker compose up --build -d
                    sudo docker image prune -f
                else
                    echo "Delete cancelled."
                fi
                sleep 1
                ;;
            4)
                break
                ;;
            *)
                echo -e "${RED}Invalid option.${NC}"
                sleep 1
                ;;
        esac
    done
}

show_management_menu() {
    cd "$PROJECT_DIR" || { echo -e "${RED}Error: Project directory '$PROJECT_DIR' not found.${NC}"; return 1; }
    while true; do
        clear
        echo -e "\n${GREEN}┌───────────────────────────┐${NC}"
        echo -e "${GREEN}│  SahraBot Management Menu │${NC}"
        echo -e "${GREEN}└───────────────────────────┘${NC}"
        PS3="Please enter your choice: "
        options=(
            "Edit Telegram Token"
            "Edit Panel URL"
            "Manage Admin Groups"
            "Edit Notification Settings"
            "Restart Bot"
            "View Logs"
            "Update Bot"
            "Uninstall Bot"
            "Quit"
        )
        select opt in "${options[@]}"; do
            case $opt in
                "Edit Telegram Token")
                    read -p "Enter your new Bot Token: " BOT_TOKEN
                    _set_env_var "BOT_TOKEN" "$BOT_TOKEN"
                    echo -e "${GREEN}Token updated. Restarting bot...${NC}"
                    sudo docker compose down
                    sudo docker compose up --build -d
                    sudo docker image prune -f
                    break
                    ;;
                "Edit Panel URL")
                    while true; do
                        read -p "Enter your new Marzneshin Panel URL: " PANEL_URL
                        PANEL_URL=$(echo "$PANEL_URL" | xargs)
                        PANEL_URL=$(echo "$PANEL_URL" | sed -E 's#(https?://[^/]+).*#\1#')
                        PANEL_URL="${PANEL_URL%/}"

                        if [[ "$PANEL_URL" =~ ^https?:// ]]; then
                            break
                        else
                            echo -e "${RED}Invalid URL. Please include http:// or https://${NC}"
                        fi
                    done
                    _set_env_var "PANEL_URL" "$PANEL_URL"
                    echo -e "${GREEN}Panel URL updated. Restarting bot...${NC}"
                    sudo docker compose down
                    sudo docker compose up --build -d
                    sudo docker image prune -f
                    break
                    ;;
                "Manage Admin Groups")
                    _manage_admins
                    break
                    ;;
                "Edit Notification Settings")
                    echo -e "\n${GREEN}--- Edit Webhook Notification Settings ---${NC}"

                    ENABLE_WEBHOOK_CURRENT=$(grep '^ENABLE_WEBHOOK=' "$PROJECT_DIR/.env" | cut -d '=' -f2)
                    WEBHOOK_ADDRESS_CURRENT=$(grep '^WEBHOOK_ADDRESS=' "$PROJECT_DIR/.env" | cut -d '"' -f2)
                    WEBHOOK_PORT_CURRENT=$(grep '^WEBHOOK_PORT=' "$PROJECT_DIR/.env" | cut -d '"' -f2)
                    WEBHOOK_SECRET_CURRENT=$(grep '^WEBHOOK_SECRET=' "$PROJECT_DIR/.env" | cut -d '"' -f2)

                    echo -e "Current Webhook Status: $ENABLE_WEBHOOK_CURRENT"
                    read -p "Enable Webhook Notifications? (y/N): " ENABLE_WEBHOOK

                    webhook_address="0.0.0.0"
                    webhook_port="9090"
                    webhook_secret="please_change_this_secret"
                    enable_webhook_flag=False

                    if [[ $ENABLE_WEBHOOK =~ ^[Yy]$ ]]; then
                        enable_webhook_flag=True

                        read -p "Webhook Address [current: $WEBHOOK_ADDRESS_CURRENT | default: 0.0.0.0]: " new_addr
                        read -p "Webhook Port [current: $WEBHOOK_PORT_CURRENT]: " new_port
                        read -p "Webhook Secret: " new_secret

                        webhook_address=${new_addr:-$WEBHOOK_ADDRESS_CURRENT}
                        webhook_port=${new_port:-$WEBHOOK_PORT_CURRENT}
                        webhook_secret=${new_secret:-$WEBHOOK_SECRET_CURRENT}
                    fi

                    {
                        sed -i "/ENABLE_WEBHOOK=/c\ENABLE_WEBHOOK=$enable_webhook_flag" "$PROJECT_DIR/.env"
                        sed -i "/WEBHOOK_ADDRESS=/c\WEBHOOK_ADDRESS=\"$webhook_address\"" "$PROJECT_DIR/.env"
                        sed -i "/WEBHOOK_PORT=/c\WEBHOOK_PORT=\"$webhook_port\"" "$PROJECT_DIR/.env"
                        sed -i "/WEBHOOK_SECRET=/c\WEBHOOK_SECRET=\"$webhook_secret\"" "$PROJECT_DIR/.env"
                    }

                    echo -e "${GREEN}Notification settings updated. Restarting bot...${NC}"
                    sudo docker compose down
                    sudo docker compose up --build -d
                    sudo docker image prune -f
                    break
                    ;;
                "Restart Bot")
                    sudo docker compose restart
                    echo -e "${GREEN}Bot restarted.${NC}"
                    break
                    ;;
                "View Logs")
                    sudo docker compose logs -f --tail=100 bot
                    break
                    ;;
                "Update Bot")
                    echo -e "${YELLOW}Pulling latest changes...${NC}"
                    cd "$PROJECT_DIR" && git pull
                    _start_bot
                    break
                    ;;
                "Uninstall Bot")
                    echo -e "${RED}WARNING: This will permanently delete the bot and its data.${NC}"
                    read -p "Are you sure? [y/N] " confirm
                    if [[ $confirm =~ ^[Yy]$ ]]; then
                        sudo docker compose down -v --rmi all
                        sudo rm -rf "$PROJECT_DIR"
                        sudo rm -f "/usr/local/bin/${COMMAND_NAME}"
                        echo -e "${GREEN}Uninstallation complete.${NC}"
                        exit 0
                    else
                        echo "Uninstall cancelled."
                    fi
                    break
                    ;;
                "Quit")
                    return 0
                    ;;
                *)
                    echo "Invalid option $REPLY"
                    break
                    ;;
            esac
        done
    done
}

if [ -f "/usr/local/bin/${COMMAND_NAME}" ]; then
    show_management_menu
else
    if [ "$EUID" -ne 0 ]; then
      echo -e "${RED}Please run this script with sudo for the first-time installation.${NC}"
      exit 1
    fi
    install_bot
fi