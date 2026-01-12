#!/bin/bash
# Helper script to run docker compose commands
# Automatically detects if docker compose (new) or docker-compose (old) should be used

# Check if docker compose (new version) works
if docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE_CMD="docker compose"
    echo "✅ Используется новая версия Docker Compose (docker compose)"
elif docker-compose --version >/dev/null 2>&1; then
    DOCKER_COMPOSE_CMD="docker-compose"
    echo "✅ Используется старая версия Docker Compose (docker-compose)"
else
    echo "❌ Ошибка: Docker Compose не найден!"
    echo ""
    echo "Установите Docker:"
    echo "  macOS:   brew install --cask docker"
    echo "  Linux:   curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh"
    echo ""
    echo "Или см. инструкцию: DOCKER_INSTALL.md"
    exit 1
fi

# Parse command line arguments
if [ "$1" == "dev" ]; then
    echo "🚀 Запуск в режиме разработки..."
    $DOCKER_COMPOSE_CMD -f docker-compose.dev.yml up --build
elif [ "$1" == "down" ]; then
    echo "🛑 Остановка контейнеров..."
    $DOCKER_COMPOSE_CMD down
elif [ "$1" == "logs" ]; then
    echo "📋 Просмотр логов..."
    $DOCKER_COMPOSE_CMD logs -f
elif [ "$1" == "build" ]; then
    echo "🔨 Пересборка образа..."
    $DOCKER_COMPOSE_CMD build --no-cache
else
    echo "🚀 Запуск в production режиме..."
    $DOCKER_COMPOSE_CMD up --build
fi
