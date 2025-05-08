#!/bin/bash

# Script to manage the audio-processor service

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

case "$1" in
  start)
    echo -e "${GREEN}Starting audio-processor service...${NC}"
    docker compose up -d
    ;;
  stop)
    echo -e "${YELLOW}Stopping audio-processor service...${NC}"
    docker compose stop audio-processor
    ;;
  restart)
    echo -e "${YELLOW}Restarting audio-processor service...${NC}"
    docker compose restart audio-processor
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
  *)
    echo -e "Usage: $0 {start|stop|restart|update|logs|status|clean}"
    echo -e ""
    echo -e "Commands:"
    echo -e "  ${GREEN}start${NC}    Start the audio-processor service"
    echo -e "  ${YELLOW}stop${NC}     Stop the audio-processor service"
    echo -e "  ${YELLOW}restart${NC}  Restart the audio-processor service"
    echo -e "  ${BLUE}update${NC}   Stop, remove, rebuild, and start the audio-processor service"
    echo -e "  ${BLUE}logs${NC}     Show and follow the logs from the audio-processor service"
    echo -e "  ${BLUE}status${NC}   Check the status of the audio-processor service"
    echo -e "  ${YELLOW}clean${NC}    Remove unused Docker images to free up disk space"
    exit 1
    ;;
esac
