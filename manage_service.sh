#!/bin/bash

# Script to manage the audio-processor service

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

case "$1" in
  start)
    echo -e "${GREEN}Starting audio-processor services...${NC}"
    docker compose up -d
    ;;
  stop)
    echo -e "${YELLOW}Stopping audio-processor services...${NC}"
    docker compose stop
    ;;
  restart)
    echo -e "${YELLOW}Restarting audio-processor services...${NC}"
    docker compose restart
    ;;
  update)
    echo -e "${BLUE}Updating audio-processor services...${NC}"
    echo -e "${YELLOW}Stopping services...${NC}"
    docker compose stop
    
    echo -e "${YELLOW}Removing containers...${NC}"
    docker compose rm -f
    
    echo -e "${BLUE}Building services...${NC}"
    docker compose build
    
    echo -e "${GREEN}Starting services...${NC}"
    docker compose up -d

    echo -e "${BLUE}Showing logs from services (Ctrl+C to exit)...${NC}"
    docker compose logs -f
    ;;
  logs)
    echo -e "${BLUE}Showing logs from services (Ctrl+C to exit)...${NC}"
    docker compose logs -f
    ;;
  status)
    echo -e "${BLUE}Checking status of services...${NC}"
    docker compose ps
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
    echo -e "  ${GREEN}start${NC}    Start all services"
    echo -e "  ${YELLOW}stop${NC}     Stop all services"
    echo -e "  ${YELLOW}restart${NC}  Restart all services"
    echo -e "  ${BLUE}update${NC}   Stop, remove, rebuild, and start all services"
    echo -e "  ${BLUE}logs${NC}     Show and follow the logs from all services"
    echo -e "  ${BLUE}status${NC}   Check the status of all services"
    echo -e "  ${YELLOW}clean${NC}    Remove unused Docker images to free up disk space"
    exit 1
    ;;
esac
