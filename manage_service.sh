#!/bin/bash
set -e

# Script to manage the audio-processor service

# Define colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if docker compose is available
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: docker is not installed or not in PATH${NC}"
    exit 1
fi

case "$1" in
  start)
    echo -e "${GREEN}Starting audio-processor service...${NC}"
    docker compose up -d
    echo -e "${GREEN}Service started successfully${NC}"
    ;;
  stop)
    echo -e "${YELLOW}Stopping audio-processor service...${NC}"
    docker compose stop audio-processor
    echo -e "${YELLOW}Service stopped${NC}"
    ;;
  restart)
    echo -e "${YELLOW}Restarting audio-processor service...${NC}"
    docker compose restart audio-processor
    echo -e "${GREEN}Service restarted${NC}"
    ;;
  update)
    echo -e "${BLUE}Updating audio-processor service...${NC}"
    echo -e "${YELLOW}Stopping audio-processor service...${NC}"
    docker compose stop audio-processor
    
    echo -e "${YELLOW}Removing audio-processor container...${NC}"
    docker compose rm -f audio-processor
    
    echo -e "${BLUE}Building audio-processor image...${NC}"
    docker compose build audio-processor
    
    echo -e "${GREEN}Starting audio-processor service...${NC}"
    docker compose up -d

    echo -e "${BLUE}Showing logs from audio-processor (Ctrl+C to exit)...${NC}"
    docker compose logs -f audio-processor
    ;;
  logs)
    echo -e "${BLUE}Showing logs from audio-processor (Ctrl+C to exit)...${NC}"
    docker compose logs -f audio-processor
    ;;
  status)
    echo -e "${BLUE}Checking status of audio-processor service...${NC}"
    docker compose ps audio-processor
    ;;
  clean)
    echo -e "${YELLOW}Cleaning unused Docker images...${NC}"
    docker image prune -f
    echo -e "${GREEN}Done cleaning unused images${NC}"
    ;;
  health)
    echo -e "${BLUE}Checking health of audio-processor service...${NC}"
    if curl -sf http://localhost:5000/api/health > /dev/null 2>&1; then
      echo -e "${GREEN}Service is healthy${NC}"
      curl -s http://localhost:5000/api/health | python3 -m json.tool
    else
      echo -e "${RED}Service is not responding${NC}"
      exit 1
    fi
    ;;
  *)
    echo -e "Usage: $0 {start|stop|restart|update|logs|status|clean|health}"
    echo -e ""
    echo -e "Commands:"
    echo -e "  ${GREEN}start${NC}    Start the audio-processor service"
    echo -e "  ${YELLOW}stop${NC}     Stop the audio-processor service"
    echo -e "  ${YELLOW}restart${NC}  Restart the audio-processor service"
    echo -e "  ${BLUE}update${NC}   Stop, remove, rebuild, and start the audio-processor service"
    echo -e "  ${BLUE}logs${NC}     Show and follow the logs from the audio-processor service"
    echo -e "  ${BLUE}status${NC}   Check the status of the audio-processor service"
    echo -e "  ${YELLOW}clean${NC}    Remove unused Docker images to free up disk space"
    echo -e "  ${BLUE}health${NC}   Check the health of the running service"
    exit 1
    ;;
esac
